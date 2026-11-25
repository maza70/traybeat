#!/usr/bin/env bash
set -e
SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 


source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
print_header "---===== Build Relaese  =====---- "

(
    FULL=false #clean all and make a complete rebuild from scratch
    CALL_PARAMS=""
    for ARG in "$@"; do
        case "$ARG" in
                --full) 
                FULL=true 
                CALL_PARAMS="--full"
                ;;
                *)
                    echo "Usage: $0 [--full]"
                    exit 1
                    ;;
        esac
    done

    cd ${ROOT_DIR}
    if [[ "$FULL" == true ]]; then
        ./dev/clean.sh
        ./dev/make-venv.sh
    fi    
    
    source .venv/bin/activate
    ./dev/pycheck.sh $CALL_PARAMS
    rm -f ./dev/dist/*
    ./dev/build-appimage.sh $CALL_PARAMS
    ./dev/build-sys-package.sh $CALL_PARAMS
    ./dev/build-flatpak.sh $CALL_PARAMS
)


