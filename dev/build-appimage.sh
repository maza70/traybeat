#!/usr/bin/env bash
set -euo pipefail
echo "---===== build AppImage  =====---- "
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 

(
    cd ${ROOT_DIR}
   
    PYTHON="./.venv/bin/python"
    mkdir -p  ./dev/dist
    mkdir -p  ./dev/build
    if [[ ! -x "$PYTHON" ]]; then
        echo "error: $PYTHON miss. Please install appimage.ctl in the .venv." >&2
        exit 1
    fi

    echo "== Check AppImage-Configuration =="
    "$PYTHON" -m appimage.ctl check

    echo "== AppImage bauen =="
    "$PYTHON" -m appimage.ctl build --require-pylock --require-build-pylock

    rm -rf ${ROOT_DIR}/build
    
    ls -hal ./dev/dist/*.AppImage
    echo
    echo "finish appimage created successfully."
)