#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")
ROOT_DIR=$(dirname "$SCRIPT_DIR") 

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"



print_header "---===== build AppImage  =====----"

(


    cd ${ROOT_DIR}
    VERSION=$(sed -n 's/^version *= *"\(.*\)"/\1/p' ${ROOT_DIR}/pyproject.toml | head -n1)
    
    FULL=false
    for ARG in "$@"; do
        case "$ARG" in
            --full) FULL=true ;;
            *)
                print_info "Usage: $0 [--full]"
                exit 1
                ;;
        esac
    done

    rm -f ./dev/dist/*.AppImage
    
    PYTHON="./.venv/bin/python"
    mkdir -p  ./dev/dist
    mkdir -p  ./dev/build
    if [[ ! -x "$PYTHON" ]]; then
        print_error "error: $PYTHON miss. Please install appimage.ctl in the .venv."
        exit 1
    fi

    if [[ "$FULL" == true ]]; then
        # update lock and hashes  
        print_header "== update tools and locks =="
        
        python -m appimage.ctl update-tools
        python -m appimage.ctl enable-reproducible
    fi
    
    print_header "== Check AppImage-Configuration =="
    
    if [[ "$FULL" == true ]]; then
        "$PYTHON" -m appimage.ctl check
    fi


    
    if [[ "$FULL" == true ]]; then
        print_header "== AppImage full build =="
        "$PYTHON" -m appimage.ctl build --require-pylock --require-build-pylock
        rm -rf ${ROOT_DIR}/build
    else
       print_header "== AppImage build =="
        "$PYTHON" -m appimage.ctl build --reproducible  
    fi    
    mv ./dev/dist/*.AppImage ./dev/dist/de.maza.traybeat_$VERSION-x86_64.AppImage
    

   
    print_info "-----------------------------------------------------------"
    print_info "finish appimage created successfully."
    ls -hal ./dev/dist/*.AppImage
    print_info "-----------------------------------------------------------"
)