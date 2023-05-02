#!/usr/bin/python
from pxr import *

import json
import struct
import numpy
import os.path
import base64

import usdUtils

__all__ = ['usdStageWithGlTF']


class glTFComponentType:
    BYTE = 5120
    UNSIGNED_BYTE = 5121
    SHORT = 5122
    UNSIGNED_SHORT = 5123
    UNSIGNED_INT = 5125
    FLOAT = 5126

    def __init__(self, type):
        self.type = type

    def unpackFormat(self):
        return {
            glTFComponentType.BYTE: numpy.uint8,
            glTFComponentType.UNSIGNED_BYTE: numpy.uint8,
            glTFComponentType.SHORT: numpy.int16,
            glTFComponentType.UNSIGNED_SHORT: numpy.uint16,
            glTFComponentType.UNSIGNED_INT: numpy.uint32,
            glTFComponentType.FLOAT: numpy.float32
            } [self.type]


class glFTTextureFilter: # TODO: support
    NEAREST = 9728
    LINEAR = 9729
    NEAREST_MIPMAP_NEAREST = 9984
    LINEAR_MIPMAP_NEAREST = 9985
    NEAREST_MIPMAP_LINEAR = 9986
    LINEAR_MIPMAP_LINEAR = 9987


class glTFWrappingMode:
    CLAMP_TO_EDGE = 33071
    MIRRORED_REPEAT = 33648
    REPEAT = 10497

    def __init__(self, mode):
        self.mode = mode

    def usdMode(self):
        return {
            glTFWrappingMode.CLAMP_TO_EDGE: 'clamp',
            glTFWrappingMode.MIRRORED_REPEAT: 'mirror',
            glTFWrappingMode.REPEAT: 'repeat'
            } [self.mode]



def loadChunk(file, format):
    size = struct.calcsize(format)
    unpack = struct.Struct(format).unpack_from
    return unpack(file.read(size))


def time2Code(time):
    fps = 24
    return int(time * fps + 0.5)


def numOfComponents(strType):
    if strType == 'VEC2':
        return 2
    elif strType == 'VEC3':
        return 3
    elif strType == 'VEC4':
        return 4
    elif strType == 'MAT4':
        return 16
    return 1


def getName(dict, template, id):
    if 'name' in dict and len(dict['name']) != 0:
        validName = usdUtils.makeValidIdentifier(dict['name'])
        if validName != 'defaultIdentifier':
            return validName
    return template + str(id)


def getInt(dict, key):
    if key in dict:
        return dict[key]
    return 0


def getVec3(v):
    return Gf.Vec3d(v[0], v[1], v[2])


def getVec4(v):
    if len(v) == 4:
        return Gf.Vec4d(v[0], v[1], v[2], v[3])
    return Gf.Vec4d(v[0], v[1], v[2], 1)


def getQuat(v):
    return Gf.Quatf(v[3], Gf.Vec3f(v[0], v[1], v[2]))


def getMatrix(m):
    return Gf.Matrix4d((m[0], m[1], m[2], m[3]), (m[4], m[5], m[6], m[7]), (m[8], m[9], m[10], m[11]), (m[12], m[13], m[14], m[15]))


def getMatrixTransform(gltfNode):
    if 'matrix' in gltfNode:
        matrix = getMatrix(gltfNode['matrix'])
    else:
        if 'scale' in gltfNode:
            matrix = Gf.Matrix4d(getVec4(gltfNode['scale']))
        else:
            matrix = Gf.Matrix4d(1)

        if 'rotation' in gltfNode:
            matRot = Gf.Matrix4d()
            matRot.SetRotate(getQuat(gltfNode['rotation']))
            matrix = matrix * matRot

        if 'translation' in gltfNode:
            matTr = Gf.Matrix4d()
            matTr.SetTranslate(getVec3(gltfNode['translation']))
            matrix = matrix * matTr 
    return matrix


def getTransformTranslation(gltfNode):
    if 'translation' in gltfNode:
        translation = gltfNode['translation']
        return Gf.Vec3f(translation[0], translation[1], translation[2])
    else:
        return Gf.Vec3f(0, 0, 0) # TODO: support decomposition?


def getTransformRotation(gltfNode):
    if 'rotation' in gltfNode:
        rotation = gltfNode['rotation']
        return Gf.Quatf(rotation[3], Gf.Vec3f(rotation[0], rotation[1], rotation[2]))
    else:
        return Gf.Quatf(1, Gf.Vec3f(0, 0, 0)) # TODO: support decomposition?


def getTransformScale(gltfNode):
    if 'scale' in gltfNode:
        scale = gltfNode['scale']
        return Gf.Vec3f(scale[0], scale[1], scale[2])
    else:
        return Gf.Vec3f(1, 1, 1) # TODO: support decomposition?


def getAnimValue(animJointComp, time):
    if time in animJointComp:
        return animJointComp[time]

    # find neighbor keys for time
    # to get an interpolated value
    lessMaxTime = -1
    greaterMinTime = -1
    for t in animJointComp:
        if t < time:
            if lessMaxTime == -1:
                lessMaxTime = t
            elif lessMaxTime < t:
                lessMaxTime = t
        elif t > time:
            if greaterMinTime == -1:
                greaterMinTime = t
            elif greaterMinTime > t:
                greaterMinTime = t

    if lessMaxTime == -1:
        return animJointComp[greaterMinTime]
    if greaterMinTime == -1:
        return animJointComp[lessMaxTime]

    l = float(time - lessMaxTime) / (greaterMinTime - lessMaxTime)
    g = float(greaterMinTime - time) / (greaterMinTime - lessMaxTime)

    return g * animJointComp[lessMaxTime] + l * animJointComp[greaterMinTime]


def getXformOp(usdGeom, type):
    ops = usdGeom.GetOrderedXformOps()
    for op in ops:
        if op.GetOpType() == type:
            return op
    return None



class glTFNodeManager(usdUtils.NodeManager):
    def __init__(self, gltfNodes):
        usdUtils.NodeManager.__init__(self)
        self.gltfNodes = gltfNodes


    def overrideGetName(self, strNodeIdx):
        # TODO: make sure there is no duplicate names
        nodeIdx = int(strNodeIdx)
        gltfNode = self.gltfNodes[nodeIdx]
        return getName(gltfNode, 'node_', nodeIdx)


    def overrideGetChildren(self, strNodeIdx):
        children = []
        gltfNode = self.gltfNodes[int(strNodeIdx)]
        if 'children' in gltfNode:
            for child in gltfNode['children']:
                children.append(str(child))
        return children


    def overrideGetLocalTransformGfMatrix4d(self, strNodeIdx):
        gltfNode = self.gltfNodes[int(strNodeIdx)]
        return getMatrixTransform(gltfNode)


class Accessor:
    def __init__(self, gltfData, accessorIdx):
        gltfAccessor = gltfData.gltf['accessors'][accessorIdx]
        accessorByteOffset = getInt(gltfAccessor, 'byteOffset')
        self.componentType = int(gltfAccessor['componentType'])
        fmt = glTFComponentType(self.componentType).unpackFormat()

        bufferViewIdx = gltfAccessor['bufferView']
        bufferView = gltfData.gltf['bufferViews'][bufferViewIdx]
        byteLength = bufferView['byteLength']
        byteOffset = getInt(bufferView, 'byteOffset')
        bufferIdx = bufferView['buffer']

        fileContent = gltfData.buffers[bufferIdx]
        offset = accessorByteOffset + byteOffset

        self.count = gltfAccessor['count']
        self.type = gltfAccessor['type']
        self.components = numOfComponents(self.type)
        self.data = numpy.frombuffer(fileContent, fmt, self.count * self.components, offset)



class glTFConverter:
    def __init__(self, gltfPath, usdPath, verbose=0):
        self.usdStage = None
        self.buffers = []
        self.gltf = None
        self.usdGeoms = {}
        self.usdMaterials = []
        self.usdSkelAnims = []
        self.nodeNames = {} # to avoid duplicate node names
        self.verbose = verbose
        self._worldTransforms = {} # use self.getWorldTransform(nodeIdx)
        self._parents = {} # use self.getParent(nodeIdx)

        filenameFull = gltfPath.split('/')[-1]
        self.srcFolder = gltfPath[:len(gltfPath)-len(filenameFull)]

        filenameFull = usdPath.split('/')[-1]
        self.dstFolder = usdPath[:len(usdPath)-len(filenameFull)]

        self.asset = usdUtils.Asset(usdPath)

        self.load(gltfPath)
        self.readAllBuffers()

        self.nodeMan = glTFNodeManager(self.gltf['nodes'])
        self.skinning = usdUtils.Skinning(self.nodeMan)

        self.postponeUsdMeshToSkeleton = {} # if USD mesh created before UsdSkeleton, bind it later 


    def load(self, gltfPath):
        fileAndExt = os.path.splitext(gltfPath)
        if len(fileAndExt) == 2 and fileAndExt[1].lower() == '.glb':
            with open(gltfPath, "rb") as file:
                (magic, version, length) = loadChunk(file, '=3i')
                (jsonLen, jsonType) = loadChunk(file, '=2i')
                self.gltf = json.loads(file.read(jsonLen))
                (bufferLen, bufferType) = loadChunk(file, '=2i')
                self.buffers.append(file.read())
        else:
            with open(gltfPath) as file:
                self.gltf = json.load(file)


    def _fillWorldTransforms(self, children, parentWorldTransform):
        for nodeIdx in children:
            gltfNode = self.gltf['nodes'][nodeIdx]
            worldTransform =  getMatrixTransform(gltfNode) * parentWorldTransform
            self._worldTransforms[str(nodeIdx)] = worldTransform
            if 'children' in gltfNode:
                self._fillWorldTransforms(gltfNode['children'], worldTransform)


    def getWorldTransform(self, nodeIdx):
        if nodeIdx == -1:
            return Gf.Matrix4d(1)
        if not self._worldTransforms:
            self._fillWorldTransforms(self.gltf['scenes'][0]['nodes'], Gf.Matrix4d(1))
        return self._worldTransforms[str(nodeIdx)]


    def _fillParents(self, children, parentId):
        for nodeIdx in children:
            gltfNode = self.gltf['nodes'][nodeIdx]
            self._parents[str(nodeIdx)] = parentId
            if 'children' in gltfNode:
                self._fillParents(gltfNode['children'], nodeIdx)


    def getParent(self, nodeIdx):
        if nodeIdx == -1:
            return -1
        if not self._parents:
            self._fillParents(self.gltf['scenes'][0]['nodes'], -1)
        return self._parents[str(nodeIdx)]


    def saveTexture(self, content, mimeType, textureIdx):
        if not os.path.isdir(self.dstFolder + 'textures'):
            os.mkdir(self.dstFolder + 'textures')

        ext = '.png'
        if mimeType == 'image/jpeg':
            ext = '.jpg'
        filename = 'textures/texgen_' + str(textureIdx) + ext
        
        newfile = open(self.dstFolder + filename, 'wb')
        newfile.write(content)
        return filename


    def saveTextureWithImage(self, image, textureIdx):
        bufferViewIdx = image['bufferView']
        bufferView = self.gltf['bufferViews'][bufferViewIdx]
        byteLength = bufferView['byteLength']
        byteOffset = getInt(bufferView, 'byteOffset')
        bufferIdx = bufferView['buffer']

        buffer = self.buffers[bufferIdx]
        content = numpy.frombuffer(buffer, numpy.uint8, byteLength, byteOffset)
        return self.saveTexture(content, image['mimeType'], textureIdx)


    def processTexture(self, dict, type, inputName, channels, material, scale = None):
        if type not in dict:
            return False

        gltfMaterialMap = dict[type]
        textureIdx = gltfMaterialMap['index']
        texCoordSet = gltfMaterialMap['texCoord'] if 'texCoord' in gltfMaterialMap else 0
        gltfTexture = self.gltf['textures'][textureIdx]
        sourceIdx = gltfTexture['source']
        image = self.gltf['images'][sourceIdx]

        textureFilename = ''
        if 'uri' in image:
            uri = image['uri']
            if len(uri) > 5 and uri[:5] == 'data:':
                # embedded texture
                for offset in range(5, len(uri) - 6):
                    if uri[offset:(offset+6)] == 'base64':
                        mimeType = uri[5:(offset-1)] if offset > 6 else ''
                        content = base64.b64decode(uri[(offset + 6):])
                        textureFilename = self.saveTexture(content, mimeType, textureIdx)
                        break
            else:
                srcTextureFilename = uri
                textureFilename = usdUtils.makeValidPath(srcTextureFilename)
                filenameAndExt = os.path.splitext(textureFilename)
                ext = filenameAndExt[1].lower()
                if '.jpeg' == ext:
                    ext = '.jpg'
                    filename = filenameAndExt[0]
                    usdUtils.copy(self.srcFolder + srcTextureFilename, self.dstFolder + filename + ext, self.verbose)
                    textureFilename = filename + ext
                elif self.srcFolder != self.dstFolder:
                    usdUtils.copy(self.srcFolder + srcTextureFilename, self.dstFolder + textureFilename, self.verbose)

        elif 'mimeType' in image and 'bufferView' in image:
            textureFilename = self.saveTextureWithImage(image, textureIdx)

        if textureFilename == '':
            return False

        wrapS = 'repeat' # default for glTF
        wrapT = 'repeat' # default for glTF

        # Wrapping mode
        if 'sampler' in gltfTexture:
            samplerIdx = gltfTexture['sampler']
            gltfSampler = self.gltf['samplers'][samplerIdx]
            if 'wrapS' in gltfSampler:
                wrapS = glTFWrappingMode(gltfSampler['wrapS']).usdMode()
            if 'wrapT' in gltfSampler:
                wrapT = glTFWrappingMode(gltfSampler['wrapT']).usdMode()

        primvarName = 'st' if texCoordSet == 0 else 'st' + str(texCoordSet)
        material.inputs[inputName] = usdUtils.Map(channels, textureFilename, None, primvarName, wrapS, wrapT, scale)
        return True


    def readAllBuffers(self):
        for buffer in self.gltf['buffers']:
            if 'uri' in buffer:
                uri = buffer['uri']
                if len(uri) > 5 and uri[:5] == 'data:':
                    for offset in range(5, len(uri) - 6):
                        if uri[offset:(offset+6)] == 'base64':
                            fileContent = base64.b64decode(uri[(offset + 6):])
                            self.buffers.append(fileContent)
                            break
                else:
                    bufferFileName = self.srcFolder + uri
                    with open(bufferFileName, mode='rb') as file:
                        fileContent = file.read()
                    self.buffers.append(fileContent)


    def textureHasAlpha(self, filename):
        filenameAndExt = os.path.splitext(filename)
        ext = filenameAndExt[1].lower()
        if '.jpg' == ext:
            return False
        return True


    def createMaterials(self):
        for gltfMaterial in self.gltf['materials'] if 'materials' in self.gltf else []:
            matName = getName(gltfMaterial, 'material_', len(self.usdMaterials))
            material = usdUtils.Material(matName)

            isBlend = False
            if 'alphaMode' in gltfMaterial and gltfMaterial['alphaMode'] == 'BLEND':
                isBlend = True

            pbr = None
            if 'pbrMetallicRoughness' in gltfMaterial:
                pbr = gltfMaterial['pbrMetallicRoughness']

                # diffuse color and opacity
                baseColorFactor = pbr['baseColorFactor'] if 'baseColorFactor' in pbr else [1, 1, 1, 1]
                baseColorScale = [baseColorFactor[0], baseColorFactor[1], baseColorFactor[2]]
                opacityScale = baseColorFactor[3]
                if self.processTexture(pbr, 'baseColorTexture', usdUtils.InputName.diffuseColor, 'rgb', material, baseColorScale):
                    if isBlend:
                        map = material.inputs[usdUtils.InputName.diffuseColor]
                        if self.textureHasAlpha(map.file):
                            self.processTexture(pbr, 'baseColorTexture', usdUtils.InputName.opacity, 'a', material, opacityScale)
                        else:
                            material.inputs[usdUtils.InputName.opacity] = baseColorFactor[3]
                else:
                    material.inputs[usdUtils.InputName.diffuseColor] = baseColorFactor
                    if isBlend:
                        material.inputs[usdUtils.InputName.opacity] = baseColorFactor[3]
                
                # metallic and roughness
                roughnessFactor = pbr['roughnessFactor'] if 'roughnessFactor' in pbr else 1.0
                metallicFactor = pbr['metallicFactor'] if 'metallicFactor' in pbr else 1.0
                if 'metallicRoughnessTexture' in pbr:
                    self.processTexture(pbr, 'metallicRoughnessTexture', usdUtils.InputName.roughness, 'g', material, roughnessFactor)
                    self.processTexture(pbr, 'metallicRoughnessTexture', usdUtils.InputName.metallic, 'b', material, metallicFactor)
                else:
                    material.inputs[usdUtils.InputName.roughness] = roughnessFactor
                    material.inputs[usdUtils.InputName.metallic] = metallicFactor

            elif 'extensions' in gltfMaterial and 'KHR_materials_pbrSpecularGlossiness' in gltfMaterial['extensions']:
                if self.verbose:
                    print "Warning: specular/glossiness workflow is not fully supported."
                pbrSG = gltfMaterial['extensions']['KHR_materials_pbrSpecularGlossiness']
                diffuseScale = None
                opacityScale = None
                if 'diffuseFactor' in pbrSG:
                    diffuseFactor = pbrSG['diffuseFactor']
                    diffuseScale = [diffuseFactor[0], diffuseFactor[1], diffuseFactor[2]]
                    opacityScale = diffuseFactor[3]
                if self.processTexture(pbrSG, 'diffuseTexture', usdUtils.InputName.diffuseColor, 'rgb', material, diffuseScale):
                    if isBlend:
                        map = material.inputs[usdUtils.InputName.diffuseColor]
                        if self.textureHasAlpha(map.file):
                            self.processTexture(pbrSG, 'diffuseTexture', usdUtils.InputName.opacity, 'a', material, opacityScale)
                        else:
                            material.inputs[usdUtils.InputName.opacity] = opacityScale
                else:
                    if diffuseScale:
                        material.inputs[usdUtils.InputName.diffuseColor] = diffuseScale
                    if isBlend and opacityScale:
                        material.inputs[usdUtils.InputName.opacity] = opacityScale

            self.processTexture(gltfMaterial, 'normalTexture', usdUtils.InputName.normal, 'rgb', material)
            self.processTexture(gltfMaterial, 'occlusionTexture', usdUtils.InputName.occlusion, 'r', material) #TODO: add occlusion scale

            emissiveFactor = gltfMaterial['emissiveFactor'] if 'emissiveFactor' in gltfMaterial else [0.0, 0.0, 0.0]
            if not self.processTexture(gltfMaterial, 'emissiveTexture', usdUtils.InputName.emissiveColor, 'rgb', material, emissiveFactor):
                if gltfMaterial != None and 'emissiveFactor' in gltfMaterial:
                    material.inputs[usdUtils.InputName.emissiveColor] = gltfMaterial['emissiveFactor']

            usdMaterial = material.makeUsdMaterial(self.asset)
            self.usdMaterials.append(usdMaterial)


    def prepareSkinning(self):
        if 'skins' not in self.gltf:
            return

        for skinIdx in range(len(self.gltf['skins'])):
            gltfSkin = self.gltf['skins'][skinIdx]

            rootIdx = gltfSkin['skeleton'] if 'skeleton' in gltfSkin else gltfSkin['joints'][0]
            skin = usdUtils.Skin(str(rootIdx))

            gltfJoints = gltfSkin['joints']
            for jointIdx in gltfJoints:
                joint = str(jointIdx)
                skin.joints.append(joint)

            # get bind matrices
            bindMatAcc = Accessor(self, gltfSkin['inverseBindMatrices'])
            m = bindMatAcc.data
            i = 0
            for jointIdx in gltfJoints:
                mat = Gf.Matrix4d(
                    float(m[i + 0]), float(m[i + 1]), float(m[i + 2]), float(m[i + 3]),
                    float(m[i + 4]), float(m[i + 5]), float(m[i + 6]), float(m[i + 7]),
                    float(m[i + 8]), float(m[i + 9]), float(m[i +10]), float(m[i +11]),
                    float(m[i +12]), float(m[i +13]), float(m[i +14]), float(m[i +15]))
                skin.bindMatrices[str(jointIdx)] = mat.GetInverse()
                i += bindMatAcc.components

            self.skinning.skins.append(skin)
        self.skinning.createSkeletonsFromSkins()


    def findSkeletonForAnimation(self, gltfAnim):
        for gltfChannel in gltfAnim['channels']:
            gltfTarget = gltfChannel['target']
            nodeIdx = gltfTarget['node']
            skeleton = self.skinning.findSkeletonByJoint(str(nodeIdx))
            return skeleton
        return None


    def processSkeletonAnimation(self):
        for gltfAnim in self.gltf['animations'] if 'animations' in self.gltf else []:

            skeleton = self.findSkeletonForAnimation(gltfAnim)
            if skeleton is None:
                continue

            name = getName(gltfAnim, 'skelAnim_', len(self.usdSkelAnims))

            # animJoints is a matrix of all animated values with time keys
            # animJoints is a dictionary with joint ids as keys
            # each element of animJoints has a three elements list: [0] -- translations, [1] -- rotations, [2] -- scales
            # each of it has a dictionary with time keys {0: value, 1: next value... }
            animJoints = {}

            gltfNodes = self.gltf['nodes']
            minTime = 999999
            maxTime = -1

            # Fill animJoints
            for gltfChannel in gltfAnim['channels']:
                gltfTarget = gltfChannel['target']
                strNodeIdx = str(gltfTarget['node'])

                if skeleton.getJointIndex(strNodeIdx) == -1:
                    if self.verbose:
                        print "  Warning: Skeletal animation contains node animation"
                    continue

                targetPath = gltfTarget['path']

                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                interpolation = gltfSampler['interpolation']

                keyTimesAcc = Accessor(self, gltfSampler['input'])
                keyValuesAcc = Accessor(self, gltfSampler['output'])
                v = keyValuesAcc.data

                if strNodeIdx not in animJoints:
                    animJoints[strNodeIdx] = [None] * 3

                values = {}

                if targetPath == 'scale':
                    for el in xrange(keyTimesAcc.count):
                        time = time2Code(keyTimesAcc.data[el])
                        p = el * keyValuesAcc.components
                        values[time] = Gf.Vec3f(float(v[p]), float(v[p + 1]), float(v[p + 2]))
                        minTime = min(minTime, time)
                        maxTime = max(maxTime, time)
                    animJoints[strNodeIdx][2] = values
                elif targetPath == 'rotation':
                    for el in xrange(keyTimesAcc.count):
                        time = time2Code(keyTimesAcc.data[el])
                        p = el * keyValuesAcc.components
                        values[time] = Gf.Quatf(float(v[p + 3]), Gf.Vec3f(float(v[p]), float(v[p + 1]), float(v[p + 2])))
                        animJoints[strNodeIdx][1] = values
                        minTime = min(minTime, time)
                        maxTime = max(maxTime, time)
                elif targetPath == 'translation':
                    for el in xrange(keyTimesAcc.count):
                        time = time2Code(keyTimesAcc.data[el])
                        p = el * keyValuesAcc.components
                        values[time] = Gf.Vec3f(float(v[p]), float(v[p + 1]), float(v[p + 2]))
                        animJoints[strNodeIdx][0] = values
                        minTime = min(minTime, time)
                        maxTime = max(maxTime, time)
                else:
                    if self.verbose:
                        print "  Warning: Skeletal animation: unsupported target path:", targetPath

            if len(animJoints) == 0:
                continue

            animationPath = self.asset.getAnimationsPath() + '/' + name
            usdSkelAnim = UsdSkel.Animation.Define(self.usdStage, animationPath)

            jointPaths = []
            for joint in skeleton.joints:
                if joint in animJoints:
                    jointPaths.append(skeleton.jointPaths[joint])

            usdSkelAnim.CreateJointsAttr().Set(jointPaths)

            scaleAttr = usdSkelAnim.CreateScalesAttr()
            rotateAttr = usdSkelAnim.CreateRotationsAttr()
            translateAttr = usdSkelAnim.CreateTranslationsAttr()

            for time in range(minTime, maxTime + 1):
                translations = []
                rotations = []
                scales = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        animJoint = animJoints[joint]
                        if animJoint[0]:
                            translations.append(getAnimValue(animJoint[0], time))
                        else:
                            translations.append(getTransformTranslation(gltfNodes[int(joint)]))
                        if animJoint[1]:
                            rotations.append(getAnimValue(animJoint[1], time))
                        else:
                            rotations.append(getTransformRotation(gltfNodes[int(joint)]))
                        if animJoint[2]:
                            scales.append(getAnimValue(animJoint[2], time))
                        else:
                            scales.append(getTransformScale(gltfNodes[int(joint)]))
                if len(scales):
                    scaleAttr.Set(scales, Usd.TimeCode(time))
                if len(rotations):
                    rotateAttr.Set(rotations, Usd.TimeCode(time))
                if len(translations):
                    translateAttr.Set(translations, Usd.TimeCode(time))

            skeleton.setSkeletalAnimation(usdSkelAnim)
            self.usdSkelAnims.append(usdSkelAnim)


    def processPrimitive(self, nodeIdx, gltfPrimitive, path, skinIdx, skeleton):
        gltfPrimitiveMode_TRIANGLES = 4
        usdMesh = UsdGeom.Mesh.Define(self.usdStage, path)
        if 'mode' in gltfPrimitive and gltfPrimitive['mode'] != gltfPrimitiveMode_TRIANGLES:
            print 'Warning: only TRIANGLES as primitive.mode is supported.'
            return usdMesh

        usdSkelBinding = None
        skin = None
        if skinIdx != -1:
            skin = self.skinning.skins[skinIdx]
            if skin.skeleton is not None:
                usdSkelBinding = UsdSkel.BindingAPI(usdMesh)
                differenceTransform = Gf.Matrix4d(1)
                usdSkelBinding.CreateGeomBindTransformAttr(differenceTransform)
                if skin.skeleton.usdSkeleton is not None:
                    usdSkelBinding.CreateSkeletonRel().AddTarget(skin.skeleton.usdSkeleton.GetPath())
                else:
                    self.postponeUsdMeshToSkeleton[usdMesh] = skin
        elif skeleton is not None:
            differenceTransform = Gf.Matrix4d(1)
            if str(nodeIdx) in skeleton.bindMatrices:
                skelRootParentWorldTransform = self.getWorldTransform(self.getParent(skeleton.getRoot()))
                meshNodeWorldMatrix = self.getWorldTransform(nodeIdx)
                differenceTransform = meshNodeWorldMatrix * skelRootParentWorldTransform.GetInverse()
            skeleton.bindRigidDeformation(str(nodeIdx), usdMesh, differenceTransform)

        attributes = gltfPrimitive['attributes']

        count = 0 # for geometry without indices
        for key in attributes:
            accessor = Accessor(self, attributes[key])

            if key == 'POSITION':
                usdMesh.CreatePointsAttr(accessor.data)
                count = accessor.count
            elif key == 'NORMAL':
                usdMesh.CreateNormalsAttr(accessor.data)
                usdMesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
            elif key == 'TANGENT':
                pass
            elif key[0:8] == 'TEXCOORD':
                if accessor.componentType != glTFComponentType.FLOAT:
                    if self.verbose:
                        print 'Warnig: component type', accessor.componentType, 'is not supported for texture coordinates'
                    break
                # Y-component of texture coordinates should be flipped
                newData = []
                for el in xrange(accessor.count):
                    newData.append((
                        float(accessor.data[el * accessor.components]),
                        float(1.0 - accessor.data[el * accessor.components + 1])))

                texCoordSet = key[9:]
                primvarName = 'st' if texCoordSet == '0' else 'st' + texCoordSet
                uvs = usdMesh.CreatePrimvar(primvarName, Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
                uvs.Set(newData)
            elif key == 'COLOR_0':
                data = accessor.data
                if accessor.type == 'VEC4':
                    # displayColor for USD should have Color3Array type
                    newData = []
                    for el in xrange(accessor.count):
                        newData.append((
                            float(data[el * accessor.components]),
                            float(data[el * accessor.components + 1]),
                            float(data[el * accessor.components + 2])))
                    data = newData
                usdMesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex).Set(data)
            elif key =='JOINTS_0':
                if usdSkelBinding != None:
                    newData = [0] * accessor.count * accessor.components
                    for i in range(accessor.count * accessor.components):
                        newData[i] = skin.remapIndex(accessor.data[i])
                    usdSkelBinding.CreateJointIndicesPrimvar(False, accessor.components).Set(newData)
            elif key =='WEIGHTS_0':
                if usdSkelBinding != None:
                    # Normalize weights
                    newData = Vt.FloatArray(map(float, accessor.data))
                    UsdSkel.NormalizeWeights(newData, accessor.components)
                    usdSkelBinding.CreateJointWeightsPrimvar(False, accessor.components).Set(newData)
            else:
                print "Warning: Unsupported primitive attribute:", key

        if 'indices' in gltfPrimitive:
            accessor = Accessor(self, gltfPrimitive['indices'])
            usdMesh.CreateFaceVertexIndicesAttr(accessor.data)
            count = accessor.count
        elif count > 0:
            count = int(count / 3) * 3 # should be divisible by 3
            indices = [0] * count
            for ind in xrange(count):
                indices[ind] = ind
            usdMesh.CreateFaceVertexIndicesAttr(indices)

        numFaceVertexCounts = count / 3
        faceVertexCounts = [3] * numFaceVertexCounts
        usdMesh.CreateFaceVertexCountsAttr(faceVertexCounts) # per-face vertex indices

        # bind material to mesh
        if 'material' in gltfPrimitive:
            materialIdx = gltfPrimitive['material']
            UsdShade.MaterialBindingAPI(usdMesh.GetPrim()).Bind(self.usdMaterials[materialIdx])

            gltfMaterial = self.gltf['materials'][materialIdx]
            if 'doubleSided' in gltfMaterial and gltfMaterial['doubleSided'] == True:
                doubleSidedAttr = usdMesh.CreateDoubleSidedAttr()
                doubleSidedAttr.Set(True)

        usdMesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        return usdMesh


    #TODO: Support instansing
    def processMesh(self, nodeIdx, path, underSkeleton):
        gltfNode = self.gltf['nodes'][nodeIdx]
        meshIdx = gltfNode['mesh']
        gltfMesh = self.gltf['meshes'][meshIdx]

        skinIdx = gltfNode['skin'] if 'skin' in gltfNode else -1

        gltfPrimitives = gltfMesh['primitives']

        if len(gltfPrimitives) == 1:
            usdGeom = self.processPrimitive(nodeIdx, gltfPrimitives[0], path, skinIdx, underSkeleton)
        else:
            usdGeom = UsdGeom.Xform.Define(self.usdStage, path)
            for i in xrange(len(gltfPrimitives)):
                newPrimitivePath = path + '/primitive_' + str(i)
                self.processPrimitive(nodeIdx, gltfPrimitives[i], newPrimitivePath, skinIdx, underSkeleton)

        return usdGeom


    def processNode(self, nodeIdx, path, underSkeleton, indent):
        gltfNode = self.gltf['nodes'][nodeIdx]

        skeletonByJoint = self.skinning.findSkeletonByJoint(str(nodeIdx))

        name = getName(gltfNode, 'node_', nodeIdx)
        if name in self.nodeNames:
            name = name + '_' + str(nodeIdx)
        self.nodeNames[name] = name

        if skeletonByJoint is not None and skeletonByJoint.sdfPath:
            # collapse object hierarchy inside skeleton
            newPath = skeletonByJoint.sdfPath + '/' + name
        else:
            newPath = path + '/' + name

        usdGeom = None
        skeleton = self.skinning.findSkeletonByRoot(str(nodeIdx))
        if skeleton is not None:
            if self.verbose:
                print indent + 'SkelRoot:', name
            usdGeom = skeleton.makeUsdSkeleton(self.usdStage, newPath)
            underSkeleton = skeleton
        elif skeletonByJoint is not None and 'mesh' not in gltfNode:
            pass
        else:
            if 'mesh' in gltfNode:
                if self.verbose:
                    if 'skin' in gltfNode:
                        print indent + 'Skinned mesh:', name
                    else:
                        print indent + 'Mesh:', name
                usdGeom = self.processMesh(nodeIdx, newPath, underSkeleton)
            else:
                if self.verbose:
                    print indent + 'Node:', name
                usdGeom = UsdGeom.Xform.Define(self.usdStage, newPath)

            if 'matrix' in gltfNode:
                usdGeom.AddTransformOp().Set(getMatrix(gltfNode['matrix']))
            else:
                if 'translation' in gltfNode:
                    usdGeom.AddTranslateOp().Set(getVec3(gltfNode['translation']))
                if 'rotation' in gltfNode:
                    usdGeom.AddOrientOp().Set(getQuat(gltfNode['rotation']))
                if 'scale' in gltfNode:
                    usdGeom.AddScaleOp().Set(getVec3(gltfNode['scale']))

        if usdGeom is not None:
            self.usdGeoms[nodeIdx] = usdGeom

        # process child nodes recursively
        if underSkeleton is not None:
            newPath = path # keep meshes directly under SkelRoot scope

        if 'children' in gltfNode:
            self.processNodeChildren(gltfNode['children'], newPath, underSkeleton, indent + '  ')


    def processNodeChildren(self, gltfChildren, path, underSkeleton, indent='  '):
        for nodeIdx in gltfChildren:
            self.processNode(nodeIdx, path, underSkeleton, indent)


    def processNodeTransformAnimation(self):
        for gltfAnim in self.gltf['animations'] if 'animations' in self.gltf else []:
            for gltfChannel in gltfAnim['channels']:
                gltfTarget = gltfChannel['target']
                nodeIdx = gltfTarget['node']

                skeleton = self.skinning.findSkeletonByJoint(str(nodeIdx))
                if skeleton is not None:
                    continue

                path = gltfTarget['path']

                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                interpolation = gltfSampler['interpolation']
                if interpolation != 'LINEAR':
                    if self.verbose:
                        print 'Warnig:', interpolation, 'interpolation for animation is not supported'
                    continue

                keyTimesAcc = Accessor(self, gltfSampler['input'])
                keyValuesAcc = Accessor(self, gltfSampler['output'])
                v = keyValuesAcc.data

                usdGeom = self.usdGeoms[nodeIdx]
                ops = usdGeom.GetOrderedXformOps()

                if path == 'scale':
                    op = getXformOp(usdGeom, UsdGeom.XformOp.TypeScale)
                    if op == None:
                        op = usdGeom.AddScaleOp()
                    for el in xrange(keyTimesAcc.count):
                        time = time2Code(keyTimesAcc.data[el])
                        p = el * keyValuesAcc.components
                        op.Set(time = time, value = Gf.Vec3f(float(v[p]), float(v[p + 1]), float(v[p + 2])))
                elif path == 'rotation':
                    op = getXformOp(usdGeom, UsdGeom.XformOp.TypeOrient)
                    if op == None:
                        op = usdGeom.AddOrientOp()
                    for el in xrange(keyTimesAcc.count):
                        time = time2Code(keyTimesAcc.data[el])
                        p = el * keyValuesAcc.components
                        op.Set(time = time, value = Gf.Quatf(float(v[p + 3]), Gf.Vec3f(float(v[p]), float(v[p + 1]), float(v[p + 2]))))
                if path == 'translation':
                    op = getXformOp(usdGeom, UsdGeom.XformOp.TypeTranslate)
                    if op == None:
                        op = usdGeom.AddTranslateOp()
                    for el in xrange(keyTimesAcc.count):
                        time = time2Code(keyTimesAcc.data[el])
                        p = el * keyValuesAcc.components
                        op.Set(time = time, value = Gf.Vec3f(float(v[p]), float(v[p + 1]), float(v[p + 2])))


    def bindPostponedSkeletons(self):
        for usdMesh, skin in self.postponeUsdMeshToSkeleton.iteritems():
            usdSkelBinding = UsdSkel.BindingAPI(usdMesh)
            if skin.skeleton.usdSkeleton is not None:
                usdSkelBinding.CreateSkeletonRel().AddTarget(skin.skeleton.usdSkeleton.GetPath())


    def makeUsdStage(self):
        self.usdStage = self.asset.makeUsdStage()
        #gltf units for all linear distance are meters
        self.usdStage.SetMetadata("metersPerUnit", 1)
        self.createMaterials()
        self.prepareSkinning()
        self.processNodeChildren(self.gltf['scenes'][0]['nodes'], self.asset.getGeomPath(), None)
        self.bindPostponedSkeletons()
        self.processSkeletonAnimation()
        self.processNodeTransformAnimation()
        return self.usdStage



def usdStageWithGlTF(gltfPath, usdPath, verbose=0):
    converter = glTFConverter(gltfPath, usdPath, verbose)
    return converter.makeUsdStage()

