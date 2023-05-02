#!/usr/bin/python

# Creates a cube mesh with two mesh groups and assigns each a separate material

from pxr import *

assetName = 'meshGroups'
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

# create mesh group with rose material
roseMeshGroup = UsdShade.MaterialBindingAPI.CreateMaterialBindSubset(UsdShade.MaterialBindingAPI(mesh.GetPrim()), 'roseMeshGroup', Vt.IntArray([0,2,4,5]))

roseMaterial = UsdShade.Material.Define(stage, '/' + assetName + '/Materials/cubeMaterialRose')
rosePBRShader = UsdShade.Shader.Define(stage, '/' + assetName + '/Materials/cubeMaterialRose/PBRShader')

rosePBRShader.CreateIdAttr('UsdPreviewSurface')
rosePBRShader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.84, 0.65, 0.65))
rosePBRShader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(0.9)
rosePBRShader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(0.2)
roseMaterial.CreateSurfaceOutput().ConnectToSource(rosePBRShader, 'surface')

UsdShade.MaterialBindingAPI(roseMeshGroup.GetPrim()).Bind(roseMaterial)

# create mesh group with teal material
tealMeshGroup = UsdShade.MaterialBindingAPI.CreateMaterialBindSubset(UsdShade.MaterialBindingAPI(mesh.GetPrim()), 'tealMeshGroup', Vt.IntArray([1,3]))

tealMaterial = UsdShade.Material.Define(stage, '/' + assetName + '/Materials/cubeMaterialTeal')
tealPBRShader = UsdShade.Shader.Define(stage, '/' + assetName + '/Materials/cubeMaterialTeal/PBRShader')

tealPBRShader.CreateIdAttr('UsdPreviewSurface')
tealPBRShader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.52, 0.62, 0.64))
tealPBRShader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(0.9)
tealPBRShader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(0.2)
tealMaterial.CreateSurfaceOutput().ConnectToSource(tealPBRShader, 'surface')

UsdShade.MaterialBindingAPI(tealMeshGroup.GetPrim()).Bind(tealMaterial)

print(stage.GetRootLayer().ExportToString())
stage.Save()

# construct .usdz archive from the .usdc file
UsdUtils.CreateNewARKitUsdzPackage('assets/'+assetName+'.usd', 'assets/'+assetName+'.usdz')
