#!/usr/bin/python

# Creates a scene that references a simple scene graph with overrides

from pxr import *

assetName = 'cubeSphere'
stage = Usd.Stage.CreateNew('assets/'+assetName+'.usd')

UsdGeom.SetStageUpAxis(stage, 'Y')

# create rootPrim, define asset metadata and set as defaultPrim
rootPrim = stage.DefinePrim('/' + assetName, 'Xform')
Usd.ModelAPI(rootPrim).SetKind('component')
rootPrim.SetAssetInfoByKey('name', assetName)
rootPrim.SetAssetInfoByKey('identifier', Sdf.AssetPath(assetName + ".usd")) 
stage.SetDefaultPrim(rootPrim)

# create cube
stage.DefinePrim('/' + assetName + '/Geom', 'Scope')
cube = UsdGeom.Cube.Define(stage, '/' + assetName + '/Geom/cube')

# create sphere
sphere = UsdGeom.Sphere.Define(stage, '/' + assetName + '/Geom/sphere')
sphere.AddTranslateOp().Set((0, 2, 0))

# create PBR material
roseMaterial = UsdShade.Material.Define(stage, '/' + assetName + '/Materials/roseGoldMaterial')
rosePbrShader = UsdShade.Shader.Define(stage, '/' + assetName + '/Materials/roseGoldMaterial/PBRShader')

rosePbrShader.CreateIdAttr('UsdPreviewSurface')
rosePbrShader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.84, 0.65, 0.65))
rosePbrShader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(0.9)
rosePbrShader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(0.2)

roseMaterial.CreateSurfaceOutput().ConnectToSource(rosePbrShader, 'surface')

# bind material to mesh
UsdShade.MaterialBindingAPI(cube.GetPrim()).Bind(roseMaterial)

# create PBR material
chromeMaterial = UsdShade.Material.Define(stage, '/' + assetName + '/Materials/chromeMaterial')
chromePbrShader = UsdShade.Shader.Define(stage, '/' + assetName + '/Materials/chromeMaterial/PBRShader')

chromePbrShader.CreateIdAttr('UsdPreviewSurface')
chromePbrShader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set((1.0, 1.0, 1.0))
chromePbrShader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(1.0)
chromePbrShader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(0.0)

chromeMaterial.CreateSurfaceOutput().ConnectToSource(chromePbrShader, 'surface')

UsdShade.MaterialBindingAPI(sphere.GetPrim()).Bind(chromeMaterial)
# print out contents of usd file
print(stage.GetRootLayer().ExportToString())
stage.Save()

# construct .usdz archive from the .usdc file
UsdUtils.CreateNewARKitUsdzPackage('assets/'+assetName+'.usd', 'assets/'+assetName+'.usdz')

# construct referencing scene
refAssetName = 'references'
refStage = Usd.Stage.CreateNew('assets/'+refAssetName+'.usd')

UsdGeom.SetStageUpAxis(refStage, 'Y')

# create rootPrim, define asset metadata and set as defaultPrim
refRootPrim = refStage.DefinePrim('/' + refAssetName, 'Xform')
Usd.ModelAPI(rootPrim).SetKind('assembly')
refRootPrim.SetAssetInfoByKey('name', refAssetName)
refRootPrim.SetAssetInfoByKey('identifier', Sdf.AssetPath(refAssetName + ".usd")) 
refStage.SetDefaultPrim(refRootPrim)

# create scenePrim that reference CubeSphere.usd
scenePrim2 = refStage.DefinePrim('/' + refAssetName + '/Scene2', 'Xform')
scenePrim2.GetReferences().AddReference('cubeSphere.usd')
UsdGeom.Xform(scenePrim2).AddTranslateOp().Set((-1.5, 0, 0))
# override diffuseColor of material
overridePrim = refStage.OverridePrim('/' + refAssetName + '/Scene2/Materials/roseGoldMaterial/PBRShader')
UsdShade.Shader(overridePrim).GetInput('diffuseColor').Set(Gf.Vec3f(0.52, 0.62, 0.64))

# create scenePrim that reference CubeSphere.usd
scenePrim3 = refStage.DefinePrim('/' + refAssetName + '/Scene3', 'Xform')
scenePrim3.GetReferences().AddReference('cubeSphere.usd')
UsdGeom.Xform(scenePrim3).AddTranslateOp().Set((1.5, 0, 0))

overridePrim3 = refStage.OverridePrim('/' + refAssetName + '/Scene3/Geom/sphere')
overridePrim3.SetActive(False)
print(refStage.GetRootLayer().ExportToString())
refStage.Save()

# construct .usdz archive from the .usdc file
UsdUtils.CreateNewARKitUsdzPackage('assets/'+refAssetName+'.usd', 'assets/'+refAssetName+'.usdz')

