import open3d as o3d
import numpy as np

# 본넷 전체, 테두리 불러오기
pcd_A = o3d.io.read_point_cloud("surface_2.ply")
pcd_B = o3d.io.read_point_cloud("plz.ply")

points_A = np.asarray(pcd_A.points)
points_B = np.asarray(pcd_B.points)

# KDTree로 B의 각 점에 대해 A에서 가장 가까운 점 찾기
pcd_A_tree = o3d.geometry.KDTreeFlann(pcd_A)

translations = []
for p in points_B:
    [_, idx, _] = pcd_A_tree.search_knn_vector_3d(p, 1)  # 가장 가까운 A의 점
    nearest_A = points_A[idx[0]]
    translations.append(nearest_A - p)

# 평균 translation
avg_translation = np.mean(translations, axis=0)

# B를 평균 translation만큼 이동
pcd_B.translate(avg_translation)

# 시각화
pcd_A.paint_uniform_color([0.7, 0.7, 0.7])  # 회색
pcd_B.paint_uniform_color([1.0, 0.0, 0.0])  # 빨강
axis = o3d.geometry.TriangleMesh.create_coordinate_frame(size=1.0)

o3d.visualization.draw_geometries([pcd_A, pcd_B, axis])
