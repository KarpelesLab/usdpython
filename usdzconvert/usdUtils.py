#!/usr/bin/python

import os.path
from shutil import copyfile
import re
from pxr import *


def makeValidIdentifier(path):
    if len(path) > 0:
        path = re.sub('[^A-Za-z0-9]', '_', path)
        if path[0].isdigit():
            path = '_' + path
        if Sdf.Path.IsValidIdentifier(path):
            return path
    return 'defaultIdentifier'


def makeValidPath(path):
    if len(path) > 0:
        path = re.sub('[^A-Za-z0-9/.]', '_', path)
        if path[0].isdigit():
            path = '_' + path
    return path


def getIndexByChannel(channel):
    if channel == 'g':
        return 1
    if channel == 'b':
        return 2
    if channel == 'a':
        return 3
    return 0


def copy(srcFile, dstFile, verbose=False):
    if verbose:
        print 'Copying file:', srcFile, dstFile
    if os.path.isfile(srcFile):
        dstFolder = os.path.dirname(dstFile)
        if dstFolder != '' and not os.path.isdir(dstFolder):
            os.makedirs(dstFolder)
        copyfile(srcFile, dstFile)
    else:
        print "Warning: can't find", srcFile


def resolvePath(textureFileName, folder):
    if textureFileName == '':
        return ''
    if os.path.isfile(textureFileName):
        return textureFileName

    path = textureFileName.replace('\\', '/')
    basename = os.path.basename(path)
    if os.path.isfile(folder + basename):
        return folder + basename

    # TODO: try more precise finding with folders info

    for root, dirnames, filenames in os.walk(folder):
        for filename in filenames:
            if filename == basename:
                return os.path.join(root, filename)

    return textureFileName



class Asset:
    materialsFolder = 'Materials'
    geomFolder = 'Geom'
    animationsFolder = 'Animations'

    def __init__(self, usdPath, usdStage=None):
        fileName = os.path.basename(usdPath)
        self.name = fileName[:fileName.find('.')]
        self.name = makeValidIdentifier(self.name)
        self.usdPath = usdPath
        self.usdStage = usdStage
        self.defaultPrim = None
        self._geomPath = ''
        self._materialsPath = ''
        self._animationsPath = ''


    def getPath(self):
        return '/' + self.name


    def getMaterialsPath(self):
        # debug
        # assert self.usdStage is not None, 'Using materials path before usdStage was created'
        if not self._materialsPath:
            self._materialsPath = self.getPath() + '/' + Asset.materialsFolder
            self.usdStage.DefinePrim(self._materialsPath, 'Scope')
        return self._materialsPath


    def getGeomPath(self):
        # debug
        # assert self.usdStage is not None, 'Using geom path before usdStage was created'
        if not self._geomPath:
            self._geomPath = self.getPath() + '/' + Asset.geomFolder
            self.usdStage.DefinePrim(self._geomPath, 'Scope')
        return self._geomPath


    def getAnimationsPath(self):
        # debug
        # assert self.usdStage is not None, 'Using animations path before usdStage was created'
        if not self._animationsPath:
            self._animationsPath = self.getPath() + '/' + Asset.animationsFolder
            self.usdStage.DefinePrim(self._animationsPath, 'Scope')
        return self._animationsPath


    def makeUsdStage(self):
        # debug
        # assert self.usdStage is None, 'Trying to create another usdStage'
        self.usdStage = Usd.Stage.CreateNew(self.usdPath)
        UsdGeom.SetStageUpAxis(self.usdStage, UsdGeom.Tokens.y)

        # make default prim
        self.defaultPrim = self.usdStage.DefinePrim(self.getPath(), 'Xform')
        self.defaultPrim.SetAssetInfoByKey('name', self.name)
        Usd.ModelAPI(self.defaultPrim).SetKind('component')
        self.usdStage.SetDefaultPrim(self.defaultPrim)

        return self.usdStage



class InputName:
    normal = 'normal'
    diffuseColor = 'diffuseColor'
    opacity = 'opacity'
    emissiveColor = 'emissiveColor'
    metallic = 'metallic'
    roughness = 'roughness'
    occlusion = 'occlusion'
    clearcoat = 'clearcoat'
    clearcoatRoughness = 'clearcoatRoughness'



class Input:
    names = [InputName.normal, InputName.diffuseColor, InputName.opacity, InputName.emissiveColor, InputName.metallic, InputName.roughness, InputName.occlusion, InputName.clearcoat, InputName.clearcoatRoughness]
    channels = ['rgb', 'rgb', 'a', 'rgb', 'r', 'r', 'r', 'r', 'r']
    types = [Sdf.ValueTypeNames.Normal3f, Sdf.ValueTypeNames.Color3f, Sdf.ValueTypeNames.Float, 
        Sdf.ValueTypeNames.Color3f, Sdf.ValueTypeNames.Float, Sdf.ValueTypeNames.Float, Sdf.ValueTypeNames.Float, Sdf.ValueTypeNames.Float, Sdf.ValueTypeNames.Float]



class Map:
    def __init__(self, channels, file, fallback=None, texCoordSet='st', wrapS='repeat', wrapT='repeat', scale = None):
        self.file = file
        self.channels = channels
        self.fallback = fallback
        self.texCoordSet = texCoordSet
        self.textureShaderName = ''
        self.wrapS = wrapS
        self.wrapT = wrapT
        self.scale = scale



class Material:
    def __init__(self, name):
        if name.find('/') != -1:
            self.path = makeValidPath(name)
            self.name = makeValidIdentifier(os.path.basename(name))
        else:
            self.path = ''
            self.name = makeValidIdentifier(name) if name != '' else ''
        self.inputs = {}


    def isEmpty(self):
        if len(self.inputs.keys()) == 0:
            return True
        return False


    def getUsdSurfaceShader(self, usdMaterial, usdStage):
        for usdShadeOutput in usdMaterial.GetOutputs():
            if UsdShade.ConnectableAPI.HasConnectedSource(usdShadeOutput) == True:
                (sourceAPI, sourceName, sourceType) = UsdShade.ConnectableAPI.GetConnectedSource(usdShadeOutput)
                if sourceName == 'surface':
                    return UsdShade.Shader(sourceAPI)
        return self._createSurfaceShader(usdMaterial, usdStage)


    def updateUsdMaterial(self, usdMaterial, surfaceShader, usdStage):
        self._makeTextureShaderNames()
        for inputIdx in range(len(Input.names)):
            self._addMapToUsdMaterial(inputIdx, usdMaterial, surfaceShader, usdStage)


    def makeUsdMaterial(self, asset):
        matPath = self.path if self.path else asset.getMaterialsPath() + '/' + self.name
        usdMaterial = UsdShade.Material.Define(asset.usdStage, matPath)

        if self.isEmpty():
            return usdMaterial

        surfaceShader = self._createSurfaceShader(usdMaterial, asset.usdStage)
        self.updateUsdMaterial(usdMaterial, surfaceShader, asset.usdStage)
        return usdMaterial


    # private methods:

    def _createSurfaceShader(self, usdMaterial, usdStage):
        matPath = str(usdMaterial.GetPath())
        surfaceShader = UsdShade.Shader.Define(usdStage, matPath + '/surfaceShader')
        surfaceShader.CreateIdAttr('UsdPreviewSurface')
        usdMaterial.CreateOutput('surface', Sdf.ValueTypeNames.Token).ConnectToSource(surfaceShader, 'surface')
        return surfaceShader


    def _makeTextureShaderNames(self):
        # combine texture shaders with the same texture
        for i in range(0, len(Input.names)):
            inputName = Input.names[i]
            if inputName in self.inputs:
                map = self.inputs[inputName]
                if not isinstance(map, Map):
                    continue
                if map.textureShaderName != '':
                    continue
                textureShaderName = inputName
                maps = [map]
                if inputName != InputName.normal:
                    for j in range(i + 1, len(Input.names)):
                        inputName2 = Input.names[j]
                        map2 = self.inputs[inputName2] if inputName2 in self.inputs else None
                        if not isinstance(map2, Map):
                            continue
                        if map2 != None and map2.file == map.file:
                            textureShaderName += '_' + inputName2
                            maps.append(map2)
                for map3 in maps:
                    map3.textureShaderName = textureShaderName


    def _makeUsdUVTexture(self, matPath, map, inputName, channels, uvInput, usdStage):
        uvReaderPath = matPath + '/uvReader_' + map.texCoordSet
        uvReader = usdStage.GetPrimAtPath(uvReaderPath)
        if uvReader:
            uvReader = UsdShade.Shader(uvReader)
        else:
            uvReader = UsdShade.Shader.Define(usdStage, uvReaderPath)
            uvReader.CreateIdAttr('UsdPrimvarReader_float2')
            if uvInput != None:
                # token inputs:varname.connect = </cubeMaterial.inputs:frame:stPrimvarName>
                uvReader.CreateInput('varname', Sdf.ValueTypeNames.Token).ConnectToSource(uvInput)
            else:
                uvReader.CreateInput('varname',Sdf.ValueTypeNames.Token).Set(map.texCoordSet)
            uvReader.CreateOutput('result', Sdf.ValueTypeNames.Float2)

        # create texture shader node
        textureShader = UsdShade.Shader.Define(usdStage, matPath + '/' + map.textureShaderName + '_texture')
        textureShader.CreateIdAttr('UsdUVTexture')

        if inputName == InputName.normal:
            # float4 inputs:scale = (2, 2, 2, 2)
            textureShader.CreateInput('scale', Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 2))
            # float4 inputs:bias = (-1, -1, -1, -1)
            textureShader.CreateInput('bias', Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, -1))
        else:
            if map.scale != None:
                gfScale = Gf.Vec4f(1)
                if channels == 'rgb':
                    if isinstance(map.scale, list):
                        gfScale[0] = float(map.scale[0])
                        gfScale[1] = float(map.scale[1])
                        gfScale[2] = float(map.scale[2])
                    else:
                        print map.scale
                        print 'Scale value', map.scale, 'for', inputName, 'is incorrect.'
                        raise
                else:
                    gfScale[getIndexByChannel(channels)] = float(map.scale)
                textureShader.CreateInput('scale', Sdf.ValueTypeNames.Float4).Set(gfScale)

        fileAndExt = os.path.splitext(map.file)
        if len(fileAndExt) == 1 or (fileAndExt[-1] != '.png' and fileAndExt[-1] != '.jpg'):
            print 'Warning: texture file', map.file, 'is not .png or .jpg'

        textureShader.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(map.file)
        textureShader.CreateInput('st', Sdf.ValueTypeNames.Float2).ConnectToSource(uvReader, 'result')
        dataType = Sdf.ValueTypeNames.Float3 if len(channels) == 3 else Sdf.ValueTypeNames.Float
        textureShader.CreateOutput(channels, dataType)

        # wrapping mode
        textureShader.CreateInput('wrapS', Sdf.ValueTypeNames.Token).Set(map.wrapS)
        textureShader.CreateInput('wrapT', Sdf.ValueTypeNames.Token).Set(map.wrapT)

        # fallback value is used if loading of the texture file is failed
        if map.fallback != None:
            # update if exists in combined textures like for ORM
            gfFallback = textureShader.GetInput('fallback').Get()
            if gfFallback is None:
                # default by Pixar spec
                gfFallback = Gf.Vec4f(0, 0, 0, 1)
            if channels == 'rgb':
                if isinstance(map.fallback, list):
                    gfFallback[0] = float(map.fallback[0])
                    gfFallback[1] = float(map.fallback[1])
                    gfFallback[2] = float(map.fallback[2])
                    # do not update alpha channel!
                else:
                    print 'Fallback value', map.fallback, 'for', inputName, 'is incorrect.'
            else:
                gfFallback[getIndexByChannel(channels)] = float(map.fallback)

            if inputName == InputName.normal:
                #normal map fallback is within 0 - 1
                gfFallback = 0.5*(gfFallback + Gf.Vec4f(1.0))
            textureShader.CreateInput('fallback', Sdf.ValueTypeNames.Float4).Set(gfFallback)

        return textureShader


    def _addMapToUsdMaterial(self, inputIdx, usdMaterial, surfaceShader, usdStage):
        inputName = Input.names[inputIdx]
        if inputName not in self.inputs:
            return

        input = self.inputs[inputName]
        inputType = Input.types[inputIdx]

        if isinstance(input, Map):
            map = input
            defaultChannels = Input.channels[inputIdx]
            channels = map.channels if len(map.channels) == len(defaultChannels) else defaultChannels
            uvInput = None
            if inputName == InputName.normal:
                # token inputs:frame:stPrimvarName = "st"
                uvInput = usdMaterial.CreateInput('frame:stPrimvarName', Sdf.ValueTypeNames.Token)
                uvInput.Set(map.texCoordSet)
            matPath = str(usdMaterial.GetPath())
            textureShader = self._makeUsdUVTexture(matPath, map, inputName, channels, uvInput, usdStage)
            surfaceShader.CreateInput(inputName, inputType).ConnectToSource(textureShader, channels)
        elif isinstance(input, list):
            gfVec3d = Gf.Vec3d(float(input[0]), float(input[1]), float(input[2]))
            surfaceShader.CreateInput(inputName, inputType).Set(gfVec3d)
        else:
            surfaceShader.CreateInput(inputName, inputType).Set(float(input))



class NodeManager:
    def __init__(self):
        pass

    def overrideGetName(self, node):
        # take care about valid identifier
        # debug
        # assert 0, "Can't find overriden method overrideGetName for node manager"
        pass

    def overrideGetChildren(self, node):
        # debug
        # assert 0, "Can't find overriden method overrideGetChildren for node manager"
        pass

    def overrideGetLocalTransformGfMatrix4d(self, node):
        # debug
        # assert 0, "Can't find overriden method overrideGetLocaLTransform for node manager"
        pass



class Skin:
    def __init__(self, root=None):
        self.root = root
        self.joints = []
        self.bindMatrices = {}
        self.skeleton = None
        self._toSkeletonIndices = {}


    def remapIndex(self, index):
        return self._toSkeletonIndices[str(index)]


    # private:
    def _setSkeleton(self, skeleton):
        self.skeleton = skeleton
        for joint in self.joints:
            self.skeleton.bindMatrices[joint] = self.bindMatrices[joint]


    def _prepareIndexRemapping(self):
        for jointIdx in range(len(self.joints)):
            joint = self.joints[jointIdx]
            self._toSkeletonIndices[str(jointIdx)] = self.skeleton.getJointIndex(joint)



class Skeleton:
    def __init__(self):
        self.joints = []
        self.jointPaths = {}   # jointPaths[joint]
        self.restMatrices ={}  # restMatrices[joint]
        self.bindMatrices = {} # bindMatrices[joint]
        self.usdSkeleton = None
        self.usdSkelAnim = None
        self.sdfPath = None


    def getJointIndex(self, joint):
        for jointIdx in range(len(self.joints)):
            if joint == self.joints[jointIdx]:
                return jointIdx
        return -1


    def getRoot(self):
        return self.joints[0] # TODO: check if does exist


    def makeUsdSkeleton(self, usdStage, sdfPath):
        if self.usdSkeleton is not None:
            return self.usdSkeleton
        self.sdfPath = sdfPath
        jointPaths = []
        restMatrices = []
        bindMatrices = []
        for joint in self.joints:
            jointPaths.append(self.jointPaths[joint])
            restMatrices.append(self.restMatrices[joint])
            if joint in self.bindMatrices:
                bindMatrices.append(self.bindMatrices[joint])
            else:
                bindMatrices.append(Gf.Matrix4d(1))

        usdGeom = UsdSkel.Root.Define(usdStage, sdfPath)

        self.usdSkeleton = UsdSkel.Skeleton.Define(usdStage, sdfPath + '/Skeleton')
        self.usdSkeleton.CreateJointsAttr().Set(jointPaths)
        self.usdSkeleton.CreateRestTransformsAttr(restMatrices)
        self.usdSkeleton.CreateBindTransformsAttr(bindMatrices)
        return usdGeom


    def bindRigidDeformation(self, joint, usdMesh, bindTransform):
        # debug
        # assert self.usdSkeleton, "Trying to bind rigid deforamtion before USD Skeleton has been created."
        jointIndex = self.getJointIndex(joint)
        if jointIndex == -1:
            return
        usdSkelBinding = UsdSkel.BindingAPI(usdMesh)

        usdSkelBinding.CreateJointIndicesPrimvar(True, 1).Set([jointIndex])
        usdSkelBinding.CreateJointWeightsPrimvar(True, 1).Set([1])
        usdSkelBinding.CreateGeomBindTransformAttr(bindTransform)

        usdSkelBinding.CreateSkeletonRel().AddTarget(self.usdSkeleton.GetPath())


    def setSkeletalAnimation(self, usdSkelAnim):
        if self.usdSkelAnim != None:
            # default animation is the first one
            return

        if self.usdSkeleton is None:
            print '  Warnig: Trying to assign Skeletal Animation before USD Skeleton has been created.'
            return

        usdSkelBinding = UsdSkel.BindingAPI(self.usdSkeleton)
        usdSkelBinding.CreateAnimationSourceRel().AddTarget(usdSkelAnim.GetPath())
        self.usdSkelAnim = usdSkelAnim


    # private:
    def _collectJoints(self, node, path, nodeMan):
        self.joints.append(node)
        name = nodeMan.overrideGetName(node)
        newPath = path + name
        self.jointPaths[node] = newPath
        self.restMatrices[node] = nodeMan.overrideGetLocalTransformGfMatrix4d(node)
        for child in nodeMan.overrideGetChildren(node):
            self._collectJoints(child, newPath + '/', nodeMan)


class Skinning:
    def __init__(self, nodeMan):
        self.skins = []
        self.skeletons = []
        self.nodeMan = nodeMan
        self.joints = {} # joint set


    def createSkeleton(self, root):
        skeleton = Skeleton()
        skeleton._collectJoints(root, '', self.nodeMan)
        self.skeletons.append(skeleton)
        return skeleton


    def createSkeletonsFromSkins(self):
        for skin in self.skins:
            if len(skin.joints) < 1:
                continue
            skeleton = self.findSkeletonByJoint(skin.joints[0])
            if skeleton is None:
                skeleton = self.createSkeleton(skin.root)
            for joint in skin.joints:
                self.joints[joint] = joint
            skin._setSkeleton(skeleton)

            # check if existed skeletons are subpart of this one
            skeletonsToRemove = []
            for subSkeleton in self.skeletons:
                if subSkeleton == skeleton:
                    continue
                if skeleton.getJointIndex(subSkeleton.getRoot()) != -1:
                    for skin in self.skins:
                        if skin.skeleton == subSkeleton:
                            skin._setSkeleton(skeleton)
                    skeletonsToRemove.append(subSkeleton)
            for skeletonToRemove in skeletonsToRemove:
                self.skeletons.remove(skeletonToRemove)


        for skin in self.skins:
            skin._prepareIndexRemapping()


    def isJoint(self, node):
        return True if node in self.joints else False


    def findSkeletonByRoot(self, node):
        for skeleton in self.skeletons:
            if skeleton.getRoot() == node:
                return skeleton
        return None


    def findSkeletonByJoint(self, node):
        for skeleton in self.skeletons:
            if skeleton.getJointIndex(node) != -1:
                return skeleton
        return None


