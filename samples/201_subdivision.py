#!/usr/bin/python

# Creates a subdivided cube mesh

from pxr import *

assetName = 'subdivision'
stage = Usd.Stage.CreateNew('assets/'+assetName+'.usd')

UsdGeom.SetStageUpAxis(stage, 'Y')

# create rootPrim, define asset metadata and set as defaultPrim
rootPrim = stage.DefinePrim('/' + assetName, 'Xform')
Usd.ModelAPI(rootPrim).SetKind('component')
rootPrim.SetAssetInfoByKey('name', assetName)
rootPrim.SetAssetInfoByKey('identifier', Sdf.AssetPath(assetName + ".usd")) 
stage.SetDefaultPrim(rootPrim)

# create mesh
stage.DefinePrim('/' + assetName + '/Geom', 'Scope')
mesh = UsdGeom.Mesh.Define(stage, '/' + assetName + '/Geom/cube')
mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.catmullClark)
mesh.CreatePointsAttr([(-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5)])
mesh.CreateExtentAttr(UsdGeom.PointBased(mesh).ComputeExtent(mesh.GetPointsAttr().Get())) # set (static) bounding box for framing and frustum culling
mesh.CreateFaceVertexCountsAttr([4, 4, 4, 4, 4, 4]) # per-face vertex count: cube consists of 6 faces with 4 vertices each
mesh.CreateFaceVertexIndicesAttr([0,1,3,2, 2,3,5,4, 4,5,7,6, 6,7,1,0, 1,7,5,3, 6,0,2,4]) # per-face vertex indices

# create edges creases for mesh
mesh.CreateCreaseLengthsAttr([2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2])
mesh.CreateCreaseIndicesAttr([0, 1, 2, 3, 4, 5, 6, 7, 0, 2, 1, 3, 2, 4, 3, 5, 4, 6, 5, 7, 6, 0, 7, 1])
mesh.CreateCreaseSharpnessesAttr([4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4])

# print out contents of usd file
print(stage.GetRootLayer().ExportToString())
stage.Save()

# construct .usdz archive from the .usdc file
UsdUtils.CreateNewARKitUsdzPackage('assets/'+assetName+'.usd', 'assets/'+assetName+'.usdz')
