import open3d as o3d
import numpy as np

def normal_maker(Edge, Surface):
    # Support both file-path input and already loaded point clouds.
    if isinstance(Edge, str):
        pcd_Edge = o3d.io.read_point_cloud(Edge)
    else:
        pcd_Edge = Edge
    if isinstance(Surface, str):
        pcd_Surface = o3d.io.read_point_cloud(Surface)
    else:
        pcd_Surface = Surface

    points_Edge = np.asarray(pcd_Edge.points)
    points_Surface = np.asarray(pcd_Surface.points)
    normals_Surface = np.asarray(pcd_Surface.normals)

    # 2. 중심 맞추기 (원점 이동)
    # KDTree로 B의 각 점에 대해 A에서 가장 가까운 점 찾기
    pcd_Edge_tree = o3d.geometry.KDTreeFlann(pcd_Edge)

    translations = []
    for p in points_Surface:
        [_, idx, _] = pcd_Edge_tree.search_knn_vector_3d(p, 1)  # 가장 가까운 A의 점
        nearest_Edge = points_Edge[idx[0]]
        translations.append(nearest_Edge - p)

    # 평균 translation
    avg_translation = np.mean(translations, axis=0)

    # B를 평균 translation만큼 이동
    pcd_Surface.translate(avg_translation)

    pcd_Edge.points = o3d.utility.Vector3dVector(points_Edge)
    pcd_Surface.points = o3d.utility.Vector3dVector(points_Surface)

    # 3. 좌표 → 법선 매핑 dict
    normal_dict = {tuple(p): n for p, n in zip(points_Surface, normals_Surface)}

    # KDTree (빠른 최근접 검색용)
    pcd_Surface_tree = o3d.geometry.KDTreeFlann(pcd_Surface)

    # 4. A의 각 점에 대해 법선 가져오기 (예외 처리: kNN 평균)
    normals_Edge = []
    k = 5  # 근처 이웃 개수

    for p in points_Edge:
        key = tuple(p)
        if key in normal_dict:
            normals_Edge.append(normal_dict[key])
        else:
            # 가까운 B의 점 k개 검색
            [_, idx, _] = pcd_Surface_tree.search_knn_vector_3d(p, k)
            neighbor_normals = normals_Surface[idx]
            avg_normal = np.mean(neighbor_normals, axis=0)
            avg_normal /= np.linalg.norm(avg_normal)  # 정규화
            normals_Edge.append(avg_normal)

    normals_Edge = np.array(normals_Edge)

    # 5. A에 법선 저장
    pcd_Edge.normals = o3d.utility.Vector3dVector(normals_Edge)

    # data = np.hstack((pcd_Edge.points, pcd_Edge.normals))
    # Edge_with_normal = data.tolist()  # numpy → 파이썬 리스트 변환
    points_arr  = np.asarray(pcd_Edge.points)
    normals_arr = np.asarray(pcd_Edge.normals)

    data = np.hstack((points_arr, normals_arr))  # (1841,6)
    print(data.shape)
    print(points_arr.shape)
    print(normals_arr.shape)
    # Edge_with_normal = data.tolist()             # list of [x,y,z,nx,ny,nz]

    # # 6. 결과 저장
    # o3d.io.write_point_cloud("Edge_with_normal.ply", pcd_Edge)
    # print("✅ 법선 매핑 완료! 'Edge_with_normal.ply' 저장됨")

    return data
