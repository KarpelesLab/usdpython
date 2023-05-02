#!/usr/bin/python

# Creates an animated skinned cube

from pxr import *

assetName = 'skinnedAnimation'
stage = Usd.Stage.CreateNew('assets/'+assetName+'.usd')

UsdGeom.SetStageUpAxis(stage, 'Y')

# create rootPrim, define asset metadata and set as defaultPrim
rootPrim = stage.DefinePrim('/' + assetName, 'Xform')
Usd.ModelAPI(rootPrim).SetKind('component')
rootPrim.SetAssetInfoByKey('name', assetName)
rootPrim.SetAssetInfoByKey('identifier', Sdf.AssetPath(assetName + ".usd")) 
stage.SetDefaultPrim(rootPrim)

stage.SetStartTimeCode(1)
stage.SetEndTimeCode(24)
stage.SetTimeCodesPerSecond(24)

# create mesh
UsdSkel.Root.Define(stage, '/' + assetName + '/cubeModel')

mesh = UsdGeom.Mesh.Define(stage, '/' + assetName + '/cubeModel/geometry')
mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
mesh.CreatePointsAttr([(-1.165, -1.165, 1.165), (1.165, -1.165, 1.165), (-1.165, 1.165, 1.165), (1.165, 1.165, 1.165), (-1.165, 1.165, -1.165), (1.165, 1.165, -1.165), (-1.165, -1.165, -1.165), (1.165, -1.165, -1.165)])
mesh.CreateExtentAttr(UsdGeom.PointBased(mesh).ComputeExtent(mesh.GetPointsAttr().Get()))
mesh.CreateNormalsAttr([(0,0,1), (0,1,0), (0,0,-1), (0,-1,0), (1,0,0), (-1,0,0)])
mesh.SetNormalsInterpolation(UsdGeom.Tokens.uniform)

mesh.CreateFaceVertexCountsAttr([4, 4, 4, 4, 4, 4])
mesh.CreateFaceVertexIndicesAttr([0, 1, 3, 2, 2, 3, 5, 4, 4, 5, 7, 6, 6, 7, 1, 0, 1, 7, 5, 3, 6, 0, 2, 4])


# create skin binding
skinBinding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())

# bind 4 joint indices and weights per vertex
skinBinding.CreateJointIndicesPrimvar(False, 4).Set([2,0,0,0, 2,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0, 2,0,0,0, 2,0,0,0])
skinBinding.CreateJointWeightsPrimvar(False, 4).Set([0.57,0.57,0,0, 0.57,0.57,0,0, 0.57,0.57,0,0, 0.57,0.57,0,0, 0.57,0.57,0,0, 0.57,0.57,0,0, 0.57,0.57,0,0, 0.57,0.57,0,0])

skinBinding.CreateGeomBindTransformAttr(Gf.Matrix4d(((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1))))
skinBinding.CreateSkeletonRel().AddTarget('/' + assetName + '/cubeModel/SkeletonRoot')
skinBinding.CreateAnimationSourceRel().AddTarget('/' + assetName + '/cubeModel/animation')


# create skeleton
skeleton = UsdSkel.Skeleton.Define(stage, '/' + assetName + '/cubeModel/SkeletonRoot')
skeleton.CreateJointsAttr().Set(['SkeletonRoot', 'SkeletonRoot/joint1', 'SkeletonRoot/joint2'])
skeleton.CreateBindTransformsAttr([Gf.Matrix4d(*xform) for xform in [((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1)), ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,1.0231736898422241,0,1)), ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,-0.9544228911399841,0,1))] ])
skeleton.CreateRestTransformsAttr([Gf.Matrix4d(*xform) for xform in [((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1)), ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,1.0231736898422241,0,1)), ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,-0.9544228911399841,0,1))] ])


# create skeletal animation
skelAnim = UsdSkel.Animation.Define(stage, '/' + assetName + '/cubeModel/animation')
skelAnim.CreateJointsAttr().Set(['SkeletonRoot', 'SkeletonRoot/joint1', 'SkeletonRoot/joint2'])

translateAttr = skelAnim.CreateTranslationsAttr()
for index, translations in enumerate([ [(0, 0.9395472, 0), (0, -0.26373994, 0), (0, -1, 0)],[(0, 0.9395472, 0), (0, 1.695752, 0), (0, -1, 0)],[(0, 2.116855, 0), (0, 3.0938458, 0), (0, -1, 0)],[(0, 3.4363647, 0), (0, 2.7743738, 0), (0, -1, 0)],[(0, 4.597689, 0), (0, 2.0715356, 0), (0, -1, 0)],[(0, 5.575705, 0), (0, 1.3686974, 0), (0, -1, 0)],[(0, 6.3150945, 0), (0, 1.0492256, 0), (0, -1, 0)],[(0, 6.8236537, 0), (0, 1.0853274, 0), (0, -1, 0)],[(0, 7.1834054, 0), (0, 1.1647512, 0), (0, -1, 0)],[(0, 7.43269, 0), (0, 1.2441751, 0), (0, -1, 0)],[(0, 7.6263967, 0), (0, 1.2802768, 0), (0, -1, 0)],[(0, 7.7827907, 0), (0, 1.2582484, 0), (0, -1, 0)],[(0, 7.8870816, 0), (0, 1.2057197, 0), (0, -1, 0)],[(0, 7.949236, 0), (0, 1.1430238, 0), (0, -1, 0)],[(0, 7.97922, 0), (0, 1.0904951, 0), (0, -1, 0)],[(0, 7.987, 0), (0, 1.0684668, 0), (0, -1, 0)],[(0, 7.987, 0), (0, 1.0231737, 0), (0, -0.9544229, 0)],[(0, 7.884441, 0), (0, 1.2645316, 0), (0, -0.96623915, 0)],[(0, 7.536293, 0), (0, 1.8358042, 0), (0, -0.98818374, 0)],[(0, 6.881852, 0), (0, 2.5077906, 0), (0, -1, 0)],[(0, 5.5482335, 0), (0, 3.6069436, 0), (0, -0.9143012, 0)],[(0, 3.8478897, 0), (0, 4.424425, 0), (0, -1, 0)],[(0, 2.1980343, 0), (0, 4.0256877, 0), (0, -1, 0)],[(0, 0.9395472, 0), (0, 4.188043, 0), (0, -1, 0)] ]):
    translateAttr.Set(translations, Usd.TimeCode(index + 1))

scaleAttr = skelAnim.CreateScalesAttr()
for index, scales in enumerate([ [(1, 1, 1), (1.18066, 1, 1.18066), (2.49414, 1, 2.49414)],[(1, 1, 1), (0.635742, 1, 0.635742), (1.12012, 1, 1.12012)],[(1, 1, 1), (0.0630493, 1, 0.0630493), (1.02344, 1, 1.02344)],[(1, 1, 1), (0.287598, 1, 0.287598), (1.00977, 1, 1.00977)],[(1, 1, 1), (0.781738, 1, 0.781738), (1.00293, 1, 1.00293)],[(1, 1, 1), (1.27637, 1, 1.27637), (1, 1, 1)],[(1, 1, 1), (1.50098, 1, 1.50098), (1, 1, 1)],[(1, 1, 1), (1.39453, 1, 1.39453), (1, 1, 1)],[(1, 1, 1), (1.16113, 1, 1.16113), (1, 1, 1)],[(1, 1, 1), (0.928223, 1, 0.928223), (1, 1, 1)],[(1, 1, 1), (0.822266, 1, 0.822266), (1, 1, 1)],[(1, 1, 1), (0.84082, 1, 0.84082), (1, 1, 1)],[(1, 1, 1), (0.884766, 1, 0.884766), (1, 1, 1)],[(1, 1, 1), (0.9375, 1, 0.9375), (1, 1, 1)],[(1, 1, 1), (0.981445, 1, 0.981445), (1, 1, 1)],[(1, 1, 1), (1, 1, 1), (1, 1, 1)],[(1, 1, 1), (1, 1, 1), (1, 1, 1)],[(1, 1, 1), (0.992676, 1, 0.992676), (0.953125, 1, 0.953125)],[(1, 1, 1), (0.941895, 1, 0.941895), (0.865723, 1, 0.865723)],[(1, 1, 1), (0.803223, 1, 0.803223), (0.818848, 1, 0.818848)],[(1, 1, 1), (0.169434, 1, 0.169434), (0.845703, 1, 0.845703)],[(1, 1, 1), (0.0844116, 1, 0.0844116), (0.967773, 1, 0.967773)],[(1, 1, 1), (0.072998, 1, 0.072998), (0.68457, 1, 0.68457)],[(1, 1, 1), (0.014122, 1, 0.014122), (1.05176, 1, 1.05176)] ]):
    scaleAttr.Set(scales, Usd.TimeCode(index + 1))

rotateAttr = skelAnim.CreateRotationsAttr()
for index, rotations in enumerate([ [(1,0,0,0), (1,0,0,0), (1,0,0,0)], [(0.99785894,0,0.065403126,0), (1,0,0,0), (1,0,0,0)], [(0.9914449,0,0.13052619,0), (1,0,0,0), (1,0,0,0)], [(0.98078525,0,0.19509032,0), (1,0,0,0), (1,0,0,0)], [(0.9659258,0,0.25881904,0), (1,0,0,0), (1,0,0,0)], [(0.9469301,0,0.32143947,0), (1,0,0,0), (1,0,0,0)], [(0.9238795,0,0.38268343,0), (1,0,0,0), (1,0,0,0)], [(0.89687276,0,0.4422887,0), (1,0,0,0), (1,0,0,0)], [(0.8660254,0,0.5,0), (1,0,0,0), (1,0,0,0)], [(0.8314696,0,0.55557024,0), (1,0,0,0), (1,0,0,0)], [(0.7933533,0,0.6087614,0), (1,0,0,0), (1,0,0,0)], [(0.7518398,0,0.6593458,0), (1,0,0,0), (1,0,0,0)], [(0.70710677,0,0.70710677,0), (1,0,0,0), (1,0,0,0)], [(0.6593458,0,0.7518398,0), (1,0,0,0), (1,0,0,0)], [(0.6087614,0,0.7933533,0), (1,0,0,0), (1,0,0,0)], [(0.55557024,0,0.8314696,0), (1,0,0,0), (1,0,0,0)], [(0.5,0,0.8660254,0), (1,0,0,0), (1,0,0,0)], [(0.4422887,0,0.89687276,0), (1,0,0,0), (1,0,0,0)], [(0.38268343,0,0.9238795,0), (1,0,0,0), (1,0,0,0)], [(0.32143947,0,0.9469301,0), (1,0,0,0), (1,0,0,0)], [(0.25881904,0,0.9659258,0), (1,0,0,0), (1,0,0,0)], [(0.19509032,0,0.98078525,0), (1,0,0,0), (1,0,0,0)], [(0.13052619,0,0.9914449,0), (1,0,0,0), (1,0,0,0)], [(0.065403126,0,0.99785894,0), (1,0,0,0), (1,0,0,0)] ]):
    rotateAttr.Set(Vt.QuatfArray([Gf.Quatf(*x) for x in rotations]), Usd.TimeCode(index + 1))


# print out contents of usd file
print(stage.GetRootLayer().ExportToString())
stage.Save()

# construct .usdz archive from the .usdc file
UsdUtils.CreateNewARKitUsdzPackage('assets/'+assetName+'.usd', 'assets/'+assetName+'.usdz')
