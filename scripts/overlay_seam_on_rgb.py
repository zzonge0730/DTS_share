#!/usr/bin/env python3
"""
overlay_seam_on_rgb.py — Draw seam pose paths on top of the captured RGB image.

This uses the raw organized point cloud as a pixel lookup table:
- raw PLY point count must equal image width * height
- each seam point is mapped to the nearest raw 3D point
- raw point index is converted to pixel (u, v)

This is robust for "same capture" overlays even when camera intrinsics are not
explicitly used elsewhere in the pipeline.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image, ImageDraw


DEFAULT_COLORS = [
    (255, 80, 80),
    (64, 200, 255),
    (255, 180, 50),
    (120, 255, 120),
]


def load_pose_csv(path: Path) -> np.ndarray:
    pts = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pts.append([float(row["x"]), float(row["y"]), float(row["z"])])
    if not pts:
        raise ValueError(f"pose CSV is empty: {path}")
    return np.asarray(pts, dtype=np.float64)


def seam_points_to_pixels(
    seam_pts: np.ndarray,
    raw_pcd: o3d.geometry.PointCloud,
    width: int,
    height: int,
) -> tuple[list[tuple[int, int]], dict[str, float]]:
    raw_pts_all = np.asarray(raw_pcd.points)
    valid_mask = np.isfinite(raw_pts_all).all(axis=1)
    valid_idx = np.flatnonzero(valid_mask)
    raw_pts = raw_pts_all[valid_mask]
    valid_pcd = o3d.geometry.PointCloud()
    valid_pcd.points = o3d.utility.Vector3dVector(raw_pts)
    tree = o3d.geometry.KDTreeFlann(valid_pcd)
    pixels: list[tuple[int, int]] = []
    dists_mm = []

    for pt in seam_pts:
        _, idx, dist2 = tree.search_knn_vector_3d(pt, 1)
        nearest_valid_idx = int(idx[0])
        nearest_idx = int(valid_idx[nearest_valid_idx])
        row = nearest_idx // width
        col = nearest_idx % width
        if row < 0 or row >= height or col < 0 or col >= width:
            continue
        pixels.append((col, row))
        dists_mm.append(float(np.sqrt(dist2[0])))

    if not pixels:
        raise ValueError("no seam points mapped to image pixels")

    stats = {
        "mapped_points": float(len(pixels)),
        "mean_nn_mm": float(np.mean(dists_mm)),
        "p90_nn_mm": float(np.percentile(dists_mm, 90)),
        "max_nn_mm": float(np.max(dists_mm)),
    }
    return pixels, stats


def draw_polyline(
    image: Image.Image,
    pixels: list[tuple[int, int]],
    color: tuple[int, int, int],
    label: str,
) -> None:
    draw = ImageDraw.Draw(image)

    if len(pixels) >= 2:
        draw.line(pixels, fill=color, width=4)

    r_main = 4
    for px, py in pixels:
        draw.ellipse((px - r_main, py - r_main, px + r_main, py + r_main), fill=color)

    start = pixels[0]
    end = pixels[-1]
    draw.ellipse((start[0] - 7, start[1] - 7, start[0] + 7, start[1] + 7), outline=(255, 255, 255), width=3)
    draw.ellipse((end[0] - 7, end[1] - 7, end[0] + 7, end[1] + 7), outline=(0, 0, 0), width=3)

    tx = min(start[0] + 12, image.width - 220)
    ty = max(start[1] - 20, 10)
    draw.rectangle((tx - 4, ty - 2, tx + 120, ty + 16), fill=(0, 0, 0))
    draw.text((tx, ty), label, fill=color)


def main() -> None:
    ap = argparse.ArgumentParser(description="Overlay seam path on RGB image")
    ap.add_argument("--rgb", type=Path, required=True)
    ap.add_argument("--raw-pcd", type=Path, required=True,
                    help="Raw organized point cloud from the same capture")
    ap.add_argument("--pose-csv", type=Path, required=True, nargs="+",
                    help="One or more pose CSV files to overlay")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rgb = Image.open(args.rgb).convert("RGB")
    width, height = rgb.size

    raw_pcd = o3d.io.read_point_cloud(str(args.raw_pcd))
    raw_pts = np.asarray(raw_pcd.points)
    if len(raw_pts) != width * height:
        raise ValueError(
            f"raw point count {len(raw_pts)} does not match image size {width}x{height}"
        )

    overlay = rgb.copy()

    for i, pose_csv in enumerate(args.pose_csv):
        seam_pts = load_pose_csv(pose_csv)
        pixels, stats = seam_points_to_pixels(seam_pts, raw_pcd, width, height)
        color = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        draw_polyline(overlay, pixels, color, pose_csv.stem.replace("_pose", ""))
        print(
            f"{pose_csv.name}: mapped={int(stats['mapped_points'])} "
            f"mean_nn_mm={stats['mean_nn_mm']:.3f} "
            f"p90_nn_mm={stats['p90_nn_mm']:.3f} "
            f"max_nn_mm={stats['max_nn_mm']:.3f}"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(args.out)
    print(f"saved overlay: {args.out}")


if __name__ == "__main__":
    main()
