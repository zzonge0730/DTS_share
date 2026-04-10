import numpy as np


EPS = 1e-9


def _to_pose_array(poses):
    arr = np.asarray(poses, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 7:
        raise ValueError("poses must be Nx7 [x,y,z,qx,qy,qz,qw]")
    return arr


def _turning_angles_rad(points):
    """Return per-index turning angle for polyline points."""
    n = len(points)
    angles = np.zeros(n, dtype=float)
    for i in range(1, n - 1):
        v1 = points[i] - points[i - 1]
        v2 = points[i + 1] - points[i]
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 < EPS or n2 < EPS:
            continue
        cos_theta = np.dot(v1, v2) / (n1 * n2)
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        angles[i] = np.arccos(cos_theta)
    return angles


def curvature_adaptive_resample_with_quat(
    poses,
    base_step_mm=5.0,
    min_step_mm=2.0,
    max_step_mm=8.0,
    angle_threshold_deg=8.0,
    curvature_gain=0.7,
):
    """
    Curvature-adaptive downsampling for [x,y,z,qx,qy,qz,qw] pose lists.

    Strategy:
    - Keep endpoints always.
    - In low curvature, keep points at wider spacing.
    - In high curvature, keep points denser.
    - Force-keep sharp-turn anchor points.
    """
    pose_arr = _to_pose_array(poses)
    n = len(pose_arr)
    if n <= 2:
        return pose_arr.tolist()

    points = pose_arr[:, :3]
    angles = _turning_angles_rad(points)
    max_angle = max(np.max(angles), EPS)
    angle_threshold = np.deg2rad(angle_threshold_deg)

    kept_idx = [0]
    acc_dist = 0.0

    for i in range(1, n - 1):
        seg = np.linalg.norm(points[i] - points[i - 1])
        acc_dist += seg

        normalized_curvature = min(1.0, angles[i] / max_angle)
        # Higher curvature -> smaller target step.
        step = base_step_mm * (1.0 - curvature_gain * normalized_curvature)
        step = float(np.clip(step, min_step_mm, max_step_mm))

        if angles[i] >= angle_threshold or acc_dist >= step:
            kept_idx.append(i)
            acc_dist = 0.0

    if kept_idx[-1] != n - 1:
        kept_idx.append(n - 1)

    return pose_arr[kept_idx].tolist()


def smooth_positions(poses, window=5):
    """
    Light moving-average smoothing on xyz only.
    Quaternion fields are kept from the original points.
    """
    pose_arr = _to_pose_array(poses)
    if window <= 1 or len(pose_arr) <= 2:
        return pose_arr.tolist()

    if window % 2 == 0:
        window += 1
    radius = window // 2
    out = pose_arr.copy()

    for i in range(len(pose_arr)):
        lo = max(0, i - radius)
        hi = min(len(pose_arr), i + radius + 1)
        out[i, :3] = np.mean(pose_arr[lo:hi, :3], axis=0)
    return out.tolist()
