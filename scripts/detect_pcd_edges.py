#!/usr/bin/env python3
"""
detect_pcd_edges.py — Detect edge points on a measurement point cloud
using local normal variation (curvature).

Edge points are where surface normals change rapidly — corners, seam lines,
wall-floor transitions. These are candidates for weld seam paths.

This script is currently used as an experimental helper for seam correction
and visualization, not as the default production path.

Usage:
    python scripts/detect_pcd_edges.py \
        --pcd /mnt/c/.../meas_battery_tight.ply \
        --output /mnt/c/.../edges.ply \
        [--threshold 0.03] \
        [--radius 5.0]

    # With seam overlay for validation:
    python scripts/detect_pcd_edges.py \
        --pcd /mnt/c/.../meas_battery_tight.ply \
        --output /mnt/c/.../edges.ply \
        --seam-csv /mnt/c/.../U1_pose.csv \
        --rgb /mnt/c/.../rgb_image_978.png \
        --raw-pcd /mnt/c/.../point_cloud_978.ply \
        --overlay /mnt/c/.../edge_overlay.png
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import open3d as o3d


def estimate_curvature(pcd: o3d.geometry.PointCloud,
                       radius: float = 5.0,
                       max_nn: int = 30) -> np.ndarray:
    """Compute per-point curvature from local normal variation.

    Returns array of curvature values [0, 1] for each point.
    High values = edge/corner regions.
    """
    if not pcd.has_normals():
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=radius, max_nn=max_nn
            )
        )

    pts = np.asarray(pcd.points)
    normals = np.asarray(pcd.normals)
    tree = o3d.geometry.KDTreeFlann(pcd)
    curvatures = np.zeros(len(pts))

    for i in range(len(pts)):
        _, idx, _ = tree.search_radius_vector_3d(pts[i], radius)
        if len(idx) < 4:
            continue
        local_normals = normals[idx]
        centered = local_normals - local_normals.mean(axis=0)
        cov = centered.T @ centered / len(idx)
        eigvals = np.linalg.eigvalsh(cov)
        curvatures[i] = eigvals[0] / (eigvals.sum() + 1e-12)

    return curvatures


def extract_edges(pcd: o3d.geometry.PointCloud,
                  curvatures: np.ndarray,
                  threshold: float = 0.03) -> o3d.geometry.PointCloud:
    """Extract points with curvature above threshold as edge candidates."""
    mask = curvatures > threshold
    edge_pcd = o3d.geometry.PointCloud()

    if not mask.any():
        return edge_pcd

    pts = np.asarray(pcd.points)[mask]
    edge_pcd.points = o3d.utility.Vector3dVector(pts)

    # Color by curvature intensity (yellow to red)
    curv_masked = curvatures[mask]
    crange = curv_masked.max() - curv_masked.min()
    if crange < 1e-12:
        curv_norm = np.zeros(len(pts))
    else:
        curv_norm = (curv_masked - curv_masked.min()) / crange
    colors = np.zeros((len(pts), 3))
    colors[:, 0] = 1.0  # red channel always on
    colors[:, 1] = 1.0 - curv_norm  # green fades as curvature increases
    edge_pcd.colors = o3d.utility.Vector3dVector(colors)

    return edge_pcd


def snap_to_edge(seam_pts: np.ndarray,
                 edge_pcd: o3d.geometry.PointCloud,
                 max_snap_dist: float = 10.0) -> tuple[np.ndarray, np.ndarray]:
    """Snap seam points to nearest edge point (within max distance).

    Returns:
        snapped: Nx3 array of snapped positions
        snap_dists: N array of snap distances (mm)
    """
    tree = o3d.geometry.KDTreeFlann(edge_pcd)
    edge_pts = np.asarray(edge_pcd.points)
    snapped = seam_pts.copy()
    snap_dists = np.zeros(len(seam_pts))

    for i, pt in enumerate(seam_pts):
        _, idx, dist2 = tree.search_knn_vector_3d(pt, 1)
        dist = float(np.sqrt(dist2[0]))
        if dist <= max_snap_dist:
            snapped[i] = edge_pts[idx[0]]
            snap_dists[i] = dist
        else:
            snap_dists[i] = -1  # not snapped (too far)

    return snapped, snap_dists


def load_seam_csv(path: Path) -> np.ndarray:
    """Load seam pose CSV, return Nx3 XYZ positions."""
    pts = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if row and row[0].strip():
                pts.append([float(row[0]), float(row[1]), float(row[2])])
    return np.array(pts)


def make_edge_overlay(rgb_path: Path, raw_pcd_path: Path,
                      edge_pcd: o3d.geometry.PointCloud,
                      seam_original: np.ndarray | None,
                      seam_snapped: np.ndarray | None,
                      output_path: Path):
    """Draw edge points + original/snapped seam on RGB image."""
    from PIL import Image, ImageDraw

    img = Image.open(rgb_path).convert("RGB")
    w, h = img.size

    raw_pcd = o3d.io.read_point_cloud(str(raw_pcd_path))
    raw_pts = np.asarray(raw_pcd.points)
    if len(raw_pts) != w * h:
        print(f"  WARNING: raw PCD {len(raw_pts)} != image {w}x{h}, skipping overlay")
        return

    # Build KDTree on valid raw points for projection
    valid_mask = np.isfinite(raw_pts).all(axis=1)
    valid_idx = np.flatnonzero(valid_mask)
    valid_pcd = o3d.geometry.PointCloud()
    valid_pcd.points = o3d.utility.Vector3dVector(raw_pts[valid_mask])
    tree = o3d.geometry.KDTreeFlann(valid_pcd)

    def project_to_pixel(pt_3d):
        _, idx, _ = tree.search_knn_vector_3d(pt_3d, 1)
        flat = int(valid_idx[idx[0]])
        return flat % w, flat // w

    draw = ImageDraw.Draw(img)

    # Draw edge points (green dots, small)
    edge_pts = np.asarray(edge_pcd.points)
    # Subsample for drawing speed
    if len(edge_pts) > 5000:
        sub_idx = np.random.default_rng(42).choice(len(edge_pts), 5000, replace=False)
        edge_sub = edge_pts[sub_idx]
    else:
        edge_sub = edge_pts
    for pt in edge_sub:
        px, py = project_to_pixel(pt)
        draw.rectangle((px-1, py-1, px+1, py+1), fill=(0, 255, 0))

    # Draw original seam (yellow)
    if seam_original is not None:
        orig_pixels = [project_to_pixel(pt) for pt in seam_original]
        if len(orig_pixels) >= 2:
            draw.line(orig_pixels, fill=(255, 255, 0), width=3)
        for px, py in orig_pixels:
            draw.ellipse((px-4, py-4, px+4, py+4), fill=(255, 255, 0))

    # Draw snapped seam (red)
    if seam_snapped is not None:
        snap_pixels = [project_to_pixel(pt) for pt in seam_snapped]
        if len(snap_pixels) >= 2:
            draw.line(snap_pixels, fill=(255, 50, 50), width=3)
        for px, py in snap_pixels:
            draw.ellipse((px-4, py-4, px+4, py+4), fill=(255, 50, 50))

    # Legend
    legend_y = 20
    for label, color in [("Green = PCD edges", (0, 255, 0)),
                         ("Yellow = Original CAD picks", (255, 255, 0)),
                         ("Red = Edge-snapped", (255, 50, 50))]:
        draw.rectangle((20, legend_y, 36, legend_y+12), fill=color)
        draw.text((42, legend_y-2), label, fill=(255, 255, 255))
        legend_y += 20

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    print(f"  Saved overlay: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Detect edge points on measurement PCD"
    )
    parser.add_argument("--pcd", type=Path, required=True,
                        help="Measurement point cloud (PLY)")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output edge point cloud (PLY)")
    parser.add_argument("--threshold", type=float, default=0.03,
                        help="Curvature threshold for edge detection (default: 0.03)")
    parser.add_argument("--radius", type=float, default=5.0,
                        help="Local neighborhood radius in mm (default: 5.0)")
    parser.add_argument("--max-nn", type=int, default=30,
                        help="Max neighbors for normal estimation")
    parser.add_argument("--seam-csv", type=Path, nargs="*", default=None,
                        help="Seam pose CSVs to snap to edges")
    parser.add_argument("--max-snap-dist", type=float, default=10.0,
                        help="Maximum snap distance in mm (default: 10)")
    parser.add_argument("--rgb", type=Path, default=None,
                        help="RGB image for overlay")
    parser.add_argument("--raw-pcd", type=Path, default=None,
                        help="Raw organized PCD for pixel projection")
    parser.add_argument("--overlay", type=Path, default=None,
                        help="Output overlay image path")
    args = parser.parse_args()

    # Load PCD
    print(f"Loading PCD: {args.pcd}")
    pcd = o3d.io.read_point_cloud(str(args.pcd))
    print(f"  Points: {len(pcd.points)}")

    # Compute curvature
    print(f"Computing curvature (radius={args.radius}mm, max_nn={args.max_nn})...")
    curvatures = estimate_curvature(pcd, radius=args.radius, max_nn=args.max_nn)

    # Extract edges
    edge_pcd = extract_edges(pcd, curvatures, threshold=args.threshold)
    n_edges = len(edge_pcd.points)
    pct = 100 * n_edges / len(pcd.points)
    print(f"  Edge points: {n_edges} ({pct:.1f}% of total)")
    print(f"  Threshold: {args.threshold}")

    # Save edge PCD
    args.output.parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_point_cloud(str(args.output), edge_pcd)
    print(f"  Saved: {args.output}")

    # Snap seams to edges
    seam_original = None
    seam_snapped = None
    if args.seam_csv:
        for csv_path in args.seam_csv:
            print(f"\nSnapping seam: {csv_path.name}")
            seam_pts = load_seam_csv(csv_path)
            snapped, dists = snap_to_edge(seam_pts, edge_pcd, args.max_snap_dist)

            valid = dists >= 0
            if valid.sum() > 0:
                print(f"  Snapped: {valid.sum()}/{len(seam_pts)} points")
                print(f"  Snap distance — mean: {dists[valid].mean():.2f}mm, "
                      f"max: {dists[valid].max():.2f}mm")
            else:
                print(f"  WARNING: no points snapped within {args.max_snap_dist}mm")

            # Save snapped seam
            snap_out = csv_path.parent / csv_path.name.replace("_pose.csv", "_edge_snap.csv")
            with open(snap_out, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["x", "y", "z", "snap_dist_mm", "snapped"])
                for j in range(len(seam_pts)):
                    writer.writerow([
                        f"{snapped[j][0]:.3f}", f"{snapped[j][1]:.3f}", f"{snapped[j][2]:.3f}",
                        f"{dists[j]:.3f}", "yes" if dists[j] >= 0 else "no"
                    ])
            print(f"  Saved: {snap_out}")

            # Keep last seam for overlay
            seam_original = seam_pts
            seam_snapped = snapped

    # Generate overlay
    if args.overlay and args.rgb and args.raw_pcd:
        print(f"\nGenerating overlay...")
        make_edge_overlay(args.rgb, args.raw_pcd, edge_pcd,
                         seam_original, seam_snapped, args.overlay)


if __name__ == "__main__":
    main()
