#!/usr/bin/env bash
set -euo pipefail
echo "---===== build AppImage  =====---- "
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
(


    cd ${ROOT_DIR}
    VERSION=$(sed -n 's/^version *= *"\(.*\)"/\1/p' ${ROOT_DIR}/pyproject.toml | head -n1)
    
    FULL=false
    for ARG in "$@"; do
        case "$ARG" in
            --full) FULL=true ;;
            *)
                echo "Usage: $0 [--full]"
                exit 1
                ;;
        esac
    done

    rm -f ./dev/dist/*.AppImage
    
    PYTHON="./.venv/bin/python"
    mkdir -p  ./dev/dist
    mkdir -p  ./dev/build
    if [[ ! -x "$PYTHON" ]]; then
        echo "error: $PYTHON miss. Please install appimage.ctl in the .venv." >&2
        exit 1
    fi

    if [[ "$FULL" == true ]]; then
        # update lock and hashes  
        echo "== update tools and locks =="
        python -m appimage.ctl update-tools
        python -m appimage.ctl enable-reproducible
    fi
    
    echo "== Check AppImage-Configuration =="
    if [[ "$FULL" == true ]]; then
        "$PYTHON" -m appimage.ctl check
    fi


    
    if [[ "$FULL" == true ]]; then
        echo "== AppImage full build =="
        "$PYTHON" -m appimage.ctl build --require-pylock --require-build-pylock
        rm -rf ${ROOT_DIR}/build
    else
        echo "== AppImage build =="
        "$PYTHON" -m appimage.ctl build --reproducible  
    fi    
    mv ./dev/dist/*.AppImage ./dev/dist/de.maza.traybeat_$VERSION-x86_64.AppImage
    

    ls -hal ./dev/dist/*.AppImage
    echo "-----------------------------------------------------------"
    echo "finish appimage created successfully."
    echo "-----------------------------------------------------------"
)