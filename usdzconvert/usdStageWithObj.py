from pxr import *

import struct
import sys
import os.path
import time
import importlib

import usdUtils


__all__ = ['usdStageWithObj']


INVALID_INDEX = -1
LAST_ELEMENT = -1


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


def fixExponent(value):
    # allow for scientific notation with X.Y(+/-)eZ
    return float(value.lower().replace('+e', 'e+').replace('-e', 'e-'))


def floatList(v):
    try:
        return list(map(float, v))
    except ValueError:
        return list(map(fixExponent, v))
    except:
        raise


def linesContinuation(fileHandle):
    for line in fileHandle:
        line = line.rstrip('\n')
        line = line.rstrip()
        while line.endswith('\\'):
            thisLine = line[:-1]
            nextLine = next(fileHandle).rstrip('\n')
            nextLine = nextLine.strip()
            line = thisLine + ' ' + nextLine
        yield line



class Subset:
    def __init__(self, materialIndex):
        self.faces = []
        self.materialIndex = materialIndex


class Group:
    def __init__(self, materialIndex):
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



class ObjConverter:
    def __init__(self, objPath, usdPath, useMtl, openParameters):
        self.usdPath = usdPath
        self.useMtl = useMtl
        self.searchPaths = openParameters.searchPaths
        self.verbose = openParameters.verbose

        filenameFull = objPath.split('/')[-1]
        self.srcFolder = objPath[:len(objPath)-len(filenameFull)]

        self.vertices = []
        self.colors = []
        self.uvs = []
        self.normals = []

        self.groups = {}
        self.currentGroup = None

        self.materialNames = []
        self.materialIndicesByName = {}
        self.currentMaterial = INVALID_INDEX
        self.materialsByName = {}  # created with .mtl files
        self.usdMaterials = []
        self.usdDefaultMaterial = None
        self.asset = None
        self.setGroup()

        self.parseObjFile(objPath)
        openParameters.metersPerUnit = 0.01


    def setMaterial(self, name):
        materialName = name if name else 'white' # white by spec
        if self.verbose:
            print('  setting material: ' + materialName)
        # find material
        self.currentMaterial = self.materialIndicesByName.get(materialName, INVALID_INDEX)
        if self.currentMaterial == INVALID_INDEX:
            self.materialNames.append(materialName)
            self.currentMaterial = len(self.materialNames) - 1
            self.materialIndicesByName[materialName] = self.currentMaterial

        if self.currentGroup != None:
            self.currentGroup.setMaterial(self.currentMaterial)


    def setGroup(self, name=''):
        groupName = name if name else 'default' # default by spec
        self.currentGroup = self.groups.get(groupName)
        if self.currentGroup == None:
            if self.verbose:
                print('  creating group: ' + groupName)
            self.currentGroup = Group(self.currentMaterial)
            self.groups[groupName] = self.currentGroup
        else:
            if self.verbose:
                print('  setting group: ' + groupName)
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
        for groupName, group in self.groups.items():
            if len(group.subsets) > 1 and len(group.subsets[LAST_ELEMENT].faces) == 0:
                del group.subsets[LAST_ELEMENT]


    def getUsdMaterial(self, materialIndex):
        if 0 <= materialIndex and materialIndex < len(self.usdMaterials):
            return self.usdMaterials[materialIndex]
        else:
            if self.usdDefaultMaterial is None:
                material = usdUtils.Material("defaultMaterial")
                self.usdDefaultMaterial = material.makeUsdMaterial(self.asset)
            return self.usdDefaultMaterial                


    def createMesh(self, geomPath, group, groupName, usdStage):
        if len(group.faceVertexCounts) == 0:
            return False

        groupName = usdUtils.makeValidIdentifier(groupName)
        if self.verbose:
            print('  creating USD mesh: ' + groupName + ('(subsets: ' + str(len(group.subsets)) + ')' if len(group.subsets) > 1 else ''))
        usdMesh = UsdGeom.Mesh.Define(usdStage, geomPath + '/' + groupName)
        usdMesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)

        usdMesh.CreateFaceVertexCountsAttr(group.faceVertexCounts)

        # vertices
        minVertexIndex = min(group.vertexIndices)
        maxVertexIndex = max(group.vertexIndices)

        groupVertices = self.vertices[minVertexIndex:maxVertexIndex+1]
        usdMesh.CreatePointsAttr(groupVertices)
        if minVertexIndex == 0: # optimization
            usdMesh.CreateFaceVertexIndicesAttr(group.vertexIndices)
        else:
            usdMesh.CreateFaceVertexIndicesAttr(list(map(lambda x: x - minVertexIndex, group.vertexIndices)))

        extent = Gf.Range3f()
        for pt in groupVertices:
            extent.UnionWith(Gf.Vec3f(pt))
        usdMesh.CreateExtentAttr([extent.GetMin(), extent.GetMax()])

        # vertex colors
        if len(self.colors) == len(self.vertices):
            colorAttr = usdMesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex)
            colorAttr.Set(self.colors[minVertexIndex:maxVertexIndex+1])

        # texture coordinates
        minUvIndex = min(group.uvIndices)
        maxUvIndex = max(group.uvIndices)

        if minUvIndex >= 0:
            if group.uvsHaveOwnIndices:
                uvPrimvar = UsdGeom.PrimvarsAPI(usdMesh).CreatePrimvar('st', Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
                uvPrimvar.Set(self.uvs[minUvIndex:maxUvIndex+1])
                if minUvIndex == 0:  # optimization
                    uvPrimvar.SetIndices(Vt.IntArray(group.uvIndices))
                else:
                    uvPrimvar.SetIndices(Vt.IntArray(list(map(lambda x: x - minUvIndex, group.uvIndices))))
            else:
                uvPrimvar = UsdGeom.PrimvarsAPI(usdMesh).CreatePrimvar('st', Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
                uvPrimvar.Set(self.uvs[minUvIndex:maxUvIndex+1])

        # normals
        minNormalIndex = min(group.normalIndices)
        maxNormalIndex = max(group.normalIndices)

        if minNormalIndex >= 0:
            if group.normalsHaveOwnIndices:
                normalPrimvar = UsdGeom.PrimvarsAPI(usdMesh).CreatePrimvar('normals', Sdf.ValueTypeNames.Normal3fArray, UsdGeom.Tokens.faceVarying)
                normalPrimvar.Set(self.normals[minNormalIndex:maxNormalIndex+1])
                if minNormalIndex == 0:  # optimization
                    normalPrimvar.SetIndices(Vt.IntArray(group.normalIndices))
                else:
                    normalPrimvar.SetIndices(Vt.IntArray(list(map(lambda x: x - minNormalIndex, group.normalIndices))))
            else:
                normalPrimvar = UsdGeom.PrimvarsAPI(usdMesh).CreatePrimvar('normals', Sdf.ValueTypeNames.Normal3fArray, UsdGeom.Tokens.vertex)
                normalPrimvar.Set(self.normals[minNormalIndex:maxNormalIndex+1])

        # materials
        if len(group.subsets) == 1:
            materialIndex = group.subsets[0].materialIndex
            if self.verbose:
                if 0 <= materialIndex and materialIndex < len(self.usdMaterials):
                    print(usdUtils.makeValidIdentifier(self.materialNames[materialIndex]))
                else:
                    print('defaultMaterial')
            UsdShade.MaterialBindingAPI(usdMesh).Bind(self.getUsdMaterial(materialIndex))
        else:
            bindingAPI = UsdShade.MaterialBindingAPI(usdMesh)
            for subset in group.subsets:
                materialIndex = subset.materialIndex
                if len(subset.faces) > 0:
                    materialName = 'defaultMaterial'
                    if 0 <= materialIndex and materialIndex < len(self.usdMaterials):
                        materialName = usdUtils.makeValidIdentifier(self.materialNames[materialIndex])
                    subsetName = materialName + 'Subset'
                    if self.verbose:
                        print('  subset: ' + subsetName + ' faces: ' + str(len(subset.faces)))
                    usdSubset = UsdShade.MaterialBindingAPI.CreateMaterialBindSubset(bindingAPI, subsetName, Vt.IntArray(subset.faces))
                    UsdShade.MaterialBindingAPI(usdSubset).Bind(self.getUsdMaterial(materialIndex))


    def loadMaterialsFromMTLFile(self, filename):
        global usdMaterialWithObjMtl_module
        usdMaterialWithObjMtl_module = importlib.import_module("usdMaterialWithObjMtl")
        usdStage = usdMaterialWithObjMtl_module.usdMaterialWithObjMtl(self, filename)


    def parseObjFile(self, objPath):
        with open(objPath, errors='ignore') as file:
            for line in linesContinuation(file):
                line = line.strip()
                if not line or '#' == line[0]:
                    continue

                arguments = list(filter(None, line.split(' ')))
                command = arguments[0]
                arguments = arguments[1:]
                
                if 'v' == command:
                    self.addVertex(arguments)
                elif 'vt' == command:
                    self.addUV(arguments)
                elif 'vn' == command:
                    self.addNormal(arguments)
                elif 'f' == command:
                    self.addFace(arguments)
                elif 'g' == command or 'o' == command:
                    self.setGroup(' '.join(arguments))
                elif 'usemtl' == command:
                    self.setMaterial(' '.join(arguments))
                elif 'mtllib' == command:
                    if self.useMtl:
                        filename = os.path.dirname(objPath) + '/' + (' '.join(arguments))
                        self.loadMaterialsFromMTLFile(filename)

        self.checkLastSubsets()


    def makeUsdStage(self):
        self.asset = usdUtils.Asset(self.usdPath)
        usdStage = self.asset.makeUsdStage()

        # create all materials
        for matName in self.materialNames:
            if matName in self.materialsByName:
                material = self.materialsByName[matName]
            else:
                material = usdUtils.Material(matName)
            usdMaterial = material.makeUsdMaterial(self.asset)
            self.usdMaterials.append(usdMaterial)

        if len(self.vertices) == 0:
            return usdStage

        # create all meshes
        geomPath = self.asset.getGeomPath()
        for groupName, group in self.groups.items():
            self.createMesh(geomPath, group, groupName, usdStage)

        return usdStage



def usdStageWithObj(objPath, usdPath, useMtl, openParameters):
    start = time.time()
    converter = ObjConverter(objPath, usdPath, useMtl, openParameters)
    usdStage = converter.makeUsdStage()
    if openParameters.verbose:
        print('  creating stage from obj file: ' + str(time.time() - start) + ' sec')
    return usdStage
