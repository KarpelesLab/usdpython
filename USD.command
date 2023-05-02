#!/bin/sh
BASEPATH=$(dirname "$0")
export PATH=$PATH:$BASEPATH/USD:$PATH:$BASEPATH/usdzconvert;
export PYTHONPATH=$PYTHONPATH:$BASEPATH/USD/lib/python

# uncomment to set the PYTHONPATH to FBX Bindings here:
# export PYTHONPATH=$PYTHONPATH:"/Applications/Autodesk/FBX Python SDK/2020.2.1/lib/Python37_x64"

if [[ $PYTHONPATH == *"FBX"* ]]; then
    :
else 
    echo "For FBX support, edit PYTHONPATH in this file (USD.command) or your shell configuration file"
fi

$SHELL
