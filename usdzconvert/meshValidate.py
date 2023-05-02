#!/usr/bin/python
import argparse
import os, shutil, sys

from pxr import *

verboseOutput = False

class TermColors:
	WARN = '\033[93m'
	FAIL = '\033[91m'
	END = '\033[0m'

def _Print(stream, msg):
	print >>stream, msg

def _Err(msg):
	sys.stderr.write(TermColors.FAIL + msg + TermColors.END + '\n')

def _Warn(msg):
	sys.stderr.write(TermColors.WARN + msg + TermColors.END + '\n')

def gatherMeshPrims(stage):
	predicate = Usd.TraverseInstanceProxies(Usd.PrimIsActive & Usd.PrimIsDefined & ~Usd.PrimIsAbstract)
	meshPrims = set()
	for prim in stage.Traverse(predicate):
		if prim.GetTypeName() == "Mesh":
			meshPrims.add(prim)
	return meshPrims

def validateTopology(faceVertexCounts, faceVertexIndices, pointsCount, meshPath):
	if len(faceVertexIndices) < len(faceVertexCounts):
		if verboseOutput: _Warn("\t" + meshPath + ": faceVertexIndices's size is less then the size of faceVertexCounts.")
		return False
	return True

def validateGeomsubset(subset, facesCount, subsetName):
	indicesAttr = subset.GetIndicesAttr()
	indices = []
	if indicesAttr:
		indices = indicesAttr.Get()

	if len(indices) == 0 or len(indices) > facesCount:
		if verboseOutput: _Warn("\tsubset " + subsetName + "'s faceIndices are invalid")
		return False
	return True

def validateMeshAttribute(meshPath, value, indices, attrName, typeName, interpolation, elementSize, facesCount, faceVertexIndicesCount, pointsCount, unauthoredValueIndex = None):
	valueCount = len(value)
	if not typeName.isArray:
		valueCount = 1
	indicesCount = len(indices)

	if interpolation == UsdGeom.Tokens.constant:
		if not valueCount == elementSize:
			if verboseOutput: _Warn("\t"+meshPath + ": " + attrName + " has constant interpolation and number of value " + str(valueCount) + " is not equal to element size " + str(elementSize))
			return False
	elif interpolation == UsdGeom.Tokens.vertex or interpolation == UsdGeom.Tokens.varying:
		if indicesCount > 0:
			if indicesCount != pointsCount:
				if verboseOutput: _Warn("\t"+meshPath + ": " + attrName + " has " + interpolation + " interpolation and number of attribute indices " + str(indicesCount) + " is not equal to points count " + str(pointsCount))
				return False
		else:
			if valueCount != pointsCount * elementSize:
				if verboseOutput: _Warn("\t"+meshPath + ": " + attrName + " has "+ interpolation + " interpolation and no indices. The number of value " + str(valueCount) + " is not equal to points count (" + str(pointsCount) + ") * elementSize (" + str(elementSize) + ")")
				return False
	elif interpolation == UsdGeom.Tokens.uniform:
		if indicesCount > 0:
			if indicesCount != facesCount:
				if verboseOutput: _Warn("\t"+meshPath + ": " + attrName + " has uniform interpolation and number of attribute indices " + indicesCount + " is not equal to faces count " + str(facesCount))
				return False
		else:
			if valueCount != facesCount * elementSize:
				if verboseOutput: _Warn("\t"+meshPath + ": " + attrName + " has uniform interpolation and no indices. The number of value " + str(valueCount) + " is not equal to faces count (" + str(facesCount) + ") * elementSize (" + str(elementSize) + ")")
				return False
	elif interpolation == UsdGeom.Tokens.faceVarying:
		if indicesCount > 0:
			if indicesCount != faceVertexIndicesCount:
				if verboseOutput: _Warn("\t"+meshPath + ": " + attrName + " has face varying interpolation and number of attribute indices " + str(indicesCount) + " is not equal to face vertices count " + str(faceVertexIndicesCount))
				return False
		else:
			if valueCount != faceVertexIndicesCount * elementSize:
				if verboseOutput: _Warn("\t"+meshPath + ": " + attrName + " has face varying interpolation and no indices. The number of value " + str(valueCount) + " is not equal to face vertices count (" + str(faceVertexIndicesCount) + ") * elementSize (" + str(elementSize) + ")")
				return False
	else:
		if verboseOutout: _Warn("\t"+meshPath + ": " + attrName + " has unknown interpolation " + interpolation)
		return False
	return True

def validatePrimvar(meshPath, primvar, facesCount, faceVertexIndicesCount, pointsCount):
	if primvar.HasAuthoredValue():
		indices = []
		if primvar.IsIndexed():
			indices = primvar.GetIndices()
		attrName, typeName, interpolation, elementSize = primvar.GetDeclarationInfo()
		unauthoredValueIndex = primvar.GetUnauthoredValuesIndex()
		if not validateMeshAttribute(meshPath, primvar.Get(), indices, attrName, typeName, interpolation, elementSize, facesCount, faceVertexIndicesCount, pointsCount, unauthoredValueIndex):
			return False

	return True

def meshValidate(file, verbose):
	global verboseOutput 
	verboseOutput = verbose
	stage = Usd.Stage.Open(file)
	meshPrims = gatherMeshPrims(stage)
	valid = True
	for prim in meshPrims:
		meshPath = prim.GetPath().pathString
		mesh = UsdGeom.Mesh(prim)
		faceVertexCounts = mesh.GetFaceVertexCountsAttr().Get()
		if faceVertexCounts is None or len(faceVertexCounts) == 0:
			if verboseOutput: _Warn("\t" + meshPath + " has no face vertex counts data")
			continue

		faceVertexIndices = mesh.GetFaceVertexIndicesAttr().Get()
		if faceVertexIndices is None or len(faceVertexIndices) == 0:
			if verboseOutput: _Warn("\t" + meshPath + " has no face vertex indices data")
			continue

		points = mesh.GetPointsAttr().Get()
		if points is None or len(points) == 0:
			if verboseOutput: _Warn("\t" + meshPath + " has no position data")
			continue

		pointsCount = len(points)
		if not validateTopology(faceVertexCounts, faceVertexIndices, pointsCount, meshPath):
			if verboseOutput: _Err("\t " + meshPath + " has invalid topology")
			valid = False
			continue

		facesCount = len(faceVertexCounts)
		faceVertexIndicesCount = len(faceVertexIndices)

		subsets = UsdGeom.Subset.GetGeomSubsets(mesh)
		for subset in subsets:
			if not validateGeomsubset(subset, facesCount, subset.GetPrim().GetName()):
				valid = False

		# handle normal attribute that's not authored as primvar
		normalAttr = mesh.GetNormalsAttr()
		if normalAttr.HasAuthoredValue():
			if not validateMeshAttribute(meshPath, normalAttr.Get(), [], normalAttr.GetName(), Sdf.ValueTypeNames.Normal3fArray, mesh.GetNormalsInterpolation(), 1, facesCount, faceVertexIndicesCount, pointsCount, None):
				valid = False

		prim = UsdGeom.PrimvarsAPI(mesh)
		# Find inherited primvars includes the primvars on prim
		inheritedPrimvars = prim.FindPrimvarsWithInheritance()
		for primvar in inheritedPrimvars:
			if not validatePrimvar(meshPath, primvar, facesCount, faceVertexIndicesCount, pointsCount):
				valid = False
	if valid:
		print("Pass mesh validation: " + file)
	else:
		_Err("Fail mesh validation: " + file)
	return valid

if __name__ == '__main__':
	raise Exception('Please do not run this file directly.')