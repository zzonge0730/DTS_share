"""배터리 케이스 촬영 데이터를 위한 정합(ICP) 파이프라인.

이 모듈은 scripts/register_battery_capture_icp.py에서 추출한
핵심 정합(ICP) 로직을 포함합니다:

- 포인트 클라우드 전처리 (필터, 크롭, 다운샘플링)
- 시드 가지치기(seed pruning)를 적용한 다단계 시드 정합(ICP)
- 역방향 정합(ICP)을 사용한 용접선(seam) 국소 정밀화
- 용접선(seam) 국소 메트릭 계산 및 비교
- 레지스트리 로드/저장 헬퍼
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d

from dts.config import (
    DEFAULT_FIXED_REGISTRY,
    DEFAULT_LIVE_REGISTRY,
    DEFAULT_ROI_MIN,
    DEFAULT_ROI_MAX,
    get_data_root,
    rebase_registry_paths,
)
from dts.transforms import transform_points


# ---------------------------------------------------------------------------
# 기본값
# ---------------------------------------------------------------------------

DEFAULT_SEED_ORDER = ("978", "741", "763", "473")
DEFAULT_SEAM_OPTIMIZE_SEAMS = ("U1_right", "U2_left")
DEFAULT_SEAM_VALIDATE_SEAMS: tuple[str, ...] = ()
DEFAULT_SEAM_LOCAL_SEAMS = DEFAULT_SEAM_OPTIMIZE_SEAMS

DEFAULT_ICP_STAGES: list[dict[str, Any]] = [
    {"voxel_mm": 8.0, "max_corr_mm": 24.0, "max_iter": 50, "method": "point_to_plane"},
    {"voxel_mm": 4.0, "max_corr_mm": 12.0, "max_iter": 60, "method": "point_to_plane"},
    {"voxel_mm": 2.0, "max_corr_mm": 6.0,  "max_iter": 60, "method": "point_to_plane"},
    {"voxel_mm": 1.0, "max_corr_mm": 3.0,  "max_iter": 80, "method": "point_to_plane"},
]

DEFAULT_SEAM_LOCAL_REFINEMENT_STAGES: list[dict[str, Any]] = [
    {"voxel_mm": 2.0, "max_corr_mm": 4.0, "max_iter": 50, "method": "point_to_plane"},
    {"voxel_mm": 1.0, "max_corr_mm": 2.0, "max_iter": 70, "method": "point_to_plane"},
]


# ---------------------------------------------------------------------------
# 레지스트리 입출력
# ---------------------------------------------------------------------------

def load_fixed_registry(path: Path = DEFAULT_FIXED_REGISTRY) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        registry = json.load(f)
    return rebase_registry_paths(registry, get_data_root())


def default_live_registry(reference_pcd: str | None = None) -> dict[str, Any]:
    return {
        "battery_case_live_registry_version": "2026-03-19",
        "reference_pcd": reference_pcd,
        "captures": {},
    }


def load_live_registry(
    path: Path = DEFAULT_LIVE_REGISTRY,
    reference_pcd: str | None = None,
) -> dict[str, Any]:
    registry = default_live_registry(reference_pcd=reference_pcd)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        registry.update(loaded)
        registry.setdefault("captures", {})
    return rebase_registry_paths(registry, get_data_root())


def save_live_registry(registry: dict[str, Any], path: Path = DEFAULT_LIVE_REGISTRY) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    return path


def load_seed_transforms(
    registry: dict[str, Any],
    capture_ids: tuple[str, ...] = DEFAULT_SEED_ORDER,
) -> list[tuple[str, np.ndarray]]:
    seeds: list[tuple[str, np.ndarray]] = []
    for capture_id in capture_ids:
        entry = registry["captures"].get(capture_id)
        if not entry:
            continue
        path = entry.get("icp_transform_npy")
        if not path:
            continue
        transform_path = Path(path)
        if not transform_path.exists():
            continue
        seeds.append((capture_id, np.load(str(transform_path))))
    return seeds


# ---------------------------------------------------------------------------
# 포인트 클라우드 전처리
# ---------------------------------------------------------------------------

def filter_finite_pcd(pcd: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
    pts = np.asarray(pcd.points)
    finite = np.isfinite(pts).all(axis=1)
    out = o3d.geometry.PointCloud()
    out.points = o3d.utility.Vector3dVector(pts[finite])
    colors = np.asarray(pcd.colors)
    if len(colors) == len(pts):
        out.colors = o3d.utility.Vector3dVector(colors[finite])
    return out


def crop_broad_roi(
    pcd: o3d.geometry.PointCloud,
    roi_min: np.ndarray = DEFAULT_ROI_MIN,
    roi_max: np.ndarray = DEFAULT_ROI_MAX,
) -> o3d.geometry.PointCloud:
    pts = np.asarray(pcd.points)
    mask = np.all((pts >= roi_min) & (pts <= roi_max), axis=1)
    out = o3d.geometry.PointCloud()
    out.points = o3d.utility.Vector3dVector(pts[mask])
    colors = np.asarray(pcd.colors)
    if len(colors) == len(pts):
        out.colors = o3d.utility.Vector3dVector(colors[mask])
    return out


def clean_pcd(pcd: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
    """다단계 정합(ICP) 전에 통계적 이상점(outlier)을 한 번 제거합니다."""
    pcd_clean, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    return pcd_clean


def prepare_icp_pcd(
    pcd: o3d.geometry.PointCloud,
    voxel_size_mm: float,
    normal_radius_mm: float,
) -> o3d.geometry.PointCloud:
    down = pcd.voxel_down_sample(voxel_size_mm)
    down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=normal_radius_mm, max_nn=50)
    )
    return down


def crop_roi_around_points(
    pcd: o3d.geometry.PointCloud,
    roi_points: np.ndarray,
    margin_mm: float,
) -> o3d.geometry.PointCloud:
    pts = np.asarray(pcd.points)
    roi_min = roi_points.min(axis=0) - margin_mm
    roi_max = roi_points.max(axis=0) + margin_mm
    mask = np.all((pts >= roi_min) & (pts <= roi_max), axis=1)
    out = o3d.geometry.PointCloud()
    out.points = o3d.utility.Vector3dVector(pts[mask])
    colors = np.asarray(pcd.colors)
    if len(colors) == len(pts):
        out.colors = o3d.utility.Vector3dVector(colors[mask])
    return out


# ---------------------------------------------------------------------------
# 정합(ICP) 핵심
# ---------------------------------------------------------------------------

def choose_best_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("비교할 정합(ICP) 결과가 없습니다")
    best = results[0]
    eps = 1e-9
    for item in results[1:]:
        if item["fitness"] > best["fitness"] + eps:
            best = item
            continue
        if abs(item["fitness"] - best["fitness"]) <= eps and item["rmse_mm"] < best["rmse_mm"] - eps:
            best = item
    return best


def _rank_icp_result(item: dict[str, Any]) -> tuple[float, float]:
    return (-float(item["fitness"]), float(item["rmse_mm"]))


def prune_seed_candidates(
    results: list[dict[str, Any]],
    max_keep: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """이후 세밀 단계에 넘길 상위 거친 단계 시드만 유지합니다."""
    ordered = sorted(results, key=_rank_icp_result)
    if max_keep <= 0 or len(ordered) <= max_keep:
        return ordered, []
    return ordered[:max_keep], ordered[max_keep:]


def _make_estimator(method: str) -> Any:
    """이름으로 정합(ICP) 추정 방법을 반환합니다."""
    if method == "gicp":
        return o3d.pipelines.registration.TransformationEstimationForGeneralizedICP(
            epsilon=0.001,
        )
    return o3d.pipelines.registration.TransformationEstimationPointToPlane()


def _run_one_icp_stage(
    meas_down: o3d.geometry.PointCloud,
    ref_down: o3d.geometry.PointCloud,
    stage: dict[str, Any],
    init_transform: np.ndarray,
) -> o3d.pipelines.registration.RegistrationResult:
    """설정된 방법으로 단일 정합(ICP) 단계를 실행합니다."""
    method = stage.get("method", "point_to_plane")
    estimator = _make_estimator(method)
    criteria = o3d.pipelines.registration.ICPConvergenceCriteria(
        relative_fitness=1e-8,
        relative_rmse=1e-8,
        max_iteration=int(stage["max_iter"]),
    )
    if method == "gicp":
        return o3d.pipelines.registration.registration_generalized_icp(
            meas_down, ref_down, stage["max_corr_mm"],
            init_transform, estimator, criteria,
        )
    return o3d.pipelines.registration.registration_icp(
        meas_down, ref_down, stage["max_corr_mm"],
        init_transform, estimator, criteria,
    )


def run_icp_stages_from_init(
    ref_pcd: o3d.geometry.PointCloud,
    meas_pcd: o3d.geometry.PointCloud,
    init_transform: np.ndarray,
    stages: list[dict[str, Any]],
    reverse_direction: bool = False,
) -> dict[str, Any]:
    """주어진 초기 변환 행렬로부터 정합(ICP) 단계들을 실행합니다.

    *reverse_direction*이 True이면 정합(ICP)의 소스/타겟을 교환하여
    점이 더 적은 클라우드(보통 CAD 기반 기준 모델)가 점이 더 많은
    측정 클라우드에서 대응점을 탐색합니다. 반환되는 변환 행렬은
    항상 원래(측정→기준) 방향 규약을 따릅니다.
    """
    stage_pcds: list[tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud]] = []
    for s in stages:
        v = float(s["voxel_mm"])
        stage_pcds.append((
            prepare_icp_pcd(ref_pcd, v, v * 3.0),
            prepare_icp_pcd(meas_pcd, v, v * 3.0),
        ))

    current_T = np.linalg.inv(init_transform) if reverse_direction else init_transform
    stage_metrics: list[dict[str, Any]] = []
    for i, stage in enumerate(stages):
        ref_down, meas_down = stage_pcds[i]
        if reverse_direction:
            reg = _run_one_icp_stage(ref_down, meas_down, stage, current_T)
        else:
            reg = _run_one_icp_stage(meas_down, ref_down, stage, current_T)
        current_T = reg.transformation
        stage_metrics.append({
            "voxel_mm": float(stage["voxel_mm"]),
            "method": stage.get("method", "point_to_plane"),
            "fitness": float(reg.fitness),
            "rmse_mm": float(reg.inlier_rmse),
        })

    final_T = np.linalg.inv(current_T) if reverse_direction else current_T
    return {
        "transformation": final_T,
        "stage_metrics": stage_metrics,
        "fitness": stage_metrics[-1]["fitness"],
        "rmse_mm": stage_metrics[-1]["rmse_mm"],
        "reverse_direction": reverse_direction,
        "ref_counts": {
            "raw": len(ref_pcd.points),
            "coarse": len(stage_pcds[0][0].points),
            "fine": len(stage_pcds[-1][0].points),
        },
        "meas_counts": {
            "raw": len(meas_pcd.points),
            "coarse": len(stage_pcds[0][1].points),
            "fine": len(stage_pcds[-1][1].points),
        },
    }


def run_seeded_icp(
    ref_pcd: o3d.geometry.PointCloud,
    meas_pcd: o3d.geometry.PointCloud,
    seed_transforms: list[tuple[str, np.ndarray]],
    stages: list[dict[str, Any]] | None = None,
    max_kept_seeds_after_stage1: int = 2,
) -> dict[str, Any]:
    if not seed_transforms:
        raise ValueError("사용 가능한 시드 변환 행렬이 없습니다")
    if len(meas_pcd.points) == 0:
        raise ValueError("크롭 후 측정 ROI가 비어 있습니다")

    if stages is None:
        stages = DEFAULT_ICP_STAGES

    stage_pcds: list[tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud]] = []
    for s in stages:
        v = s["voxel_mm"]
        stage_pcds.append((
            prepare_icp_pcd(ref_pcd, v, v * 3.0),
            prepare_icp_pcd(meas_pcd, v, v * 3.0),
        ))

    # 1단계: 모든 시드를 한 번 실행한 뒤, 상위 몇 개만 유지합니다.
    stage0 = stages[0]
    ref_stage0, meas_stage0 = stage_pcds[0]
    stage0_runs: list[dict[str, Any]] = []
    for seed_name, seed_transform in seed_transforms:
        reg = _run_one_icp_stage(meas_stage0, ref_stage0, stage0, seed_transform)
        stage0_runs.append({
            "seed_name": seed_name,
            "fitness": float(reg.fitness),
            "rmse_mm": float(reg.inlier_rmse),
            "transformation": reg.transformation,
            "stage_metrics": [{
                "voxel_mm": stage0["voxel_mm"],
                "method": stage0.get("method", "point_to_plane"),
                "fitness": float(reg.fitness),
                "rmse_mm": float(reg.inlier_rmse),
            }],
        })

    retained_stage0, pruned_stage0 = prune_seed_candidates(
        stage0_runs, max_keep=max_kept_seeds_after_stage1,
    )

    results: list[dict[str, Any]] = []
    for seed_run in retained_stage0:
        current_T = seed_run["transformation"]
        stage_metrics = list(seed_run["stage_metrics"])

        for i, s in enumerate(stages[1:], start=1):
            ref_down, meas_down = stage_pcds[i]
            reg = _run_one_icp_stage(meas_down, ref_down, s, current_T)
            current_T = reg.transformation
            stage_metrics.append({
                "voxel_mm": s["voxel_mm"],
                "method": s.get("method", "point_to_plane"),
                "fitness": float(reg.fitness),
                "rmse_mm": float(reg.inlier_rmse),
            })

        final = stage_metrics[-1]
        results.append({
            "seed_name": seed_run["seed_name"],
            "fitness": final["fitness"],
            "rmse_mm": final["rmse_mm"],
            "transformation": current_T,
            "coarse_fitness": stage_metrics[0]["fitness"],
            "coarse_rmse_mm": stage_metrics[0]["rmse_mm"],
            "stage_metrics": stage_metrics,
        })

    best = choose_best_result(results)
    first_ref, _ = stage_pcds[0]
    last_ref, _ = stage_pcds[-1]
    first_meas = stage_pcds[0][1]
    last_meas = stage_pcds[-1][1]
    return {
        "best": best,
        "candidates": [
            {
                "seed_name": item["seed_name"],
                "fitness": item["fitness"],
                "rmse_mm": item["rmse_mm"],
                "coarse_fitness": item["coarse_fitness"],
                "coarse_rmse_mm": item["coarse_rmse_mm"],
                "stage_metrics": item["stage_metrics"],
            }
            for item in results
        ],
        "seed_pruning": {
            "evaluated_seed_count": len(stage0_runs),
            "retained_seed_count": len(retained_stage0),
            "retained_seed_names": [item["seed_name"] for item in retained_stage0],
            "pruned_seed_names": [item["seed_name"] for item in pruned_stage0],
            "stage1_rankings": [
                {
                    "seed_name": item["seed_name"],
                    "fitness": item["fitness"],
                    "rmse_mm": item["rmse_mm"],
                }
                for item in sorted(stage0_runs, key=_rank_icp_result)
            ],
        },
        "stages": [{"voxel_mm": s["voxel_mm"], "max_corr_mm": s["max_corr_mm"]} for s in stages],
        "coarse_voxel_mm": stages[0]["voxel_mm"],
        "fine_voxel_mm": stages[-1]["voxel_mm"],
        "coarse_max_corr_mm": stages[0]["max_corr_mm"],
        "fine_max_corr_mm": stages[-1]["max_corr_mm"],
        "ref_counts": {
            "raw": len(ref_pcd.points),
            "coarse": len(first_ref.points),
            "fine": len(last_ref.points),
        },
        "meas_counts": {
            "raw": len(meas_pcd.points),
            "coarse": len(first_meas.points),
            "fine": len(last_meas.points),
        },
    }


# ---------------------------------------------------------------------------
# 용접선(seam) 국소 메트릭 및 정밀화
# ---------------------------------------------------------------------------

def combine_seam_name_groups(*groups: tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for name in group:
            if name not in seen:
                ordered.append(name)
                seen.add(name)
    return tuple(ordered)


def compute_direction_agnostic_tangent_error_deg(
    tangents_a: np.ndarray,
    tangents_b: np.ndarray,
) -> np.ndarray:
    """역방향도 동일하게 취급하는 포인트별 접선(tangent) 각도 오차를 반환합니다."""
    dots = np.sum(tangents_a * tangents_b, axis=1)
    dots = np.clip(np.abs(dots), 0.0, 1.0)
    return np.degrees(np.arccos(dots))


def compute_polyline_geometry_metrics(
    nominal_points: np.ndarray,
    measured_points: np.ndarray,
    *,
    centerline_threshold_mm: float,
    tangent_threshold_deg: float,
) -> dict[str, float]:
    """동일 길이의 두 폴리라인을 용접선(seam) 기하 메트릭으로 비교합니다."""
    from dts.pose import compute_tangent_vectors

    if len(nominal_points) != len(measured_points):
        raise ValueError("nominal_points와 measured_points의 길이가 같아야 합니다")
    if len(nominal_points) == 0:
        return {
            "centerline_mean_mm": float("inf"),
            "centerline_p90_mm": float("inf"),
            "centerline_max_mm": float("inf"),
            "tangent_mean_deg": float("inf"),
            "tangent_p90_deg": float("inf"),
            "tangent_max_deg": float("inf"),
            "corridor_inlier_ratio": 0.0,
            "corridor_pass": False,
            "endpoint_start_mm": float("inf"),
            "endpoint_end_mm": float("inf"),
            "max_contiguous_outlier_points": 0.0,
        }

    centerline_err = np.linalg.norm(measured_points - nominal_points, axis=1)
    tangent_err_deg = compute_direction_agnostic_tangent_error_deg(
        compute_tangent_vectors(nominal_points),
        compute_tangent_vectors(measured_points),
    )
    corridor_mask = (
        (centerline_err <= centerline_threshold_mm)
        & (tangent_err_deg <= tangent_threshold_deg)
    )

    max_run = 0
    current_run = 0
    for is_outlier in (~corridor_mask):
        if is_outlier:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0

    return {
        "centerline_mean_mm": float(np.mean(centerline_err)),
        "centerline_p90_mm": float(np.percentile(centerline_err, 90)),
        "centerline_max_mm": float(np.max(centerline_err)),
        "tangent_mean_deg": float(np.mean(tangent_err_deg)),
        "tangent_p90_deg": float(np.percentile(tangent_err_deg, 90)),
        "tangent_max_deg": float(np.max(tangent_err_deg)),
        "corridor_inlier_ratio": float(np.mean(corridor_mask.astype(float))),
        "corridor_pass": bool(np.all(corridor_mask)),
        "endpoint_start_mm": float(np.linalg.norm(measured_points[0] - nominal_points[0])),
        "endpoint_end_mm": float(np.linalg.norm(measured_points[-1] - nominal_points[-1])),
        "max_contiguous_outlier_points": float(max_run),
    }


def summarize_seam_local_scores(
    per_seam: dict[str, dict[str, Any]],
    *,
    centerline_corridor_mm: float,
    tangent_corridor_deg: float,
    corridor_min_inlier_ratio: float,
) -> dict[str, float]:
    if not per_seam:
        return {
            "avg_mean_nn_mm": float("inf"),
            "avg_p90_nn_mm": float("inf"),
            "worst_max_nn_mm": float("inf"),
            "avg_centerline_mean_mm": float("inf"),
            "avg_centerline_p90_mm": float("inf"),
            "worst_centerline_max_mm": float("inf"),
            "avg_tangent_mean_deg": float("inf"),
            "avg_tangent_p90_deg": float("inf"),
            "worst_tangent_max_deg": float("inf"),
            "avg_corridor_inlier_ratio": 0.0,
            "min_corridor_inlier_ratio": 0.0,
            "corridor_pass": False,
            "avg_endpoint_start_mm": float("inf"),
            "avg_endpoint_end_mm": float("inf"),
            "worst_endpoint_start_mm": float("inf"),
            "worst_endpoint_end_mm": float("inf"),
            "worst_contiguous_outlier_points": 0.0,
            "total_points": 0.0,
        }

    mean_vals = [float(item["mean_nn_mm"]) for item in per_seam.values()]
    p90_vals = [float(item["p90_nn_mm"]) for item in per_seam.values()]
    max_vals = [float(item["max_nn_mm"]) for item in per_seam.values()]
    centerline_mean_vals = [float(item["centerline_mean_mm"]) for item in per_seam.values()]
    centerline_p90_vals = [float(item["centerline_p90_mm"]) for item in per_seam.values()]
    centerline_max_vals = [float(item["centerline_max_mm"]) for item in per_seam.values()]
    tangent_mean_vals = [float(item["tangent_mean_deg"]) for item in per_seam.values()]
    tangent_p90_vals = [float(item["tangent_p90_deg"]) for item in per_seam.values()]
    tangent_max_vals = [float(item["tangent_max_deg"]) for item in per_seam.values()]
    corridor_ratio_vals = [float(item["corridor_inlier_ratio"]) for item in per_seam.values()]
    endpoint_start_vals = [float(item["endpoint_start_mm"]) for item in per_seam.values()]
    endpoint_end_vals = [float(item["endpoint_end_mm"]) for item in per_seam.values()]
    contiguous_vals = [float(item["max_contiguous_outlier_points"]) for item in per_seam.values()]
    point_vals = [float(item["n_points"]) for item in per_seam.values()]
    summary = {
        "avg_mean_nn_mm": float(np.mean(mean_vals)),
        "avg_p90_nn_mm": float(np.mean(p90_vals)),
        "worst_max_nn_mm": float(np.max(max_vals)),
        "avg_centerline_mean_mm": float(np.mean(centerline_mean_vals)),
        "avg_centerline_p90_mm": float(np.mean(centerline_p90_vals)),
        "worst_centerline_max_mm": float(np.max(centerline_max_vals)),
        "avg_tangent_mean_deg": float(np.mean(tangent_mean_vals)),
        "avg_tangent_p90_deg": float(np.mean(tangent_p90_vals)),
        "worst_tangent_max_deg": float(np.max(tangent_max_vals)),
        "avg_corridor_inlier_ratio": float(np.mean(corridor_ratio_vals)),
        "min_corridor_inlier_ratio": float(np.min(corridor_ratio_vals)),
        "avg_endpoint_start_mm": float(np.mean(endpoint_start_vals)),
        "avg_endpoint_end_mm": float(np.mean(endpoint_end_vals)),
        "worst_endpoint_start_mm": float(np.max(endpoint_start_vals)),
        "worst_endpoint_end_mm": float(np.max(endpoint_end_vals)),
        "worst_contiguous_outlier_points": float(np.max(contiguous_vals)),
        "total_points": float(np.sum(point_vals)),
    }
    summary["corridor_pass"] = (
        summary["worst_centerline_max_mm"] <= centerline_corridor_mm
        and summary["worst_tangent_max_deg"] <= tangent_corridor_deg
        and summary["min_corridor_inlier_ratio"] >= corridor_min_inlier_ratio
    )
    return summary


def _compare_seam_local_summary(lhs: dict[str, float], rhs: dict[str, float]) -> int:
    """lhs가 더 좋으면 -1, rhs가 더 좋으면 1, 동일하면 0을 반환합니다."""
    lhs_key = (
        float(lhs["avg_p90_nn_mm"]),
        float(lhs["worst_max_nn_mm"]),
        float(lhs["avg_mean_nn_mm"]),
    )
    rhs_key = (
        float(rhs["avg_p90_nn_mm"]),
        float(rhs["worst_max_nn_mm"]),
        float(rhs["avg_mean_nn_mm"]),
    )
    if lhs_key < rhs_key:
        return -1
    if lhs_key > rhs_key:
        return 1
    return 0


def seam_local_summary_not_worse(
    before: dict[str, float],
    after: dict[str, float],
    *,
    mean_tol_mm: float = 0.02,
    p90_tol_mm: float = 0.05,
    max_tol_mm: float = 0.05,
) -> bool:
    if before.get("total_points", 0.0) <= 0 or after.get("total_points", 0.0) <= 0:
        return True
    return (
        float(after["avg_mean_nn_mm"]) <= float(before["avg_mean_nn_mm"]) + mean_tol_mm
        and float(after["avg_p90_nn_mm"]) <= float(before["avg_p90_nn_mm"]) + p90_tol_mm
        and float(after["worst_max_nn_mm"]) <= float(before["worst_max_nn_mm"]) + max_tol_mm
    )


def compute_seam_local_metrics(
    ref_pcd: o3d.geometry.PointCloud,
    meas_pcd: o3d.geometry.PointCloud,
    transformation: np.ndarray,
    seam_names: tuple[str, ...],
    step_mm: float = 10.0,
    *,
    centerline_corridor_mm: float,
    tangent_corridor_deg: float,
    corridor_min_inlier_ratio: float,
    seam_candidates: dict[str, Any],
    snap_to_surface_fn: Any,
    score_nn_distance_fn: Any,
) -> dict[str, Any]:
    """선택된 정합(ICP) 변환 행렬에 대해 용접선(seam) 국소 표면 일관성을 평가합니다.

    이 함수는 순환 임포트(circular import)를 방지하기 위해
    용접선(seam) 파이프라인의 용접선 후보(seam candidates)와
    스냅(snap)/점수(score) 함수에 대한 참조가 필요합니다.
    """
    from dts.pose import compute_tangent_vectors, resample_uniform

    def _resample_polyline_to_count(points: np.ndarray, count: int) -> np.ndarray:
        if len(points) == 0:
            return np.zeros((0, 3), dtype=float)
        if len(points) == 1 or count <= 1:
            return np.repeat(points[:1], max(count, 1), axis=0)

        diffs = np.diff(points, axis=0)
        seg_lengths = np.linalg.norm(diffs, axis=1)
        cum_len = np.concatenate([[0.0], np.cumsum(seg_lengths)])
        total_len = cum_len[-1]
        if total_len < 1e-12:
            return np.repeat(points[:1], count, axis=0)

        targets = np.linspace(0.0, total_len, count)
        result: list[np.ndarray] = []
        seg_idx = 0
        for t in targets:
            while seg_idx < len(cum_len) - 2 and cum_len[seg_idx + 1] < t:
                seg_idx += 1
            local_t = t - cum_len[seg_idx]
            seg_len = seg_lengths[seg_idx] if seg_idx < len(seg_lengths) else 1e-12
            if seg_len < 1e-12:
                result.append(points[seg_idx])
            else:
                alpha = max(0.0, min(1.0, local_t / seg_len))
                result.append(points[seg_idx] * (1 - alpha) + points[seg_idx + 1] * alpha)
        return np.asarray(result, dtype=float)

    T_inv = np.linalg.inv(transformation)
    per_seam: dict[str, dict[str, Any]] = {}
    for seam_name in seam_names:
        seam_def = seam_candidates.get(seam_name)
        if not seam_def:
            continue
        raw_pts = np.asarray(seam_def["points"], dtype=float)
        snapped = snap_to_surface_fn(raw_pts, ref_pcd, k=5)
        raw_resampled = resample_uniform(raw_pts, step_mm)
        snapped_resampled = resample_uniform(snapped, step_mm)
        match_count = max(2, len(raw_resampled), len(snapped_resampled))
        raw_resampled = _resample_polyline_to_count(raw_resampled, match_count)
        snapped_resampled = _resample_polyline_to_count(snapped_resampled, match_count)
        raw_resampled_cam = transform_points(raw_resampled, T_inv)
        resampled_cam = transform_points(snapped_resampled, T_inv)
        score = score_nn_distance_fn(resampled_cam, meas_pcd)
        geometry = compute_polyline_geometry_metrics(
            raw_resampled_cam,
            resampled_cam,
            centerline_threshold_mm=centerline_corridor_mm,
            tangent_threshold_deg=tangent_corridor_deg,
        )
        per_seam[seam_name] = {
            "n_points": int(len(resampled_cam)),
            "mean_nn_mm": score["mean_nn_mm"],
            "p90_nn_mm": score["p90_nn_mm"],
            "max_nn_mm": score["max_nn_mm"],
            "min_nn_mm": score["min_nn_mm"],
            **geometry,
            "corridor_centerline_threshold_mm": float(centerline_corridor_mm),
            "corridor_tangent_threshold_deg": float(tangent_corridor_deg),
        }

    return {
        "seams": per_seam,
        "summary": summarize_seam_local_scores(
            per_seam,
            centerline_corridor_mm=centerline_corridor_mm,
            tangent_corridor_deg=tangent_corridor_deg,
            corridor_min_inlier_ratio=corridor_min_inlier_ratio,
        ),
        "step_mm": float(step_mm),
    }


def build_reference_seam_points(
    ref_pcd: o3d.geometry.PointCloud,
    seam_names: tuple[str, ...],
    step_mm: float = 10.0,
    *,
    seam_candidates: dict[str, Any],
    snap_to_surface_fn: Any,
) -> np.ndarray:
    """국소 정밀화(refinement) ROI용으로 기준 좌표계의 용접선(seam) 포인트들을 연결하여 생성합니다."""
    from dts.pose import resample_uniform

    chunks: list[np.ndarray] = []
    for seam_name in seam_names:
        seam_def = seam_candidates.get(seam_name)
        if not seam_def:
            continue
        raw_pts = np.asarray(seam_def["points"], dtype=float)
        snapped = snap_to_surface_fn(raw_pts, ref_pcd, k=5)
        resampled = resample_uniform(snapped, step_mm)
        if len(resampled):
            chunks.append(resampled)
    if not chunks:
        raise ValueError("국소 정밀화(refinement)를 위한 용접선(seam) 기준 포인트가 없습니다")
    return np.vstack(chunks)
