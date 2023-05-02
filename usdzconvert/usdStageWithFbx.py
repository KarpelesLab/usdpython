from pxr import *
import os, os.path
import numpy
import re
import usdUtils


import imp

usdStageWithFbxLoaded = True
try:
    imp.find_module('fbx')
    import fbx
except ImportError:
    usdUtils.printError("Failed to import fbx module. Please install FBX Python bindings from http://www.autodesk.com/fbx and add path to FBX Python SDK to your PYTHONPATH")
    usdStageWithFbxLoaded = False


class ConvertError(Exception):
    pass


def printErrorAndExit(message):
    usdUtils.printError(message)
    raise ConvertError()


def GfMatrix4dWithFbxMatrix(m):
    return Gf.Matrix4d(
        m[0][0], m[0][1], m[0][2], m[0][3],
        m[1][0], m[1][1], m[1][2], m[1][3],
        m[2][0], m[2][1], m[2][2], m[2][3],
        m[3][0], m[3][1], m[3][2], m[3][3])


def getFbxNodeTransforms(fbxNode):
    return GfMatrix4dWithFbxMatrix(fbxNode.EvaluateLocalTransform())


def getFbxNodeGeometricTransform(fbxNode):
    # geometry transform is an additional transform for geometry
    # it is relative to the node transform
    # this transform is not distributing to the children nodes in scene graph
    translation = fbxNode.GetGeometricTranslation(fbx.FbxNode.eSourcePivot)
    rotation = fbxNode.GetGeometricRotation(fbx.FbxNode.eSourcePivot)
    scale = fbxNode.GetGeometricScaling(fbx.FbxNode.eSourcePivot)
    return fbx.FbxAMatrix(translation, rotation, scale)



class FbxNodeManager(usdUtils.NodeManager):
    def __init__(self, value=None):
        usdUtils.NodeManager.__init__(self)


    def overrideGetName(self, fbxNode):
        return usdUtils.makeValidIdentifier(fbxNode.GetName().split(":")[-1])


    def overrideGetChildren(self, fbxNode):
        children = []
        for childIdx in xrange(fbxNode.GetChildCount()):
            children.append(fbxNode.GetChild(childIdx))
        return children


    def overrideGetLocalTransformGfMatrix4d(self, fbxNode):
        return GfMatrix4dWithFbxMatrix(fbxNode.EvaluateLocalTransform())


    def overrideGetWorldTransformGfMatrix4d(self, fbxNode):
        return GfMatrix4dWithFbxMatrix(fbxNode.EvaluateGlobalTransform())


    def overrideGetParent(self, fbxNode):
        return fbxNode.GetParent()



class FbxConverter:
    def __init__(self, fbxPath, usdPath, legacyModifier, copyTextures, verbose):
        self.verbose = verbose
        self.legacyModifier = legacyModifier
        self.copyTextures = copyTextures
        self.asset = usdUtils.Asset(usdPath)
        self.usdStage = None
        self.usdMaterials = {}
        self.nodeId = 0
        self.nodePaths = {}
        self.fbxSkinToSkin = {}
        self.startAnimationTime = 0
        self.stopAnimationTime = 0
        self.skeletonByNode = {} # collect skinned mesh to construct later
        self.copiedTextures = {} # avoid copying textures more then once

        self.extent = [[], []]

        self.fbxScene = None

        filenameFull = fbxPath.split('/')[-1]
        self.srcFolder = fbxPath[:len(fbxPath)-len(filenameFull)]

        filenameFull = usdPath.split('/')[-1]
        self.dstFolder = usdPath[:len(usdPath)-len(filenameFull)]

        self.loadFbxScene(fbxPath)
        self.fps = fbx.FbxTime.GetFrameRate(fbx.FbxTime.GetGlobalTimeMode())
        self.asset.setFPS(self.fps)

        self.nodeManager = FbxNodeManager()
        self.skinning = usdUtils.Skinning(self.nodeManager)

    
    def loadFbxScene(self, fbxPath):
        fbxManager = fbx.FbxManager.Create()
        if not fbxManager:
            printErrorAndExit("failed to create FBX manager object")

        self.fbxManager = fbxManager

        fbxIOSettings = fbx.FbxIOSettings.Create(fbxManager, fbx.IOSROOT)
        fbxManager.SetIOSettings(fbxIOSettings)

        fbxImporter = fbx.FbxImporter.Create(fbxManager, "")
        result = fbxImporter.Initialize(fbxPath, -1, fbxManager.GetIOSettings())
        if not result:
            printErrorAndExit("failed to initialize FbxImporter object")

        if fbxImporter.IsFBX():
            fbxManager.GetIOSettings().SetBoolProp(fbx.EXP_FBX_MATERIAL, True)
            fbxManager.GetIOSettings().SetBoolProp(fbx.EXP_FBX_TEXTURE, True)
            fbxManager.GetIOSettings().SetBoolProp(fbx.EXP_FBX_EMBEDDED, True)
            fbxManager.GetIOSettings().SetBoolProp(fbx.EXP_FBX_SHAPE, True)
            fbxManager.GetIOSettings().SetBoolProp(fbx.EXP_FBX_GOBO, True)
            fbxManager.GetIOSettings().SetBoolProp(fbx.EXP_FBX_ANIMATION, True)
            fbxManager.GetIOSettings().SetBoolProp(fbx.EXP_FBX_GLOBAL_SETTINGS, True)

        self.fbxScene = fbx.FbxScene.Create(fbxManager, "")
        result = fbxImporter.Import(self.fbxScene)
        fbxImporter.Destroy()
        if not result:
            printErrorAndExit("failed to load FBX scene")


    def getTextureProperties(self, materialProperty):
        if materialProperty.GetSrcObjectCount(fbx.FbxCriteria.ObjectType(fbx.FbxFileTexture.ClassId)) > 0:
            fbxFileTexture = materialProperty.GetSrcObject(fbx.FbxCriteria.ObjectType(fbx.FbxFileTexture.ClassId), 0)
            texCoordSet = 'st'
            if fbxFileTexture.UVSet is not None:
                texCoordSet = str(fbxFileTexture.UVSet.Get())
                if texCoordSet == '' or texCoordSet == 'default':
                    texCoordSet = 'st'
                else:
                    texCoordSet = usdUtils.makeValidIdentifier(texCoordSet)
            wrapS = 'repeat'
            wrapT = 'repeat'
            if fbxFileTexture.GetWrapModeU() == fbx.FbxTexture.eClamp:
                wrapS = 'clamp'
            if fbxFileTexture.GetWrapModeV() == fbx.FbxTexture.eClamp:
                wrapT = 'clamp'
            return fbxFileTexture.GetFileName(), texCoordSet, wrapS, wrapT
        elif materialProperty.GetSrcObjectCount(fbx.FbxCriteria.ObjectType(fbx.FbxLayeredTexture.ClassId)) > 0:
            pass
        return '', 'st', 'repeat', 'repeat'


    def processMaterialProperty(self, input, propertyName, property, factorProperty, channels, material, fbxMaterial):
        value = None
        if property is not None:
            if channels == 'rgb':
                value = [property.Get()[0], property.Get()[1], property.Get()[2]]
            else:
                if input == usdUtils.InputName.opacity:
                    value = 1.0 - property.Get()[0]
                else:
                    value = float(property.Get()[0])
        factor = float(factorProperty.Get()) if factorProperty is not None else None

        srcTextureFilename = '' # source texture filename on drive
        textureFilename = '' # valid for USD
        materialProperty = fbxMaterial.FindProperty(propertyName)

        if materialProperty.IsValid():
            srcTextureFilename, texCoordSet, wrapS, wrapT = self.getTextureProperties(materialProperty)
            srcTextureFilename = usdUtils.resolvePath(srcTextureFilename, self.srcFolder)
            textureFilename = usdUtils.makeValidPath(srcTextureFilename)

        if  textureFilename != '' and (self.copyTextures or srcTextureFilename != textureFilename):
            if srcTextureFilename in self.copiedTextures:
                textureFilename = self.copiedTextures[srcTextureFilename]
            else:
                newTextureFilename = 'textures/' + os.path.basename(textureFilename)

                # do not rewrite the texture with same basename
                subfolderIdx = 0
                while newTextureFilename in self.copiedTextures.values():
                    newTextureFilename = 'textures/' + str(subfolderIdx) + '/' + os.path.basename(textureFilename)
                    subfolderIdx += 1

                usdUtils.copy(srcTextureFilename, self.dstFolder + newTextureFilename, self.verbose)
                self.copiedTextures[srcTextureFilename] = newTextureFilename
                textureFilename = newTextureFilename

        if textureFilename != '':
            scale = None
            if factor is not None:
                if channels == 'rgb':
                    scale = [factor, factor, factor]
                else:
                    scale = factor
            material.inputs[input] = usdUtils.Map(channels, textureFilename, value, texCoordSet, wrapS, wrapT, scale)
        else:
            if value is not None:
                material.inputs[input] = value


    def processMaterials(self):
        for i in range(self.fbxScene.GetMaterialCount()):
            fbxMaterial = self.fbxScene.GetMaterial(i)
            material = usdUtils.Material(fbxMaterial.GetName().split(":")[-1])
            normalMap = fbxMaterial.NormalMap if hasattr(fbxMaterial, 'NormalMap') else None
            self.processMaterialProperty(usdUtils.InputName.normal, fbx.FbxSurfaceMaterial.sNormalMap, normalMap, None, 'rgb', material, fbxMaterial)
            diffuse = fbxMaterial.Diffuse if hasattr(fbxMaterial, 'Diffuse') else None
            diffuseFactor = fbxMaterial.DiffuseFactor if hasattr(fbxMaterial, 'DiffuseFactor') else None
            self.processMaterialProperty(usdUtils.InputName.diffuseColor, fbx.FbxSurfaceMaterial.sDiffuse, diffuse, diffuseFactor, 'rgb', material, fbxMaterial)

            transparentColor = fbxMaterial.TransparentColor if hasattr(fbxMaterial, 'TransparentColor') else None
            transparencyFactor = fbxMaterial.TransparencyFactor if hasattr(fbxMaterial, 'TransparencyFactor') else None
            self.processMaterialProperty(usdUtils.InputName.opacity, fbx.FbxSurfaceMaterial.sTransparentColor, transparentColor, transparencyFactor, 'a', material, fbxMaterial)

            emissive = fbxMaterial.Emissive if hasattr(fbxMaterial, 'Emissive') else None
            emissiveFactor = fbxMaterial.EmissiveFactor if hasattr(fbxMaterial, 'EmissiveFactor') else None
            self.processMaterialProperty(usdUtils.InputName.emissiveColor, fbx.FbxSurfaceMaterial.sEmissive, emissive, emissiveFactor, 'rgb', material, fbxMaterial)

            ambient = fbxMaterial.Ambient if hasattr(fbxMaterial, 'Ambient') else None
            ambientFactor = fbxMaterial.AmbientFactor if hasattr(fbxMaterial, 'AmbientFactor') else None
            self.processMaterialProperty(usdUtils.InputName.occlusion, fbx.FbxSurfaceMaterial.sAmbient, ambient, ambientFactor, 'r', material, fbxMaterial)
            # 'metallic', 'roughness' ?
            usdMaterial = material.makeUsdMaterial(self.asset)

            if self.legacyModifier is not None:
                self.legacyModifier.opacityAndDiffuseOneTexture(material)

            self.usdMaterials[fbxMaterial.GetName()] = usdMaterial


    def prepareAnimations(self):
        animStacksCount = self.fbxScene.GetSrcObjectCount(fbx.FbxCriteria.ObjectType(fbx.FbxAnimStack.ClassId))
        if animStacksCount < 1:
            if self.verbose:
                print 'No animation found'
            return

        fbxAnimStack = self.fbxScene.GetSrcObject(fbx.FbxCriteria.ObjectType(fbx.FbxAnimStack.ClassId), 0)
        timeSpan = fbxAnimStack.GetLocalTimeSpan()
        self.startAnimationTime = timeSpan.GetStart().GetSecondDouble()
        self.stopAnimationTime = timeSpan.GetStop().GetSecondDouble()
        self.asset.extentTime(self.startAnimationTime)
        self.asset.extentTime(self.stopAnimationTime)


    def processControlPoints(self, fbxMesh, usdMesh):
        points = [Gf.Vec3f(p[0], p[1], p[2]) for p in fbxMesh.GetControlPoints()]
        extent = Gf.Range3f()
        for point in points:
            extent.UnionWith(point)

        usdMesh.CreatePointsAttr(points)
        usdMesh.CreateExtentAttr([Gf.Vec3f(extent.GetMin()), Gf.Vec3f(extent.GetMax())])

        if not any(self.extent):
            self.extent[0] = extent.GetMin()
            self.extent[1] = extent.GetMax()
        else:
            for i in range(3):
                self.extent[0][i] = min(self.extent[0][i], extent.GetMin()[i])
                self.extent[1][i] = max(self.extent[1][i], extent.GetMax()[i])


    def getVec3fArrayWithLayerElements(self, elements, fbxLayerElements):
        elementsArray = fbxLayerElements.GetDirectArray()
        for i in xrange(elementsArray.GetCount()):
            element = elementsArray.GetAt(i)
            elements.append(Gf.Vec3f(element[0], element[1], element[2]))


    def getIndicesWithLayerElements(self, fbxMesh, fbxLayerElements):
        mappingMode = fbxLayerElements.GetMappingMode()
        referenceMode = fbxLayerElements.GetReferenceMode()
        indexToDirect = (
            referenceMode == fbx.FbxLayerElement.eIndexToDirect or
            referenceMode == fbx.FbxLayerElement.eIndex)

        indices = []
        if mappingMode == fbx.FbxLayerElement.eByControlPoint:
            if indexToDirect:
                for contorlPointIdx in xrange(fbxMesh.GetControlPointsCount()):
                    indices.append(fbxLayerElements.GetIndexArray().GetAt(contorlPointIdx))
        elif mappingMode == fbx.FbxLayerElement.eByPolygonVertex:
            pointIdx = 0
            for polygonIdx in xrange(fbxMesh.GetPolygonCount()):
                for vertexIdx in xrange(fbxMesh.GetPolygonSize(polygonIdx)):
                    if indexToDirect:
                        indices.append(fbxLayerElements.GetIndexArray().GetAt(pointIdx))
                    else:
                        indices.append(pointIdx)
                    pointIdx += 1
        elif mappingMode == fbx.FbxLayerElement.eByPolygon:
            for polygonIdx in xrange(fbxMesh.GetPolygonCount()):
                if indexToDirect:
                    indices.append(fbxLayerElements.GetIndexArray().GetAt(polygonIdx))
                else:
                    indices.append(polygonIdx)
        return indices


    def getInterpolationWithLayerElements(self, fbxLayerElements):
        mappingMode = fbxLayerElements.GetMappingMode()
        if mappingMode == fbx.FbxLayerElement.eByControlPoint:
            return UsdGeom.Tokens.vertex
        elif mappingMode == fbx.FbxLayerElement.eByPolygonVertex:
            return UsdGeom.Tokens.faceVarying
        elif mappingMode == fbx.FbxLayerElement.eByPolygon:
            return UsdGeom.Tokens.uniform
        elif mappingMode == fbx.FbxLayerElement.eAllSame:
            return UsdGeom.Tokens.constant
        elif mappingMode == fbx.FbxLayerElement.eByEdge:
            usdUtils.printWarning("Mapping mode eByEdge for layer elements is not supported.")
        return ''


    def processNormals(self, fbxMesh, usdMesh, vertexIndices):
        for layerIdx in xrange(fbxMesh.GetLayerCount()):
            fbxLayerNormals = fbxMesh.GetLayer(layerIdx).GetNormals()
            if fbxLayerNormals is None:
                continue

            normals = []
            self.getVec3fArrayWithLayerElements(normals, fbxLayerNormals)
            if not any(normals):
                continue

            indices = self.getIndicesWithLayerElements(fbxMesh, fbxLayerNormals)
            interpolation = self.getInterpolationWithLayerElements(fbxLayerNormals)
            normalPrimvar = usdMesh.CreatePrimvar('normals', Sdf.ValueTypeNames.Normal3fArray, interpolation)
            normalPrimvar.Set(normals)
            if len(indices) != 0:
                normalPrimvar.SetIndices(Vt.IntArray(indices))
            break # normals can be in one layer only


    def processUVs(self, fbxMesh, usdMesh, vertexIndices):
        for layerIdx in xrange(fbxMesh.GetLayerCount()):
            fbxLayerUVs = fbxMesh.GetLayer(layerIdx).GetUVs() # get diffuse texture uv-s
            if fbxLayerUVs is None:
                continue

            uvs = []
            uvArray = fbxLayerUVs.GetDirectArray()
            for i in xrange(uvArray.GetCount()):
                uv = uvArray.GetAt(i)
                uvs.append(Gf.Vec2f(uv[0], uv[1]))
            if not any(uvs):
                continue

            indices = self.getIndicesWithLayerElements(fbxMesh, fbxLayerUVs)
            interpolation = self.getInterpolationWithLayerElements(fbxLayerUVs)

            texCoordSet = 'st'
            uvSets = fbxMesh.GetLayer(layerIdx).GetUVSets()
            if len(uvSets) > 0:
                fbxLayerElementUV = fbxMesh.GetLayer(layerIdx).GetUVSets()[0]
                texCoordSet = str(fbxLayerElementUV.GetName())
                if layerIdx == 0 or texCoordSet == '' or texCoordSet == 'default':
                    texCoordSet = 'st'
                else:
                    texCoordSet = usdUtils.makeValidIdentifier(texCoordSet)

            uvPrimvar = usdMesh.CreatePrimvar(texCoordSet, Sdf.ValueTypeNames.Float2Array, interpolation)
            uvPrimvar.Set(uvs)
            if len(indices) != 0:
                uvPrimvar.SetIndices(Vt.IntArray(indices))


    def processVertexColors(self, fbxMesh, usdMesh, vertexIndices):
        for layerIdx in xrange(fbxMesh.GetLayerCount()):
            fbxLayerColors = fbxMesh.GetLayer(layerIdx).GetVertexColors()
            if fbxLayerColors is None:
                continue

            colors = []
            colorArray = fbxLayerColors.GetDirectArray()
            for i in xrange(colorArray.GetCount()):
                fbxColor = colorArray.GetAt(i)
                colors.append(Gf.Vec3f(fbxColor.mRed, fbxColor.mGreen, fbxColor.mBlue))
            if not any(colors):
                continue
            
            indices = self.getIndicesWithLayerElements(fbxMesh, fbxLayerColors)
            interpolation = self.getInterpolationWithLayerElements(fbxLayerColors)
            displayColorPrimvar = usdMesh.CreateDisplayColorPrimvar(interpolation)
            displayColorPrimvar.Set(colors)
            if len(indices) != 0:
                displayColorPrimvar.SetIndices(Vt.IntArray(indices))
            break # vertex colors can be in one layer only


    def applySkinning(self, fbxNode, fbxSkin, usdMesh, indices):
        skin = self.fbxSkinToSkin[fbxSkin]
        skeleton = skin.skeleton

        maxPointIndex = 0
        for clusterIdx in range(fbxSkin.GetClusterCount()):
            fbxCluster = fbxSkin.GetCluster(clusterIdx)
            for i in range(fbxCluster.GetControlPointIndicesCount()):
                pointIndex = fbxCluster.GetControlPointIndices()[i]
                if maxPointIndex < pointIndex:
                    maxPointIndex = pointIndex
        vertexCount = maxPointIndex + 1 # should be equal to number of vertices: max(indices) + 1

        jointIndicesPacked = [[] for i in range(vertexCount)]
        weightsPacked = [[] for i in range(vertexCount)]
        for clusterIdx in range(fbxSkin.GetClusterCount()):
            fbxCluster = fbxSkin.GetCluster(clusterIdx)
            for i in range(fbxCluster.GetControlPointIndicesCount()):
                pointIndex = fbxCluster.GetControlPointIndices()[i]
                jointIndicesPacked[pointIndex].append(skin.remapIndex(clusterIdx))
                weightsPacked[pointIndex].append(float(fbxCluster.GetControlPointWeights()[i]))

        components = 0
        for indicesPerVertex in jointIndicesPacked:
            if components < len(indicesPerVertex):
                components = len(indicesPerVertex)

        jointIndices = [0] * vertexCount * components
        weights = [float(0)] * vertexCount * components
        for i in range(vertexCount):
            indicesPerVertex = jointIndicesPacked[i]
            for j in range(len(indicesPerVertex)):
                jointIndices[i * components + j] = indicesPerVertex[j]
                weights[i * components + j] = weightsPacked[i][j]
        weights = Vt.FloatArray(weights)
        UsdSkel.NormalizeWeights(weights, components)

        usdSkelBinding = UsdSkel.BindingAPI(usdMesh)
        usdSkelBinding.CreateJointIndicesPrimvar(False, components).Set(jointIndices)
        usdSkelBinding.CreateJointWeightsPrimvar(False, components).Set(weights)

        bindTransform = Gf.Matrix4d(1)
        if fbxSkin.GetClusterCount() > 0:
            # FBX stores bind transform matrix for the skin in each cluster
            # get it from the first one
            fbxCluster = fbxSkin.GetCluster(0)
            fbxBindTransform = fbx.FbxAMatrix()
            fbxBindTransform = fbxCluster.GetTransformMatrix(fbxBindTransform)
            bindTransform = GfMatrix4dWithFbxMatrix(fbxBindTransform)

        usdSkelBinding.CreateGeomBindTransformAttr(bindTransform)
        usdSkelBinding.CreateSkeletonRel().AddTarget(skeleton.usdSkeleton.GetPath())
        if self.legacyModifier is not None:
            self.legacyModifier.addSkelAnimToMesh(usdMesh, skeleton)


    def bindRigidDeformation(self, fbxNode, usdMesh, skeleton):
        meshNodeWorldMatrix = GfMatrix4dWithFbxMatrix(fbxNode.EvaluateGlobalTransform())
        transform = GfMatrix4dWithFbxMatrix(getFbxNodeGeometricTransform(fbxNode)) * meshNodeWorldMatrix

        skeleton.bindRigidDeformation(fbxNode, usdMesh, GfMatrix4dWithFbxMatrix(transform))
        if self.legacyModifier is not None:
            self.legacyModifier.addSkelAnimToMesh(usdMesh, skeleton)


    def bindMaterials(self, fbxMesh, usdMesh):
        for layerIdx in xrange(fbxMesh.GetLayerCount()):
            fbxLayerMaterials = fbxMesh.GetLayer(layerIdx).GetMaterials()
            if not fbxLayerMaterials:
                continue

            # looks like there is a bug in FBX SDK:
            # GetDirectArray() does not work if .GetCount() has not been called
            materialsCount = fbxLayerMaterials.GetDirectArray().GetCount()

            if fbxLayerMaterials.GetIndexArray().GetCount() > 1 and fbxLayerMaterials.GetMappingMode() == fbx.FbxLayerElement.eByPolygon:
                # subsets
                subsets = [[] for i in range(materialsCount)]
                for polygonIdx in range(fbxLayerMaterials.GetIndexArray().GetCount()):
                    materialIndex = fbxLayerMaterials.GetIndexArray().GetAt(polygonIdx)
                    subsets[materialIndex].append(polygonIdx)

                bindingAPI = UsdShade.MaterialBindingAPI(usdMesh)
                for materialIndex in range(materialsCount):
                    facesCount = len(subsets[materialIndex])
                    if facesCount > 0:
                        fbxMaterial = fbxLayerMaterials.GetDirectArray().GetAt(materialIndex)
                        materialName = usdUtils.makeValidIdentifier(fbxMaterial.GetName())
                        subsetName = materialName + '_subset'
                        if self.verbose:
                            print '  subset:', subsetName, 'faces:', facesCount
                        usdSubset = UsdShade.MaterialBindingAPI.CreateMaterialBindSubset(bindingAPI, subsetName, Vt.IntArray(subsets[materialIndex]))
                        usdMaterial = self.usdMaterials[fbxMaterial.GetName()]
                        UsdShade.MaterialBindingAPI(usdSubset).Bind(usdMaterial)
            elif fbxLayerMaterials.GetIndexArray().GetCount() > 0:
                # one material for whole mesh
                fbxMaterial = fbxLayerMaterials.GetDirectArray().GetAt(0)
                if fbxMaterial is not None and fbxMaterial.GetName() in self.usdMaterials:
                    usdMaterial = self.usdMaterials[fbxMaterial.GetName()]
                    UsdShade.Material.Bind(usdMaterial, usdMesh.GetPrim())


    def getFbxMesh(self, fbxNode):
        fbxNodeAttribute = fbxNode.GetNodeAttribute()
        if fbxNodeAttribute:
            fbxAttributeType = fbxNodeAttribute.GetAttributeType()
            if (fbx.FbxNodeAttribute.eMesh == fbxAttributeType or
                fbx.FbxNodeAttribute.eSubDiv == fbxAttributeType):
                return fbxNodeAttribute
        return None


    def getFbxSkin(self, fbxNode):
        fbxMesh = self.getFbxMesh(fbxNode)
        if fbxMesh is not None and fbxMesh.GetDeformerCount(fbx.FbxDeformer.eSkin) > 0:
            return fbxMesh.GetDeformer(0, fbx.FbxDeformer.eSkin)
        return None


    def processMesh(self, fbxNode, newPath, underSkeleton, indent):
        usdMesh = UsdGeom.Mesh.Define(self.usdStage, newPath)

        fbxMesh = fbxNode.GetNodeAttribute()
        if fbx.FbxNodeAttribute.eSubDiv == fbxMesh.GetAttributeType():
            fbxMesh = fbxMesh.GetBaseMesh()
        else:
            usdMesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)

        indices = []
        faceVertexCounts = []
        for polygonIdx in xrange(fbxMesh.GetPolygonCount()):
            polygonSize = fbxMesh.GetPolygonSize(polygonIdx)
            faceVertexCounts.append(polygonSize)
            for polygonVertexIdx in xrange(polygonSize):
                index = fbxMesh.GetPolygonVertex(polygonIdx, polygonVertexIdx)
                indices.append(index)
        usdMesh.CreateFaceVertexCountsAttr(faceVertexCounts)
        usdMesh.CreateFaceVertexIndicesAttr(indices)

        # positions, normals, texture coordinates
        self.processControlPoints(fbxMesh, usdMesh)
        self.processNormals(fbxMesh, usdMesh, indices)
        self.processUVs(fbxMesh, usdMesh, indices)
        self.processVertexColors(fbxMesh, usdMesh, indices)

        fbxSkin = self.getFbxSkin(fbxNode)
        if fbxSkin is not None:
            self.applySkinning(fbxNode, fbxSkin, usdMesh, indices)
        elif underSkeleton is not None:
            self.bindRigidDeformation(fbxNode, usdMesh, underSkeleton)

        if self.verbose:
            type = 'Mesh'
            if fbxSkin is not None:
                type = 'Skinned mesh'
            elif underSkeleton is not None:
                type = 'Rigid skinned mesh'
            print indent + type + ': ' + fbxNode.GetName()

        self.bindMaterials(fbxMesh, usdMesh)

        return usdMesh


    def addTranslateOpIfNotEmpty(self, prim, op, name = ''):
        if op != fbx.FbxVector4(0, 0, 0, 1):
            prim.AddTranslateOp(UsdGeom.XformOp.PrecisionFloat, name).Set((op[0], op[1], op[2]))

    def addInvertTranslateOpIfNotEmpty(self, prim, op, name = ''):
        if op != fbx.FbxVector4(0, 0, 0, -1):
            prim.AddTranslateOp(UsdGeom.XformOp.PrecisionFloat, name, True)

    def addRotationOpIfNotEmpty(self, prim, op, name = '', idRotation = None):
        if idRotation is None:
            idRotation = fbx.FbxVector4(0, 0, 0, 1)

        if op != idRotation:
            prim.AddRotateXYZOp(UsdGeom.XformOp.PrecisionFloat, name).Set((op[0], op[1], op[2]))

    def addScalingOpIfNotEmpty(self, prim, op, name = '', idScaling = None):
        if idScaling is None:
            idScaling = fbx.FbxVector4(1, 1, 1, 1)

        if op != idScaling:
            prim.AddScaleOp(UsdGeom.XformOp.PrecisionFloat, name).Set((op[0], op[1], op[2]))

    def getXformOp(self, usdGeom, type):
        ops = usdGeom.GetOrderedXformOps()
        for op in ops:
            # find operation without suffix
            if op.GetOpType() == type and len(op.GetName().split(':')) == 2:
                return op

        op = None
        if type == UsdGeom.XformOp.TypeTranslate:
            op = usdGeom.AddTranslateOp()
        elif type == UsdGeom.XformOp.TypeRotateXYZ:
            op = usdGeom.AddRotateXYZOp()
        if type == UsdGeom.XformOp.TypeOrient:
            op = usdGeom.AddOrientOp()
        if type == UsdGeom.XformOp.TypeScale:
            op = usdGeom.AddScaleOp()

        if op is not None:
            opNames = [
                "xformOp:translate",

                "xformOp:translate:rotationOffset",
                "xformOp:translate:rotationPivot",
                "xformOp:rotateXYZ:preRotation",
                "xformOp:rotateXYZ",
                "xformOp:rotateXYZ:postRotation",
                "!invert!xformOp:translate:rotationPivot",

                "xformOp:translate:scalingOffset",
                "xformOp:translate:scalingPivot",
                "xformOp:scale",
                "!invert!xformOp:translate:scalingPivot",
            ]

            ops = usdGeom.GetOrderedXformOps()
            newOps = []
            for opName in opNames:
                checkInverse = False
                if opName[0:8] == '!invert!':
                    opName = opName[8:]
                    checkInverse = True
                for operation in ops:
                    if operation.GetName() == opName and operation.IsInverseOp() == checkInverse:
                        newOps.append(operation)
                        break
            usdGeom.SetXformOpOrder(newOps)

        return op


    def setNodeTransforms(self, node, prim):
        t = fbx.FbxVector4(node.LclTranslation.Get())

        ro = node.GetRotationOffset(fbx.FbxNode.eSourcePivot)
        rp = node.GetRotationPivot(fbx.FbxNode.eSourcePivot)
        preRotation = node.GetPreRotation(fbx.FbxNode.eSourcePivot)
        r = fbx.FbxVector4(node.LclRotation.Get())
        postRotation = node.GetPostRotation(fbx.FbxNode.eSourcePivot)

        so = node.GetScalingOffset(fbx.FbxNode.eSourcePivot)
        sp = node.GetScalingPivot(fbx.FbxNode.eSourcePivot)
        s = fbx.FbxVector4(node.LclScaling.Get())

        # set translation
        self.addTranslateOpIfNotEmpty(prim, t)

        # set rotation offset, pivot and pre-post rotation ops 
        self.addTranslateOpIfNotEmpty(prim, ro, "rotationOffset")
        self.addTranslateOpIfNotEmpty(prim, rp, "rotationPivot")
        self.addRotationOpIfNotEmpty(prim, preRotation, "preRotation")
        self.addRotationOpIfNotEmpty(prim, r)
        self.addRotationOpIfNotEmpty(prim, postRotation, "postRotation")
        self.addInvertTranslateOpIfNotEmpty(prim, -rp, "rotationPivot")

        # set scaling offset & pivot
        self.addTranslateOpIfNotEmpty(prim, so, "scalingOffset")
        self.addTranslateOpIfNotEmpty(prim, sp, "scalingPivot")
        self.addScalingOpIfNotEmpty(prim, s)
        self.addInvertTranslateOpIfNotEmpty(prim, -rp, "scalingPivot")


    def hasGeometricTransform(self, fbxNode):
        if (fbx.FbxVector4(0, 0, 0, 1) != fbxNode.GetGeometricTranslation(fbx.FbxNode.eSourcePivot) or
            fbx.FbxVector4(0, 0, 0, 1) != fbxNode.GetGeometricRotation(fbx.FbxNode.eSourcePivot) or
            fbx.FbxVector4(1, 1, 1, 1) != fbxNode.GetGeometricScaling(fbx.FbxNode.eSourcePivot)):
            return True
        return False


    def setGeometricTransform(self, fbxNode, prim):
        gt = fbxNode.GetGeometricTranslation(fbx.FbxNode.eSourcePivot)
        gr = fbxNode.GetGeometricRotation(fbx.FbxNode.eSourcePivot)
        gs = fbxNode.GetGeometricScaling(fbx.FbxNode.eSourcePivot)

        self.addTranslateOpIfNotEmpty(prim, gt, "geometricTranslation")
        self.addRotationOpIfNotEmpty(prim, gr, "geometricRotation")
        self.addScalingOpIfNotEmpty(prim, gs, "geometricScaling")


    def processSkeletalAnimation(self, skeletonIdx):
        skeleton = self.skinning.skeletons[skeletonIdx]

        framesCount = int((self.stopAnimationTime - self.startAnimationTime) * self.fps + 0.5) + 1
        startFrame = int(self.startAnimationTime * self.fps + 0.5)

        if framesCount == 1:
            if self.verbose:
                print '  no skeletal animation'
            return

        animationName = self.asset.getAnimationsPath() + '/' + 'SkelAnimation'
        if skeletonIdx > 0:
            animationName += '_' + str(skeletonIdx)
        if self.verbose:
            print 'Animation:', animationName

        usdSkelAnim = UsdSkel.Animation.Define(self.usdStage, animationName)
        translateAttr = usdSkelAnim.CreateTranslationsAttr()
        rotateAttr = usdSkelAnim.CreateRotationsAttr()
        scaleAttr = usdSkelAnim.CreateScalesAttr()

        jointPaths = []
        for fbxNode in skeleton.joints:
            jointPaths.append(skeleton.jointPaths[fbxNode])

        fbxAnimEvaluator = self.fbxScene.GetAnimationEvaluator()
        for frame in range(framesCount):
            time = frame / self.fps + self.startAnimationTime

            translations = []
            rotations = []
            scales = []

            for fbxNode in skeleton.joints:
                fbxTime = fbx.FbxTime()
                fbxTime.SetSecondDouble(time)

                fbxMatrix = fbxAnimEvaluator.GetNodeLocalTransform(fbxNode, fbxTime)

                translation = fbxMatrix.GetT()
                q = fbxMatrix.GetQ()
                rotation = Gf.Quatf(float(q[3]), Gf.Vec3f(float(q[0]), float(q[1]), float(q[2])))
                scale = fbxMatrix.GetS()

                translations.append([translation[0], translation[1], translation[2]])
                rotations.append(rotation)
                scales.append([scale[0], scale[1], scale[2]])


            translateAttr.Set(translations, Usd.TimeCode(frame + startFrame))
            rotateAttr.Set(rotations, Usd.TimeCode(frame + startFrame))
            scaleAttr.Set(scales, Usd.TimeCode(frame + startFrame))

        usdSkelAnim.CreateJointsAttr(jointPaths)
        skeleton.setSkeletalAnimation(usdSkelAnim)


    def processNodeTransformAnimation(self, fbxNode, fbxProperty, fbxAnimCurveNode, usdGeom):
        fbxTimeSpan = fbx.FbxTimeSpan()
        fbxAnimCurveNode.GetAnimationInterval(fbxTimeSpan)

        startTime = fbxTimeSpan.GetStart().GetSecondDouble()
        stopTime = fbxTimeSpan.GetStop().GetSecondDouble()
        framesCount = int((stopTime - startTime) * self.fps + 0.5) + 1
        if framesCount < 1:
            return
        startFrame = int(startTime * self.fps + 0.5)

        isTranslation = False
        isRotation = False
        isScale = False

        channelName = str(fbxProperty.GetName()).strip()

        if channelName == 'Lcl Translation':
            isTranslation = True
        elif channelName == 'Lcl Rotation':
            isRotation = True
        elif channelName == 'Lcl Scaling':
            isScale = True
        else:
            if self.verbose:
                print 'Warnig: animation channel"', channelName, '"is not supported.'

        fbxAnimEvaluator = self.fbxScene.GetAnimationEvaluator()
        # TODO: for linear curves use key frames only
        for frame in range(startFrame, startFrame + framesCount):
            time = frame / self.fps + startTime
            timeCode = self.asset.toTimeCode(time, True)
            fbxTime = fbx.FbxTime()
            fbxTime.SetSecondDouble(time)

            if isTranslation:
                op = self.getXformOp(usdGeom, UsdGeom.XformOp.TypeTranslate)
                v = fbxNode.EvaluateLocalTranslation(fbxTime)
                op.Set(time = timeCode, value = Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])))
            elif isRotation:
                op = self.getXformOp(usdGeom, UsdGeom.XformOp.TypeRotateXYZ)
                v = fbxNode.EvaluateLocalRotation(fbxTime)
                op.Set(time = timeCode, value = Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])))
            elif isScale:
                op = self.getXformOp(usdGeom, UsdGeom.XformOp.TypeScale)
                v = fbxNode.EvaluateLocalScaling(fbxTime)
                op.Set(time = timeCode, value = Gf.Vec3f(float(v[0]), float(v[1]), float(v[2])))


    def processNodeAnimations(self, fbxNode, usdGeom):
        animStacksCount = self.fbxScene.GetSrcObjectCount(fbx.FbxCriteria.ObjectType(fbx.FbxAnimStack.ClassId))
        if animStacksCount < 1:
            return
        for animStackIdx in range(animStacksCount):
            fbxAnimStack = self.fbxScene.GetSrcObject(fbx.FbxCriteria.ObjectType(fbx.FbxAnimStack.ClassId), animStackIdx)
            for layerIdx in range(fbxAnimStack.GetMemberCount(fbx.FbxCriteria.ObjectType(fbx.FbxAnimLayer.ClassId))):
                fbxAnimLayer = fbxAnimStack.GetMember(fbx.FbxCriteria.ObjectType(fbx.FbxAnimLayer.ClassId), layerIdx)
                for curveNodeIdx in range(fbxAnimLayer.GetMemberCount(fbx.FbxCriteria.ObjectType(fbx.FbxAnimCurveNode.ClassId))):
                    fbxAnimCurveNode = fbxAnimLayer.GetMember(fbx.FbxCriteria.ObjectType(fbx.FbxAnimCurveNode.ClassId), curveNodeIdx)
                    for propertyIdx in range(fbxAnimCurveNode.GetDstPropertyCount()):
                        fbxProperty = fbxAnimCurveNode.GetDstProperty(propertyIdx)
                        fbxObject = fbxProperty.GetFbxObject()
                        if fbxObject == fbxNode:
                            self.processNodeTransformAnimation(fbxNode, fbxProperty, fbxAnimCurveNode, usdGeom)


    def processNode(self, fbxNode, path, underSkeleton, indent):
        nodeName = usdUtils.makeValidIdentifier(fbxNode.GetName().split(":")[-1])
        newPath = path + '/' + nodeName
        if newPath in self.nodePaths:
            newPath = newPath + str(self.nodeId)
            self.nodeId = self.nodeId + 1

        fbxAttributeType = fbx.FbxNodeAttribute.eNone
        fbxNodeAttribute = fbxNode.GetNodeAttribute()
        if fbxNodeAttribute:
            fbxAttributeType = fbxNodeAttribute.GetAttributeType()

        if fbx.FbxNodeAttribute.eSkeleton == fbxAttributeType:
            if fbxNodeAttribute.IsSkeletonRoot():
                skeleton = self.skinning.findSkeletonByRoot(fbxNode)
                if skeleton is None:
                    skeleton = self.skinning.findSkeletonByJoint(fbxNode)
                if skeleton is not None:
                    skeleton.makeUsdSkeleton(self.usdStage, newPath, self.nodeManager)
                    if self.verbose:
                        print indent + "SkelRoot:", nodeName
                    underSkeleton = skeleton

        if underSkeleton and self.getFbxMesh(fbxNode) is not None:
            self.skeletonByNode[fbxNode] = underSkeleton
        elif self.getFbxSkin(fbxNode) is not None:
            self.skeletonByNode[fbxNode] = None
        else:
            # if we have a geometric transformation we shouldn't propagate it to node's children
            usdNode = None
            hasGeometricTransform = self.hasGeometricTransform(fbxNode)
            if underSkeleton is None and hasGeometricTransform and underSkeleton is None:
                usdNode = UsdGeom.Xform.Define(self.usdStage, newPath)
                geometryPath = newPath + '/' + nodeName + '_geometry'
            else:
                geometryPath = newPath

            usdGeometry = None
            if (fbx.FbxNodeAttribute.eMesh == fbxAttributeType or
                fbx.FbxNodeAttribute.eSubDiv == fbxAttributeType):
                usdGeometry = self.processMesh(fbxNode, geometryPath, underSkeleton, indent)

            if underSkeleton is None:
                if usdGeometry is None:
                    usdGeometry = UsdGeom.Xform.Define(self.usdStage, geometryPath)

                self.nodePaths[newPath] = newPath
                if hasGeometricTransform:
                    self.setNodeTransforms(fbxNode, usdNode)
                    self.setGeometricTransform(fbxNode, usdGeometry)
                    self.processNodeAnimations(fbxNode, usdNode)
                else:
                    self.setNodeTransforms(fbxNode, usdGeometry)
                    self.processNodeAnimations(fbxNode, usdGeometry)

        # process child nodes recursively
        if underSkeleton is not None:
            newPath = path # keep meshes directly under SkelRoot scope

        for childIdx in xrange(fbxNode.GetChildCount()):
            self.processNode(fbxNode.GetChild(childIdx), newPath, underSkeleton, indent + '  ')


    def populateSkeletons(self, fbxNode):
        fbxNodeAttribute = fbxNode.GetNodeAttribute()
        if fbxNodeAttribute:
            fbxAttributeType = fbxNodeAttribute.GetAttributeType()
            if fbx.FbxNodeAttribute.eSkeleton == fbxAttributeType:
                if fbxNodeAttribute.IsSkeletonRoot():
                    self.skinning.createSkeleton(fbxNode)
        for childIdx in xrange(fbxNode.GetChildCount()):
            self.populateSkeletons(fbxNode.GetChild(childIdx))


    def findSkelRoot(self, fbxNode):
        fbxNodeAttribute = fbxNode.GetNodeAttribute()
        if fbxNodeAttribute:
            fbxAttributeType = fbxNodeAttribute.GetAttributeType()
            if fbx.FbxNodeAttribute.eSkeleton == fbxAttributeType:
                if fbxNodeAttribute.IsSkeletonRoot():
                    return fbxNode
        fbxParentNode = fbxNode.GetParent()
        if fbxParentNode is not None:
            return self.findSkelRoot(fbxParentNode)
        return None


    def populateSkins(self, fbxNode):
        fbxNodeAttribute = fbxNode.GetNodeAttribute()
        if fbxNodeAttribute:
            fbxAttributeType = fbxNodeAttribute.GetAttributeType()
            if (fbx.FbxNodeAttribute.eMesh == fbxAttributeType or
                fbx.FbxNodeAttribute.eSubDiv == fbxAttributeType):
                fbxMesh = fbxNode.GetNodeAttribute()
                for i in range(fbxMesh.GetDeformerCount(fbx.FbxDeformer.eSkin)):
                    fbxSkin = fbxMesh.GetDeformer(i, fbx.FbxDeformer.eSkin)
                    # try to find skeleton root (.eSkeleton) in parent nodes
                    root = self.findSkelRoot(fbxSkin.GetCluster(0).GetLink()) if fbxSkin.GetClusterCount() > 0 else None
                    skin = usdUtils.Skin(root)
                    for clusterIdx in range(fbxSkin.GetClusterCount()):
                        fbxCluster = fbxSkin.GetCluster(clusterIdx)
                        fbxJointNode = fbxCluster.GetLink()
                        skin.joints.append(fbxJointNode)

                        linkWorldTransform = fbx.FbxAMatrix()
                        linkWorldTransform = fbxCluster.GetTransformLinkMatrix(linkWorldTransform)
                        skin.bindMatrices[fbxJointNode] = GfMatrix4dWithFbxMatrix(linkWorldTransform)
                    self.skinning.skins.append(skin)
                    self.fbxSkinToSkin[fbxSkin] = skin

        for childIdx in xrange(fbxNode.GetChildCount()):
            self.populateSkins(fbxNode.GetChild(childIdx))


    def processSkinning(self):
        self.populateSkeletons(self.fbxScene.GetRootNode())
        self.populateSkins(self.fbxScene.GetRootNode())
        self.skinning.createSkeletonsFromSkins()
        if self.verbose:
            if len(self.skinning.skeletons) > 0:
                print "  Found skeletons:", len(self.skinning.skeletons), "with", len(self.skinning.skins), "skin(s)"


    def processSkinnedMeshes(self):
        for fbxNode, skeleton in self.skeletonByNode.iteritems():
            fbxSkin = self.getFbxSkin(fbxNode)
            if skeleton is None:
                if fbxSkin is None:
                    continue
                skin = self.fbxSkinToSkin[fbxSkin]
                skeleton = skin.skeleton

            nodeName = usdUtils.makeValidIdentifier(fbxNode.GetName().split(":")[-1])
            newPath = skeleton.sdfPath + '/' + nodeName
            if newPath in self.nodePaths:
                newPath = newPath + str(self.nodeId)
                self.nodeId = self.nodeId + 1
            self.nodePaths[newPath] = newPath
            self.processMesh(fbxNode, newPath, skeleton, '')


    def processSkeletalAnimations(self):
        for skeletonIdx in range(len(self.skinning.skeletons)):
            self.processSkeletalAnimation(skeletonIdx)


    def makeUsdStage(self):
        self.usdStage = self.asset.makeUsdStage()

        # axis system for USD should be Y-up, odd-forward, and right-handed
        sceneAxisSystem = self.fbxScene.GetGlobalSettings().GetAxisSystem()
        axisSystem = fbx.FbxAxisSystem(fbx.FbxAxisSystem.EUpVector(fbx.FbxAxisSystem.eYAxis),
                                       fbx.FbxAxisSystem.EFrontVector(fbx.FbxAxisSystem.eParityOdd),
                                       fbx.FbxAxisSystem.ECoordSystem(fbx.FbxAxisSystem.eRightHanded))
        if sceneAxisSystem != axisSystem:
            if self.verbose:
                print("  converting to Y-up, odd-forward, and right-handed axis system")
            axisSystem.ConvertScene(self.fbxScene)

        systemUnit = self.fbxScene.GetGlobalSettings().GetSystemUnit()
        if systemUnit != fbx.FbxSystemUnit.cm: # cm is default for USD and FBX
            fbxMetersPerUnit = 0.01
            metersPerUnit = systemUnit.GetScaleFactor() * fbxMetersPerUnit
            if self.legacyModifier is not None and self.legacyModifier.getMetersPerUnit() == 0:
                self.legacyModifier.setMetersPerUnit(metersPerUnit)
            else:
                self.usdStage.SetMetadata("metersPerUnit", metersPerUnit)

        self.processMaterials()
        self.processSkinning()
        self.prepareAnimations()
        self.processNode(self.fbxScene.GetRootNode(), self.asset.getGeomPath(), None, '')
        self.processSkeletalAnimations()
        self.processSkinnedMeshes()
        self.asset.finalize()
        return self.usdStage


def usdStageWithFbx(fbxPath, usdPath, legacyModifier, copyTextures, verbose):
    if usdStageWithFbxLoaded == False:
        return None

    try:
        fbxConverter = FbxConverter(fbxPath, usdPath, legacyModifier, copyTextures, verbose)
        return fbxConverter.makeUsdStage()
    except ConvertError:
        return None
    except:
        raise

    return None

