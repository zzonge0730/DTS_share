import numpy as np
import open3d as o3d

def make_B_perp_to_A(A, B):
    A = np.array(A, dtype=float)
    B = np.array(B, dtype=float)

    # 평면 법선
    n = np.cross(A, B)

    # 평면 위에서 A와 수직인 벡터
    B_perp = np.cross(n, A)

    # 정규화 (길이 1)
    B_perp = B_perp / np.linalg.norm(B_perp)

    return B_perp

def orientation(Poselist, Scaled_Poselist):
    Oriented_Pose_List = list()
    ######################################

    #Make dictionary that... key = position, value = normal

    pcd = o3d.io.read_point_cloud("A_with_normals.ply")
    pcd_scaled = o3d.io.read_point_cloud("A_with_normals.ply")

    points = np.asarray(pcd.points)
    normals = np.asarray(pcd.normals)
    scaled_points = np.asarray(pcd.points)
    scaled_normals = np.asarray(pcd.normals)

    # 좌표 → 법선 딕셔너리
    point_normal_dict = {tuple(p): tuple(n) for p, n in zip(points, normals)}
    scaled_point_normal_dict = {tuple(p): tuple(n) for p, n in zip(scaled_points, scaled_normals)}


    #Make only contain postion(index will be aligned.)
    positions = [list[p] for p in points]
    scaled_positions= [list[p] for p in scaled_points]
    ## ADD THE INDEX ALINGING ##

    #Make vectors between Scaled and not scaled.
    vectors = list()
    for i in range[len(positions)]:
        vectors.append(positions[i] - scaled_positions[i])

    #Get transfromation matrix makes those vector orthogonal to each normal.
    xs = list()
    for i in range[len(normals)]:
        xs.append(make_B_perp_to_A(normals[i], vectors[i]))

    #Combine normal and vectors
    # xz = [list[p, q] for p, q in normals, xs]

    #Make other axis vector generator apply to above vector set.
    Oriented_Pose_List = list()
    for i in range(len(normals)):
        Oriented_Pose_List.append(xs[i], np.cross(xs[i], normals[i]), normals[i])

    #So we can make each basis.

    ######################################
    return Oriented_Pose_List