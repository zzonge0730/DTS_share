import argparse
import json

try:
    import numpy as np
except Exception:  # pragma: no cover - runtime fallback for minimal env
    np = None


def _require_numpy():
    if np is None:
        raise RuntimeError("numpy is required for pose processing")


def _as_pose_array(poses_nx7):
    _require_numpy()
    arr = np.asarray(poses_nx7, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 7:
        raise ValueError("poses_nx7 must be Nx7 [x,y,z,qw,qx,qy,qz]")
    return arr


def _normalize_quat(q):
    _require_numpy()
    q = np.asarray(q, dtype=float)
    n = np.linalg.norm(q)
    if n < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
    return q / n


def _quat_multiply(q1, q2):
    _require_numpy()
    # Hamilton product for [qw,qx,qy,qz].
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dtype=float,
    )


def _rotation_matrix_to_quaternion_from_orientation(R):
    _require_numpy()
    # Reuse Orientation_gpt conversion when available, with local fallback for headless tests.
    try:
        import Orientation_gpt

        return np.asarray(Orientation_gpt.rotation_matrix_to_quaternion(np.asarray(R, dtype=float)), dtype=float)
    except Exception:
        R = np.asarray(R, dtype=float)
        m00, m01, m02 = R[0, 0], R[0, 1], R[0, 2]
        m10, m11, m12 = R[1, 0], R[1, 1], R[1, 2]
        m20, m21, m22 = R[2, 0], R[2, 1], R[2, 2]
        tr = m00 + m11 + m22
        if tr > 0:
            S = np.sqrt(tr + 1.0) * 2.0
            qw = 0.25 * S
            qx = (m21 - m12) / S
            qy = (m02 - m20) / S
            qz = (m10 - m01) / S
        elif (m00 > m11) and (m00 > m22):
            S = np.sqrt(1.0 + m00 - m11 - m22) * 2.0
            qw = (m21 - m12) / S
            qx = 0.25 * S
            qy = (m01 + m10) / S
            qz = (m02 + m20) / S
        elif m11 > m22:
            S = np.sqrt(1.0 + m11 - m00 - m22) * 2.0
            qw = (m02 - m20) / S
            qx = (m01 + m10) / S
            qy = 0.25 * S
            qz = (m12 + m21) / S
        else:
            S = np.sqrt(1.0 + m22 - m00 - m11) * 2.0
            qw = (m10 - m01) / S
            qx = (m02 + m20) / S
            qy = (m12 + m21) / S
            qz = 0.25 * S
        return np.array([qw, qx, qy, qz], dtype=float)


def apply_rigid_transform(poses_nx7, T_4x4):
    _require_numpy()
    pose_arr = _as_pose_array(poses_nx7)
    T = np.asarray(T_4x4, dtype=float)
    if T.shape != (4, 4):
        raise ValueError("T_4x4 must be 4x4")

    R = T[:3, :3]
    t = T[:3, 3]
    q_t = _normalize_quat(_rotation_matrix_to_quaternion_from_orientation(R))

    out = pose_arr.copy()
    out[:, :3] = (R @ pose_arr[:, :3].T).T + t

    for i in range(len(out)):
        q_pose = _normalize_quat(out[i, 3:7])
        q_new = _normalize_quat(_quat_multiply(q_t, q_pose))
        out[i, 3:7] = q_new
    return out.tolist()


def _apply_scale_to_positions(poses_nx7, scale):
    arr = _as_pose_array(poses_nx7)
    out = arr.copy()
    out[:, :3] *= float(scale)
    return out.tolist()


def _rotation_jump_indices(poses_nx7, threshold_deg=30.0):
    arr = _as_pose_array(poses_nx7)
    if len(arr) < 2:
        return []

    qs = arr[:, 3:7].copy()
    norms = np.linalg.norm(qs, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    qs = qs / norms

    out = []
    for i in range(len(qs) - 1):
        d = abs(float(np.dot(qs[i], qs[i + 1])))
        d = min(1.0, max(-1.0, d))
        ang_deg = float(np.degrees(2.0 * np.arccos(d)))
        if ang_deg > threshold_deg:
            out.append(i)
    return out


def _filter_pose_outliers_drop(poses_nx7, threshold_deg=30.0, max_ratio=0.02):
    arr = _as_pose_array(poses_nx7)
    jumps = _rotation_jump_indices(arr, threshold_deg=threshold_deg)
    if not jumps:
        return arr.tolist(), {"removed": 0, "ratio": 0.0, "jump_count": 0}

    # Drop the later point of each jump pair (i -> i+1).
    drop_idx = {i + 1 for i in jumps}
    ratio = len(drop_idx) / max(1, len(arr))
    if ratio > max_ratio:
        raise RuntimeError(
            "rotation outlier ratio too high: "
            f"{ratio:.4f} > {max_ratio:.4f} (jump_count={len(jumps)})"
        )

    keep = [i for i in range(len(arr)) if i not in drop_idx]
    filtered = arr[keep]
    return filtered.tolist(), {"removed": len(drop_idx), "ratio": ratio, "jump_count": len(jumps)}


def _mean_nn_distance_to_pcd(poses_nx7, pcd_path):
    import open3d as o3d

    arr = _as_pose_array(poses_nx7)
    pcd = o3d.io.read_point_cloud(pcd_path)
    if len(pcd.points) == 0:
        raise ValueError(f"empty point cloud: {pcd_path}")
    tree = o3d.geometry.KDTreeFlann(pcd)

    dists = []
    for p in arr[:, :3]:
        _, _, dist2 = tree.search_knn_vector_3d(p, 1)
        if not dist2:
            continue
        dists.append(np.sqrt(float(dist2[0])))
    if not dists:
        return float("inf")
    return float(np.mean(dists))


def _candidate_scales(unit_mode):
    if unit_mode == "none":
        return [1.0]
    if unit_mode == "m_to_mm":
        return [1000.0]
    if unit_mode == "mm_to_m":
        return [0.001]
    if unit_mode == "auto":
        return [1.0, 1000.0, 0.001]
    raise ValueError(f"unknown unit mode: {unit_mode}")


def _candidate_directions(direction_mode):
    if direction_mode == "direct":
        return ["direct"]
    if direction_mode == "inverse":
        return ["inverse"]
    if direction_mode == "auto":
        return ["direct", "inverse"]
    raise ValueError(f"unknown direction mode: {direction_mode}")


def _resolve_transform(poses_nx7, T_4x4, direction_mode, unit_mode, ref_pcd_path):
    T = np.asarray(T_4x4, dtype=float)
    if T.shape != (4, 4):
        raise ValueError("T_4x4 must be 4x4")

    dirs = _candidate_directions(direction_mode)
    scales = _candidate_scales(unit_mode)

    # If no auto behavior requested, use fixed transform without scoring.
    needs_scoring = (direction_mode == "auto") or (unit_mode == "auto")
    if not needs_scoring:
        use_T = np.linalg.inv(T) if dirs[0] == "inverse" else T
        return apply_rigid_transform(_apply_scale_to_positions(poses_nx7, scales[0]), use_T), {
            "direction": dirs[0],
            "unit_scale": scales[0],
            "distance_mean": None,
        }

    if not ref_pcd_path:
        raise ValueError("transform auto mode requires --transform-ref-pcd (or --visualize)")

    best = None
    for d in dirs:
        use_T = np.linalg.inv(T) if d == "inverse" else T
        for s in scales:
            candidate = apply_rigid_transform(_apply_scale_to_positions(poses_nx7, s), use_T)
            mean_dist = _mean_nn_distance_to_pcd(candidate, ref_pcd_path)
            item = (mean_dist, d, s, candidate)
            if best is None or item[0] < best[0]:
                best = item

    return best[3], {"direction": best[1], "unit_scale": best[2], "distance_mean": best[0]}


def _load_transform_from_json(path):
    _require_numpy()
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    metrics = payload.get("metrics", {})
    T = metrics.get("transformation")
    if T is None:
        raise ValueError("metrics.transformation missing in transform json")
    arr = np.asarray(T, dtype=float)
    if arr.shape != (4, 4):
        raise ValueError("metrics.transformation must be 4x4")
    return arr


def _save_pose_output(path, poses_nx7, as_csv=False):
    _require_numpy()
    arr = _as_pose_array(poses_nx7)
    if as_csv:
        np.savetxt(
            path,
            arr,
            fmt="%.6f",
            delimiter=",",
            header="x,y,z,qw,qx,qy,qz",
            comments="",
        )
    else:
        np.savetxt(path, arr, fmt="%.6f")


def build_pose_path(
    edge_path,
    surface_path,
    enable_smoothing=False,
    smooth_window=5,
    base_step_mm=5.0,
    min_step_mm=2.0,
    max_step_mm=8.0,
    angle_threshold_deg=8.0,
    curvature_gain=0.7,
):
    _require_numpy()
    import Orientation_gpt
    import Sampling
    import mapping

    edge_with_normals = mapping.normal_maker(edge_path, surface_path)
    raw_poses = Orientation_gpt.orientation(edge_with_normals)
    processed = raw_poses

    if enable_smoothing:
        processed = Sampling.smooth_positions(processed, window=smooth_window)

    processed = Sampling.curvature_adaptive_resample_with_quat(
        processed,
        base_step_mm=base_step_mm,
        min_step_mm=min_step_mm,
        max_step_mm=max_step_mm,
        angle_threshold_deg=angle_threshold_deg,
        curvature_gain=curvature_gain,
    )
    return raw_poses, processed


def main():
    ap = argparse.ArgumentParser(description="DTS FINAL_PJT pose pipeline")
    ap.add_argument("--edge", default="plz.ply", help="Edge point cloud path")
    ap.add_argument("--surface", default="surface_2.ply", help="Surface point cloud path")
    ap.add_argument("--out", default="final.txt", help="Output pose txt path")
    ap.add_argument("--csv", action="store_true", help="Write output as CSV with header")
    ap.add_argument(
        "--transform-json",
        default="",
        help="Path to gab.py output JSON containing metrics.transformation 4x4 matrix",
    )
    ap.add_argument(
        "--transform-direction",
        choices=["direct", "inverse", "auto"],
        default="direct",
        help="How to apply transformation matrix direction",
    )
    ap.add_argument(
        "--transform-unit",
        choices=["none", "m_to_mm", "mm_to_m", "auto"],
        default="none",
        help="Position unit scaling before rigid transform",
    )
    ap.add_argument(
        "--transform-ref-pcd",
        default="",
        help="Reference PCD path used to score transform candidates in auto mode",
    )
    ap.add_argument(
        "--visualize",
        default="",
        help="Visualize seam and torch directions over this PCD path",
    )
    ap.add_argument(
        "--outlier-policy",
        choices=["none", "drop"],
        default="none",
        help="Orientation outlier handling policy",
    )
    ap.add_argument("--outlier-angle-deg", type=float, default=30.0, help="Quaternion jump threshold")
    ap.add_argument(
        "--outlier-max-ratio",
        type=float,
        default=0.02,
        help="Fail-safe threshold for outlier ratio",
    )
    ap.add_argument("--smooth", action="store_true", help="Apply xyz smoothing before resampling")
    ap.add_argument("--smooth-window", type=int, default=5, help="Smoothing window size (odd)")
    ap.add_argument("--base-step-mm", type=float, default=5.0, help="Base resampling step")
    ap.add_argument("--min-step-mm", type=float, default=2.0, help="Minimum step in high curvature")
    ap.add_argument("--max-step-mm", type=float, default=8.0, help="Maximum step in low curvature")
    ap.add_argument("--angle-threshold-deg", type=float, default=8.0, help="Force-keep turning angle")
    ap.add_argument("--curvature-gain", type=float, default=0.7, help="Curvature sensitivity (0~1)")
    args = ap.parse_args()

    raw, final = build_pose_path(
        edge_path=args.edge,
        surface_path=args.surface,
        enable_smoothing=args.smooth,
        smooth_window=args.smooth_window,
        base_step_mm=args.base_step_mm,
        min_step_mm=args.min_step_mm,
        max_step_mm=args.max_step_mm,
        angle_threshold_deg=args.angle_threshold_deg,
        curvature_gain=args.curvature_gain,
    )
    if args.transform_json:
        T = _load_transform_from_json(args.transform_json)
        ref_pcd = args.transform_ref_pcd or args.visualize
        final, transform_info = _resolve_transform(
            final,
            T,
            direction_mode=args.transform_direction,
            unit_mode=args.transform_unit,
            ref_pcd_path=ref_pcd,
        )
        print(
            "[transform] direction=%s unit_scale=%s mean_nn_dist=%s"
            % (
                transform_info["direction"],
                transform_info["unit_scale"],
                "n/a" if transform_info["distance_mean"] is None else f"{transform_info['distance_mean']:.6f}",
            )
        )

    if args.outlier_policy == "drop":
        final, outlier_info = _filter_pose_outliers_drop(
            final,
            threshold_deg=args.outlier_angle_deg,
            max_ratio=args.outlier_max_ratio,
        )
        print(
            "[outlier] policy=drop removed=%d jump_count=%d ratio=%.4f"
            % (outlier_info["removed"], outlier_info["jump_count"], outlier_info["ratio"])
        )

    _save_pose_output(args.out, final, as_csv=args.csv)
    print("[pose] raw=%d sampled=%d out=%s" % (len(raw), len(final), args.out))

    if args.visualize:
        import checker

        checker.visualize_seam_on_pcd(args.visualize, final)


if __name__ == "__main__":
    main()
