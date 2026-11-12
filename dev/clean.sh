#!/usr/bin/env bash
echo "---===== Cleanup projekt  =====---- "
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
(
    cd ${ROOT_DIR}
    rm -rf ${ROOT_DIR}/build
    rm -rf ${ROOT_DIR}/dev/build/ ${ROOT_DIR}/dev/dist/  ${ROOT_DIR}/.venv

    find "${ROOT_DIR}" -type d \( -name '__pycache__' -o -name '*.egg-info' \) -prune \
     -exec sh -c 'for dir do printf "Deleting: %s\n" "$dir"; rm -rf -- "$dir"; done' sh {} +

    

    
    echo "---=====  Make venv  =====----"
    #python3 -m venv --system-site-packages .venv
    python3 -m venv  .venv
    echo "----===== Install pip =====----"
    .venv/bin/python -m pip install --upgrade pip
    echo "----=====  Install projekt dependencies =====----"
    .venv/bin/python -m pip install -e ".[dev]"
)

