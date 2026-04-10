"""Shared rotation / pose transform helpers used across DTS Python tools.

Delegates to dts.transforms when the package is importable (repo-root on
sys.path), otherwise falls back to a self-contained local implementation
so that ``python scripts/transforms.py`` and ``from transforms import ...``
both work regardless of how sys.path is configured.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Sequence, Tuple

# Try to import from the dts package.  If the repo root is not on sys.path
# (e.g. running directly from scripts/), add it once and retry.
try:
    from dts.transforms import (  # noqa: F401
        euler_zyx_to_rotation_matrix,
        rotation_matrix_to_euler_zyx,
        rotation_matrix_to_quaternion,
        quat_to_euler_zyx,
        transform_points,
    )
except ImportError:
    _repo_root = str(Path(__file__).resolve().parents[1])
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    try:
        from dts.transforms import (  # noqa: F401
            euler_zyx_to_rotation_matrix,
            rotation_matrix_to_euler_zyx,
            rotation_matrix_to_quaternion,
            quat_to_euler_zyx,
            transform_points,
        )
    except ImportError:
        # Ultimate fallback: define locally so the module never breaks.
        import numpy as np

        def euler_zyx_to_rotation_matrix(
            rx_deg: float, ry_deg: float, rz_deg: float,
        ) -> Tuple[Tuple[float, ...], ...]:
            rx, ry, rz = math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
            cx, sx = math.cos(rx), math.sin(rx)
            cy, sy = math.cos(ry), math.sin(ry)
            cz, sz = math.cos(rz), math.sin(rz)
            return (
                (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
                (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
                (-sy, cy * sx, cy * cx),
            )

        def rotation_matrix_to_euler_zyx(R: Sequence[Sequence[float]]) -> Tuple[float, float, float]:
            sy = math.sqrt(R[0][0] ** 2 + R[1][0] ** 2)
            if sy > 1e-6:
                return (math.degrees(math.atan2(R[2][1], R[2][2])),
                        math.degrees(math.atan2(-R[2][0], sy)),
                        math.degrees(math.atan2(R[1][0], R[0][0])))
            return (math.degrees(math.atan2(-R[1][2], R[1][1])),
                    math.degrees(math.copysign(math.pi / 2, -R[2][0])), 0.0)

        def rotation_matrix_to_quaternion(R: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
            trace = R[0][0] + R[1][1] + R[2][2]
            if trace > 0:
                s = 0.5 / math.sqrt(trace + 1.0)
                qw, qx = 0.25 / s, (R[2][1] - R[1][2]) * s
                qy, qz = (R[0][2] - R[2][0]) * s, (R[1][0] - R[0][1]) * s
            elif R[0][0] > R[1][1] and R[0][0] > R[2][2]:
                s = 2.0 * math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2])
                qw, qx = (R[2][1] - R[1][2]) / s, 0.25 * s
                qy, qz = (R[0][1] + R[1][0]) / s, (R[0][2] + R[2][0]) / s
            elif R[1][1] > R[2][2]:
                s = 2.0 * math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2])
                qw, qx = (R[0][2] - R[2][0]) / s, (R[0][1] + R[1][0]) / s
                qy, qz = 0.25 * s, (R[1][2] + R[2][1]) / s
            else:
                s = 2.0 * math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1])
                qw, qx = (R[1][0] - R[0][1]) / s, (R[0][2] + R[2][0]) / s
                qy, qz = (R[1][2] + R[2][1]) / s, 0.25 * s
            norm = math.sqrt(qw**2 + qx**2 + qy**2 + qz**2)
            if norm < 1e-12:
                raise ValueError("near-zero quaternion")
            return qw / norm, qx / norm, qy / norm, qz / norm

        def quat_to_euler_zyx(qw: float, qx: float, qy: float, qz: float) -> Tuple[float, float, float]:
            roll = math.atan2(2.0 * (qw * qx + qy * qz), 1.0 - 2.0 * (qx * qx + qy * qy))
            sinp = max(-1.0, min(1.0, 2.0 * (qw * qy - qz * qx)))
            pitch = math.asin(sinp)
            yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
            return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)

        def transform_points(pts, T):
            ones = np.ones((len(pts), 1))
            pts_h = np.hstack([pts, ones])
            return (T @ pts_h.T).T[:, :3]
