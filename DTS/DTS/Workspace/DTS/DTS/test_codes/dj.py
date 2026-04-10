import trimesh
import numpy as np

def trim_stl_boundary(stl_path, trim_distance, output_path):
    """
    STL 파일의 외곽선에서 지정된 거리만큼 삼각형을 삭제합니다.

    :param stl_path: 입력 STL 파일 경로
    :param trim_distance: 삭제할 외곽선으로부터의 거리 (mm)
    :param output_path: 수정된 STL 파일 저장 경로
    """
    try:
        # 1. STL 파일 불러오기
        mesh = trimesh.load_mesh(stl_path)
        
        # 2. 외곽선 모서리 찾기
        boundary_edges = mesh.edges_unique[trimesh.grouping.group_rows(mesh.face_adjacency, require_count=1)]
        
        # 3. 외곽선 모서리의 모든 꼭짓점 찾기
        boundary_vertices = np.unique(boundary_edges.flatten())
        
        # 4. 각 삼각형의 꼭짓점들과 외곽선 꼭짓점들 사이의 최소 거리 계산
        # 이 과정은 계산량이 많으므로, KD-Tree를 사용하여 효율성을 높일 수 있습니다.
        boundary_tree = trimesh.parent.Geometry.kdtree(boundary_vertices)
        
        # 5. 삭제할 삼각형 인덱스 식별
        # 외곽선으로부터의 거리가 trim_distance보다 작은 모든 삼각형을 찾습니다.
        faces_to_delete = []
        for face_index, face_vertices in enumerate(mesh.faces):
            # 삼각형의 각 꼭짓점과 외곽선까지의 최소 거리 계산
            distances = boundary_tree.query(mesh.vertices[face_vertices])[0]
            if np.min(distances) < trim_distance:
                faces_to_delete.append(face_index)

        # 6. 삼각형 삭제 및 메시 재구성
        # 삭제할 삼각형의 마스크를 생성하여 메시를 재구성합니다.
        faces_mask = np.ones(len(mesh.faces), dtype=bool)
        faces_mask[faces_to_delete] = False
        new_mesh = mesh.submesh([faces_mask], append=True)
        
        # 7. 새로운 STL 파일 저장
        new_mesh.export(output_path)
        print(f"STL 파일이 성공적으로 처리되어 {output_path}에 저장되었습니다.")

    except Exception as e:
        print(f"오류가 발생했습니다: {e}")

# 사용 예시
trim_stl_boundary("5mm.stl", 5.0, "output.stl")