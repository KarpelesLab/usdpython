#!/usr/bin/python
from pxr import *

import struct
import sys
import os.path
import time


__all__ = ['usdStageWithObj', 'makeValidUsdObjectName']


INVALID_INDEX = -1
LAST_ELEMENT = -1


class Subset:
    def __init__(self, materialIndex):
        self.faces = []
        self.materialIndex = materialIndex


class Group:
    def __init__(self, name, materialIndex):
        self.subsets = []
        self.currentSubset = None

        self.vertexIndices = []

        self.uvIndices = []
        self.uvsHaveOwnIndices = False  # avoid creating indexed uv UsdAttribute if uv indices are identical to vertex indices

        self.normalIndices = []
        self.normalsHaveOwnIndices = False  # avoid creating indexed normal UsdAttribute if normal indices are identical to vertex indices

        self.faceVertexCounts = []
        self.setMaterial(materialIndex)


    def setMaterial(self, materialIndex):
        self.currentSubset = None
        for subset in self.subsets:
            if subset.materialIndex == materialIndex:
                self.currentSubset = subset
                break
        # if currentSubset does not exist, create new one and append to subsets
        if self.currentSubset == None:
            # remove last empty subset
            if len(self.subsets) and len(self.subsets[LAST_ELEMENT].faces) == 0:
                del self.subsets[LAST_ELEMENT]

            self.currentSubset = Subset(materialIndex)
            self.subsets.append(self.currentSubset)


    def appendIndices(self, vertexIndex, uvIndex, normalIndex):
        self.vertexIndices.append(vertexIndex)
        self.uvIndices.append(uvIndex)
        self.normalIndices.append(normalIndex)


def fixExponent(value):
    # allow for scientific notation with X.Y(+/-)eZ
    return float(value.lower().replace('+e', 'e+').replace('-e', 'e-'))


def floatList(v):
    try:
        return map(float, v)
    except ValueError:
        return map(fixExponent, v)
    except:
        raise


class ObjData:
    def __init__(self, verbose):
        self.vertices = []
        self.colors = []
        self.uvs = []
        self.normals = []

        self.groups = {}
        self.currentGroup = None

        self.materials = []
        self.materialIndicesByName = {}
        self.currentMaterial = INVALID_INDEX
        self.usdMaterials = []
        self.verbose = verbose
        self.setGroup()


    def setMaterial(self, name):
        materialName = name if name else 'white' # white by spec
        if self.verbose:
            print '  setting material:', materialName
        # find material
        self.currentMaterial = self.materialIndicesByName.get(materialName, INVALID_INDEX)
        if self.currentMaterial < 0:
            self.materials.append(materialName)
            self.currentMaterial = len(self.materials) - 1
            self.materialIndicesByName[materialName] = self.currentMaterial

        if self.currentGroup != None:
            self.currentGroup.setMaterial(self.currentMaterial)


    def setGroup(self, name=''):
        groupName = name if name else 'default' # default by spec
        self.currentGroup = self.groups.get(groupName)
        if self.currentGroup == None:
            if self.verbose:
                print '  creating group:', groupName
            self.currentGroup = Group(groupName, self.currentMaterial)
            self.groups[groupName] = self.currentGroup
        else:
            if self.verbose:
                print '  setting group:', groupName
            self.currentGroup.setMaterial(self.currentMaterial)


    def addVertex(self, v):
        v = floatList(v)
        vLen = len(v)
        self.vertices.append(Gf.Vec3f(v[0:3]) if vLen >= 3 else Gf.Vec3f())
        if vLen >= 6:
            self.colors.append(Gf.Vec3f(v[3:6]))


    def addUV(self, v):
        v = floatList(v)
        self.uvs.append(Gf.Vec2f(v[0:2]) if len(v) >= 2 else Gf.Vec2f())


    def addNormal(self, v):
        v = floatList(v)
        self.normals.append(Gf.Vec3f(v[0:3]) if len(v) >= 3 else Gf.Vec3f())


    def addFace(self, arguments):
        # arguments have format like this: ['1/1/1', '2/2/2', '3/3/3']
        faceVertexCount = 0
        for indexStr in arguments:
            indices = indexStr.split('/')

            vertexIndex = convertObjIndexToUsd(indices[0], len(self.vertices))
            if vertexIndex == INVALID_INDEX:
                break

            uvIndex = INVALID_INDEX
            if 1 < len(indices):
                uvIndex = convertObjIndexToUsd(indices[1], len(self.uvs))
                if uvIndex != vertexIndex:
                    self.currentGroup.uvsHaveOwnIndices = True

            normalIndex = INVALID_INDEX
            if 2 < len(indices):
                normalIndex = convertObjIndexToUsd(indices[2], len(self.normals))
                if normalIndex != vertexIndex:
                    self.currentGroup.normalsHaveOwnIndices = True

            self.currentGroup.appendIndices(vertexIndex, uvIndex, normalIndex)
            faceVertexCount += 1

        if faceVertexCount > 0:
            self.currentGroup.currentSubset.faces.append(len(self.currentGroup.faceVertexCounts))
            self.currentGroup.faceVertexCounts.append(faceVertexCount)


    def checkLastSubsets(self):
        for groupName, group in self.groups.iteritems():
            if len(group.subsets) > 1 and len(group.subsets[LAST_ELEMENT].faces) == 0:
                    del group.subsets[LAST_ELEMENT]


def makeValidUsdObjectName(path):
    if len(path) > 0:
        if path[0].isdigit():
            path = '_' + path
        path = path.replace(' ', '_')
        path = path.replace('-', '_')
        path = path.replace('.', '_')
        path = path.replace(':', '_')
        path = path.replace('[', '_')
        path = path.replace(']', '_')
        path = path.replace('(', '_')
        path = path.replace(')', '_')
        path = path.replace('/', '_')
        path = path.replace('%', '_')
        if Sdf.Path.IsValidIdentifier(path):
            return path
    return 'default'


def convertObjIndexToUsd(strIndex, elementsCount):
    if not strIndex:
        return INVALID_INDEX
    index = int(strIndex)
    # OBJ indices starts from 1, USD indices starts from 0
    if 0 < index and index <= elementsCount:
        return index - 1
    # OBJ indices can be negative as reverse indexing
    if index < 0:
        return elementsCount + index
    return INVALID_INDEX


def createMaterial(objData, materialsPath, name, stage):
    materialName = makeValidUsdObjectName(name)
    usdMaterial = UsdShade.Material.Define(stage, materialsPath + '/' + materialName)
    objData.usdMaterials.append(usdMaterial)


def createMesh(objData, geomPath, group, groupName, stage):
    if len(group.faceVertexCounts) == 0:
        return False

    groupName = makeValidUsdObjectName(groupName)
    if objData.verbose:
        print '  creating USD mesh:', groupName, ('(subsets: ' + str(len(group.subsets)) + ')' if len(group.subsets) > 1 else '')
    mesh = UsdGeom.Mesh.Define(stage, geomPath + '/' + groupName)
    mesh.GetSubdivisionSchemeAttr().Set('none')

    mesh.CreateFaceVertexCountsAttr(group.faceVertexCounts)

    # vertices
    minVertexIndex = min(group.vertexIndices)
    maxVertexIndex = max(group.vertexIndices)

    groupVertices = objData.vertices[minVertexIndex:maxVertexIndex+1]
    mesh.CreatePointsAttr(groupVertices)
    if minVertexIndex == 0: # optimization
        mesh.CreateFaceVertexIndicesAttr(group.vertexIndices)
    else:
        mesh.CreateFaceVertexIndicesAttr(map(lambda x: x - minVertexIndex, group.vertexIndices))

    extent = Gf.Range3f()
    for pt in groupVertices:
        extent.UnionWith(Gf.Vec3f(pt))
    mesh.GetExtentAttr().Set([extent.GetMin(), extent.GetMax()])

    # vertex colors
    if len(objData.colors) == len(objData.vertices):
        colorAttr = mesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex)
        colorAttr.Set(objData.colors[minVertexIndex:maxVertexIndex+1])

    # texture coordinates
    minUvIndex = min(group.uvIndices)
    maxUvIndex = max(group.uvIndices)

    if minUvIndex >= 0:
        if group.uvsHaveOwnIndices:
            uvPrimvar = mesh.CreatePrimvar('st', Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
            uvPrimvar.Set(objData.uvs[minUvIndex:maxUvIndex+1])
            if minUvIndex == 0:  # optimization
                uvPrimvar.SetIndices(Vt.IntArray(group.uvIndices))
            else:
                uvPrimvar.SetIndices(Vt.IntArray(map(lambda x: x - minUvIndex, group.uvIndices)))
        else:
            uvPrimvar = mesh.CreatePrimvar('st', Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
            uvPrimvar.Set(objData.uvs[minUvIndex:maxUvIndex+1])

    # normals
    minNormalIndex = min(group.normalIndices)
    maxNormalIndex = max(group.normalIndices)

    if minNormalIndex >= 0:
        if group.normalsHaveOwnIndices:
            normalPrimvar = mesh.CreatePrimvar('normals', Sdf.ValueTypeNames.Normal3fArray, UsdGeom.Tokens.faceVarying)
            normalPrimvar.Set(objData.normals[minNormalIndex:maxNormalIndex+1])
            if minNormalIndex == 0:  # optimization
                normalPrimvar.SetIndices(Vt.IntArray(group.normalIndices))
            else:
                normalPrimvar.SetIndices(Vt.IntArray(map(lambda x: x - minNormalIndex, group.normalIndices)))
        else:
            mesh.CreateNormalsAttr(objData.normals[minNormalIndex:maxNormalIndex+1])

    # materials
    if len(group.subsets) == 1:
        materialIndex = group.subsets[0].materialIndex
        if 0 <= materialIndex and materialIndex < len(objData.usdMaterials):
            if objData.verbose:
                print '  material:', objData.materials[materialIndex]
            UsdShade.MaterialBindingAPI(mesh).Bind(objData.usdMaterials[materialIndex])
    else:
        bindingAPI = UsdShade.MaterialBindingAPI(mesh)
        for subset in group.subsets:
            materialIndex = subset.materialIndex
            if 0 <= materialIndex and materialIndex < len(objData.usdMaterials) and len(subset.faces) > 0:
                materialName = makeValidUsdObjectName(objData.materials[materialIndex])
                subsetName = materialName + 'Subset'
                if objData.verbose:
                    print '  subset:', subsetName, 'faces:', len(subset.faces)
                usdSubset = UsdShade.MaterialBindingAPI.CreateMaterialBindSubset(bindingAPI, subsetName, Vt.IntArray(subset.faces))
                UsdShade.MaterialBindingAPI(usdSubset).Bind(objData.usdMaterials[materialIndex])

def linesContinuation(fileHandle):
    for line in fileHandle:
        line = line.rstrip('\n')
        while line.endswith('\\'):
            thisLine = line[:-1]
            nextLine = next(fileHandle).rstrip('\n')
            line = thisLine + nextLine

        yield line

def parseObjFile(objPath, verbose):
    objData = ObjData(verbose)
    with open(objPath) as file:
        for line in linesContinuation(file):
            line = line.strip()
            if not line or '#' == line[0]:
                continue

            arguments = filter(None, line.split(' '))
            command = arguments[0]
            arguments = arguments[1:]
            
            if 'v' == command:
                objData.addVertex(arguments)
            elif 'vt' == command:
                objData.addUV(arguments)
            elif 'vn' == command:
                objData.addNormal(arguments)
            elif 'f' == command:
                objData.addFace(arguments)
            elif 'g' == command or 'o' == command:
                objData.setGroup(' '.join(arguments))
            elif 'usemtl' == command:
                objData.setMaterial(' '.join(arguments))

    objData.checkLastSubsets()

    return objData


def usdStageWithObj(objPath, usdPath, verbose=0):
    start = time.time()
    objData = parseObjFile(objPath, verbose)
    if verbose:
        print '  parsing OBJ file:', time.time() - start, 'sec'

    usdStage = Usd.Stage.CreateNew(usdPath)
    UsdGeom.SetStageUpAxis(usdStage, UsdGeom.Tokens.y)

    fileName = os.path.basename(usdPath)
    assetName = fileName[:fileName.find('.')]
    assetName = makeValidUsdObjectName(assetName)

    assetPath = '/' + assetName

    # create root prim
    rootPrim = usdStage.DefinePrim(assetPath, 'Xform')
    rootPrim.SetAssetInfoByKey('name', assetName)
    Usd.ModelAPI(rootPrim).SetKind('component')
    usdStage.SetDefaultPrim(rootPrim)

    # create all materials
    materialsPath = assetPath + '/Materials'
    usdStage.DefinePrim(materialsPath, 'Scope')
    for material in objData.materials:
        createMaterial(objData, materialsPath, material, usdStage)

    if len(objData.vertices) == 0:
        return usdStage

    # create all meshes
    geomPath = assetPath + '/Geom'
    usdStage.DefinePrim(geomPath, 'Scope')
    for groupName, group in objData.groups.iteritems():
        createMesh(objData, geomPath, group, groupName, usdStage)
    if verbose:
        print '  creating stage from obj file:', time.time() - start, 'sec'

    return usdStage
