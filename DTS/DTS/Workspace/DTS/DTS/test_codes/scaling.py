import open3d as o3d
import numpy as np

def scaling(Original):
    # Point cloud 읽기
    pcd = o3d.io.read_point_cloud(Original)

    # ===== 1. 비율 축소 (0.9배) =====
    scale = 0.99
    points = np.asarray(pcd.points)
    scaled_points = points * scale

    pcd_scaled = o3d.geometry.PointCloud()
    pcd_scaled.points = o3d.utility.Vector3dVector(scaled_points)

    # ===== 2. 중심점 계산 =====
    centroid_A = np.mean(points, axis=0)
    centroid_B = np.mean(scaled_points, axis=0)

    # ===== 3. 원점으로 이동 =====
    # pcd.translate(-centroid_A)
    translation = centroid_A - centroid_B
    pcd_scaled.translate(translation)


    # ===== 4. 색상 지정 =====
    # pcd.paint_uniform_color([0.7, 0.7, 0.7])   # 원본 (회색)
    # pcd_scaled.paint_uniform_color([1, 0, 0]) # 축소본 (빨강)

    # ===== 5. 시각화 =====
    # o3d.visualization.draw_geometries([pcd, pcd_scaled])
    return pcd_scaled



    ###################################################

