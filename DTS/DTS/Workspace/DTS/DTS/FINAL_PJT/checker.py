import open3d as o3d
import numpy as np
import os


def _quat_to_rot(qw, qx, qy, qz):
    q = np.array([qw, qx, qy, qz], dtype=float)
    n = np.linalg.norm(q)
    if n < 1e-12:
        return np.eye(3, dtype=float)
    qw, qx, qy, qz = q / n
    return np.array(
        [
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
            [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
            [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
        ],
        dtype=float,
    )


def visualize_seam_on_pcd(pcd_path, poses_nx7, arrow_scale=5.0):
    pose_arr = np.asarray(poses_nx7, dtype=float)
    if pose_arr.ndim != 2 or pose_arr.shape[1] != 7:
        raise ValueError("poses_nx7 must be Nx7 [x,y,z,qw,qx,qy,qz]")

    pcd = o3d.io.read_point_cloud(pcd_path)
    if len(pcd.points) == 0:
        raise ValueError(f"empty point cloud: {pcd_path}")
    pcd.paint_uniform_color([0.6, 0.6, 0.6])

    points = pose_arr[:, :3]
    line_pairs = [[i, i + 1] for i in range(len(points) - 1)] if len(points) >= 2 else []
    seam_line = o3d.geometry.LineSet(
        points=o3d.utility.Vector3dVector(points),
        lines=o3d.utility.Vector2iVector(line_pairs),
    )
    if line_pairs:
        seam_line.colors = o3d.utility.Vector3dVector([[1.0, 1.0, 0.0] for _ in line_pairs])

    arrow_points = []
    arrow_lines = []
    arrow_colors = []
    for i, row in enumerate(pose_arr):
        p = row[:3]
        qw, qx, qy, qz = row[3:7]
        z_axis = _quat_to_rot(qw, qx, qy, qz)[:, 2]
        q = p + z_axis * float(arrow_scale)
        base = len(arrow_points)
        arrow_points.extend([p, q])
        arrow_lines.append([base, base + 1])
        arrow_colors.append([1.0, 0.0, 0.0])

    arrow_set = o3d.geometry.LineSet(
        points=o3d.utility.Vector3dVector(np.asarray(arrow_points, dtype=float)),
        lines=o3d.utility.Vector2iVector(arrow_lines),
    )
    arrow_set.colors = o3d.utility.Vector3dVector(np.asarray(arrow_colors, dtype=float))

    if os.environ.get("DTS_NO_VIS", "0") == "1":
        print("[checker] DTS_NO_VIS=1, skip visualize_seam_on_pcd draw")
        return
    o3d.visualization.draw_geometries([pcd, seam_line, arrow_set])


def visualize_vectors(origins, vectors, vectors_2, scale=1.0):
    """
    origins: (N,3) 시작점들
    vectors: (N,3) 방향 벡터들
    """
    origins = np.asarray(origins)
    vectors = np.asarray(vectors)

    # 끝점 계산
    endpoints = origins + vectors * scale

    # 모든 점 (시작점 + 끝점)
    points = np.vstack((origins, endpoints))

    # 시작점-끝점 연결선 정의
    lines = [[i, i+len(origins)] for i in range(len(origins))]

    line_set = o3d.geometry.LineSet(
        points=o3d.utility.Vector3dVector(points),
        lines=o3d.utility.Vector2iVector(lines)
    )
    line_set.paint_uniform_color([1, 0, 0])  # 빨간색 화살표

    vectors_2 = np.asarray(vectors_2)
    # Backward compatibility for callers passing [normals] instead of normals.
    if vectors_2.ndim == 3 and vectors_2.shape[0] == 1:
        vectors_2 = vectors_2[0]

    # 끝점 계산
    endpoints = origins + vectors_2 * scale

    # 모든 점 (시작점 + 끝점)
    points2 = np.vstack((origins, endpoints))

    # 시작점-끝점 연결선 정의
    lines2 = [[i, i+len(origins)] for i in range(len(origins))]

    line_set_2 = o3d.geometry.LineSet(
        points=o3d.utility.Vector3dVector(points2),
        lines=o3d.utility.Vector2iVector(lines2)
    )
    line_set_2.paint_uniform_color([0, 1, 0])  # 빨간색 화살표
    if os.environ.get("DTS_NO_VIS", "0") == "1":
        print("[checker] DTS_NO_VIS=1, skip visualize_vectors draw")
        return
    o3d.visualization.draw_geometries([line_set, line_set_2])


# PLY 파일 읽기
def visual(pcd):
    # pcd = o3d.io.read_point_cloud("Edge_with_normal.ply")
    # pcd= o3d.io.read_point_cloud("plz.ply")

    # 법선 없으면 추정
    if not pcd.has_normals():
        print("법선 정보가 없어 추정합니다.")
        pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=30))

    points = np.asarray(pcd.points)
    normals = np.asarray(pcd.normals)

    # 최초 5개만 선택
    points_5 = points[:2000]
    normals_5 = normals[:2000]

    # Open3D용 geometry list
    geoms = [pcd]  # 전체 point cloud 표시

    # 5개 점 강조 (파란색 구로 표시)
    for p in points_5:
        sphere = o3d.geometry.TriangleMesh.create_sphere(radius=0.001)  # 크기는 데이터 scale 맞게 조정
        sphere.translate(p)
        sphere.paint_uniform_color([0, 0, 1])  # 파란색
        geoms.append(sphere)

    # 5개 노멀 벡터 (빨간색 선으로 표시)
    for p, n in zip(points_5, normals_5):
        line = o3d.geometry.LineSet()
        line.points = o3d.utility.Vector3dVector([p, p + n * 5])  # 길이 scale은 필요에 맞게
        line.lines = o3d.utility.Vector2iVector([[0, 1]])
        line.colors = o3d.utility.Vector3dVector([[1, 0, 0]])  # 빨강
        geoms.append(line)

    # 시각화
    if os.environ.get("DTS_NO_VIS", "0") == "1":
        print("[checker] DTS_NO_VIS=1, skip visual draw")
        return
    o3d.visualization.draw_geometries(geoms)
    # o3d.visualization.draw_geometries([pcd, pcd_edged])
