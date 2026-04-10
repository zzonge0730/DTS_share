import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime


def _remove_zero_points(pcd, threshold=0.01):
    """Remove points close to origin using vectorized masking."""
    import numpy as np

    pts = np.asarray(pcd.points)
    if pts.size == 0:
        return pcd
    mask = np.linalg.norm(pts, axis=1) > threshold
    return pcd.select_by_index(np.where(mask)[0].tolist())

def _crop_roi(pcd, bbox_min, bbox_max):
    """Crop point cloud to axis-aligned bounding box."""
    import numpy as np
    import open3d as o3d

    mi = np.asarray(bbox_min, dtype=np.float64)
    ma = np.asarray(bbox_max, dtype=np.float64)
    aabb = o3d.geometry.AxisAlignedBoundingBox(min_bound=mi, max_bound=ma)
    return pcd.crop(aabb)


def compute_gap_metrics(ref_path, meas_path, max_corr=2.0, poisson_depth=9,
                        voxel_size=0.0, roi_min=None, roi_max=None):
    import numpy as np
    import open3d as o3d
    import trimesh

    pcd_ref = o3d.io.read_point_cloud(ref_path)
    pcd_meas = o3d.io.read_point_cloud(meas_path)

    if len(pcd_ref.points) == 0 or len(pcd_meas.points) == 0:
        raise ValueError("empty point cloud")

    # Remove invalid points (0,0,0)
    pcd_ref = _remove_zero_points(pcd_ref)
    pcd_meas = _remove_zero_points(pcd_meas)
    print(f"[preprocess] after zero removal: ref={len(pcd_ref.points)}, meas={len(pcd_meas.points)}")

    # ROI crop
    if roi_min is not None and roi_max is not None:
        pcd_ref = _crop_roi(pcd_ref, roi_min, roi_max)
        pcd_meas = _crop_roi(pcd_meas, roi_min, roi_max)
        print(f"[preprocess] after ROI crop: ref={len(pcd_ref.points)}, meas={len(pcd_meas.points)}")

    # Voxel downsampling
    if voxel_size > 0:
        pcd_ref = pcd_ref.voxel_down_sample(voxel_size)
        pcd_meas = pcd_meas.voxel_down_sample(voxel_size)
        print(f"[preprocess] after voxel downsample ({voxel_size}): ref={len(pcd_ref.points)}, meas={len(pcd_meas.points)}")

    pcd_ref, _ = pcd_ref.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    pcd_meas, _ = pcd_meas.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    print(f"[preprocess] after outlier removal: ref={len(pcd_ref.points)}, meas={len(pcd_meas.points)}")

    pcd_ref.estimate_normals()
    mesh_ref, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd_ref, depth=poisson_depth
    )
    densities = np.asarray(densities)
    vertices_to_remove = densities < np.quantile(densities, 0.01)
    mesh_ref.remove_vertices_by_mask(vertices_to_remove)

    pcd_meas.estimate_normals()
    reg_p2p = o3d.pipelines.registration.registration_icp(
        pcd_meas,
        pcd_ref,
        max_correspondence_distance=max_corr,
        init=np.eye(4),
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(),
    )
    pcd_meas.transform(reg_p2p.transformation)

    tri_mesh = trimesh.Trimesh(
        vertices=np.asarray(mesh_ref.vertices),
        faces=np.asarray(mesh_ref.triangles),
    )

    points = np.asarray(pcd_meas.points)
    _, distances, _ = tri_mesh.nearest.on_surface(points)
    distances = np.abs(distances)

    avg_gap = float(np.mean(distances))
    rms_gap = float(np.sqrt(np.mean(distances ** 2)))
    max_gap = float(np.max(distances))
    samples = int(len(distances))

    return {
        "pcd_meas": pcd_meas,
        "mesh_ref": mesh_ref,
        "distances": distances,
        "avg_gap_mm": avg_gap,
        "rms_gap_mm": rms_gap,
        "max_gap_mm": max_gap,
        "samples": samples,
        "icp_fitness": float(reg_p2p.fitness),
        "icp_inlier_rmse": float(reg_p2p.inlier_rmse),
        "transformation": reg_p2p.transformation.tolist(),
    }


def evaluate_icp_quality(metrics, fitness_min=0.3, rmse_max=1.5):
    reasons = []
    fitness = float(metrics["icp_fitness"])
    rmse = float(metrics["icp_inlier_rmse"])

    if fitness < fitness_min:
        reasons.append(f"ICP_FITNESS_LOW({fitness:.3f}<{fitness_min:.3f})")
    if rmse > rmse_max:
        reasons.append(f"ICP_RMSE_HIGH({rmse:.3f}>{rmse_max:.3f})")

    verdict = "OK" if not reasons else "NG"
    return {"verdict": verdict, "reasons": reasons}


def build_gap_json(
    metrics,
    session_id="manual",
    part_id="unknown",
    confidence=1.0,
    fitness_min=0.3,
    rmse_max=1.5,
):
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    icp_quality = evaluate_icp_quality(metrics, fitness_min=fitness_min, rmse_max=rmse_max)
    return {
        "session_id": session_id,
        "part_id": part_id,
        "timestamp": now,
        "metrics": {
            "max_gap_mm": metrics["max_gap_mm"],
            "avg_gap_mm": metrics["avg_gap_mm"],
            "rms_gap_mm": metrics["rms_gap_mm"],
            "samples": metrics["samples"],
            "icp_fitness": metrics["icp_fitness"],
            "icp_inlier_rmse": metrics["icp_inlier_rmse"],
            "transformation": metrics["transformation"],
        },
        "quality": {
            "source": "gab.py",
            "confidence": confidence,
            "icp_fitness": metrics["icp_fitness"],
            "icp_inlier_rmse": metrics["icp_inlier_rmse"],
            "icp_verdict": icp_quality["verdict"],
            "icp_reasons": icp_quality["reasons"],
            "icp_fitness_min": fitness_min,
            "icp_inlier_rmse_max": rmse_max,
        },
    }


def visualize_heatmap(metrics):
    import matplotlib.pyplot as plt
    import open3d as o3d

    distances = metrics["distances"]
    pcd_meas = metrics["pcd_meas"]
    mesh_ref = metrics["mesh_ref"]

    denom = max(1e-12, float(distances.max() - distances.min()))
    dist_norm = (distances - distances.min()) / denom
    colors = plt.get_cmap("jet")(dist_norm)[:, :3]
    pcd_meas.colors = o3d.utility.Vector3dVector(colors)
    o3d.visualization.draw_geometries([mesh_ref, pcd_meas])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="reference point cloud path")
    ap.add_argument("--meas", required=True, help="measured point cloud path")
    ap.add_argument("--json-out", default="", help="write gap contract json")
    ap.add_argument("--session-id", default="manual")
    ap.add_argument("--part-id", default="unknown")
    ap.add_argument("--confidence", type=float, default=1.0)
    ap.add_argument("--max-corr", type=float, default=2.0)
    ap.add_argument("--poisson-depth", type=int, default=9)
    ap.add_argument("--icp-fitness-min", type=float, default=0.3)
    ap.add_argument("--icp-rmse-max", type=float, default=1.5)
    ap.add_argument("--voxel-size", type=float, default=2.0,
                    help="voxel downsample size in mm (0 to disable)")
    ap.add_argument("--roi-min", type=float, nargs=3, default=None,
                    help="ROI bounding box min (x y z)")
    ap.add_argument("--roi-max", type=float, nargs=3, default=None,
                    help="ROI bounding box max (x y z)")
    ap.add_argument("--visualize", action="store_true")
    args = ap.parse_args()

    metrics = compute_gap_metrics(
        ref_path=args.ref,
        meas_path=args.meas,
        max_corr=args.max_corr,
        poisson_depth=args.poisson_depth,
        voxel_size=args.voxel_size,
        roi_min=args.roi_min,
        roi_max=args.roi_max,
    )

    print("평균 오차:", metrics["avg_gap_mm"])
    print("RMS 오차:", metrics["rms_gap_mm"])
    print("최대 오차:", metrics["max_gap_mm"])
    print("샘플 수:", metrics["samples"])

    if args.json_out:
        payload = build_gap_json(
            metrics,
            session_id=args.session_id,
            part_id=args.part_id,
            confidence=args.confidence,
            fitness_min=args.icp_fitness_min,
            rmse_max=args.icp_rmse_max,
        )
        out_dir = os.path.dirname(os.path.abspath(args.json_out)) or "."
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=out_dir,
                prefix=".tmp_gap_",
                suffix=".json",
                delete=False,
            ) as f:
                temp_path = f.name
                json.dump(payload, f, ensure_ascii=True, indent=2)
                f.flush()
                os.fsync(f.fileno())
            shutil.move(temp_path, args.json_out)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        print("JSON 저장:", args.json_out)

    if args.visualize:
        visualize_heatmap(metrics)


if __name__ == "__main__":
    main()
