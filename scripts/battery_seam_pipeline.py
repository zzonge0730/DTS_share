#!/usr/bin/env python3
"""
battery_seam_pipeline.py — Battery case seam candidates → surface snap
→ ICP transform → pose with Euler → 1100 format + NN scoring

Thin CLI wrapper around dts.seam.

Usage:
    python scripts/battery_seam_pipeline.py \
        --ref-pcd  ref_battery_case.ply \
        --meas-pcd meas_battery_roi.ply \
        --icp-transform icp_transform.npy \
        --out-dir  output/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401 — repo root + scripts/ on sys.path

from seam_to_pose import (
    Pose6D,
    resample_uniform,
    compute_tangent_vectors,
    rotation_matrix_to_euler_zyx,
    format_1100,
    save_pose_csv,
    save_1100,
)
from detect_pcd_edges import estimate_curvature, extract_edges, snap_to_edge

from dts.transforms import transform_points
from dts.seam import (
    build_seam_candidates,
    snap_to_surface,
    snap_to_surface_constrained,
    apply_snap_strategy,
    resolve_snap_mode,
    score_nn_distance,
    estimate_local_normals,
    build_poses_local_normal,
)

try:
    import open3d as o3d
except ImportError:
    sys.exit("open3d is required: pip install open3d")


# ---------------------------------------------------------------------------
# Module-level seam candidates (used by GUI, ICP, and other scripts)
# ---------------------------------------------------------------------------

SEAM_CANDIDATES = build_seam_candidates()


# ---------------------------------------------------------------------------
# Main pipeline for one seam candidate
# ---------------------------------------------------------------------------

def process_seam(name: str, seam_def: dict,
                 ref_pcd: o3d.geometry.PointCloud,
                 meas_pcd: o3d.geometry.PointCloud,
                 T_icp: np.ndarray,
                 step_mm: float,
                 out_dir: Path,
                 snap_mode: str = "surface_k5",
                 constrained_max_offset_mm: float = 2.0,
                 edge_snap: bool = False,
                 edge_threshold: float = 0.03,
                 edge_radius: float = 5.0,
                 max_snap_dist: float = 3.0,
                 min_valid_ratio: float = 0.8) -> dict:
    """Full pipeline for one seam candidate."""
    print(f"\n{'='*60}")
    print(f"  {name}: {seam_def['description']}")
    print(f"{'='*60}")

    raw_pts = np.array(seam_def["points"], dtype=np.float64)
    print(f"[1] Raw CAD points: {len(raw_pts)}")
    snap_mode = resolve_snap_mode(seam_def, snap_mode)

    if edge_snap:
        # Experimental mode:
        # raw points -> nearest edge where possible, surface snap elsewhere.
        seam_extent = raw_pts.max(axis=0) - raw_pts.min(axis=0)
        roi_margin = max(50.0, seam_extent.max() * 0.3)
        roi_min = raw_pts.min(axis=0) - roi_margin
        roi_max = raw_pts.max(axis=0) + roi_margin

        ref_pts_arr = np.asarray(ref_pcd.points)
        roi_mask = np.all((ref_pts_arr >= roi_min) & (ref_pts_arr <= roi_max), axis=1)
        roi_pcd = o3d.geometry.PointCloud()
        roi_pcd.points = o3d.utility.Vector3dVector(ref_pts_arr[roi_mask])
        print(f"[2] Edge-snap ROI: {roi_mask.sum()} pts from ref PCD")

        curvatures = estimate_curvature(roi_pcd, radius=edge_radius)
        edge_pcd = extract_edges(roi_pcd, curvatures, threshold=edge_threshold)
        n_edges = len(edge_pcd.points)
        print(f"    Edge points: {n_edges} (threshold={edge_threshold})")

        edge_snapped = None
        if n_edges > 0:
            edge_snapped, snap_dists = snap_to_edge(raw_pts, edge_pcd, max_snap_dist)
            valid = snap_dists >= 0
            n_valid = int(valid.sum())
            valid_ratio = n_valid / len(raw_pts)
            print(f"    Edge-snapped: {n_valid}/{len(raw_pts)} ({valid_ratio:.0%}) "
                  f"within {max_snap_dist}mm")
            if n_valid > 0:
                print(f"    Snap dist — mean: {snap_dists[valid].mean():.2f}mm, "
                      f"max: {snap_dists[valid].max():.2f}mm")

        surface_snapped = apply_snap_strategy(
            raw_pts, ref_pcd, snap_mode, constrained_max_offset_mm)

        if edge_snapped is not None and n_valid > 0:
            valid_ratio = n_valid / len(raw_pts)

            if valid_ratio >= min_valid_ratio:
                T_inv = np.linalg.inv(T_icp)
                score_surface = score_nn_distance(
                    transform_points(surface_snapped, T_inv), meas_pcd)
                score_edge = score_nn_distance(
                    transform_points(edge_snapped, T_inv), meas_pcd)
                print(f"    NN score — surface: {score_surface['mean_nn_mm']:.2f}mm, "
                      f"edge: {score_edge['mean_nn_mm']:.2f}mm")

                if score_edge["mean_nn_mm"] <= score_surface["mean_nn_mm"]:
                    snapped = edge_snapped
                    print(f"    ACCEPT: edge-snap adopted")
                else:
                    snapped = surface_snapped
                    print(f"    REJECT: edge NN worse, using surface-snap")
            else:
                snapped = surface_snapped.copy()
                snapped[valid] = edge_snapped[valid]
                print(f"    HYBRID: {n_valid} pts edge + "
                      f"{len(raw_pts)-n_valid} pts surface-snap")
        else:
            snapped = surface_snapped
            print(f"    No edges found, using surface-snap")

        print(f"[2] Final snap result:")
        for i, (r, s) in enumerate(zip(raw_pts, snapped)):
            d = np.linalg.norm(r - s)
            src = "edge" if (edge_snapped is not None and valid[i]) else "surf"
            print(f"    [{i}] ({r[0]:.1f},{r[1]:.1f},{r[2]:.1f}) -> "
                  f"({s[0]:.1f},{s[1]:.1f},{s[2]:.1f})  {d:.2f}mm [{src}]")
    else:
        snapped = apply_snap_strategy(raw_pts, ref_pcd, snap_mode, constrained_max_offset_mm)
        print(f"[2] Snap mode: {snap_mode}")
        for i, (r, s) in enumerate(zip(raw_pts, snapped)):
            d = np.linalg.norm(r - s)
            print(f"    [{i}] ({r[0]:.1f},{r[1]:.1f},{r[2]:.1f}) -> "
                  f"({s[0]:.1f},{s[1]:.1f},{s[2]:.1f})  snap_dist={d:.2f}mm")

    # Resample at uniform interval
    resampled = resample_uniform(snapped, step_mm)
    print(f"[3] Resampled: {len(snapped)} -> {len(resampled)} pts (step={step_mm}mm)")

    # Estimate local surface normals on ref PCD
    normals_ref = estimate_local_normals(resampled, ref_pcd, radius=20.0)
    print(f"[4] Local normals estimated on ref PCD")

    # Compute tangent vectors
    tangents_ref = compute_tangent_vectors(resampled)

    # Build poses in CAD frame
    poses_cad = build_poses_local_normal(resampled, tangents_ref, normals_ref)
    print(f"[5] Poses in CAD frame: {len(poses_cad)}")

    # Transform to camera frame via T_inv
    T_inv = np.linalg.inv(T_icp)
    resampled_cam = transform_points(resampled, T_inv)
    print(f"[6] Transformed to camera frame")

    # Transform normals (rotation only)
    R_inv = T_inv[:3, :3]
    normals_cam = (R_inv @ normals_ref.T).T
    for i in range(len(normals_cam)):
        normals_cam[i] /= np.linalg.norm(normals_cam[i])

    tangents_cam = compute_tangent_vectors(resampled_cam)

    # Build final poses in camera frame
    poses_cam = build_poses_local_normal(resampled_cam, tangents_cam, normals_cam)
    print(f"[7] Final poses in camera frame: {len(poses_cam)}")
    if poses_cam:
        p0, pn = poses_cam[0], poses_cam[-1]
        print(f"    first: ({p0.x:.1f},{p0.y:.1f},{p0.z:.1f}) "
              f"rx={p0.rx:.1f} ry={p0.ry:.1f} rz={p0.rz:.1f}")
        print(f"    last:  ({pn.x:.1f},{pn.y:.1f},{pn.z:.1f}) "
              f"rx={pn.rx:.1f} ry={pn.ry:.1f} rz={pn.rz:.1f}")

    # Score against measured PCD
    score = score_nn_distance(resampled_cam, meas_pcd)
    print(f"[8] NN Score vs meas PCD:")
    print(f"    mean={score['mean_nn_mm']:.2f}mm  "
          f"p90={score['p90_nn_mm']:.2f}mm  "
          f"max={score['max_nn_mm']:.2f}mm")

    # Path length
    if len(resampled_cam) > 1:
        total_len = np.sum(np.linalg.norm(np.diff(resampled_cam, axis=0), axis=1))
        print(f"[9] Path length: {total_len:.1f}mm")

    # Save outputs
    out_dir.mkdir(parents=True, exist_ok=True)
    save_pose_csv(poses_cam, out_dir / f"{name}_pose.csv")
    save_1100(poses_cam, out_dir / f"{name}_1100.txt")

    return {
        "name": name,
        "n_poses": len(poses_cam),
        "score": score,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Battery case seam pipeline")
    parser.add_argument("--ref-pcd", type=Path, required=True)
    parser.add_argument("--meas-pcd", type=Path, required=True)
    parser.add_argument("--icp-transform", type=Path, required=True)
    parser.add_argument("--step-mm", type=float, default=10.0)
    parser.add_argument("--seams", nargs="*", default=None,
                        help="Seam names to process (required)")
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--snap-mode",
        default="auto",
        choices=["auto", "no_snap", "surface_k1", "surface_k5", "constrained_k1", "constrained_k5"],
    )
    parser.add_argument("--constrained-max-offset-mm", type=float, default=2.0)
    parser.add_argument("--edge-snap", action="store_true")
    parser.add_argument("--edge-threshold", type=float, default=0.03)
    parser.add_argument("--edge-radius", type=float, default=5.0)
    parser.add_argument("--max-snap-dist", type=float, default=3.0)
    parser.add_argument("--min-valid-ratio", type=float, default=0.8)
    args = parser.parse_args()

    print(f"Loading ref PCD: {args.ref_pcd}")
    ref_pcd = o3d.io.read_point_cloud(str(args.ref_pcd))
    print(f"  {len(ref_pcd.points)} points")

    print(f"Loading meas PCD: {args.meas_pcd}")
    meas_pcd = o3d.io.read_point_cloud(str(args.meas_pcd))
    print(f"  {len(meas_pcd.points)} points")

    print(f"Loading ICP transform: {args.icp_transform}")
    T_icp = np.load(str(args.icp_transform))
    print(f"  shape: {T_icp.shape}")

    if not SEAM_CANDIDATES:
        parser.error("No seam assets found. Add seam CSV/asset files under the configured cad_seam_dirs.")

    if not args.seams:
        available = ", ".join(sorted(SEAM_CANDIDATES))
        parser.error(f"--seams is required. Available seams: {available}")

    names = args.seams
    missing = [name for name in names if name not in SEAM_CANDIDATES]
    if missing:
        available = ", ".join(sorted(SEAM_CANDIDATES))
        parser.error(f"Unknown seam(s): {', '.join(missing)}. Available seams: {available}")

    results = []
    for name in names:
        r = process_seam(name, SEAM_CANDIDATES[name],
                         ref_pcd, meas_pcd, T_icp,
                         args.step_mm, args.out_dir,
                         snap_mode=args.snap_mode,
                         constrained_max_offset_mm=args.constrained_max_offset_mm,
                         edge_snap=args.edge_snap,
                         edge_threshold=args.edge_threshold,
                         edge_radius=args.edge_radius,
                         max_snap_dist=args.max_snap_dist,
                         min_valid_ratio=args.min_valid_ratio)
        results.append(r)

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    for r in results:
        s = r["score"]
        print(f"  {r['name']}: {r['n_poses']} poses, "
              f"mean_NN={s['mean_nn_mm']:.2f}mm, "
              f"p90_NN={s['p90_nn_mm']:.2f}mm")
    print(f"\nOutputs in: {args.out_dir}/")


if __name__ == "__main__":
    main()
