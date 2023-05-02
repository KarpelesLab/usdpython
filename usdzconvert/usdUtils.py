import os.path
from shutil import copyfile
import re
import math
from pxr import *


class ConvertError(Exception):
    pass

class ConvertExit(Exception):
    pass


def printError(message):
    print('  \033[91m' + 'Error: ' + message + '\033[0m')


def printWarning(message):
    print('  \033[93m' + 'Warning: ' + message + '\033[0m')


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
        print('Copying file: ' + srcFile + ' ' + dstFile)
    if os.path.isfile(srcFile):
        dstFolder = os.path.dirname(dstFile)
        if dstFolder != '' and not os.path.isdir(dstFolder):
            os.makedirs(dstFolder)
        copyfile(srcFile, dstFile)
    else:
        printWarning("can't find " + srcFile)


def resolvePath(textureFileName, folder, searchPaths=None):
    if textureFileName == '':
        return ''
    if os.path.isfile(textureFileName):
        return textureFileName

    if folder == '':
        folder = os.getcwd()

    path = textureFileName.replace('\\', '/')
    basename = os.path.basename(path)
    if os.path.isfile(folder + basename):
        return folder + basename

    # TODO: try more precise finding with folders info

    for root, dirnames, filenames in os.walk(folder):
        for filename in filenames:
            if filename == basename:
                return os.path.join(root, filename)

    if searchPaths is not None:
        for searchPath in searchPaths:
            for root, dirnames, filenames in os.walk(searchPath):
                for filename in filenames:
                    if filename == basename:
                        return os.path.join(root, filename)

    return textureFileName



class WrapMode:
    black = 'black'
    clamp = 'clamp'
    repeat = 'repeat'
    mirror = 'mirror'
    useMetadata = 'useMetadata'


def isWrapModeCorrect(mode):
    modes = [WrapMode.black, WrapMode.clamp, WrapMode.repeat, WrapMode.mirror, WrapMode.useMetadata]
    if mode in modes:
        return True
    return False


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
        self.beginTime = float('inf')
        self.endTime = float('-inf')
        self.timeCodesPerSecond = 24 # default for USD
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


    def setFPS(self, fps):
        # set one time code per frame
        self.timeCodesPerSecond = fps


    def extentTime(self, time):
        if math.isinf(self.endTime):
            self.beginTime = time
            self.endTime = time
            return
        if self.beginTime > time:
            self.beginTime = time
        if self.endTime < time:
            self.endTime = time


    def toTimeCode(self, time, extentTime=False):
        if extentTime:
            self.extentTime(time)
        real = time * self.timeCodesPerSecond
        round = int(real + 0.5)
        epsilon = 0.001
        if abs(real - round) < epsilon:
            return round
        return real


    def makeUniqueBlendShapeName(self, name, path):
        geomPath = self.getGeomPath()
        if len(path) > len(geomPath) and path[:len(geomPath)] == geomPath:
            path = path[len(geomPath):]

        blendShapeName = path.replace("/", ":") + ":" + name
        if blendShapeName[0] == ":":
            blendShapeName = blendShapeName[1:]
        return blendShapeName


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


    def finalize(self):
        if not math.isinf(self.endTime):
            self.usdStage.SetStartTimeCode(self.toTimeCode(self.beginTime))
            self.usdStage.SetEndTimeCode(self.toTimeCode(self.endTime))
            self.usdStage.SetTimeCodesPerSecond(self.timeCodesPerSecond)



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



class MapTransform:
    def __init__(self, translation, scale, rotation):
        self.translation = translation
        self.scale = scale
        self.rotation = rotation    



class Map:
    def __init__(self, channels, file, fallback=None, texCoordSet='st', wrapS=WrapMode.useMetadata, wrapT=WrapMode.useMetadata, scale=None, transform=None):
        self.file = file
        self.channels = channels
        self.fallback = fallback
        self.texCoordSet = texCoordSet
        self.textureShaderName = ''
        self.wrapS = wrapS
        self.wrapT = wrapT
        self.scale = scale
        self.transform = transform



class Material:
    def __init__(self, name):
        if name.find('/') != -1:
            self.path = makeValidPath(name)
            self.name = makeValidIdentifier(os.path.basename(name))
        else:
            self.path = ''
            self.name = makeValidIdentifier(name) if name != '' else ''
        self.inputs = {}
        self.opacityThreshold = None


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
        surfaceShader = self._createSurfaceShader(usdMaterial, asset.usdStage)

        if self.isEmpty():
            return usdMaterial

        self.updateUsdMaterial(usdMaterial, surfaceShader, asset.usdStage)
        return usdMaterial


    # private methods:

    def _createSurfaceShader(self, usdMaterial, usdStage):
        matPath = str(usdMaterial.GetPath())
        surfaceShader = UsdShade.Shader.Define(usdStage, matPath + '/surfaceShader')
        surfaceShader.CreateIdAttr('UsdPreviewSurface')
        surfaceOutput = surfaceShader.CreateOutput('surface', Sdf.ValueTypeNames.Token)
        usdMaterial.CreateOutput('surface', Sdf.ValueTypeNames.Token).ConnectToSource(surfaceOutput)
        if self.opacityThreshold is not None:
            surfaceShader.CreateInput('opacityThreshold', Sdf.ValueTypeNames.Float).Set(float(self.opacityThreshold))
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
                            # channel factors (scales) shouldn't be rewritten
                            split = (map.scale is not None and map2.scale is not None and
                                len(map.channels) == 1 and len(map2.channels) == 1 and
                                map.channels == map2.channels and map.scale != map2.scale)
                            if not split:
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

        # texture transform
        if map.transform != None:
            transformShaderPath = matPath + '/' + map.textureShaderName + '_transform2D'
            transformShader = UsdShade.Shader.Define(usdStage, transformShaderPath)
            transformShader.SetSdrMetadataByKey("role", "math")
            transformShader.CreateIdAttr('UsdTransform2d')
            transformShader.CreateInput('in', Sdf.ValueTypeNames.Float2).ConnectToSource(uvReader.GetOutput('result'))

            if map.transform.translation[0] != 0 or map.transform.translation[1] != 0:
                transformShader.CreateInput('translation', Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(map.transform.translation[0], map.transform.translation[1]))
            if map.transform.scale[0] != 1 or map.transform.scale[1] != 1:
                transformShader.CreateInput('scale', Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(map.transform.scale[0], map.transform.scale[1]))
            if map.transform.rotation != 0:
                transformShader.CreateInput('rotation', Sdf.ValueTypeNames.Float).Set(float(map.transform.rotation))

            transformShader.CreateOutput('result', Sdf.ValueTypeNames.Float2)
            uvReader = transformShader

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
                scaleInput = textureShader.GetInput('scale')
                if scaleInput is not None and scaleInput.Get() is not None:
                    gfScale = scaleInput.Get()
                if channels == 'rgb':
                    if isinstance(map.scale, list):
                        gfScale[0] = float(map.scale[0])
                        gfScale[1] = float(map.scale[1])
                        gfScale[2] = float(map.scale[2])
                    else:
                        printError('Scale value ' + map.scale + ' for ' + inputName + ' is incorrect.')
                        raise
                else:
                    gfScale[getIndexByChannel(channels)] = float(map.scale)
                if Gf.Vec4f(1) != gfScale: # skip default value
                    textureShader.CreateInput('scale', Sdf.ValueTypeNames.Float4).Set(gfScale)

        fileAndExt = os.path.splitext(map.file)
        if len(fileAndExt) == 1 or (fileAndExt[-1] != '.png' and fileAndExt[-1] != '.jpg'):
            printWarning('texture file ' + map.file + ' is not .png or .jpg')

        textureShader.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(map.file)
        textureShader.CreateInput('st', Sdf.ValueTypeNames.Float2).ConnectToSource(uvReader.GetOutput('result'))
        dataType = Sdf.ValueTypeNames.Float3 if len(channels) == 3 else Sdf.ValueTypeNames.Float
        textureShader.CreateOutput(channels, dataType)

        # wrapping mode
        if map.wrapS != WrapMode.useMetadata:
            textureShader.CreateInput('wrapS', Sdf.ValueTypeNames.Token).Set(map.wrapS)
        if map.wrapT != WrapMode.useMetadata:
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
                    printWarning('fallback value ' + map.fallback + ' for ' + inputName + ' is incorrect.')
            else:
                gfFallback[getIndexByChannel(channels)] = float(map.fallback)

            if inputName == InputName.normal:
                #normal map fallback is within 0 - 1
                gfFallback = 0.5*(gfFallback + Gf.Vec4f(1.0))
            if Gf.Vec4f(0, 0, 0, 1) != gfFallback: # skip default value
                textureShader.CreateInput('fallback', Sdf.ValueTypeNames.Float4).Set(gfFallback)

        return textureShader


    def _isDefaultValue(self, inputName):
        input = self.inputs[inputName]
        if isinstance(input, Map):
            return False

        if isinstance(input, list):
            gfVec3d = Gf.Vec3d(float(input[0]), float(input[1]), float(input[2]))
            if InputName.diffuseColor == inputName and gfVec3d == Gf.Vec3d(0.18, 0.18, 0.18):
                return True
            if InputName.emissiveColor == inputName and gfVec3d == Gf.Vec3d(0, 0, 0):
                return True
            if InputName.normal == inputName and gfVec3d == Gf.Vec3d(0, 0, 1.0):
                return True
        else:
            if InputName.metallic == inputName and float(input) == 0.0:
                return True
            if InputName.roughness == inputName and float(input) == 0.5:
                return True
            if InputName.clearcoat == inputName and float(input) == 0.0:
                return True
            if InputName.clearcoatRoughness == inputName and float(input) == 0.01:
                return True
            if InputName.opacity == inputName and float(input) == 1.0:
                return True
            if InputName.occlusion == inputName and float(input) == 1.0:
                return True
        return False


    def _addMapToUsdMaterial(self, inputIdx, usdMaterial, surfaceShader, usdStage):
        inputName = Input.names[inputIdx]
        if inputName not in self.inputs:
            return

        if self._isDefaultValue(inputName):
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
            surfaceShader.CreateInput(inputName, inputType).ConnectToSource(textureShader.GetOutput(channels))
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

    def overrideGetWorldTransformGfMatrix4d(self, node):
        pass

    def overrideGetParent(self, node):
        pass


    def getCommonParent(self, node1, node2):
        parent1 = node1
        while parent1 is not None:
            parent2 = node2
            while parent2 is not None:
                if parent1 == parent2:
                    return parent2
                parent2 = self.overrideGetParent(parent2)
            parent1 = self.overrideGetParent(parent1)
        return None


    def findRoot(self, nodes):
        if len(nodes) == 0:
            return None
        if len(nodes) == 1:
            return nodes[0]
        parent = nodes[0]
        for i in range(1, len(nodes)):
            parent = self.getCommonParent(parent, nodes[i])
        return parent



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


    def makeUsdSkeleton(self, usdStage, sdfPath, nodeManager):
        if self.usdSkeleton is not None:
            return self.usdSkeleton
        self.sdfPath = sdfPath
        jointPaths = []
        restMatrices = []
        bindMatrices = []
        for joint in self.joints:
            if joint is None:
                continue
            jointPaths.append(self.jointPaths[joint])
            restMatrices.append(self.restMatrices[joint])
            if joint in self.bindMatrices:
                bindMatrices.append(self.bindMatrices[joint])
            else:
                bindMatrices.append(nodeManager.overrideGetWorldTransformGfMatrix4d(joint))

        usdGeom = UsdSkel.Root.Define(usdStage, sdfPath)

        self.usdSkeleton = UsdSkel.Skeleton.Define(usdStage, sdfPath + '/Skeleton')
        self.usdSkeleton.CreateJointsAttr(jointPaths)
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
            printWarning('trying to assign Skeletal Animation before USD Skeleton has been created.')
            return

        usdSkelBinding = UsdSkel.BindingAPI(self.usdSkeleton)
        usdSkelBinding.CreateAnimationSourceRel().AddTarget(usdSkelAnim.GetPath())
        self.usdSkelAnim = usdSkelAnim


    # private:
    def _collectJoints(self, node, path, nodeManager):
        self.joints.append(node)
        name = nodeManager.overrideGetName(node)
        newPath = path + name
        self.jointPaths[node] = newPath
        self.restMatrices[node] = nodeManager.overrideGetLocalTransformGfMatrix4d(node)
        for child in nodeManager.overrideGetChildren(node):
            self._collectJoints(child, newPath + '/', nodeManager)


class Skinning:
    def __init__(self, nodeManager):
        self.skins = []
        self.skeletons = []
        self.nodeManager = nodeManager
        self.joints = {} # joint set


    def createSkeleton(self, root):
        skeleton = Skeleton()
        skeleton._collectJoints(root, '', self.nodeManager)
        self.skeletons.append(skeleton)
        return skeleton


    def createSkeletonsFromSkins(self):
        for skin in self.skins:
            if len(skin.joints) < 1:
                continue
            if skin.root == None:
                skin.root = self.nodeManager.findRoot(skin.joints)
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



class BlendShape:
    def __init__(self, weightsCount):
        self.weightsCount = weightsCount
        self.usdSkeleton = None
        self.usdSkelAnim = None
        self.sdfPath = None
        self.skeleton = None
        self.blendShapeList = []


    def makeUsdSkeleton(self, usdStage, sdfPath):
        if self.usdSkeleton is not None:
            return self.usdSkeleton
        self.sdfPath = sdfPath

        usdGeom = UsdSkel.Root.Define(usdStage, sdfPath)

        self.usdSkeleton = UsdSkel.Skeleton.Define(usdStage, sdfPath + '/Skeleton')

        usdSkelBlendShapeBinding = UsdSkel.BindingAPI(usdGeom)
        usdSkelBlendShapeBinding.CreateSkeletonRel().AddTarget("Skeleton")

        return usdGeom


    def setSkeletalAnimation(self, usdSkelAnim):
        if self.usdSkelAnim != None:
            # default animation is the first one
            return

        if self.usdSkeleton is None:
            printWarning('trying to assign Skeletal Animation before USD Skeleton has been created.')
            return

        usdSkelBinding = UsdSkel.BindingAPI(self.usdSkeleton)
        usdSkelBinding.CreateAnimationSourceRel().AddTarget(usdSkelAnim.GetPath())
        self.usdSkelAnim = usdSkelAnim


    def addBlendShapeList(self, blendShapeList):
        # TODO: combine lists?
        self.blendShapeList = blendShapeList



class ShapeBlending:
    def __init__(self):
        self.blendShapes = []


    def createBlendShape(self, weightsCount):
        blendShape = BlendShape(weightsCount)
        self.blendShapes.append(blendShape)
        return blendShape


    def flush(self):
        for blendShape in self.blendShapes:
            if blendShape.usdSkelAnim is not None:
                blendShape.usdSkelAnim.CreateBlendShapesAttr(blendShape.blendShapeList)


