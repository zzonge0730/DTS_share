from stl import mesh

your_mesh = mesh.Mesh.from_file("Product_0812.stl")

# 삼각형 개수
print(len(your_mesh.normals))

# 각 삼각형의 법선 출력
for i, normal in enumerate(your_mesh.normals[:5]):  # 앞 5개만
    print(f"Triangle {i}: Normal = {normal}")
