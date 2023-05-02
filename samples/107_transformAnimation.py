#!/usr/bin/python

# Builds a scene graph of several objects and sets (animated) translate, rotate, and scale transforms

from pxr import *

assetName = 'tansformAnimation'
stage = Usd.Stage.CreateNew('assets/'+assetName+'.usd')

UsdGeom.SetStageUpAxis(stage, 'Y')

# create rootPrim, define asset metadata and set as defaultPrim
rootPrim = stage.DefinePrim('/' + assetName, 'Xform')
Usd.ModelAPI(rootPrim).SetKind('component')
rootPrim.SetAssetInfoByKey('name', assetName)
rootPrim.SetAssetInfoByKey('identifier', Sdf.AssetPath(assetName + ".usd")) 
stage.SetDefaultPrim(rootPrim)

stage.SetStartTimeCode(0)
stage.SetEndTimeCode(89)
stage.SetTimeCodesPerSecond(24)

# set static transform, in the common translate/rotate/scale decomposition
stage.DefinePrim('/' + assetName + '/Geom', 'Scope')
cone = UsdGeom.Cone.Define(stage, '/' + assetName + '/Geom/cone')
cone.GetAxisAttr().Set("Y")
cone.AddTranslateOp().Set((0,0,0))
cone.AddRotateXYZOp().Set((0,0,0))
cone.AddScaleOp().Set((1.2,2.0,1.2))

# parent two sphere objects under a common, rotating transform node
xform1 = UsdGeom.Xform.Define(stage, '/' + assetName + '/Geom/xform1')
xform1.AddTranslateOp().Set((0,3,0))
xform1RotateOp = xform1.AddRotateYOp()
for index, value in enumerate(range(90)):
	xform1RotateOp.Set(4*value, Usd.TimeCode(index))

sphere1 = UsdGeom.Sphere.Define(stage, '/' + assetName + '/Geom/xform1/sphere1')
sphere1.AddTranslateOp().Set((2,0,0))

sphere2 = UsdGeom.Sphere.Define(stage, '/' + assetName + '/Geom/xform1/sphere2')
sphere2.AddTranslateOp().Set((-2,0,0))

# print out contents of usd file
print(stage.GetRootLayer().ExportToString())
stage.Save()

# construct .usdz archive from the .usdc file
UsdUtils.CreateNewARKitUsdzPackage('assets/'+assetName+'.usd', 'assets/'+assetName+'.usdz')
