from pxr import *

import struct
import sys
import os.path
import time

import usdUtils


__all__ = ['usdMaterialWithObjMtl']


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



def usdMaterialWithObjMtl(converter, filename):
    if not os.path.isfile(filename):
        usdUtils.printWarning("Can't load material file. File not found: " + filename)
        return

    with open(filename, errors='ignore') as file:
        material = None

        primvarName = 'st'
        wrapS = usdUtils.WrapMode.repeat
        wrapT = usdUtils.WrapMode.repeat
        scaleFactor=None

        for line in linesContinuation(file):
            line = line.strip()
            if not line or '#' == line[0]:
                continue

            arguments = list(filter(None, line.split(' ')))
            command = arguments[0]
            arguments = arguments[1:]

            if 'newmtl' == command:
                primvarName = 'st'
                wrapS = usdUtils.WrapMode.repeat
                wrapT = usdUtils.WrapMode.repeat
                scaleFactor=None

                matName = ' '.join(arguments)
                converter.setMaterial(matName)
                material = usdUtils.Material(matName)
                converter.materialsByName[matName] = material
            elif material is not None:
                if 'Kd' == command:
                    diffuseColor = arguments
                    if usdUtils.InputName.diffuseColor in material.inputs:
                        material.inputs[usdUtils.InputName.diffuseColor].scale = diffuseColor
                    else:
                        material.inputs[usdUtils.InputName.diffuseColor] = diffuseColor
                        scaleFactor = diffuseColor
                elif 'd' == command:
                    material.inputs[usdUtils.InputName.opacity] = arguments[0] if len(arguments) > 0 else 1
                elif 'map_Kd' == command:
                    textureFilename = usdUtils.resolvePath(' '.join(arguments), converter.srcFolder, converter.searchPaths)
                    material.inputs[usdUtils.InputName.diffuseColor] = usdUtils.Map('rgb', textureFilename, None, primvarName, wrapS, wrapT, scaleFactor)
                elif 'map_bump' == command or 'bump' == command:
                    textureFilename = usdUtils.resolvePath(' '.join(arguments), converter.srcFolder, converter.searchPaths)
                    material.inputs[usdUtils.InputName.normal] = usdUtils.Map('rgb', textureFilename, None, primvarName, wrapS, wrapT)
                elif 'map_ao' == command:
                    textureFilename = usdUtils.resolvePath(' '.join(arguments), converter.srcFolder, converter.searchPaths)
                    material.inputs[usdUtils.InputName.occlusion] = usdUtils.Map('rgb', textureFilename, None, primvarName, wrapS, wrapT)
                elif 'map_metallic' == command:
                    textureFilename = usdUtils.resolvePath(' '.join(arguments), converter.srcFolder, converter.searchPaths)
                    material.inputs[usdUtils.InputName.metallic] = usdUtils.Map('rgb', textureFilename, None, primvarName, wrapS, wrapT)
                elif 'map_roughness' == command:
                    textureFilename = usdUtils.resolvePath(' '.join(arguments), converter.srcFolder, converter.searchPaths)
                    material.inputs[usdUtils.InputName.roughness] = usdUtils.Map('rgb', textureFilename, None, primvarName, wrapS, wrapT)


