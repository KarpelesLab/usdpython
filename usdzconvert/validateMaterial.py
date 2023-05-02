import argparse
import os, shutil, sys

from pxr import *

class TermColors:
    WARN = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'

def _Err(msg):
    sys.stderr.write(TermColors.FAIL + msg + TermColors.END + '\n')

def _Warn(msg):
    sys.stderr.write(TermColors.WARN + msg + TermColors.END + '\n')

def validateType(property, correctType, shaderPath, verboseOutput, errorData):
    if not property:
        return True
    if property.GetTypeName() != correctType:
        errorData.append({
            "code": "ERR_INCORRECT_PROPERTY_TYPE",
            "shaderPath": shaderPath,
            "propertyName": property.GetFullName(),
            "propertyTypeName": str(property.GetTypeName()),
            "correctPropertyType": str(correctType)
        })
        if verboseOutput:_Err("\t" + shaderPath + ": " + property.GetFullName() + " type " +
                              str(property.GetTypeName()) + " is not correct type "+ str(correctType) + ".")
        return False
    return True

def validateConnection(property, connection, verboseOutput, errorData):
    if not connection:
        return True
    elif connection[2] == UsdShade.AttributeType.Output:
        output = connection[0].GetOutput(connection[1])
        if not output:
            errorData.append({
                "code": "ERR_MISSING_OUTPUT",
                "connectionPath": connection[0].GetPrim().GetPath().pathString,
                "output": connection[1]
            })
            if verboseOutput: _Err("\t" + connection[0].GetPrim().GetPath().pathString + ": is missing output " +
                                   connection[1] + ".")
            return False
        else:
            if property.GetTypeName().cppTypeName != output.GetTypeName().cppTypeName:
                errorData.append({
                    "code": "ERR_MISMATCHED_PROPERTY_TYPE",
                    "connectionPath": connection[0].GetPrim().GetPath().pathString,
                    "outputTypeName": str(output.GetTypeName()),
                    "propertyTypeName": str(property.GetTypeName())
                })
                if verboseOutput: _Err("\t" + connection[0].GetPrim().GetPath().pathString + ": output type of " +
                                       str(output.GetTypeName()) + " mismatches connecting property type " +
                                       str(property.GetTypeName()) + ".")
                return False

    elif connection[2] ==  UsdShade.AttributeType.Input:
        input = connection[0].GetInput(connection[1])
        if not input:
            errorData.append({
                "code": "ERR_MISSING_INPUT",
                "connectionPath": connection[0].GetPrim().GetPath().pathString,
                "input": connection[1]
            })
            if verboseOutput: _Err("\t" + connection[0].GetPrim().GetPath().pathString + ": is missing input " +
                                   connection[1] + ".")
            return False
        else:
            if property.GetTypeName().cppTypeName != input.GetTypeName().cppTypeName:
                errorData.append({
                    "code": "ERR_MISMATCHED_PROPERTY_TYPE",
                    "connectionPath": connection[0].GetPrim().GetPath().pathString,
                    "outputTypeName": str(output.GetTypeName()),
                    "propertyTypeName": str(property.GetTypeName())
                })
                if verboseOutput: _Err("\t" + connection[0].GetPrim().GetPath().pathString + ": output type of " +
                                       str(input.GetTypeName()) + " mismatches connecting property type " +
                                       str(property.GetTypeName()) + ".")
                return False
    else:
        pass
    return True

def validatePropertyType(shaderPath, property, verboseOutput, errorData):
    baseName = property.GetBaseName()
    if baseName in ["diffuseColor", "emissiveColor", "specularColor"]:
        if not validateType(property, Sdf.ValueTypeNames.Color3f, shaderPath, verboseOutput, errorData):
            return False
    elif baseName == "normal":
        if not validateType(property, Sdf.ValueTypeNames.Normal3f, shaderPath, verboseOutput, errorData):
            return False
    elif baseName in ["ior", "metallic", "roughness", "clearcoat", "clearcoatRoughness", "opacity",
                        "opacityThreshold", "occlusion", "displacement"]:
        if not validateType(property, Sdf.ValueTypeNames.Float, shaderPath, verboseOutput, errorData):
            return False
    elif baseName == "useSpecularWorkflow":
        if not validateType(property, Sdf.ValueTypeNames.Int, shaderPath, verboseOutput, errorData):
            return False
    return True


def validateTextureNode(shaderNode, verboseOutput, errorData):
    shaderPath = shaderNode.GetPrim().GetPath().pathString
    assetInput = shaderNode.GetInput("file")
    if not validateType(assetInput, Sdf.ValueTypeNames.Asset, shaderPath, verboseOutput, errorData):
        return False
    if not assetInput or assetInput.Get() == None:
        errorData.append({
            "code": "WRN_NO_TEXTURE_FILE",
            "shaderPath": shaderPath
        })
        if verboseOutput:_Warn("\t" + shaderPath + ": no texture file authored, fallback value will be used.")

    fallback = shaderNode.GetInput("fallback")
    default = shaderNode.GetInput("default")
    if default and not fallback:
        errorData.append({
            "code": "WRN_INPUT_DEFAULT_DEPRECATED",
            "shaderPath": shaderPath
        })
        if verboseOutput:_Warn("\t" + shaderPath+": input:default is deprecated, please author with input:fallback.")

    if not validateType(fallback, Sdf.ValueTypeNames.Float4, shaderPath, verboseOutput, errorData):
        return False

    if not validateType(shaderNode.GetInput("scale"), Sdf.ValueTypeNames.Float4, shaderPath, verboseOutput, errorData):
        return False

    if not validateType(shaderNode.GetInput("bias"), Sdf.ValueTypeNames.Float4, shaderPath, verboseOutput, errorData):
        return False

    if not validateType(shaderNode.GetInput("wrapS"), Sdf.ValueTypeNames.Token, shaderPath, verboseOutput, errorData):
        return False

    if not validateType(shaderNode.GetInput("wrapT"), Sdf.ValueTypeNames.Token, shaderPath, verboseOutput, errorData):
        return False

    st = shaderNode.GetInput("st")
    if not validateType(st, Sdf.ValueTypeNames.Float2, shaderPath, verboseOutput, errorData):
        return False

    if not st:
        errorData.append({
            "code": "ERR_NO_ST",
            "shaderPath": shaderPath
        })
        if verboseOutput: _Err("\t" + shaderPath + ": has no st input.")
        return False

    connect = UsdShade.ConnectableAPI.GetConnectedSource(st)
    if connect == None:
        return True

    if not validateConnection(st, connect, verboseOutput, errorData):
        return False

    connectable = UsdShade.Shader(connect[0])
    shaderId = connectable.GetIdAttr().Get()
    if shaderId == "UsdTransform2d":
        return validateTransform2dNode(connectable, verboseOutput, errorData)
    elif shaderId == "UsdPrimvarReader_float2":
        return validatePrimvarReaderNode(connectable, verboseOutput, errorData)
    else:
        errorData.append({
            "code": "ERR_ST_CONNECTION",
            "shaderPath": shaderPath,
            "shaderId": shaderId
        })
        if verboseOutput: _Err("\t" + shaderPath + ": st connect to " + shaderId + ".")
        return False

def validatePrimvarReaderNode(shaderNode, verboseOutput, errorData):
    shaderPath = shaderNode.GetPrim().GetPath().pathString
    shaderId = shaderNode.GetIdAttr().Get()
    primvarReaderType = shaderId[len('UsdPrimvarReader_'):]

    # TODO: support more types in preview surface proposal, we only check float2 for now
    if primvarReaderType != "float2":
        errorData.append({
            "code": "WRN_FLOAT2_TYPE_ONLY",
            "shaderPath": shaderPath,
            "shaderId": str(shaderId)
        })
        if verboseOutput: _Warn("\t" + shaderPath +": has shader id type " + str(shaderId) +
                                ", currently not supported by this checker.")
        return True

    varname = shaderNode.GetInput("varname")
    if not varname:
        errorData.append({
            "code": "ERR_NO_VARNAME",
            "shaderPath": shaderPath
        })
        if verboseOutput: _Err("\t" + shaderPath + ": has no varname input.")
        return False
    varnameType = varname.GetTypeName()
    if not (varnameType == Sdf.ValueTypeNames.String or varnameType == Sdf.ValueTypeNames.Token):
        errorData.append({
            "code": "ERR_INVALID_VARNAME_TYPE",
            "shaderPath": shaderPath,
            "varnameType": str(varnameType)
        })
        if verboseOutput:_Err("\t" + shaderPath + ": has invalid varname type " + str(varnameType) + ".")
        return False

    connect = UsdShade.ConnectableAPI.GetConnectedSource(varname)
    if not validateConnection(varname, connect, verboseOutput, errorData):
        return False

    fallback = shaderNode.GetInput("fallback")
    if not validateType(fallback, Sdf.ValueTypeNames.Float2, shaderPath, verboseOutput, errorData):
        return False

    output = shaderNode.GetOutput("result")
    if not validateType(output, Sdf.ValueTypeNames.Float2, shaderPath, verboseOutput, errorData):
        return False
    return True

def validateTransform2dNode(shaderNode, verboseOutput, errorData):
    shaderPath = shaderNode.GetPrim().GetPath().pathString

    input = shaderNode.GetInput("in")
    if not input:
        errorData.append({
            "code": "ERR_NO_INPUTS_IN",
            "shaderPath": shaderPath
        })
        if verboseOutput: _Err("\t" + shaderPath +": does not have inputs:in.")
        return False

    connect = UsdShade.ConnectableAPI.GetConnectedSource(input)

    if connect:
        if not validateConnection(input, connect, verboseOutput, errorData):
            return False
        else:
            connectable = UsdShade.Shader(connect[0])
            shaderId = connectable.GetIdAttr().Get()
            if shaderId == "UsdPrimvarReader_float2":
                if not validatePrimvarReaderNode(connectable, verboseOutput, errorData):
                    return False

    rotation = shaderNode.GetInput('rotation')
    if not validateType(rotation, Sdf.ValueTypeNames.Float, shaderPath, verboseOutput, errorData):
        return False

    scale = shaderNode.GetInput('scale')
    if not validateType(scale, Sdf.ValueTypeNames.Float2, shaderPath, verboseOutput, errorData):
        return False

    translation = shaderNode.GetInput('translation')
    if not validateType(translation, Sdf.ValueTypeNames.Float2, shaderPath, verboseOutput, errorData):
        return False
    return True


def validateMaterialProperty(pbrShader, property, verboseOutput, errorData):
    pbrShaderPath = pbrShader.GetPrim().GetPath().pathString
    if not validatePropertyType(pbrShaderPath, property, verboseOutput, errorData):
        return False

    connection = UsdShade.ConnectableAPI.GetConnectedSource(property)
    if connection == None:
        # constant material property
        return True
    if not validateConnection(property, connection, verboseOutput, errorData):
        return False

    connectable = UsdShade.Shader(connection[0])
    connectablePath = connectable.GetPrim().GetPath().pathString

    shaderId = connectable.GetIdAttr().Get()
    if shaderId == None:
        errorData.append({
            "code": "WRN_MISSING_SHADER_ID",
            "connectablePath": connectablePath
        })
        if verboseOutput: _Warn("\t" + connectablePath +": is missing shader id.")
        return False

    if shaderId == "UsdUVTexture":
        if not validateTextureNode(connectable, verboseOutput, errorData):
            return False
    elif shaderId.startswith("UsdPrimvarReader_"):
        if not validatePrimvarReaderNode(connectable, verboseOutput, errorData):
            return False
    else:
        errorData.append({
            "code": "WRN_UNRECOGNIZED_SHADER_ID",
            "connectablePath": connectablePath,
            "shaderId": shaderId
        })
        if verboseOutput:_Warn("\t" + connectablePath +": has unrecognized shaderId: " + shaderId + ".")
        return False

    return True

def validateMaterial(materialPrim, verbose, errorData):
    verboseOutput = verbose
    material = UsdShade.Material(materialPrim)
    materialPath = material.GetPrim().GetPath().pathString

    surface = material.GetSurfaceOutput()
    connect = UsdShade.ConnectableAPI.GetConnectedSource(surface)
    if not validateConnection(surface, connect, verboseOutput, errorData):
        return False
    if connect is None or not connect[0].IsContainer():
        # Empty material is valid
        return True

    connectable = connect[0]
    primPath = connectable.GetPrim().GetPath().pathString

    if not connectable.GetOutput("surface"):
        errorData.append({
            "code": "ERR_MISSING_SURFACE_OUTPUT",
            "primPath": primPath
        })
        if verboseOutput: _Err("\t" + primPath +": is missing surface output.")
        return False

    shader = UsdShade.Shader(connectable.GetPrim())

    if shader.GetIdAttr().Get() != "UsdPreviewSurface":
        errorData.append({
            "code": "ERR_NOT_USDPREVIEWSURFACE",
            "primPath": primPath
        })
        if verboseOutput: _Err("\t" + primPath + ": is not UsdPreviewSurface shader.")
        return False

    for shaderInput in shader.GetInputs():
        if not validateMaterialProperty(shader, shaderInput, verboseOutput, errorData):
            return False
    return True
