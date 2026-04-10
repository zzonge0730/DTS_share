#!/usr/bin/env python3
"""
seam_to_pose.py — ordered seam CSV → resample → pose (6DOF) → 1100 format

Backward-compatible shim: all logic now lives in dts.pose.
This file re-exports everything so existing scripts keep working.

Usage:
    python scripts/seam_to_pose.py \
        --seam ordered_seam.csv \
        --step-mm 10.0 \
        --out-pose seam_pose.csv \
        --out-1100 seam_1100.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# --- Ensure dts package is importable ---
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from dts.pose import (  # noqa: E402, F401 — re-export
    Pose6D,
    load_seam_csv,
    resample_uniform,
    compute_tangent_vectors,
    estimate_surface_normal,
    build_poses,
    save_pose_csv,
    format_1100,
    save_1100,
)
from dts.transforms import rotation_matrix_to_euler_zyx  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Main (CLI kept here — dts.pose is library-only)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Convert ordered seam to 6DOF pose + 1100 format")
    parser.add_argument("--seam", required=True, type=Path, help="Input: ordered_seam.csv (x,y,z)")
    parser.add_argument("--step-mm", type=float, default=10.0, help="Resample interval in mm")
    parser.add_argument("--unit", choices=["m", "mm"], default="m",
                        help="Input coordinate unit (Mech-Eye outputs meters)")
    parser.add_argument("--normal", type=float, nargs=3, default=None,
                        metavar=("NX", "NY", "NZ"),
                        help="Override surface normal instead of SVD estimate")
    parser.add_argument("--out-pose", type=Path, default=Path("seam_pose.csv"),
                        help="Output: pose CSV (x,y,z,rx,ry,rz in mm/degrees)")
    parser.add_argument("--out-1100", type=Path, default=Path("seam_1100.txt"),
                        help="Output: 1100 protocol string")
    args = parser.parse_args()

    # 1. Load ordered seam
    seam = load_seam_csv(args.seam)
    print(f"[load] {len(seam)} points from {args.seam}")

    # 2. Convert to mm if needed
    if args.unit == "m":
        seam_mm = seam * 1000.0
        print(f"[unit] converted m -> mm")
    else:
        seam_mm = seam.copy()

    # 3. Resample at uniform interval
    resampled = resample_uniform(seam_mm, args.step_mm)
    print(f"[resample] {len(seam_mm)} -> {len(resampled)} points (step={args.step_mm}mm)")

    # 4. Compute tangent vectors
    tangents = compute_tangent_vectors(resampled)

    # 5. Estimate surface normal
    if args.normal is not None:
        normal = np.asarray(args.normal, dtype=np.float64)
        normal_norm = np.linalg.norm(normal)
        if normal_norm < 1e-12:
            raise ValueError("normal override must be non-zero")
        normal = normal / normal_norm
        print(f"[normal] using override: ({normal[0]:.3f}, {normal[1]:.3f}, {normal[2]:.3f})")
    else:
        normal = estimate_surface_normal(resampled)
        print(f"[normal] estimated surface normal: ({normal[0]:.3f}, {normal[1]:.3f}, {normal[2]:.3f})")

    # 6. Build 6DOF poses
    poses = build_poses(resampled, tangents, normal)
    print(f"[pose] generated {len(poses)} poses")

    # 7. Compute path statistics
    if len(resampled) > 1:
        diffs = np.diff(resampled, axis=0)
        total_len = np.sum(np.linalg.norm(diffs, axis=1))
        print(f"[stats] total path length: {total_len:.1f} mm")

    # 8. Save outputs
    save_pose_csv(poses, args.out_pose)
    save_1100(poses, args.out_1100)

    print("\n[done] Pipeline complete: seam -> resample -> pose -> 1100")


if __name__ == "__main__":
    main()
