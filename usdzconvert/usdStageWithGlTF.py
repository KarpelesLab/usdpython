from pxr import *

import json
import struct
import os.path
import base64
import math

import usdUtils


usdStageWithGlTFLoaded = True
try:
    import numpy
except Exception as e:
    usdUtils.printError("Failed to import numpy module. Please install numpy module for Python 3. macOS: $ sudo pip3 install numpy")
    usdStageWithGlTFLoaded = False

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


    def size(self):
        return {
            glTFComponentType.BYTE: 1,
            glTFComponentType.UNSIGNED_BYTE: 1,
            glTFComponentType.SHORT: 2,
            glTFComponentType.UNSIGNED_SHORT: 2,
            glTFComponentType.UNSIGNED_INT: 4,
            glTFComponentType.FLOAT: 4
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
            glTFWrappingMode.CLAMP_TO_EDGE: usdUtils.WrapMode.clamp,
            glTFWrappingMode.MIRRORED_REPEAT: usdUtils.WrapMode.mirror,
            glTFWrappingMode.REPEAT: usdUtils.WrapMode.repeat
            } [self.mode]


class gltfPrimitiveMode:
    POINTS = 0
    LINES = 1
    LINE_LOOP = 2
    LINE_STRIP = 3
    TRIANGLES = 4
    TRIANGLE_STRIP = 5
    TRIANGLE_FAN = 6


def loadChunk(file, format):
    size = struct.calcsize(format)
    unpack = struct.Struct(format).unpack_from
    return unpack(file.read(size))


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


def getInterpolatedValue(timeValueDic, time, isSlerp=False):
    if time in timeValueDic:
        return timeValueDic[time]
    # find neighbor keys for time
    # to get an interpolated value
    lessMaxTime = -1
    greaterMinTime = -1
    for t in timeValueDic:
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
        return timeValueDic[greaterMinTime]
    if greaterMinTime == -1:
        return timeValueDic[lessMaxTime]

    k = float(time - lessMaxTime) / (greaterMinTime - lessMaxTime)

    if isSlerp:
        q = Gf.Slerp(k, timeValueDic[lessMaxTime], timeValueDic[greaterMinTime])
        i = q.GetImaginary()
        return Gf.Quatf(q.GetReal(), Gf.Vec3f(i[0], i[1], i[2]))

    return timeValueDic[lessMaxTime] * (1-k) + timeValueDic[greaterMinTime] * k


def getXformOp(usdGeom, type):
    ops = usdGeom.GetOrderedXformOps()
    for op in ops:
        if op.GetOpType() == type:
            return op
    return None


def indicesWithTriangleStrip(indices):
    if len(indices) <= 3:
        return indices
    newIndices = [int(indices[0]), int(indices[1]), int(indices[2])]
    for i in range(3, len(indices)):
        newIndices.append(int(indices[i-1]))
        newIndices.append(int(indices[i-2]))
        newIndices.append(int(indices[i]))
    return newIndices


def indicesWithTriangleFan(indices):
    if len(indices) <= 3:
        return indices
    newIndices = []
    for i in range(2, len(indices)):
        newIndices.append(int(indices[0]))
        newIndices.append(int(indices[i-1]))
        newIndices.append(int(indices[i]))
    return newIndices


def deindexPoints(points, indices):
    newPoints = []
    for  i in range(len(indices)):
        newPoints.append(Gf.Vec3f(
            float(points[indices[i]*3]), 
            float(points[indices[i]*3 + 1]),
            float(points[indices[i]*3 + 2])))
    return newPoints


def getGfVec3fFromData(data, offset, elementCount):
    return Gf.Vec3f(float(data[offset]), float(data[offset + 1]), float(data[offset + 2]))


def getGfQuatfFromData(data, offset, elementCount):
    return Gf.Quatf(float(data[offset + 3]), Gf.Vec3f(float(data[offset]), float(data[offset + 1]), float(data[offset + 2])))


def getFloatArrayFromData(data, offset, elementCount):
    elements = []
    for i in range(elementCount):
        elements.append(float(data[offset + i]))
    return Vt.FloatArray(elements)


def convertUVTransformForUSD(translation, scale, rotation):
    inversePivot = Gf.Matrix4d(1)
    inversePivot[3] = Gf.Vec4d(0, 1, 0, 1)

    scaleMatrix = Gf.Matrix4d(Gf.Vec4d(scale[0], scale[1], 1, 1))
    inverseScaleMatrix = Gf.Matrix4d(Gf.Vec4d(1.0 / scale[0], 1.0 / scale[1], 1, 1))

    rotationMatrix = Gf.Matrix4d(
        math.cos(rotation), -math.sin(rotation), 0, 0,
        math.sin(rotation),  math.cos(rotation), 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1)
    
    translateMatrix = Gf.Matrix4d(1)
    translateMatrix.SetTranslate(Gf.Vec3d(translation[0],translation[1],0))
    uvTransform = scaleMatrix * rotationMatrix * translateMatrix
    
    pivot = Gf.Matrix4d(1)
    pivot[3] = Gf.Vec4d(0, -1, 0, 1)

    transform = uvTransform * pivot * inverseScaleMatrix * rotationMatrix.GetTranspose() * inversePivot

    transform[0] = rotationMatrix[0] * scale[0]
    transform[1] = rotationMatrix[1] * scale[1]
    transform[2] = rotationMatrix[2]

    transform[0] = Gf.Vec4d(transform[0][0], -1.0 * transform[0][1], transform[0][2], transform[0][3])
    transform[1] = Gf.Vec4d(-1.0 * transform[1][0], transform[1][1], transform[1][2], transform[1][3])

    transform[3] = Gf.Vec4d(transform[3][0], -1.0 * transform[3][1], transform[3][2], transform[3][3])

    translation3d = transform.ExtractTranslation()
    translation[0] = translation3d[0]
    translation[1] = translation3d[1]

    rotation3D = transform.ExtractRotationMatrix().GetOrthonormalized().ExtractRotation()
    rotationVec3d = rotation3D.Decompose(Gf.Vec3d(1,0,0), Gf.Vec3d(0,1,0), Gf.Vec3d(0,0,1))
    rotation = rotationVec3d[2] # degrees
    return (translation, scale, rotation)


class glTFNodeManager(usdUtils.NodeManager):
    def __init__(self, converter):
        usdUtils.NodeManager.__init__(self)
        self.converter = converter


    def overrideGetName(self, strNodeIdx):
        # TODO: make sure there is no duplicate names
        if strNodeIdx is None:
            return ''
        nodeIdx = int(strNodeIdx)
        gltfNode = self.converter.gltf['nodes'][nodeIdx]
        return getName(gltfNode, 'node_', nodeIdx)


    def overrideGetChildren(self, strNodeIdx):
        children = []
        if strNodeIdx is None:
            for i in range(len(self.converter.gltf['nodes'])):
                if self.overrideGetParent(str(i)) is None:
                    children.append(str(i))
            return children
        gltfNode = self.converter.gltf['nodes'][int(strNodeIdx)]
        if 'children' in gltfNode:
            for child in gltfNode['children']:
                children.append(str(child))
        return children


    def overrideGetLocalTransformGfMatrix4d(self, strNodeIdx):
        if strNodeIdx is None:
            return Gf.Matrix4d(1)
        gltfNode = self.converter.gltf['nodes'][int(strNodeIdx)]
        return getMatrixTransform(gltfNode)


    def overrideGetWorldTransformGfMatrix4d(self, strNodeIdx):
        if strNodeIdx is None:
            return Gf.Matrix4d(1)
        return self.converter.getWorldTransform(int(strNodeIdx))


    def overrideGetParent(self, node):
        parentIdx = self.converter.getParent(int(node))
        if parentIdx == -1:
            return None
        return str(parentIdx)



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

        self.stride = getInt(bufferView, 'byteStride')
        if self.stride != 0 and self.stride != glTFComponentType(self.componentType).size() * self.components:
            elementsSize = glTFComponentType(self.componentType).size() * self.components
            data = b''
            for i in range(self.count):
                start = offset + i * self.stride
                data += fileContent[start : start + elementsSize]
            self.data = numpy.frombuffer(data, fmt, self.count * self.components)
        else:
            self.data = numpy.frombuffer(fileContent, fmt, self.count * self.components, offset)



class glTFConverter:
    def __init__(self, gltfPath, usdPath, legacyModifier, openParameters):
        self.usdStage = None
        self.buffers = []
        self.gltf = None
        self.usdGeoms = {}
        self.usdMaterials = []
        self.usdSkelAnims = []
        self.nodeNames = {} # to avoid duplicate node names
        self.copyTextures = openParameters.copyTextures
        self.verbose = openParameters.verbose
        self.legacyModifier = legacyModifier # for iOS 12 compatibility
        self.skeletonByNode = {} # collect skinned mesh to construct later 
        self.blendShapeByNode = {} # collect meshes with blend shapes to construct later 
        self._worldTransforms = {} # use self.getWorldTransform(nodeIdx)
        self._parents = {} # use self.getParent(nodeIdx)
        self._loadFailed = False
        openParameters.metersPerUnit = 1

        filenameFull = gltfPath.split('/')[-1]
        self.srcFolder = gltfPath[:len(gltfPath)-len(filenameFull)]

        filenameFull = usdPath.split('/')[-1]
        self.dstFolder = usdPath[:len(usdPath)-len(filenameFull)]

        self.asset = usdUtils.Asset(usdPath)

        try:
            self.load(gltfPath)
        except:
            usdUtils.printError("can't load the input file.")
            self._loadFailed = True
            return
        if not self.checkGLTFVersion():
            return
        self.readAllBuffers()

        self.nodeManager = glTFNodeManager(self)
        self.skinning = usdUtils.Skinning(self.nodeManager)
        self.shapeBlending = usdUtils.ShapeBlending()


    def load(self, gltfPath):
        fileAndExt = os.path.splitext(gltfPath)
        if len(fileAndExt) == 2 and fileAndExt[1].lower() == '.glb':
            with open(gltfPath, "rb") as file:
                (magic, version, length) = loadChunk(file, '<3i')
                (jsonLen, jsonType) = loadChunk(file, '<2i')
                self.gltf = json.loads(file.read(jsonLen))
                (bufferLen, bufferType) = loadChunk(file, '<2i')
                self.buffers.append(file.read())
        else:
            with open(gltfPath) as file:
                self.gltf = json.load(file)


    def checkGLTFVersion(self):
        if 'asset' in self.gltf and 'version' in self.gltf['asset']:
            version = self.gltf['asset']['version']
            if float(version) < 2.0 or float(version) >= 3.0:
                usdUtils.printError('glTF 2.x is supported only. Version of glTF of input file is ' + version)
                self._loadFailed = True
        else:
            usdUtils.printError("can't detect the version of glTF.")
            self._loadFailed = True
        return not self._loadFailed


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


    def processTexture(self, dict, type, inputName, channels, material, scaleFactor=None):
        if type not in dict:
            return False

        gltfMaterialMap = dict[type]
        textureIdx = gltfMaterialMap['index']
        texCoordSet = gltfMaterialMap['texCoord'] if 'texCoord' in gltfMaterialMap else 0
        gltfTexture = self.gltf['textures'][textureIdx]
        sourceIdx = gltfTexture['source']
        image = self.gltf['images'][sourceIdx]

        srcTextureFilename = '' # source texture filename on drive
        textureFilename = '' # valid for USD
        if 'uri' in image:
            uri = image['uri']
            if len(uri) > 5 and uri[:5] == 'data:':
                # embedded texture
                for offset in range(5, len(uri) - 6):
                    if uri[offset:(offset+6)] == 'base64':
                        mimeType = uri[5:(offset-1)] if offset > 6 else ''
                        content = base64.b64decode(uri[(offset + 6):])
                        textureFilename = self.saveTexture(content, mimeType, textureIdx)
                        srcTextureFilename = self.dstFolder + textureFilename
                        break
            else:
                srcTextureFilename = uri
                textureFilename = usdUtils.makeValidPath(srcTextureFilename)
                filenameAndExt = os.path.splitext(textureFilename)
                ext = filenameAndExt[1].lower()
                if '.jpeg' == ext:
                    textureFilename = filenameAndExt[0] + '.jpg'
                    usdUtils.copy(self.srcFolder + srcTextureFilename, self.dstFolder + textureFilename, self.verbose)
                elif self.srcFolder != self.dstFolder:
                    if self.copyTextures or srcTextureFilename != textureFilename:
                        usdUtils.copy(self.srcFolder + srcTextureFilename, self.dstFolder + textureFilename, self.verbose)
                    else:
                        textureFilename = self.srcFolder + textureFilename
                srcTextureFilename = self.srcFolder + srcTextureFilename

        elif 'mimeType' in image and 'bufferView' in image:
            textureFilename = self.saveTextureWithImage(image, textureIdx)
            srcTextureFilename = self.dstFolder + textureFilename

        if textureFilename == '':
            return False

        if self.legacyModifier is not None and (channels == 'g' or channels == 'b' or channels == 'r'):
            newTextureFilename = self.legacyModifier.makeOneChannelTexture(srcTextureFilename, self.dstFolder, channels, self.verbose)
            if newTextureFilename:
                textureFilename = newTextureFilename
                channels = 'r'

        wrapS = usdUtils.WrapMode.repeat # default for glTF
        wrapT = usdUtils.WrapMode.repeat # default for glTF

        # Wrapping mode
        if 'sampler' in gltfTexture:
            samplerIdx = gltfTexture['sampler']
            gltfSampler = self.gltf['samplers'][samplerIdx]
            if 'wrapS' in gltfSampler:
                wrapS = glTFWrappingMode(gltfSampler['wrapS']).usdMode()
            if 'wrapT' in gltfSampler:
                wrapT = glTFWrappingMode(gltfSampler['wrapT']).usdMode()

        primvarName = 'st' if texCoordSet == 0 else 'st' + str(texCoordSet)

        # texture transform extension: KHR_texture_transform
        mapTransform = None
        if 'extensions' in gltfMaterialMap and 'KHR_texture_transform' in gltfMaterialMap['extensions']:
            gltfTransform = gltfMaterialMap['extensions']['KHR_texture_transform']

            translation = gltfTransform['offset'] if 'offset' in gltfTransform else [0, 0]
            scale = gltfTransform['scale'] if 'scale' in gltfTransform else [1, 1]
            rotation = gltfTransform['rotation'] if 'rotation' in gltfTransform else 0

            (translation, scale, rotation) = convertUVTransformForUSD(translation, scale, rotation)
            mapTransform = usdUtils.MapTransform(translation, scale, rotation)

        material.inputs[inputName] = usdUtils.Map(channels, textureFilename, None, primvarName, wrapS, wrapT, scaleFactor, mapTransform)
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

            isBlendOrMask = False
            if 'alphaMode' in gltfMaterial and gltfMaterial['alphaMode'] == 'BLEND':
                isBlendOrMask = True

            if 'alphaMode' in gltfMaterial and gltfMaterial['alphaMode'] == 'MASK':
                isBlendOrMask = True
                if 'alphaCutoff' in gltfMaterial:
                    material.opacityThreshold = float(gltfMaterial['alphaCutoff'])
                else:
                    material.opacityThreshold = 0.5 # default by glTF spec

            if 'pbrMetallicRoughness' in gltfMaterial:
                pbr = gltfMaterial['pbrMetallicRoughness']

                # diffuse color and opacity
                baseColorFactor = pbr['baseColorFactor'] if 'baseColorFactor' in pbr else [1, 1, 1, 1]
                baseColorScale = [baseColorFactor[0], baseColorFactor[1], baseColorFactor[2]]
                opacityScale = baseColorFactor[3]
                if self.processTexture(pbr, 'baseColorTexture', usdUtils.InputName.diffuseColor, 'rgb', material, baseColorScale):
                    if isBlendOrMask:
                        map = material.inputs[usdUtils.InputName.diffuseColor]
                        if self.textureHasAlpha(map.file):
                            self.processTexture(pbr, 'baseColorTexture', usdUtils.InputName.opacity, 'a', material, opacityScale)
                        else:
                            material.inputs[usdUtils.InputName.opacity] = baseColorFactor[3]
                else:
                    material.inputs[usdUtils.InputName.diffuseColor] = baseColorFactor
                    if isBlendOrMask:
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
                    usdUtils.printWarning("specular/glossiness workflow is not fully supported.")
                pbrSG = gltfMaterial['extensions']['KHR_materials_pbrSpecularGlossiness']
                diffuseScale = None
                opacityScale = None
                if 'diffuseFactor' in pbrSG:
                    diffuseFactor = pbrSG['diffuseFactor']
                    diffuseScale = [diffuseFactor[0], diffuseFactor[1], diffuseFactor[2]]
                    opacityScale = diffuseFactor[3]
                if self.processTexture(pbrSG, 'diffuseTexture', usdUtils.InputName.diffuseColor, 'rgb', material, diffuseScale):
                    if isBlendOrMask:
                        map = material.inputs[usdUtils.InputName.diffuseColor]
                        if self.textureHasAlpha(map.file):
                            self.processTexture(pbrSG, 'diffuseTexture', usdUtils.InputName.opacity, 'a', material, opacityScale)
                        else:
                            material.inputs[usdUtils.InputName.opacity] = opacityScale
                else:
                    if diffuseScale:
                        material.inputs[usdUtils.InputName.diffuseColor] = diffuseScale
                    if isBlendOrMask and opacityScale:
                        material.inputs[usdUtils.InputName.opacity] = opacityScale

            if 'extensions' in gltfMaterial and 'KHR_materials_clearcoat' in gltfMaterial['extensions']:
                clearcoatExt = gltfMaterial['extensions']['KHR_materials_clearcoat']
                if 'clearcoatFactor' in clearcoatExt:
                    material.inputs[usdUtils.InputName.clearcoat] = clearcoatExt['clearcoatFactor']
                if 'clearcoatRoughnessFactor' in clearcoatExt:
                    material.inputs[usdUtils.InputName.clearcoatRoughness] = clearcoatExt['clearcoatRoughnessFactor']

            self.processTexture(gltfMaterial, 'normalTexture', usdUtils.InputName.normal, 'rgb', material)
            self.processTexture(gltfMaterial, 'occlusionTexture', usdUtils.InputName.occlusion, 'r', material) #TODO: add occlusion scale

            emissiveFactor = gltfMaterial['emissiveFactor'] if 'emissiveFactor' in gltfMaterial else [0.0, 0.0, 0.0]
            if not self.processTexture(gltfMaterial, 'emissiveTexture', usdUtils.InputName.emissiveColor, 'rgb', material, emissiveFactor):
                if 'emissiveFactor' in gltfMaterial:
                    material.inputs[usdUtils.InputName.emissiveColor] = emissiveFactor

            usdMaterial = material.makeUsdMaterial(self.asset)
            self.usdMaterials.append(usdMaterial)


    def prepareSkinning(self):
        if 'skins' not in self.gltf:
            return

        for skinIdx in range(len(self.gltf['skins'])):
            gltfSkin = self.gltf['skins'][skinIdx]

            root = str(gltfSkin['skeleton']) if 'skeleton' in gltfSkin else None
            skin = usdUtils.Skin(root)

            gltfJoints = gltfSkin['joints']
            for jointIdx in gltfJoints:
                joint = str(jointIdx)
                skin.joints.append(joint)

            # get bind matrices
            if 'inverseBindMatrices' in gltfSkin:
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
            else:
                # default identity matrices by spec, which implies that inverse-bind matrices were pre-applied
                for jointIdx in gltfJoints:
                    skin.bindMatrices[str(jointIdx)] = Gf.Matrix4d(1)

            self.skinning.skins.append(skin)
        self.skinning.createSkeletonsFromSkins()
        if self.verbose:
            print("  Found skeletons: " + str(len(self.skinning.skeletons)) + " with " + str(len(self.skinning.skins)) + " skin(s)")
        for skeleton in self.skinning.skeletons:
            if skeleton.getRoot() is None:
                skeleton.makeUsdSkeleton(self.usdStage, self.asset.getGeomPath() + '/RootNodeSkel', self.nodeManager)


    def _prepareBlendShape(self, nodeIdx):
        gltfNode = self.gltf['nodes'][nodeIdx]
        if 'mesh' in gltfNode:
            meshIdx = gltfNode['mesh']
            gltfMesh = self.gltf['meshes'][meshIdx]

            weightsCount = len(gltfMesh['weights']) if 'weights' in gltfMesh else 0

            if 'primitives' in gltfMesh:
                gltfPrimitives = gltfMesh['primitives']

                for gltfPrimitive in gltfPrimitives:
                    if 'targets' in gltfPrimitive:
                        blendShape = self.shapeBlending.createBlendShape(weightsCount)
                        self.blendShapeByNode[str(nodeIdx)] = blendShape
                        break

        if 'children' in gltfNode:
            for childNodeIdx in gltfNode['children']:
                self._prepareBlendShape(childNodeIdx)


    def prepareBlendShapes(self):
        for childNodeIdx in self.gltf['scenes'][0]['nodes']:
            self._prepareBlendShape(childNodeIdx)


    def findSkeletonForAnimation(self, gltfAnim):
        for gltfChannel in gltfAnim['channels']:
            gltfTarget = gltfChannel['target']
            if 'node' not in gltfTarget:
                continue
            nodeIdx = gltfTarget['node']
            skeleton = self.skinning.findSkeletonByJoint(str(nodeIdx))
            if skeleton is not None:
                return skeleton
        return None


    def findBlendShapeForAnimation(self, gltfAnim):
        for gltfChannel in gltfAnim['channels']:
            gltfTarget = gltfChannel['target']
            if 'node' not in gltfTarget:
                continue
            nodeIdx = gltfTarget['node']
            strNodeIdx = str(nodeIdx)
            if strNodeIdx in self.blendShapeByNode:
                blendShape = self.blendShapeByNode[strNodeIdx]
                return blendShape
        return None


    def prepareAnimations(self):
        if 'animations' not in self.gltf:
            return
        # find good FPS based on key time data
        minTimeInterval = 1.0 / 24 # default for USD
        epsilon = 0.01
        for gltfAnim in self.gltf['animations']:
            for gltfChannel in gltfAnim['channels']:
                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                keyTimesAcc = Accessor(self, gltfSampler['input'])
                for el in range(keyTimesAcc.count-1):
                    timeInterval = keyTimesAcc.data[el+1] - keyTimesAcc.data[el]
                    if minTimeInterval > timeInterval and timeInterval > epsilon:
                        minTimeInterval = timeInterval
        self.asset.setFPS(int(1.0 / minTimeInterval))


    def getInterpolatedValues(self, interpolation, keyTimesAcc, keyValuesAcc, getValueFromData, timeSet=None, elementCount=1):
        values = {}
        data = keyValuesAcc.data
        valueElementCount = keyValuesAcc.components * elementCount
        if interpolation == 'CUBICSPLINE':
            for el in range(keyTimesAcc.count - 1):
                t0 = self.asset.toTimeCode(keyTimesAcc.data[el], True)
                t1 = self.asset.toTimeCode(keyTimesAcc.data[el + 1], True)

                smallTimeRange = 0.00001
                timeRange = t1 - t0
                if timeRange < smallTimeRange: timeRange = smallTimeRange
                timeSteps = int(timeRange)
                if timeSteps == 0: timeSteps = 1

                # math is described in glTF specification
                offset = el * valueElementCount * 3 + valueElementCount
                p0 = getValueFromData(data, offset, elementCount)
                offset = el * valueElementCount * 3 + valueElementCount * 2
                m0 = getValueFromData(data, offset, elementCount) * timeRange
                offset = (el + 1) * valueElementCount * 3
                m1 = getValueFromData(data, offset, elementCount) * timeRange
                offset = (el + 1) * valueElementCount * 3 + valueElementCount
                p1 = getValueFromData(data, offset, elementCount)

                for timeStep in range(timeSteps):
                    t = float(timeStep) / timeSteps
                    t2 = t * t
                    t3 = t2 * t
                    p = (2*t3 - 3*t2 + 1) * p0 + (t3 - 2*t2 + t) * m0 + (-2*t3 + 3*t2) * p1 + (t3 - t2) * m1
                    if type(p) is Gf.Quatf:
                        p = p.GetNormalized()
                    values[t0 + timeStep] = p
                    if timeSet is not None:
                        timeSet.add(t0 + timeStep)

            el = keyTimesAcc.count - 1
            time = self.asset.toTimeCode(keyTimesAcc.data[el], True)
            offset = el * valueElementCount * 3 + valueElementCount
            values[time] = getValueFromData(data, offset, elementCount)
            if timeSet is not None:
                timeSet.add(time)
        else:
            if interpolation == 'STEP':
                for el in range(1, keyTimesAcc.count):
                    time = self.asset.toTimeCode(keyTimesAcc.data[el], True) - 1
                    offset = (el - 1) * valueElementCount
                    values[time] = getValueFromData(data, offset, elementCount)
                    if timeSet is not None:
                        timeSet.add(time)
            for el in range(keyTimesAcc.count):
                time = self.asset.toTimeCode(keyTimesAcc.data[el], True)
                offset = el * valueElementCount
                values[time] = getValueFromData(data, offset, elementCount)
                if timeSet is not None:
                    timeSet.add(time)

        return values


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

            translationTimeSet = set()
            rotationTimeSet = set()
            scaleTimeSet = set()

            # Fill animJoints
            for gltfChannel in gltfAnim['channels']:
                gltfTarget = gltfChannel['target']
                strNodeIdx = str(gltfTarget['node'])

                if skeleton.getJointIndex(strNodeIdx) == -1:
                    if self.verbose:
                        usdUtils.printWarning("Skeletal animation contains node animation")
                    continue

                targetPath = gltfTarget['path']

                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                interpolation = gltfSampler['interpolation'] if 'interpolation' in gltfSampler else 'LINEAR'

                keyTimesAcc = Accessor(self, gltfSampler['input'])
                keyValuesAcc = Accessor(self, gltfSampler['output'])

                if strNodeIdx not in animJoints:
                    animJoints[strNodeIdx] = [None] * 3

                pathIdx = -1
                timeSet = None
                if targetPath == 'translation':
                    pathIdx = 0
                    timeSet = translationTimeSet
                elif targetPath == 'rotation':
                    pathIdx = 1
                    timeSet = rotationTimeSet
                elif targetPath == 'scale':
                    pathIdx = 2
                    timeSet = scaleTimeSet
                else:
                    if self.verbose:
                        usdUtils.printWarning("Skeletal animation: unsupported target path: " + targetPath)
                    continue

                getValueFromData = getGfQuatfFromData if targetPath == 'rotation' else getGfVec3fFromData
                values = self.getInterpolatedValues(interpolation, keyTimesAcc, keyValuesAcc, getValueFromData, timeSet)
                animJoints[strNodeIdx][pathIdx] = values

            if len(animJoints) == 0:
                continue

            animationPath = self.asset.getAnimationsPath() + '/' + name
            usdSkelAnim = UsdSkel.Animation.Define(self.usdStage, animationPath)

            jointPaths = []
            for joint in skeleton.joints:
                if joint in animJoints:
                    jointPaths.append(skeleton.jointPaths[joint])

            usdSkelAnim.CreateJointsAttr(jointPaths)

            gltfNodes = self.gltf['nodes']

            # translations attribute
            times = sorted(translationTimeSet)
            attr = usdSkelAnim.CreateTranslationsAttr()
            for time in times:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        animJoint = animJoints[joint]
                        if animJoint[0]:
                            values.append(getInterpolatedValue(animJoint[0], time))
                        else:
                            values.append(getTransformTranslation(gltfNodes[int(joint)]))
                if len(values):
                    attr.Set(values, Usd.TimeCode(time))
            if len(times) == 0: # add default values if no keys
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        values.append(Gf.Vec3f(0, 0, 0))
                attr.Set(values)

            # rotations attribute
            times = sorted(rotationTimeSet)
            attr = usdSkelAnim.CreateRotationsAttr()
            for time in times:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        animJoint = animJoints[joint]
                        if animJoint[1]:
                            values.append(getInterpolatedValue(animJoint[1], time, True))
                        else:
                            values.append(getTransformRotation(gltfNodes[int(joint)]))
                if len(values):
                    attr.Set(values, Usd.TimeCode(time))
            if len(times) == 0:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        values.append(Gf.Quatf(1, Gf.Vec3f(0, 0, 0)))
                attr.Set(values)

            # scales attribute
            times = sorted(scaleTimeSet)
            attr = usdSkelAnim.CreateScalesAttr()
            for time in times:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        animJoint = animJoints[joint]
                        if animJoint[2]:
                            values.append(getInterpolatedValue(animJoint[2], time))
                        else:
                            values.append(getTransformScale(gltfNodes[int(joint)]))
                if len(values):
                    attr.Set(values, Usd.TimeCode(time))
            if len(times) == 0:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        values.append(Gf.Vec3f(1, 1, 1))
                attr.Set(values)

            skeleton.setSkeletalAnimation(usdSkelAnim)
            self.usdSkelAnims.append(usdSkelAnim)


    def processBlendShapeAnimations(self):
        for gltfAnim in self.gltf['animations'] if 'animations' in self.gltf else []:

            blendShape = self.findBlendShapeForAnimation(gltfAnim)
            if blendShape is None:
                continue

            name = getName(gltfAnim, 'skelAnim_', len(self.usdSkelAnims))
            animationPath = self.asset.getAnimationsPath() + '/' + name
            usdSkelAnim = UsdSkel.Animation.Define(self.usdStage, animationPath)

            attr = usdSkelAnim.CreateBlendShapeWeightsAttr()

            for gltfChannel in gltfAnim['channels']:
                gltfTarget = gltfChannel['target']
                strNodeIdx = str(gltfTarget['node'])

                targetPath = gltfTarget['path']
                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                interpolation = gltfSampler['interpolation'] if 'interpolation' in gltfSampler else 'LINEAR'
                keyTimesAcc = Accessor(self, gltfSampler['input'])
                keyValuesAcc = Accessor(self, gltfSampler['output'])

                if targetPath == 'weights':
                    values = self.getInterpolatedValues(interpolation, keyTimesAcc, keyValuesAcc, getFloatArrayFromData, None, blendShape.weightsCount)
                    for time, value in values.items():
                        attr.Set(time = time, value = value)

            blendShape.setSkeletalAnimation(usdSkelAnim)
            self.usdSkelAnims.append(usdSkelAnim)



    def processPrimitive(self, nodeIdx, gltfPrimitive, path, skinIdx, skeleton):
        if 'extensions' in gltfPrimitive:
            extensions = gltfPrimitive['extensions']
            if 'KHR_draco_mesh_compression' in extensions:
                usdUtils.printError("draco compression is not supported.")
                raise usdUtils.ConvertError()

        mode = gltfPrimitive['mode'] if 'mode' in gltfPrimitive else gltfPrimitiveMode.TRIANGLES

        count = 0 # points count (deindiced)
        indices = None
        if 'indices' in gltfPrimitive:
            accessor = Accessor(self, gltfPrimitive['indices'])
            count = accessor.count
            indices = accessor.data

        # points and curve points can't have indices in USD
        toDeindexPoints = False

        usdGeom = None
        if mode == gltfPrimitiveMode.POINTS:
            usdGeom = UsdGeom.Points.Define(self.usdStage, path)
            toDeindexPoints = indices is not None
        elif mode == gltfPrimitiveMode.LINES:
            usdGeom = UsdGeom.BasisCurves.Define(self.usdStage, path)
            usdGeom.CreateTypeAttr('linear')
            usdGeom.CreateWrapAttr('nonperiodic')
            toDeindexPoints = indices is not None
        elif mode == gltfPrimitiveMode.LINE_LOOP:
            usdGeom = UsdGeom.BasisCurves.Define(self.usdStage, path)
            usdGeom.CreateTypeAttr('linear')
            usdGeom.CreateWrapAttr('periodic')
            toDeindexPoints = indices is not None
        elif mode == gltfPrimitiveMode.LINE_STRIP:
            usdGeom = UsdGeom.BasisCurves.Define(self.usdStage, path)
            usdGeom.CreateTypeAttr('linear')
            usdGeom.CreateWrapAttr('nonperiodic')
            toDeindexPoints = indices is not None

        if usdGeom is None:
            usdGeom = UsdGeom.Mesh.Define(self.usdStage, path)

        usdSkelBinding = None
        skin = None
        if skinIdx != -1:
            skin = self.skinning.skins[skinIdx]
            if skin.skeleton is not None:
                usdSkelBinding = UsdSkel.BindingAPI(usdGeom)
                differenceTransform = Gf.Matrix4d(1)
                usdSkelBinding.CreateGeomBindTransformAttr(differenceTransform)
                if skin.skeleton.usdSkeleton is not None:
                    usdSkelBinding.CreateSkeletonRel().AddTarget(skin.skeleton.usdSkeleton.GetPath())
                    if self.legacyModifier is not None:
                        self.legacyModifier.addSkelAnimToMesh(usdGeom, skin.skeleton)
        elif skeleton is not None:
            meshNodeWorldMatrix = self.getWorldTransform(nodeIdx)
            skeleton.bindRigidDeformation(str(nodeIdx), usdGeom, meshNodeWorldMatrix)
            if self.legacyModifier is not None:
                self.legacyModifier.addSkelAnimToMesh(usdGeom, skeleton)

        attributes = gltfPrimitive['attributes']

        for key in attributes:
            accessor = Accessor(self, attributes[key])

            if key == 'POSITION':
                if toDeindexPoints:
                    points = deindexPoints(accessor.data, indices)
                    usdGeom.CreatePointsAttr(points)
                else:
                    usdGeom.CreatePointsAttr(accessor.data)
                    if count == 0: # no indices
                        count = accessor.count
            elif key == 'NORMAL':
                normalPrimvar = UsdGeom.PrimvarsAPI(usdGeom).CreatePrimvar('normals', Sdf.ValueTypeNames.Normal3fArray, UsdGeom.Tokens.vertex)
                normalPrimvar.Set(accessor.data)
            elif key == 'TANGENT':
                pass
            elif key[0:8] == 'TEXCOORD':
                if accessor.componentType != glTFComponentType.FLOAT:
                    if self.verbose:
                        print('Warnig: component type ' + accessor.componentType + ' is not supported for texture coordinates')
                    break
                # Y-component of texture coordinates should be flipped
                newData = []
                for el in range(accessor.count):
                    newData.append((
                        float(accessor.data[el * accessor.components]),
                        float(1.0 - accessor.data[el * accessor.components + 1])))

                texCoordSet = key[9:]
                primvarName = 'st' if texCoordSet == '0' else 'st' + texCoordSet
                uvs = UsdGeom.PrimvarsAPI(usdGeom).CreatePrimvar(primvarName, Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
                uvs.Set(newData)
            elif key == 'COLOR_0':
                data = accessor.data
                if accessor.type == 'VEC4':
                    # displayColor for USD should have Color3Array type
                    newData = []
                    for el in range(accessor.count):
                        newData.append((
                            float(data[el * accessor.components]),
                            float(data[el * accessor.components + 1]),
                            float(data[el * accessor.components + 2])))
                    data = newData
                usdGeom.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex).Set(data)
            elif key =='JOINTS_0':
                if usdSkelBinding != None:
                    newData = [0] * accessor.count * accessor.components
                    for i in range(accessor.count * accessor.components):
                        newData[i] = skin.remapIndex(accessor.data[i])
                    usdSkelBinding.CreateJointIndicesPrimvar(False, accessor.components).Set(newData)
            elif key =='WEIGHTS_0':
                if usdSkelBinding != None:
                    # Normalize weights
                    newData = Vt.FloatArray(list(map(float, accessor.data)))
                    UsdSkel.NormalizeWeights(newData, accessor.components)
                    usdSkelBinding.CreateJointWeightsPrimvar(False, accessor.components).Set(newData)
            else:
                usdUtils.printWarning("Unsupported primitive attribute: " + key)

        if (mode == gltfPrimitiveMode.TRIANGLES or 
            mode == gltfPrimitiveMode.TRIANGLE_STRIP or 
            mode == gltfPrimitiveMode.TRIANGLE_FAN):
            if indices is not None:
                if mode == gltfPrimitiveMode.TRIANGLE_STRIP:
                    indices = indicesWithTriangleStrip(indices)
                    count = len(indices)
                elif mode == gltfPrimitiveMode.TRIANGLE_FAN:
                    indices = indicesWithTriangleFan(indices)
                    count = len(indices)
                usdGeom.CreateFaceVertexIndicesAttr(indices)
            elif count > 0:
                if mode == gltfPrimitiveMode.TRIANGLES:
                    count = int(count / 3) * 3 # should be divisible by 3
                indices = [0] * count
                for ind in range(count):
                    indices[ind] = ind 
                if mode == gltfPrimitiveMode.TRIANGLE_STRIP:
                    indices = indicesWithTriangleStrip(indices)
                    count = len(indices)
                elif mode == gltfPrimitiveMode.TRIANGLE_FAN:
                    indices = indicesWithTriangleFan(indices)
                    count = len(indices)
                usdGeom.CreateFaceVertexIndicesAttr(indices)
            numFaceVertexCounts = int(count / 3)
            faceVertexCounts = [3] * numFaceVertexCounts
            usdGeom.CreateFaceVertexCountsAttr(faceVertexCounts) # per-face vertex indices
            usdGeom.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        elif mode == gltfPrimitiveMode.LINES:
            numCurveVertex = int(count / 2)
            curveVertexCounts = [2] * numCurveVertex
            usdGeom.CreateCurveVertexCountsAttr(curveVertexCounts) # per-face vertex indices
        elif (mode == gltfPrimitiveMode.LINE_LOOP or
            mode == gltfPrimitiveMode.LINE_STRIP):
            curveVertexCounts = [count] * 1
            usdGeom.CreateCurveVertexCountsAttr(curveVertexCounts) # per-face vertex indices

        # bind material to mesh
        if 'material' in gltfPrimitive:
            materialIdx = gltfPrimitive['material']
            UsdShade.MaterialBindingAPI(usdGeom.GetPrim()).Bind(self.usdMaterials[materialIdx])

            gltfMaterial = self.gltf['materials'][materialIdx]
            if 'doubleSided' in gltfMaterial and gltfMaterial['doubleSided'] == True:
                usdGeom.CreateDoubleSidedAttr(True)

        hasBlendShapes = True if 'targets' in gltfPrimitive else False
        if hasBlendShapes:
            targets = gltfPrimitive['targets']
            blendShapes = []
            blendShapeTargets = []
            for target in targets:
                blendShapeName = "blendShape" + str(targets.index(target))
                blendShapeTarget = path + "/" + blendShapeName
                blendShapeName = self.asset.makeUniqueBlendShapeName(blendShapeName, path)
                blendShapes.append(blendShapeName)
                blendShapeTargets.append(blendShapeTarget)
                usdBlendShape = UsdSkel.BlendShape.Define(self.usdStage, blendShapeTarget)

                positions = None
                positionsLen = 0
                normals = None
                normalsLen = 0
                for key in target:
                    if key == 'POSITION':
                        accessor = Accessor(self, target[key])
                        positions = accessor.data
                        positionsLen = int(len(positions) / 3)
                    elif key == 'NORMAL':
                        accessor = Accessor(self, target[key])
                        normals = accessor.data
                        normalsLen = int(len(normals) / 3)

                offsets = []
                normalOffsets = []
                pointIndices = []
                pointsCount = max(positionsLen, normalsLen)

                for idx in range(pointsCount):
                    if ((positionsLen and (positions[idx*3] != 0 or positions[idx*3 + 1] != 0 or positions[idx*3 + 2] != 0)) or
                        (normalsLen and (normals[idx*3] != 0 or normals[idx*3 + 1] != 0 or normals[idx*3 + 2] != 0))):

                        if positionsLen:
                            offsets.append(Gf.Vec3f(
                                float(positions[idx*3]), 
                                float(positions[idx*3 + 1]), 
                                float(positions[idx*3 + 2])))

                        if normalsLen:
                            normalOffsets.append(Gf.Vec3f(
                                float(normals[idx*3]), 
                                float(normals[idx*3 + 1]), 
                                float(normals[idx*3 + 2])))

                        pointIndices.append(idx)

                if positionsLen:
                    usdBlendShape.CreateOffsetsAttr(offsets)
                if normalsLen:
                    usdBlendShape.CreateNormalOffsetsAttr(normalOffsets)
                usdBlendShape.CreatePointIndicesAttr(pointIndices)

            usdSkelBlendShapeBinding = UsdSkel.BindingAPI(usdGeom)
            usdSkelBlendShapeBinding.CreateBlendShapesAttr(blendShapes)
            usdSkelBlendShapeBinding.CreateBlendShapeTargetsRel().SetTargets(blendShapeTargets)

            UsdSkel.BindingAPI.Apply(usdGeom.GetPrim())

            strNodeIdx = str(nodeIdx)
            if strNodeIdx in self.blendShapeByNode:
                blendShape = self.blendShapeByNode[strNodeIdx]
                blendShape.addBlendShapeList(blendShapes)

        return usdGeom


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
            for i in range(len(gltfPrimitives)):
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
        strNodeIdx = str(nodeIdx)
        skeleton = self.skinning.findSkeletonByRoot(str(nodeIdx))
        blendShape = self.blendShapeByNode[strNodeIdx] if strNodeIdx in self.blendShapeByNode else None
        if blendShape is not None:
            if self.verbose:
                print(indent + 'SkelRoot for Blend Shape: ' + name)
            usdGeom = blendShape.makeUsdSkeleton(self.usdStage, newPath)
        elif skeleton is not None:
            if self.verbose:
                print(indent + 'SkelRoot: ' + name)
            usdGeom = skeleton.makeUsdSkeleton(self.usdStage, newPath, self.nodeManager)
            underSkeleton = skeleton
        elif skeletonByJoint is not None and 'mesh' not in gltfNode:
            pass
        else:
            if 'mesh' in gltfNode:
                if 'skin' in gltfNode or underSkeleton is not None:
                    self.skeletonByNode[str(nodeIdx)] = underSkeleton
                    if self.verbose:
                        print(indent + 'Skinned mesh: ' + name)
                else:
                    if self.verbose:
                        print(indent + 'Mesh: ' + name)
                    usdGeom = self.processMesh(nodeIdx, newPath, underSkeleton)
            else:
                if self.verbose:
                    print(indent + 'Node: ' + name)
                usdGeom = UsdGeom.Xform.Define(self.usdStage, newPath)

            if usdGeom is not None:
                if 'matrix' in gltfNode:
                    usdGeom.AddTransformOp().Set(getMatrix(gltfNode['matrix']))
                else:
                    if 'translation' in gltfNode:
                        usdGeom.AddTranslateOp().Set(getVec3(gltfNode['translation']))
                    if 'rotation' in gltfNode:
                        if self.legacyModifier is None:
                            usdGeom.AddOrientOp().Set(getQuat(gltfNode['rotation']))
                        else:
                            usdGeom.AddRotateXYZOp().Set(self.legacyModifier.eulerWithQuat(getQuat(gltfNode['rotation'])))
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
                if 'node' not in gltfTarget:
                    continue
                nodeIdx = gltfTarget['node']

                skeleton = self.skinning.findSkeletonByJoint(str(nodeIdx))
                if skeleton is not None:
                    continue

                targetPath = gltfTarget['path']

                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                interpolation = gltfSampler['interpolation'] if 'interpolation' in gltfSampler else 'LINEAR'
                keyTimesAcc = Accessor(self, gltfSampler['input'])
                keyValuesAcc = Accessor(self, gltfSampler['output'])
                data = keyValuesAcc.data

                if nodeIdx not in self.usdGeoms:
                    continue

                usdGeom = self.usdGeoms[nodeIdx]

                xformOp = None
                getValueFromData = getGfQuatfFromData if targetPath == 'rotation' else getGfVec3fFromData

                if self.legacyModifier is not None and targetPath == 'rotation':
                    getValueFromData = self.legacyModifier.getEulerFromData

                if targetPath == 'translation':
                    xformOp = getXformOp(usdGeom, UsdGeom.XformOp.TypeTranslate)
                    if xformOp == None:
                        xformOp = usdGeom.AddTranslateOp()
                elif targetPath == 'rotation':
                    if self.legacyModifier is None:
                        xformOp = getXformOp(usdGeom, UsdGeom.XformOp.TypeOrient)
                        if xformOp == None:
                            xformOp = usdGeom.AddOrientOp()
                    else:
                        xformOp = getXformOp(usdGeom, UsdGeom.XformOp.TypeRotateXYZ)
                        if xformOp == None:
                            xformOp = usdGeom.AddRotateXYZOp()
                elif targetPath == 'scale':
                    xformOp = getXformOp(usdGeom, UsdGeom.XformOp.TypeScale)
                    if xformOp == None:
                        xformOp = usdGeom.AddScaleOp()
                elif targetPath == 'weights':
                    pass
                else:
                    if self.verbose:
                        usdUtils.printWarning("Animation: unsupported target path: " + targetPath)
                    continue

                if xformOp == None:
                    continue

                values = self.getInterpolatedValues(interpolation, keyTimesAcc, keyValuesAcc, getValueFromData)
                for time, value in values.items():
                    xformOp.Set(time = time, value = value)


    def processSkinnedMeshes(self):
        for strNodeIdx, skeleton in self.skeletonByNode.items():
            nodeIdx = int(strNodeIdx)
            gltfNode = self.gltf['nodes'][nodeIdx]
            if skeleton is None and 'skin' in gltfNode:
                skinIdx = gltfNode['skin']
                skin = self.skinning.skins[skinIdx]
                skeleton = skin.skeleton

            name = getName(gltfNode, 'node_', nodeIdx)
            if name in self.nodeNames:
                name = name + '_' + str(nodeIdx)
            self.nodeNames[name] = name

            newPath = skeleton.sdfPath + '/' + name
            usdGeom = self.processMesh(nodeIdx, newPath, skeleton)
            if usdGeom is not None:
                self.usdGeoms[nodeIdx] = usdGeom


    def processBlendShapeMeshes(self):
        for strNodeIdx, blendShape in self.blendShapeByNode.items():
            if strNodeIdx in self.skeletonByNode:
                continue # avoid nodes with skeletons
            nodeIdx = int(strNodeIdx)
            gltfNode = self.gltf['nodes'][nodeIdx]

            name = getName(gltfNode, 'node_', nodeIdx)
            if name in self.nodeNames:
                name = name + '_' + str(nodeIdx)
            self.nodeNames[name] = name

            newPath = blendShape.sdfPath + '/' + name
            usdGeom = self.processMesh(nodeIdx, newPath, None)
            if usdGeom is not None:
                self.usdGeoms[nodeIdx] = usdGeom


    def makeUsdStage(self):
        if self._loadFailed:
            return None
        self.usdStage = self.asset.makeUsdStage()
        self.createMaterials()
        self.prepareSkinning()
        self.prepareBlendShapes()
        self.prepareAnimations()
        self.processNodeChildren(self.gltf['scenes'][0]['nodes'], self.asset.getGeomPath(), None)
        self.processSkeletonAnimation()
        self.processBlendShapeAnimations()
        self.processSkinnedMeshes()
        self.processBlendShapeMeshes()
        self.processNodeTransformAnimation()
        self.shapeBlending.flush()
        self.asset.finalize()
        return self.usdStage



def usdStageWithGlTF(gltfPath, usdPath, legacyModifier, openParameters):
    if usdStageWithGlTFLoaded == False:
        return None

    converter = glTFConverter(gltfPath, usdPath, legacyModifier, openParameters)
    return converter.makeUsdStage()

