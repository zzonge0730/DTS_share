import open3d as o3d
import numpy as np

def normal_maker(Edge, Surface):

    pcd_Edge = Edge
    pcd_Surface = Surface

    points_Edge = np.asarray(pcd_Edge.points)
    points_Surface = np.asarray(pcd_Surface.points)
    normals_Surface = np.asarray(pcd_Surface.normals)

    pcd_Edge_tree = o3d.geometry.KDTreeFlann(pcd_Edge)

    translations = []
    for p in points_Surface:
        [_, idx, _] = pcd_Edge_tree.search_knn_vector_3d(p, 1)
        nearest_Edge = points_Edge[idx[0]]
        translations.append(nearest_Edge - p)

    avg_translation = np.mean(translations, axis=0)

    pcd_Surface.translate(avg_translation)

    pcd_Edge.points = o3d.utility.Vector3dVector(points_Edge)
    pcd_Surface.points = o3d.utility.Vector3dVector(points_Surface)

    normal_dict = {tuple(p): n for p, n in zip(points_Surface, normals_Surface)}

    pcd_Surface_tree = o3d.geometry.KDTreeFlann(pcd_Surface)

    normals_Edge = []
    k = 5

    for p in points_Edge:
        key = tuple(p)
        if key in normal_dict:
            normals_Edge.append(normal_dict[key])
        else:
            [_, idx, _] = pcd_Surface_tree.search_knn_vector_3d(p, k)
            neighbor_normals = normals_Surface[idx]
            avg_normal = np.mean(neighbor_normals, axis=0)
            avg_normal /= np.linalg.norm(avg_normal)
            normals_Edge.append(avg_normal)

    normals_Edge = np.array(normals_Edge)

    pcd_Edge.normals = o3d.utility.Vector3dVector(normals_Edge)

    points_arr  = np.asarray(pcd_Edge.points)
    normals_arr = np.asarray(pcd_Edge.normals)

    data = np.hstack((points_arr, normals_arr))  # (1841,6)
    print(data.shape)
    print(points_arr.shape)
    print(normals_arr.shape)


    return data

def scaling(Original):
    # Read point cloud
    pcd = Original

    scale = 0.99
    points = np.asarray(pcd.points)
    scaled_points = points * scale

    pcd_scaled = o3d.geometry.PointCloud()
    pcd_scaled.points = o3d.utility.Vector3dVector(scaled_points)

    centroid_A = np.mean(points, axis=0)
    centroid_B = np.mean(scaled_points, axis=0)

    # pcd move(centroid_A via center point of A)
    translation = centroid_A - centroid_B
    pcd_scaled.translate(translation)


    return pcd_scaled

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
    return np.array([qx, qy, qz, qw])

def orientation(Edge_with_normal):
    Oriented_Pose_List = []
    points = []
    normals = []
    for i in range(len(Edge_with_normal)):
        points.append(Edge_with_normal[i][:3])
        normals.append(Edge_with_normal[i][3:])

    pcd = o3d.geometry.PointCloud()
    pcd.points  = o3d.utility.Vector3dVector(points)
    pcd.normals = o3d.utility.Vector3dVector(normals)

    # read pcd
    points = np.asarray(pcd.points)
    normals = np.asarray(pcd.normals)
    scaled = scaling(pcd)

    scaled_points = np.asarray(scaled.points)

    # Vector (outward)
    vectors = [points[i] - scaled_points[i] for i in range(len(points))]

    # make basis for each point
    for i in range(len(points)):
        z = normals[i] / np.linalg.norm(normals[i])  # z축
        x = make_B_perp_to_A(z, vectors[i])          # x축
        if np.linalg.norm(x) < 1e-8:
            continue
        y = np.cross(z, x)
        y /= np.linalg.norm(y)

        # rot -> quaternion
        R = np.column_stack((x, y, z))
        q = rotation_matrix_to_quaternion(R)

        pose = [*points[i], *q]   # [x,y,z,qx,qy,qz,qw]
        Oriented_Pose_List.append(pose)

    return Oriented_Pose_List



def final(Edge, Surface):

    New_edge = normal_maker(Edge, Surface)

    final = orientation(New_edge)

    return final