import open3d as o3d
import numpy as np

# PLY 파일 읽기
pcd = o3d.io.read_point_cloud("Edge_with_normal.ply")
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
o3d.visualization.draw_geometries(geoms)
# o3d.visualization.draw_geometries([pcd, pcd_edged])
