#!/usr/bin/env bash
SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
print_header "---===== Cleanup projekt  =====---- "

(
    cd ${ROOT_DIR}
    
    rm -rf ${ROOT_DIR}/build \
           ${ROOT_DIR}/dev/build/ \
           ${ROOT_DIR}/dev/dist/  \
           ${ROOT_DIR}/dev/.venv/ \
           ${ROOT_DIR}/dev/flatpak/.flatpak-builder/ \
           ${ROOT_DIR}/.venv/ 
           


    find "${ROOT_DIR}" -type d \( -name '__pycache__' -o -name '*.egg-info' \) -prune \
     -exec sh -c 'for dir do printf "Deleting: %s\n" "$dir"; rm -rf -- "$dir"; done' sh {} +

)


