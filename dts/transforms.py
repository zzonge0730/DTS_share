"""회전, 포즈, 포인트 클라우드 변환 공용 헬퍼 모듈.

이 모듈은 다음 기능을 통합합니다:
- 오일러(Euler) ZYX <-> 회전 행렬(rotation matrix) 변환
- 회전 행렬(rotation matrix) <-> 쿼터니언(quaternion) 변환
- 강체 변환(rigid transform) 4x4 행렬을 포인트 집합에 적용

모든 각도 값은 별도 표기가 없는 한 도(degree) 단위입니다.
오일러(Euler) 컨벤션: sxyz (외적 XYZ = 내적 ZYX), Mech-Mind / Hyundai 규격 기준.
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# 오일러(Euler) / 회전 행렬(rotation matrix)
# ---------------------------------------------------------------------------

def euler_zyx_to_rotation_matrix(
    rx_deg: float, ry_deg: float, rz_deg: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    """오일러(Euler) ZYX 도(degree) -> 3x3 회전 행렬(중첩 튜플)."""
    rx = math.radians(rx_deg)
    ry = math.radians(ry_deg)
    rz = math.radians(rz_deg)

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    return (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )


def rotation_matrix_to_euler_zyx(
    R: Sequence[Sequence[float]],
) -> Tuple[float, float, float]:
    """3x3 회전 행렬 -> 오일러(Euler) ZYX 도(degree) (rx, ry, rz)."""
    sy = math.sqrt(R[0][0] ** 2 + R[1][0] ** 2)

    if sy > 1e-6:
        rx = math.atan2(R[2][1], R[2][2])
        ry = math.atan2(-R[2][0], sy)
        rz = math.atan2(R[1][0], R[0][0])
        return math.degrees(rx), math.degrees(ry), math.degrees(rz)

    rx = math.degrees(math.atan2(-R[1][2], R[1][1]))
    ry = math.degrees(math.copysign(math.pi / 2, -R[2][0]))
    rz = 0.0
    return rx, ry, rz


# ---------------------------------------------------------------------------
# 쿼터니언(Quaternion)
# ---------------------------------------------------------------------------

def rotation_matrix_to_quaternion(
    R: Sequence[Sequence[float]],
) -> Tuple[float, float, float, float]:
    """3x3 회전 행렬 -> (qw, qx, qy, qz), 스칼라 우선(scalar-first) 형식."""
    trace = R[0][0] + R[1][1] + R[2][2]

    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        qw = 0.25 / s
        qx = (R[2][1] - R[1][2]) * s
        qy = (R[0][2] - R[2][0]) * s
        qz = (R[1][0] - R[0][1]) * s
    elif R[0][0] > R[1][1] and R[0][0] > R[2][2]:
        s = 2.0 * math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2])
        qw = (R[2][1] - R[1][2]) / s
        qx = 0.25 * s
        qy = (R[0][1] + R[1][0]) / s
        qz = (R[0][2] + R[2][0]) / s
    elif R[1][1] > R[2][2]:
        s = 2.0 * math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2])
        qw = (R[0][2] - R[2][0]) / s
        qx = (R[0][1] + R[1][0]) / s
        qy = 0.25 * s
        qz = (R[1][2] + R[2][1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1])
        qw = (R[1][0] - R[0][1]) / s
        qx = (R[0][2] + R[2][0]) / s
        qy = (R[1][2] + R[2][1]) / s
        qz = 0.25 * s

    norm = math.sqrt(qw**2 + qx**2 + qy**2 + qz**2)
    if norm < 1e-12:
        raise ValueError("rotation_matrix_to_quaternion: 거의 영(zero)인 쿼터니언(quaternion)이 생성됨")
    return qw / norm, qx / norm, qy / norm, qz / norm


def quat_to_euler_zyx(
    qw: float, qx: float, qy: float, qz: float,
) -> Tuple[float, float, float]:
    """쿼터니언(quaternion) 스칼라 우선(scalar-first) -> 오일러(Euler) ZYX 도(degree)."""
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (qw * qy - qz * qx)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)

    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


# ---------------------------------------------------------------------------
# 강체 변환(rigid transform) 포인트 적용
# ---------------------------------------------------------------------------

def transform_points(pts: np.ndarray, T: np.ndarray) -> np.ndarray:
    """4x4 강체 변환(rigid transform) 행렬을 Nx3 포인트에 적용."""
    ones = np.ones((len(pts), 1))
    pts_h = np.hstack([pts, ones])
    return (T @ pts_h.T).T[:, :3]
