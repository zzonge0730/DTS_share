"""용접선(seam) 에셋 로딩, 스냅 정책, 최근접 이웃(NN) 점수, 포즈(pose) 생성.

scripts/battery_seam_pipeline.py에서 추출한 모듈.  재사용 가능한 용접선(seam)
로직을 담고 있으며, 원본 스크립트는 얇은 CLI 래퍼 역할만 수행합니다.
"""
from __future__ import annotations

import csv as _csv
import json as _json
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d

from dts.config import get_cad_seam_dirs
from dts.transforms import transform_points


# ---------------------------------------------------------------------------
# 용접선(seam) 에셋 / CSV 로딩
# ---------------------------------------------------------------------------

def load_seam_asset(name: str, cad_seam_dirs: list[Path] | None = None) -> tuple[dict | None, Path | None]:
    """설정된 디렉토리에서 이름으로 용접선(seam) 에셋 JSON을 로드합니다."""
    dirs = cad_seam_dirs or get_cad_seam_dirs()
    for d in dirs:
        p = d / f"seam_{name}.asset.json"
        if p.exists():
            return _json.loads(p.read_text(encoding="utf-8")), p
    return None, None


def load_seam_csv(name: str, cad_seam_dirs: list[Path] | None = None) -> tuple[list[list[float]] | None, Path | None]:
    """오버라이드/CAD 내보내기 CSV 파일에서 용접선(seam) 포인트를 로드합니다."""
    dirs = cad_seam_dirs or get_cad_seam_dirs()
    for filename in (f"seam_{name}_override.csv", f"seam_{name}.csv"):
        for d in dirs:
            p = d / filename
            if p.exists():
                pts = []
                with p.open("r", encoding="utf-8") as f:
                    reader = _csv.DictReader(f)
                    for row in reader:
                        pts.append([float(row["x"]), float(row["y"]), float(row["z"])])
                if pts:
                    return pts, p
    return None, None


def build_seam_candidates(cad_seam_dirs: list[Path] | None = None) -> dict[str, Any]:
    """CSV와 에셋 JSON으로부터 용접선(seam) 후보 딕셔너리를 생성합니다."""
    candidates: dict[str, Any] = {}

    # 생산용 U자형 용접선(seam)
    for name, default_desc in [
        ("U1_right", "우측 U자형 용접선, FreeCAD STEP에서 추출한 CAD 에지, 2mm 간격"),
        ("U2_left", "좌측 U자형 용접선, FreeCAD STEP에서 추출한 CAD 에지, 2mm 간격"),
    ]:
        pts, src_path = load_seam_csv(name, cad_seam_dirs)
        asset, _ = load_seam_asset(name, cad_seam_dirs)
        if pts:
            desc = default_desc
            if src_path and src_path.name.endswith("_override.csv"):
                desc = f"{default_desc} (수동 보정본)"
            candidates[name] = {
                "points": pts,
                "description": desc,
                "runtime_contract": (asset or {}).get("runtime_contract", {}),
            }

    # 추가 용접선(seam) 에셋
    for name, desc in [
        ("S3_complex_bottom", "코너와 전이 구간이 포함된 하단 복합 용접선 후보"),
        ("S4_right_step", "공칭 전달 평가에 사용한 우측 단차 용접선 후보"),
        ("S5_long_bottom_steps", "반복 단차 전이 구간이 있는 긴 하단 용접선"),
    ]:
        pts, _ = load_seam_csv(name, cad_seam_dirs)
        asset, _ = load_seam_asset(name, cad_seam_dirs)
        if pts:
            candidates[name] = {
                "points": pts,
                "description": desc,
                "runtime_contract": (asset or {}).get("runtime_contract", {}),
            }

    return candidates


# ---------------------------------------------------------------------------
# 표면 스냅(surface snap)
# ---------------------------------------------------------------------------

def snap_to_surface(seam_pts: np.ndarray, pcd: o3d.geometry.PointCloud,
                    k: int = 5) -> np.ndarray:
    """K-최근접 이웃(KNN) 평균을 사용하여 용접선(seam) 포인트를 PCD 최근접 표면으로 스냅합니다."""
    tree = o3d.geometry.KDTreeFlann(pcd)
    ref_pts = np.asarray(pcd.points)
    snapped = np.zeros_like(seam_pts)
    for i, pt in enumerate(seam_pts):
        _, idx, _ = tree.search_knn_vector_3d(pt, k)
        neighbors = ref_pts[idx]
        snapped[i] = neighbors.mean(axis=0)
    return snapped


def snap_to_surface_constrained(
    seam_pts: np.ndarray,
    pcd: o3d.geometry.PointCloud,
    k: int = 5,
    max_offset_mm: float = 2.0,
) -> np.ndarray:
    """중심선 방향을 보존하는 표면 스냅(surface snap).

    공칭(nominal) 용접선(seam) 접선 방향의 변위를 제거하고,
    나머지 오프셋 크기를 복도(corridor) 크기 경계값으로 클리핑합니다.
    """
    from dts.pose import compute_tangent_vectors

    if len(seam_pts) == 0:
        return np.zeros((0, 3), dtype=float)

    snapped = snap_to_surface(seam_pts, pcd, k=k)
    tangents = compute_tangent_vectors(seam_pts)
    offsets = snapped - seam_pts

    constrained = np.zeros_like(seam_pts)
    for i, (pt, tangent, offset) in enumerate(zip(seam_pts, tangents, offsets)):
        tangent = tangent / max(np.linalg.norm(tangent), 1e-12)
        offset_perp = offset - np.dot(offset, tangent) * tangent
        perp_norm = np.linalg.norm(offset_perp)
        if perp_norm > max_offset_mm > 0.0:
            offset_perp = offset_perp / perp_norm * max_offset_mm
        constrained[i] = pt + offset_perp
    return constrained


def apply_snap_strategy(
    seam_pts: np.ndarray,
    pcd: o3d.geometry.PointCloud,
    snap_mode: str,
    constrained_max_offset_mm: float = 2.0,
) -> np.ndarray:
    """요청된 공칭(nominal) 용접선(seam) 전달 전략을 적용합니다."""
    if snap_mode == "no_snap":
        return seam_pts.copy()
    if snap_mode == "surface_k1":
        return snap_to_surface(seam_pts, pcd, k=1)
    if snap_mode == "surface_k5":
        return snap_to_surface(seam_pts, pcd, k=5)
    if snap_mode == "constrained_k1":
        return snap_to_surface_constrained(
            seam_pts, pcd, k=1, max_offset_mm=constrained_max_offset_mm)
    if snap_mode == "constrained_k5":
        return snap_to_surface_constrained(
            seam_pts, pcd, k=5, max_offset_mm=constrained_max_offset_mm)
    raise ValueError(f"unknown snap_mode: {snap_mode}")


def resolve_snap_mode(seam_def: dict, snap_mode: str) -> str:
    """용접선(seam) 에셋의 runtime_contract에서 'auto' 스냅 모드를 해석합니다."""
    if snap_mode != "auto":
        return snap_mode
    strategy = seam_def.get("runtime_contract", {}).get("snap_strategy", "surface_k5")
    mapping = {
        "ref_pcd_surface_snap_k5": "surface_k5",
        "ref_pcd_surface_snap_k1": "surface_k1",
        "ref_pcd_no_snap": "no_snap",
        "ref_pcd_constrained_snap_k1": "constrained_k1",
        "ref_pcd_constrained_snap_k5": "constrained_k5",
        "no_snap": "no_snap",
        "surface_k1": "surface_k1",
        "surface_k5": "surface_k5",
        "constrained_k1": "constrained_k1",
        "constrained_k5": "constrained_k5",
    }
    return mapping.get(strategy, "surface_k5")


# ---------------------------------------------------------------------------
# 최근접 이웃(NN) 거리 점수
# ---------------------------------------------------------------------------

def score_nn_distance(pts: np.ndarray, pcd: o3d.geometry.PointCloud) -> dict:
    """포인트에서 PCD까지의 최근접 이웃(NN) 거리를 계산합니다."""
    pcd_pts = np.asarray(pcd.points)
    finite_mask = np.isfinite(pcd_pts).all(axis=1)
    if not finite_mask.any():
        return {
            "mean_nn_mm": float("inf"),
            "p90_nn_mm": float("inf"),
            "max_nn_mm": float("inf"),
            "min_nn_mm": float("inf"),
        }

    if finite_mask.all():
        score_pcd = pcd
    else:
        score_pcd = o3d.geometry.PointCloud()
        score_pcd.points = o3d.utility.Vector3dVector(pcd_pts[finite_mask])

    tree = o3d.geometry.KDTreeFlann(score_pcd)
    dists = []
    for pt in pts:
        _, _, dist2 = tree.search_knn_vector_3d(pt, 1)
        if dist2:
            dists.append(np.sqrt(float(dist2[0])))
    dists = np.array(dists)
    return {
        "mean_nn_mm": float(dists.mean()),
        "p90_nn_mm": float(np.percentile(dists, 90)),
        "max_nn_mm": float(dists.max()),
        "min_nn_mm": float(dists.min()),
    }


# ---------------------------------------------------------------------------
# 로컬 표면 법선(normal) 추정
# ---------------------------------------------------------------------------

def estimate_local_normals(seam_pts: np.ndarray, pcd: o3d.geometry.PointCloud,
                           radius: float = 20.0) -> np.ndarray:
    """인근 PCD 포인트로부터 각 용접선(seam) 포인트의 표면 법선(normal)을 추정합니다."""
    tree = o3d.geometry.KDTreeFlann(pcd)
    ref_pts = np.asarray(pcd.points)
    normals = np.zeros_like(seam_pts)

    for i, pt in enumerate(seam_pts):
        _, idx, _ = tree.search_radius_vector_3d(pt, radius)
        if len(idx) < 3:
            _, idx, _ = tree.search_knn_vector_3d(pt, 30)
        neighbors = ref_pts[idx]
        centered = neighbors - neighbors.mean(axis=0)
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        normal = vh[2]
        if normal[2] < 0:
            normal = -normal
        normals[i] = normal / np.linalg.norm(normal)

    return normals


# ---------------------------------------------------------------------------
# 로컬 법선(normal) 기반 포즈(pose) 생성
# ---------------------------------------------------------------------------

def build_poses_local_normal(points_mm: np.ndarray, tangents: np.ndarray,
                              normals: np.ndarray) -> list:
    """포인트별 로컬 표면 법선(normal)을 사용하여 6자유도(6DOF) 포즈를 생성합니다.

    dts.pose 모듈의 Pose6D 데이터클래스 리스트를 반환합니다.
    """
    from dts.pose import Pose6D
    from dts.transforms import rotation_matrix_to_euler_zyx

    poses = []
    for i in range(len(points_mm)):
        z_axis = normals[i] / np.linalg.norm(normals[i])

        t = tangents[i]
        x_axis = t - np.dot(t, z_axis) * z_axis
        x_norm = np.linalg.norm(x_axis)
        if x_norm < 1e-8:
            for fallback in (np.array([1, 0, 0]), np.array([0, 1, 0])):
                x_axis = fallback - np.dot(fallback, z_axis) * z_axis
                x_norm = np.linalg.norm(x_axis)
                if x_norm > 1e-8:
                    break
        x_axis = x_axis / x_norm

        y_axis = np.cross(z_axis, x_axis)
        y_axis = y_axis / np.linalg.norm(y_axis)

        R = np.column_stack([x_axis, y_axis, z_axis])
        rx, ry, rz = rotation_matrix_to_euler_zyx(R)

        poses.append(Pose6D(
            x=points_mm[i, 0], y=points_mm[i, 1], z=points_mm[i, 2],
            rx=rx, ry=ry, rz=rz,
        ))
    return poses
