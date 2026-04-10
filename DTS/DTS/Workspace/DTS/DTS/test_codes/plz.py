import open3d as o3d
import numpy as np

# 포인트 클라우드 읽기
pcd = o3d.io.read_point_cloud("surface.ply")
points = np.asarray(pcd.points)

# 중심점
centroid = np.mean(points, axis=0)
vectors = points - centroid

# 구 좌표 변환
r = np.linalg.norm(vectors, axis=1)
theta = np.degrees(np.arctan2(vectors[:,1], vectors[:,0]))   # -180 ~ 180
phi = np.degrees(np.arccos(vectors[:,2] / r))                # 0 ~ 180

# 각도 resolution (deg)
theta_step = 5
phi_step = 5

selected = []
for t in range(-180, 180, theta_step):
    for p in range(0, 180, phi_step):
        mask = ((theta >= t) & (theta < t + theta_step) &
                (phi   >= p) & (phi   < p + phi_step))
        if np.any(mask):
            idx = np.argmax(r[mask])  # 해당 bin에서 가장 먼 점
            selected.append(points[mask][idx])

selected = np.array(selected)

# 결과 시각화
pcd.paint_uniform_color([0.7, 0.7, 0.7])   # 원본 (회색)
pcd_outline = o3d.geometry.PointCloud()
pcd_outline.points = o3d.utility.Vector3dVector(selected)
pcd_outline.paint_uniform_color([1, 0, 0]) # 윤곽 (빨강)
pcd_centroid = o3d.geometry.PointCloud()
pcd_centroid.points = o3d.utility.Vector3dVector([centroid])
pcd_centroid.paint_uniform_color([1, 0, 0])

# o3d.visualization.draw_geometries([pcd, pcd_outline])
o3d.visualization.draw_geometries([pcd, pcd_centroid])
