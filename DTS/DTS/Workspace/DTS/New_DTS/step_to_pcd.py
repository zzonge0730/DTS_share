from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopoDS import topods_Face
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepTools import breptools_UVBounds
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
import numpy as np

# STEP 파일 불러오기
reader = STEPControl_Reader()
reader.ReadFile("CAD(GT).STP")
reader.TransferRoots()
shape = reader.OneShape()

# Face에서 샘플링
points = []
exp = TopExp_Explorer(shape, TopAbs_FACE)
while exp.More():
    face = topods_Face(exp.Current())
    surf = BRepAdaptor_Surface(face)
    umin, umax, vmin, vmax = breptools_UVBounds(face)

    for i in np.linspace(umin, umax, 50):  # u 방향 50개
        for j in np.linspace(vmin, vmax, 50):  # v 방향 50개
            p = surf.Value(i, j)  # (u,v) → 3D 좌표
            points.append((p.X(), p.Y(), p.Z()))

    exp.Next()

print("Extracted", len(points), "points")
