#!/usr/bin/env python3
"""
register_battery_capture_icp.py - Auto-register a new battery-case capture.

Thin CLI wrapper around dts.icp.  Takes a raw capture PLY, crops it to the
battery-case broad ROI, runs seeded ICP against the reference PCD, saves the
chosen transform under repo-side data/, and writes a local live registry
entry so the GUI can treat the capture as runnable.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d

import _bootstrap  # noqa: F401 — repo root + scripts/ on sys.path

from dts.config import (
    REPO_ROOT,
    SCRIPTS_DIR,
    DEFAULT_FIXED_REGISTRY,
    DEFAULT_LIVE_REGISTRY,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_ROI_MIN,
    DEFAULT_ROI_MAX,
)
from dts.icp import (
    # Registry I/O
    load_fixed_registry,
    default_live_registry,
    load_live_registry,
    save_live_registry,
    load_seed_transforms,
    # PCD preprocessing
    filter_finite_pcd,
    crop_broad_roi,
    crop_roi_around_points,
    # ICP core
    run_seeded_icp,
    run_icp_stages_from_init,
    choose_best_result,
    prune_seed_candidates,
    # Seam-local
    compute_seam_local_metrics,
    build_reference_seam_points,
    summarize_seam_local_scores,
    compute_polyline_geometry_metrics,
    compute_direction_agnostic_tangent_error_deg,
    combine_seam_name_groups,
    _compare_seam_local_summary,
    seam_local_summary_not_worse,
    # Defaults
    DEFAULT_SEED_ORDER,
    DEFAULT_SEAM_OPTIMIZE_SEAMS,
    DEFAULT_SEAM_VALIDATE_SEAMS,
    DEFAULT_SEAM_LOCAL_SEAMS,
    DEFAULT_ICP_STAGES,
    DEFAULT_SEAM_LOCAL_REFINEMENT_STAGES,
)
from dts.paths import capture_id_from_raw_pcd
from dts.transforms import transform_points

from seam_eval_policy import load_threshold_spec


# ---------------------------------------------------------------------------
# Threshold spec (loaded once at import time)
# ---------------------------------------------------------------------------

_THRESHOLD_SPEC = load_threshold_spec()
DEFAULT_SEAM_THRESHOLD_VERSION = str(_THRESHOLD_SPEC["version"])
DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM = float(_THRESHOLD_SPEC["centerline_corridor_mm"])
DEFAULT_SEAM_TANGENT_CORRIDOR_DEG = float(_THRESHOLD_SPEC["tangent_corridor_deg"])
DEFAULT_SEAM_CORRIDOR_MIN_INLIER_RATIO = float(_THRESHOLD_SPEC["corridor_min_inlier_ratio"])


# ---------------------------------------------------------------------------
# Seam metric helpers (wrapping dts.icp with threshold defaults)
# ---------------------------------------------------------------------------

def _compute_seam_local(ref_pcd, meas_pcd, transformation, seam_names, step_mm=10.0):
    """Convenience wrapper that injects seam pipeline dependencies."""
    from battery_seam_pipeline import SEAM_CANDIDATES, score_nn_distance, snap_to_surface
    return compute_seam_local_metrics(
        ref_pcd=ref_pcd,
        meas_pcd=meas_pcd,
        transformation=transformation,
        seam_names=seam_names,
        step_mm=step_mm,
        centerline_corridor_mm=DEFAULT_SEAM_CENTERLINE_CORRIDOR_MM,
        tangent_corridor_deg=DEFAULT_SEAM_TANGENT_CORRIDOR_DEG,
        corridor_min_inlier_ratio=DEFAULT_SEAM_CORRIDOR_MIN_INLIER_RATIO,
        seam_candidates=SEAM_CANDIDATES,
        snap_to_surface_fn=snap_to_surface,
        score_nn_distance_fn=score_nn_distance,
    )


def _build_ref_seam_points(ref_pcd, seam_names, step_mm=10.0):
    """Convenience wrapper that injects seam pipeline dependencies."""
    from battery_seam_pipeline import SEAM_CANDIDATES, snap_to_surface
    return build_reference_seam_points(
        ref_pcd=ref_pcd,
        seam_names=seam_names,
        step_mm=step_mm,
        seam_candidates=SEAM_CANDIDATES,
        snap_to_surface_fn=snap_to_surface,
    )


# ---------------------------------------------------------------------------
# Live capture entry builder
# ---------------------------------------------------------------------------

def make_live_capture_entry(
    raw_capture_ply: Path,
    icp_transform_npy: Path,
    icp_report_json: Path,
    best_seed_name: str,
    fitness: float,
    rmse_mm: float,
    seam_local_summary: dict[str, Any] | None = None,
    seed_pruning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    notes = [
        f"Live capture auto-registered on {datetime.now().isoformat(timespec='seconds')}",
        f"Auto ICP seed selected from baseline capture {best_seed_name}",
        f"ICP fitness={fitness:.4f}, rmse={rmse_mm:.3f}mm",
        "Raw capture PLY is the canonical NN evaluation cloud unless a verified eval cloud is later added",
    ]
    if seam_local_summary:
        avg_mean = seam_local_summary.get("avg_mean_nn_mm", float("inf"))
        worst_max = seam_local_summary.get("worst_max_nn_mm", float("inf"))
        centerline_p90 = seam_local_summary.get("avg_centerline_p90_mm", float("inf"))
        tangent_p90 = seam_local_summary.get("avg_tangent_p90_deg", float("inf"))
        corridor_ratio = seam_local_summary.get("avg_corridor_inlier_ratio", 0.0)
        if np.isfinite(avg_mean) and np.isfinite(worst_max):
            notes.append(
                f"Seam-local NN summary: mean={avg_mean:.3f}mm, worst max={worst_max:.3f}mm"
            )
        if np.isfinite(centerline_p90) and np.isfinite(tangent_p90):
            notes.append(
                "Seam corridor summary: "
                f"centerline p90={centerline_p90:.3f}mm, "
                f"tangent p90={tangent_p90:.2f}deg, "
                f"inlier={corridor_ratio:.2%}"
            )
    if seed_pruning:
        notes.append(
            "Seed pruning: kept "
            f"{seed_pruning.get('retained_seed_count', 0)}/"
            f"{seed_pruning.get('evaluated_seed_count', 0)} seeds after stage 1"
        )

    return {
        "raw_capture_ply": str(raw_capture_ply),
        "roi_or_eval_pcd": None,
        "icp_transform_npy": str(icp_transform_npy),
        "canonical_nn_evaluation_cloud": "raw_capture_ply",
        "icp_report_json": str(icp_report_json),
        "notes": notes,
        "_source": "live_capture_registry",
    }


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def register_live_capture_icp(
    raw_capture_ply: Path,
    capture_id: str | None = None,
    fixed_registry_path: Path = DEFAULT_FIXED_REGISTRY,
    live_registry_path: Path = DEFAULT_LIVE_REGISTRY,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    roi_min: np.ndarray = DEFAULT_ROI_MIN,
    roi_max: np.ndarray = DEFAULT_ROI_MAX,
    seam_local_refine_margin_mm: float = 30.0,
) -> dict[str, Any]:
    raw_capture_ply = raw_capture_ply.resolve()
    if not raw_capture_ply.exists():
        raise FileNotFoundError(f"raw capture not found: {raw_capture_ply}")

    fixed_registry = load_fixed_registry(fixed_registry_path)
    reference_pcd = Path(fixed_registry["reference_pcd"])
    if not reference_pcd.exists():
        raise FileNotFoundError(f"reference PCD not found: {reference_pcd}")

    live_registry = load_live_registry(
        path=live_registry_path,
        reference_pcd=str(reference_pcd),
    )

    capture_id = capture_id or capture_id_from_raw_pcd(raw_capture_ply)
    output_dir = output_root / capture_id
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_pcd = filter_finite_pcd(o3d.io.read_point_cloud(str(raw_capture_ply)))
    meas_roi = crop_broad_roi(raw_pcd, roi_min=roi_min, roi_max=roi_max)
    ref_pcd = filter_finite_pcd(o3d.io.read_point_cloud(str(reference_pcd)))
    seed_transforms = load_seed_transforms(fixed_registry)

    icp = run_seeded_icp(ref_pcd=ref_pcd, meas_pcd=meas_roi, seed_transforms=seed_transforms)
    best = icp["best"]
    optimize_seam_local = _compute_seam_local(
        ref_pcd, meas_roi, best["transformation"], DEFAULT_SEAM_OPTIMIZE_SEAMS)
    validation_seam_local = _compute_seam_local(
        ref_pcd, meas_roi, best["transformation"], DEFAULT_SEAM_VALIDATE_SEAMS)
    combined_seam_local = _compute_seam_local(
        ref_pcd, meas_roi, best["transformation"],
        combine_seam_name_groups(DEFAULT_SEAM_OPTIMIZE_SEAMS, DEFAULT_SEAM_VALIDATE_SEAMS))

    seam_local_refinement: dict[str, Any] = {
        "attempted": False, "applied": False, "reason": "not_run",
    }

    try:
        ref_seam_points = _build_ref_seam_points(ref_pcd, DEFAULT_SEAM_OPTIMIZE_SEAMS)
        meas_seam_points = transform_points(ref_seam_points, np.linalg.inv(best["transformation"]))
        ref_local = crop_roi_around_points(ref_pcd, ref_seam_points, seam_local_refine_margin_mm)
        meas_local = crop_roi_around_points(meas_roi, meas_seam_points, seam_local_refine_margin_mm)
        seam_local_refinement["attempted"] = True
        seam_local_refinement["ref_local_count"] = len(ref_local.points)
        seam_local_refinement["meas_local_count"] = len(meas_local.points)

        if len(ref_local.points) >= 100 and len(meas_local.points) >= 100:
            local_icp = run_icp_stages_from_init(
                ref_pcd=ref_local, meas_pcd=meas_local,
                init_transform=best["transformation"],
                stages=DEFAULT_SEAM_LOCAL_REFINEMENT_STAGES,
                reverse_direction=True,
            )
            refined_optimize = _compute_seam_local(
                ref_pcd, meas_roi, local_icp["transformation"], DEFAULT_SEAM_OPTIMIZE_SEAMS)
            refined_validation = _compute_seam_local(
                ref_pcd, meas_roi, local_icp["transformation"], DEFAULT_SEAM_VALIDATE_SEAMS)
            refined_combined = _compute_seam_local(
                ref_pcd, meas_roi, local_icp["transformation"],
                combine_seam_name_groups(DEFAULT_SEAM_OPTIMIZE_SEAMS, DEFAULT_SEAM_VALIDATE_SEAMS))
            seam_local_refinement.update({
                "local_stages": DEFAULT_SEAM_LOCAL_REFINEMENT_STAGES,
                "stage_metrics": local_icp["stage_metrics"],
                "before_optimize_summary": optimize_seam_local["summary"],
                "after_optimize_summary": refined_optimize["summary"],
                "before_validation_summary": validation_seam_local["summary"],
                "after_validation_summary": refined_validation["summary"],
            })
            if _compare_seam_local_summary(
                refined_optimize["summary"], optimize_seam_local["summary"],
            ) < 0 and seam_local_summary_not_worse(
                validation_seam_local["summary"], refined_validation["summary"],
            ):
                best = {
                    **best,
                    "transformation": local_icp["transformation"],
                    "fitness": local_icp["fitness"],
                    "rmse_mm": local_icp["rmse_mm"],
                    "local_refined": True,
                }
                optimize_seam_local = refined_optimize
                validation_seam_local = refined_validation
                combined_seam_local = refined_combined
                seam_local_refinement["applied"] = True
                seam_local_refinement["reason"] = "improved_optimize_without_validation_regression"
            else:
                seam_local_refinement["reason"] = "no_safe_holdout_improvement"
        else:
            seam_local_refinement["reason"] = "local_roi_too_small"
    except Exception as exc:
        seam_local_refinement["reason"] = f"failed:{type(exc).__name__}"
        seam_local_refinement["error"] = str(exc)

    transform_path = output_dir / f"icp_transform_{capture_id}.npy"
    report_path = output_dir / f"icp_report_{capture_id}.json"
    np.save(str(transform_path), best["transformation"])

    report = {
        "capture_id": capture_id,
        "raw_capture_ply": str(raw_capture_ply),
        "reference_pcd": str(reference_pcd),
        "transform_path": str(transform_path),
        "roi_min": roi_min.tolist(),
        "roi_max": roi_max.tolist(),
        "best_seed_name": best["seed_name"],
        "fitness": best["fitness"],
        "rmse_mm": best["rmse_mm"],
        "candidate_results": icp["candidates"],
        "seed_pruning": icp["seed_pruning"],
        "seam_local_metrics": optimize_seam_local,
        "optimize_seam_local_metrics": optimize_seam_local,
        "validation_seam_local_metrics": validation_seam_local,
        "combined_seam_local_metrics": combined_seam_local,
        "seam_local_refinement": seam_local_refinement,
        "ref_counts": icp["ref_counts"],
        "meas_counts": icp["meas_counts"],
        "coarse_voxel_mm": icp["coarse_voxel_mm"],
        "fine_voxel_mm": icp["fine_voxel_mm"],
        "coarse_max_corr_mm": icp["coarse_max_corr_mm"],
        "fine_max_corr_mm": icp["fine_max_corr_mm"],
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    entry = make_live_capture_entry(
        raw_capture_ply=raw_capture_ply,
        icp_transform_npy=transform_path,
        icp_report_json=report_path,
        best_seed_name=best["seed_name"],
        fitness=best["fitness"],
        rmse_mm=best["rmse_mm"],
        seam_local_summary=optimize_seam_local["summary"],
        seed_pruning=icp["seed_pruning"],
    )
    live_registry["reference_pcd"] = str(reference_pcd)
    live_registry.setdefault("captures", {})
    live_registry["captures"][capture_id] = entry
    save_live_registry(live_registry, live_registry_path)

    return {
        "capture_id": capture_id,
        "icp_transform_npy": str(transform_path),
        "icp_report_json": str(report_path),
        "fitness": best["fitness"],
        "rmse_mm": best["rmse_mm"],
        "best_seed_name": best["seed_name"],
        "seam_local_metrics": optimize_seam_local,
        "optimize_seam_local_metrics": optimize_seam_local,
        "validation_seam_local_metrics": validation_seam_local,
        "combined_seam_local_metrics": combined_seam_local,
        "seed_pruning": icp["seed_pruning"],
        "seam_local_refinement": seam_local_refinement,
        "entry": entry,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Register a new battery-case capture via seeded ICP")
    parser.add_argument("--raw-capture-ply", type=Path, required=True)
    parser.add_argument("--capture-id", default=None)
    parser.add_argument("--fixed-registry", type=Path, default=DEFAULT_FIXED_REGISTRY)
    parser.add_argument("--live-registry", type=Path, default=DEFAULT_LIVE_REGISTRY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    result = register_live_capture_icp(
        raw_capture_ply=args.raw_capture_ply,
        capture_id=args.capture_id,
        fixed_registry_path=args.fixed_registry,
        live_registry_path=args.live_registry,
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
