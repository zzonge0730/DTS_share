import numpy as np
from sklearn.decomposition import PCA
from scipy.spatial import ConvexHull
import open3d as o3d

def order_boundary_points_3d(data):
    points = np.asarray(data.points)

    # 1. PCA로 평면 찾기
    pca = PCA(n_components=2)
    projected = pca.fit_transform(points)  # 3D -> 2D 투영

    # 2. Convex Hull로 바깥 경계 순서 구하기
    hull = ConvexHull(projected)
    ordered_2d = projected[hull.vertices]

    # 3. 2D -> 3D 복원
    ordered_3d = pca.inverse_transform(ordered_2d)

    data.points = o3d.utility.Vector3dVector(ordered_3d)

    return data