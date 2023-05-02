#!/usr/bin/python

# Creates a cube mesh and assigns it a simple PBR material 

from pxr import *

assetName = 'simpleMaterial'
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
mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
mesh.CreatePointsAttr([(-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5)])
mesh.CreateExtentAttr(UsdGeom.PointBased(mesh).ComputeExtent(mesh.GetPointsAttr().Get()))
mesh.CreateNormalsAttr([(0,0,1), (0,1,0), (0,0,-1), (0,-1,0), (1,0,0), (-1,0,0)])
mesh.SetNormalsInterpolation(UsdGeom.Tokens.uniform)

mesh.CreateFaceVertexCountsAttr([4, 4, 4, 4, 4, 4])
mesh.CreateFaceVertexIndicesAttr([0, 1, 3, 2, 2, 3, 5, 4, 4, 5, 7, 6, 6, 7, 1, 0, 1, 7, 5, 3, 6, 0, 2, 4])

# create PBR material
material = UsdShade.Material.Define(stage, '/' + assetName + '/Materials/cubeMaterial')
pbrShader = UsdShade.Shader.Define(stage, '/' + assetName + '/Materials/cubeMaterial/PBRShader')

pbrShader.CreateIdAttr('UsdPreviewSurface')
pbrShader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.84, 0.65, 0.65))
pbrShader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(0.9)
pbrShader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(0.2)

material.CreateSurfaceOutput().ConnectToSource(pbrShader, 'surface')

# bind material to mesh
UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(material)

print(stage.GetRootLayer().ExportToString())
stage.Save()

# construct .usdz archive from the .usdc file
UsdUtils.CreateNewARKitUsdzPackage('assets/'+assetName+'.usd', 'assets/'+assetName+'.usdz')
