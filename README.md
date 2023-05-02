# USD Python Tools

This archive contains
- `usdzconvert`, a Python-based tool to convert from various file formats to usdz
- `usdARKitChecker`, a Python-based tool for usdz validation
- precompiled macOS Python modules for Pixar's USD library
- a set of sample scripts that demonstrate how to write usd files
- the `fixOpacity` tool
- usdzcreateassetlib, a standalone tool to generate an asset library from multiple assets

The easiest way to start using these command-line tools is to double-click `USD.command` in the Finder. This will open a Terminal window with all necessary environment variables set.

For more details, including demos, see the WWDC 2019 session "Working with USD": 
https://developer.apple.com/videos/play/wwdc2019/602/

## usdzconvert (version 0.62)

`usdzconvert` is a Python script that converts obj, gltf, fbx, abc, and usda/usdc/usd assets to usdz.
It also performs asset validation on the generated usdz.
For more information, run 

    usdzconvert -h

### iOS 12 Compatibility

To export .usdz files that play back correctly on iOS 12, use `usdzconvert`'s  `-iOS12` compatibility switch. When run with `-iOS12`, `usdzconvert` will use the Python Imaging Library (PIL) module to do texture conversion. 
If your Python environment is missing PIL, you can install it by running:

    pip install pillow

### FBX Support

Note that FBX support in `usdzconvert` requires both Autodesk's FBX SDK and FBX Python bindings to be installed on your system.
To make FBX bindings available to Python, uncomment the line 

    # export PYTHONPATH=$PYTHONPATH:/Applications/Autodesk/FBX\ Python\ SDK/2019.0/lib/Python27_x86

in `USD.command`, and adjust the path to point to the location of fbx.so (for Python 2.7).

## usdARKitChecker

`usdARKitChecker` is a Python script that validates existing usdz files. It is automatically run by `usdzconvert`, but can also be used as a stand-alone tool to validate files from other sources.
For more information, run 

    usdARKitChecker -h

Currently `usdARKitChecker` consists of three parts:
- validation through Pixar's `usdchecker`
- mesh attribute validation
- UsdPreviewSurface material validation

## Precompiled macOS Python Modules for Pixar's USD Library (Version 19.05)

This library was compiled using version 19.05 of [the public USD GitHub repository](http://openusd.org) with the following build script arguments (see USDPython/README.md for further details):

    python USD/build_scripts/build_usd.py --build-args TBB,extra_inc=big_iron.inc --python --no-imaging --docs --no-usdview --build-monolithic USDPython

If you prefer to set your environment variables directly , 

To start using USD in Python, set your PATH and PYTHONPATH variables as follows (replace `<PATH_TO_USDPYTHON>` with the path to this USDPython folder):

    export PATH=$PATH:<PATH_TO_USDPYTHON>/USD
    export PYTHONPATH=$PYTHONPATH:<PATH_TO_USDPYTHON>/USD/lib/python

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

## usdzcreateassetlib

usdzcreateassetlib is a script that generates a single-file asset library from multiple usdz assets. The result is a nested usdz file that contains the source usdz assets and references them in a variant set.
This script does not depend on the USD library, which should make it easy to deploy on servers.

