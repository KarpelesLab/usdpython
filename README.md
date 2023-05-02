# USD Python Tools

This archive contains
- `usdzconvert`, a Python-based tool to convert from various file formats to usdz
- precompiled macOS Python modules for Pixar's USD library
- a set of sample scripts that demonstrate how to write usd files
- the `fixOpacity` tool

## usdzconvert (version 0.56)

usdzconvert is a Python script that converts obj and gltf models to usdz (with further formats coming soon).
It also performs asset validation on the generated usdz (using Pixar's usdchecker and further checks).
For more information, run 

    usdzconvert -h

## Precompiled macOS Python Modules for Pixar's USD Library (Version 19.05)

This library was compiled using version 19.05 of [the public USD GitHub repository](http://openusd.org) with the following build script arguments (see USDPython/README.md for further details):

    python USD/build_scripts/build_usd.py --build-args TBB,extra_inc=big_iron.inc --python --no-imaging --docs --no-usdview --build-monolithic USDPython

To start using USD in Python, set your PATH and PYTHONPATH variables as follows (replace `<PATH_TO_USDPYTHON>` with the path to this USDPython folder):

    export PATH=$PATH:<PATH_TO_USDPYTHON>/USD
    export PYTHONPATH=$PYTHONPATH:<PATH_TO_USDPYTHON>/USD

You should then be able to start using the USD library in Python:

    > python     
    Python 2.7.10 (default, Feb 22 2019, 21:55:15) 
    Type "help", "copyright", "credits" or "license" for more information.
    >>> import pxr
    >>> 

## Samples

The `samples` folder contains a set of simple scripts that focus on different aspects of writing USD data, such as geometry, materials, skinning and animation. 
Each script generates a .usd and a .usdz file in the `assets` sub folder, and also prints the generated .usd file's content.

| Script | Purpose |
| ------ | --- |
| `101_scenegraph.py` | creates a scene graph |
| `102_mesh.py` | creates a cube mesh |
| `103_simpleMaterial.py` | creates a simple PBR material |
| `104_texturedMaterial.py` | creates a cube mesh and assigns it a PBR material with a diffuse texture |
| `105_pbrMaterial.py` | creates a cube mesh and assigns it a more complex PBR material with textures for normal, roughness and diffuse channels |
| `106_meshGroups.py` | creates a cube mesh with two mesh groups and assigns each a separate material |
| `107_transformAnimation.py` |  builds a scene graph of several objects and sets (animated) translate, rotate, and scale transforms |
| `109_skinnedAnimation.py` | creates an animated skinned cube |
| `201_subdivision.py` | creates a subdivided cube with creases |
| `202_references.py` | creates an asset file then a reference file that reference and overwrite the asset file|

## fixOpacity

If you converted your usdz asset with Xcode's usdz_converter, and it has translucent materials that render opaque in iOS 13, use this script to correct the asset's translucent materials:

    fixOpacity model.usdz

