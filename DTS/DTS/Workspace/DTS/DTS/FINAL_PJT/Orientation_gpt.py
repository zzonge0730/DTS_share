import numpy as np
import open3d as o3d
import Scaling
import checker
import Ordering

def make_B_perp_to_A(A, B):
    A = np.array(A, dtype=float)
    B = np.array(B, dtype=float)
    n = np.cross(A, B)
    if np.linalg.norm(n) < 1e-8:
        return np.zeros(3)
    B_perp = np.cross(n, A)
    if np.linalg.norm(B_perp) > 1e-8:
        B_perp /= np.linalg.norm(B_perp)
    return B_perp

def rotation_matrix_to_quaternion(R):
    # """3x3 회전행렬 -> 쿼터니언 [x,y,z,w]"""
    m00, m01, m02 = R[0,0], R[0,1], R[0,2]
    m10, m11, m12 = R[1,0], R[1,1], R[1,2]
    m20, m21, m22 = R[2,0], R[2,1], R[2,2]
    tr = m00 + m11 + m22

    if tr > 0:
        S = np.sqrt(tr+1.0) * 2
        qw = 0.25 * S
        qx = (m21 - m12) / S
        qy = (m02 - m20) / S
        qz = (m10 - m01) / S
    elif (m00 > m11) and (m00 > m22):
        S = np.sqrt(1.0 + m00 - m11 - m22) * 2
        qw = (m21 - m12) / S
        qx = 0.25 * S
        qy = (m01 + m10) / S
        qz = (m02 + m20) / S
    elif m11 > m22:
        S = np.sqrt(1.0 + m11 - m00 - m22) * 2
        qw = (m02 - m20) / S
        qx = (m01 + m10) / S
        qy = 0.25 * S
        qz = (m12 + m21) / S
    else:
        S = np.sqrt(1.0 + m22 - m00 - m11) * 2
        qw = (m10 - m01) / S
        qx = (m02 + m20) / S
        qy = (m12 + m21) / S
        qz = 0.25 * S
    return np.array([qw, qx, qy, qz])

def orientation(Edge_with_normal):
    Oriented_Pose_List = []
    points = []
    normals = []
    for i in range(len(Edge_with_normal)):
        # points  = [row[:3] for row in Edge_with_normal]  # xyz
        # normals = [row[3:] for row in Edge_with_normal]  # normal
        points.append(Edge_with_normal[i][:3])
        normals.append(Edge_with_normal[i][3:])

    pcd = o3d.geometry.PointCloud()
    pcd.points  = o3d.utility.Vector3dVector(points)
    pcd.normals = o3d.utility.Vector3dVector(normals)

    # 포인트 클라우드 읽기
    # pcd = o3d.io.read_point_cloud(Edge_with_normal)
    # pcd = Ordering.order_boundary_points_3d(pcd)
    points = np.asarray(pcd.points)
    normals = np.asarray(pcd.normals)
    scaled = Scaling.scaling_9(pcd)
    # scaled = Ordering.order_boundary_points_3d(scaled)

    # (예시) scaled는 그냥 같은 걸 쓰지만, 실제로는 따로 불러야 함
    scaled_points = np.asarray(scaled.points)

    # 벡터 차이
    vectors = [scaled_points[i] - points[i] for i in range(len(points))]

    x = [make_B_perp_to_A(normals[i] / np.linalg.norm(normals[i]), vectors[i]) for i in range(len(vectors))]

    checker.visualize_vectors(points, x, [normals])

    # 각 점마다 pose 생성
    for i in range(len(points)):
        z = normals[i] / np.linalg.norm(normals[i])  # z축
        x = make_B_perp_to_A(z, vectors[i])          # x축
        if np.linalg.norm(x) < 1e-8:
            continue
        y = np.cross(z, x)
        y /= np.linalg.norm(y)

        # 회전행렬 -> 쿼터니언
        R = np.column_stack((x, y, z))
        q = rotation_matrix_to_quaternion(R)

        pose = [*points[i], *q]   # [x,y,z,qx,qy,qz,qw]
        Oriented_Pose_List.append(pose)

    return Oriented_Pose_List