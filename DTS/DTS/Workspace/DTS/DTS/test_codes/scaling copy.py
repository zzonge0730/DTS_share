import open3d as o3d
import numpy as np

# Point cloud 읽기
pcd = o3d.io.read_point_cloud("plz.ply")

# ===== 1. 비율 축소 (0.9배) =====
scale = 0.99
points = np.asarray(pcd.points)
scaled_points = points * scale

pcd_scaled = o3d.geometry.PointCloud()
pcd_scaled.points = o3d.utility.Vector3dVector(scaled_points)

# ===== 2. 중심점 계산 =====
centroid_A = np.mean(points, axis=0)
centroid_B = np.mean(scaled_points, axis=0)


points = np.array([centroid_A,
                   centroid_B,
                   ])

centroids = o3d.geometry.PointCloud()
centroids.points = o3d.utility.Vector3dVector(points)
centroids.paint_uniform_color([0, 1, 0])  # 초록


print(centroid_A)
print(centroid_B)

# ===== 3. 원점으로 이동 =====
pcd.translate(-centroid_A)
pcd_scaled.translate(-centroid_B)

# ===== 4. 색상 지정 =====
pcd.paint_uniform_color([0.7, 0.7, 0.7])   # 원본 (회색)
pcd_scaled.paint_uniform_color([1, 0, 0]) # 축소본 (빨강)

# ===== 5. 시각화 =====
o3d.visualization.draw_geometries([pcd, pcd_scaled, centroids])



###################################################

