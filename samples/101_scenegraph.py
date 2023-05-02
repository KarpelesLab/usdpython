#!/usr/bin/python

# Creates a scene graph

from pxr import *

assetName = 'scenegraph'
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
sphere.AddTranslateOp().Set((4,0,0))

# print out contents of usd file
print(stage.GetRootLayer().ExportToString())
stage.Save()

# construct .usdz archive from the .usdc file
UsdUtils.CreateNewARKitUsdzPackage('assets/'+assetName+'.usd', 'assets/'+assetName+'.usdz')
