import os.path
from shutil import copyfile
import imp
from pxr import *

import usdUtils


_pilLibraryLoaded = True
try:
    imp.find_module('PIL')
    from PIL import Image
except ImportError:
    usdUtils.printError('failed to import PIL. Please install module, e.g. using "$ sudo pip3 install pillow".')
    _pilLibraryLoaded = False



class iOS12LegacyModifier:
    def __init__(self):
        self.oneChannelTextures = {}


    def eulerWithQuat(self, quat):
        rot = Gf.Rotation()
        rot.SetQuat(quat)
        return rot.Decompose(Gf.Vec3d(1, 0, 0), Gf.Vec3d(0, 1, 0), Gf.Vec3d(0, 0, 1))


    def getEulerFromData(self, data, offset):
        quat = Gf.Quatf(float(data[offset + 3]), Gf.Vec3f(float(data[offset]), float(data[offset + 1]), float(data[offset + 2])))
        return self.eulerWithQuat(quat)


    def makeOneChannelTexture(self, srcFile, dstFolder, channel, verbose):
        if not _pilLibraryLoaded:
            return ''
        pilChannel = channel.upper()
        if pilChannel != 'R' and pilChannel != 'G' and pilChannel != 'B':
            return ''

        basename = os.path.basename(srcFile)
        (name, ext) = os.path.splitext(basename)
        textureFilename = name + '_' + channel + ext
        lenDstFolder = len(dstFolder)
        newPath = dstFolder
        if lenDstFolder > 0 and dstFolder[lenDstFolder-1] != '/' and dstFolder[lenDstFolder-1] != '\\':
            newPath += '/'
        newPath += textureFilename
        if newPath in self.oneChannelTextures:
            return self.oneChannelTextures[newPath]

        image = None
        try:
            image = Image.open(srcFile)
            image = image.getchannel(pilChannel)
        except:
            usdUtils.printWarning("can't get channel " + pilChannel + " from texture " + basename)
            return ''

        if image is not None:
            image.save(newPath)
            self.oneChannelTextures[newPath] = textureFilename
            if verbose:
                print('One channel texture: ' + textureFilename)
            return textureFilename
        return ''


    def makeORMTextures(self, material, folder, verbose):
        inputNames = [
            usdUtils.InputName.occlusion, 
            usdUtils.InputName.roughness,
            usdUtils.InputName.metallic
            ]

        for inputName in inputNames:
            texture = self._getMapTextureFilename(material, inputName)
            if texture:
                map = material.inputs[inputName]
                file = self.makeOneChannelTexture(folder + '/' + texture, folder, map.channels, verbose)
                if file:
                    map.file = file
                    map.channels = 'r'


    def addSkelAnimToMesh(self, usdMesh, skeleton):
        if skeleton.usdSkelAnim is not None:
            usdSkelBinding = UsdSkel.BindingAPI(usdMesh)
            usdSkelBinding.CreateAnimationSourceRel().AddTarget(skeleton.usdSkelAnim.GetPath())


    def opacityAndDiffuseOneTexture(self, material):
        opacity = material.inputs[usdUtils.InputName.opacity] if usdUtils.InputName.opacity in material.inputs else None
        if not isinstance(opacity, usdUtils.Map):
            return
        diffuse = material.inputs[usdUtils.InputName.diffuseColor] if usdUtils.InputName.diffuseColor in material.inputs else None
        if not isinstance(diffuse, usdUtils.Map):
            return
        if opacity.file and diffuse.file and opacity.file != diffuse.file:
            usdUtils.printError('iOS12 compatibility: material ' + material.name + ' has different texture files for diffuseColor and opacity.')
            raise usdUtils.ConvertError()


    def _getMapTextureFilename(self, material, inputName):
        if not inputName in material.inputs:
            return None
        input = material.inputs[inputName]
        if not isinstance(input, usdUtils.Map):
            return None
        return input.file



def createLegacyModifier():
    return iOS12LegacyModifier()

