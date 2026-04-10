"""포즈(pose) 데이터 타입, 리샘플링(resample), 접선(tangent) 계산, 출력 형식.

scripts/seam_to_pose.py에서 추출하여 dts/ 패키지가 독립적으로 동작하도록 분리.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np

from dts.transforms import rotation_matrix_to_euler_zyx


# ---------------------------------------------------------------------------
# 데이터 타입
# ---------------------------------------------------------------------------

@dataclass
class Pose6D:
    x: float  # mm
    y: float  # mm
    z: float  # mm
    rx: float  # 도(degree) (오일러(Euler) ZYX)
    ry: float
    rz: float


# ---------------------------------------------------------------------------
# 시임(seam) 로드
# ---------------------------------------------------------------------------

def load_seam_csv(path: Path) -> np.ndarray:
    """시임(seam) CSV 파일(x,y,z)을 로드한다. Nx3 배열을 반환."""
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) < 3:
                raise ValueError(f"expected at least 3 columns in seam file: {path}")
            rows.append([float(row[0]), float(row[1]), float(row[2])])
    if not rows:
        raise ValueError(f"empty seam file: {path}")
    return np.asarray(rows, dtype=np.float64)


# ---------------------------------------------------------------------------
# 균일 간격으로 리샘플링(resample)
# ---------------------------------------------------------------------------

def resample_uniform(points: np.ndarray, step: float) -> np.ndarray:
    """폴리라인(polyline)을 균일 호 길이(arc-length) 간격으로 리샘플링한다 (입력과 동일 단위)."""
    if len(points) < 2:
        return points.copy()

    diffs = np.diff(points, axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    cum_len = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    total_len = cum_len[-1]

    if total_len < 1e-12:
        return points[:1].copy()

    n_samples = max(2, int(math.ceil(total_len / step)) + 1)
    targets = np.linspace(0, total_len, n_samples)

    result = []
    seg_idx = 0
    for t in targets:
        while seg_idx < len(cum_len) - 2 and cum_len[seg_idx + 1] < t:
            seg_idx += 1
        if seg_idx >= len(cum_len) - 1:
            result.append(points[-1])
            continue
        local_t = t - cum_len[seg_idx]
        seg_len = seg_lengths[seg_idx] if seg_idx < len(seg_lengths) else 1e-12
        if seg_len < 1e-12:
            result.append(points[seg_idx])
        else:
            alpha = local_t / seg_len
            alpha = max(0.0, min(1.0, alpha))
            pt = points[seg_idx] * (1 - alpha) + points[seg_idx + 1] * alpha
            result.append(pt)

    return np.array(result)


# ---------------------------------------------------------------------------
# 방향 벡터 및 포즈(pose) 계산
# ---------------------------------------------------------------------------

def compute_tangent_vectors(points: np.ndarray) -> np.ndarray:
    """폴리라인(polyline)을 따라 단위 접선(tangent) 벡터(방향 벡터)를 계산한다."""
    n = len(points)
    tangents = np.zeros_like(points)
    if n <= 1:
        return tangents

    for i in range(n):
        if i == 0:
            t = points[1] - points[0]
        elif i == n - 1:
            t = points[-1] - points[-2]
        else:
            t = points[i + 1] - points[i - 1]
        norm = np.linalg.norm(t)
        if norm > 1e-12:
            t = t / norm
        tangents[i] = t

    return tangents


def estimate_surface_normal(points: np.ndarray) -> np.ndarray:
    """SVD를 이용하여 시임(seam)의 근사 표면 법선(surface normal)을 추정한다."""
    if len(points) < 3:
        return np.array([0.0, 0.0, 1.0])

    centered = points - np.mean(points, axis=0)
    _, s, vh = np.linalg.svd(centered, full_matrices=False)

    normal = vh[2]
    if normal[2] < 0:
        normal = -normal

    return normal / np.linalg.norm(normal)


def build_poses(points_mm: np.ndarray, tangents: np.ndarray,
                surface_normal: np.ndarray) -> List[Pose6D]:
    """점, 접선(tangent) 벡터, 표면 법선(surface normal)으로부터 6자유도(6DOF) 포즈(pose)를 생성한다."""
    poses = []
    for i in range(len(points_mm)):
        z_axis = surface_normal / np.linalg.norm(surface_normal)

        t = tangents[i]
        x_axis = t - np.dot(t, z_axis) * z_axis
        x_norm = np.linalg.norm(x_axis)
        if x_norm < 1e-8:
            for fallback in (
                np.array([1.0, 0.0, 0.0]),
                np.array([0.0, 1.0, 0.0]),
                np.array([0.0, 0.0, 1.0]),
            ):
                x_axis = fallback - np.dot(fallback, z_axis) * z_axis
                x_norm = np.linalg.norm(x_axis)
                if x_norm > 1e-8:
                    break
            if x_norm < 1e-8:
                raise ValueError("failed to construct orthogonal x_axis")
        x_axis = x_axis / x_norm

        y_axis = np.cross(z_axis, x_axis)
        y_axis = y_axis / np.linalg.norm(y_axis)

        R = np.column_stack([x_axis, y_axis, z_axis])
        rx, ry, rz = rotation_matrix_to_euler_zyx(R)

        poses.append(Pose6D(
            x=points_mm[i, 0],
            y=points_mm[i, 1],
            z=points_mm[i, 2],
            rx=rx, ry=ry, rz=rz,
        ))

    return poses


# ---------------------------------------------------------------------------
# 출력 형식
# ---------------------------------------------------------------------------

def save_pose_csv(poses: List[Pose6D], path: Path) -> None:
    """포즈(pose)를 CSV로 저장한다: x,y,z,rx,ry,rz (mm, 도(degree))."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["x", "y", "z", "rx", "ry", "rz"])
        for p in poses:
            writer.writerow([
                f"{p.x:.3f}", f"{p.y:.3f}", f"{p.z:.3f}",
                f"{p.rx:.3f}", f"{p.ry:.3f}", f"{p.rz:.3f}",
            ])
    print(f"[pose] saved {len(poses)} poses to {path}")


def format_1100(poses: List[Pose6D]) -> str:
    """포즈(pose)를 DTS용 1100 프로토콜 문자열로 포맷한다."""
    count = len(poses)
    parts = [f"1100,{count}"]
    for p in poses:
        parts.append(
            f"{p.x:.3f},{p.y:.3f},{p.z:.3f},"
            f"{p.rx:.3f},{p.ry:.3f},{p.rz:.3f}"
        )
    return ",".join(parts)


def save_1100(poses: List[Pose6D], path: Path) -> None:
    """1100 프로토콜 문자열을 파일로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = format_1100(poses)
    path.write_text(content, encoding="utf-8")
    print(f"[1100] saved {len(poses)} poses to {path}")
    if poses:
        p0 = poses[0]
        pn = poses[-1]
        print(f"  first: ({p0.x:.1f}, {p0.y:.1f}, {p0.z:.1f}) rx={p0.rx:.1f} ry={p0.ry:.1f} rz={p0.rz:.1f}")
        print(f"  last:  ({pn.x:.1f}, {pn.y:.1f}, {pn.z:.1f}) rx={pn.rx:.1f} ry={pn.ry:.1f} rz={pn.rz:.1f}")
