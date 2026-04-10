import open3d as o3d
import numpy as np

def normal_maker(Edge, Surface):
    # 1. 포인트 클라우드 읽기
    pcd_Edge = o3d.io.read_point_cloud(Edge)
    pcd_Surface = o3d.io.read_point_cloud(Surface)

    points_A = np.asarray(pcd_Edge.points)
    points_B = np.asarray(pcd_Surface.points)
    normals_B = np.asarray(pcd_Surface.normals)

    # 2. 중심 맞추기 (원점 이동)
    # KDTree로 B의 각 점에 대해 A에서 가장 가까운 점 찾기
    pcd_Edge_tree = o3d.geometry.KDTreeFlann(pcd_Edge)

    translations = []
    for p in points_B:
        [_, idx, _] = pcd_Edge_tree.search_knn_vector_3d(p, 1)  # 가장 가까운 A의 점
        nearest_A = points_A[idx[0]]
        translations.append(nearest_A - p)

    # 평균 translation
    avg_translation = np.mean(translations, axis=0)

    # B를 평균 translation만큼 이동
    pcd_Surface.translate(avg_translation)

    pcd_Edge.points = o3d.utility.Vector3dVector(points_A)
    pcd_Surface.points = o3d.utility.Vector3dVector(points_B)
    pcd_Edge.paint_uniform_color([0.7, 0.7, 0.7])   # 원본 (회색)
    pcd_Surface.paint_uniform_color([0.7, 0, 0])   # 원본 (회색)

    o3d.visualization.draw_geometries([pcd_Edge, pcd_Surface])

    # 3. 좌표 → 법선 매핑 dict
    normal_dict = {tuple(p): n for p, n in zip(points_B, normals_B)}

    # KDTree (빠른 최근접 검색용)
    pcd_Surface_tree = o3d.geometry.KDTreeFlann(pcd_Surface)

    # 4. A의 각 점에 대해 법선 가져오기 (예외 처리: kNN 평균)
    normals_A = []
    k = 5  # 근처 이웃 개수

    for p in points_A:
        key = tuple(p)
        if key in normal_dict:
            normals_A.append(normal_dict[key])
        else:
            # 가까운 B의 점 k개 검색
            [_, idx, _] = pcd_Surface_tree.search_knn_vector_3d(p, k)
            neighbor_normals = normals_B[idx]
            avg_normal = np.mean(neighbor_normals, axis=0)
            avg_normal /= np.linalg.norm(avg_normal)  # 정규화
            normals_A.append(avg_normal)

    normals_A = np.array(normals_A)

    # 5. A에 법선 저장
    pcd_Edge.normals = o3d.utility.Vector3dVector(normals_A)

    # 6. 결과 저장
    o3d.io.write_point_cloud("A_with_normals.ply", pcd_Edge)
    print("✅ 법선 매핑 완료! 'A_with_normals.ply' 저장됨")
