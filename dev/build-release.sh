#!/usr/bin/env bash
set -e
echo "---===== Build Relaese  =====---- "
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
(
    cd ${ROOT_DIR}
   

    source .venv/bin/activate
    ./dev/pycheck.sh
    # update lock and hashes  
    python -m appimage.ctl update-tools
    python -m appimage.ctl enable-reproducible

    ./dev/build-appimage.sh
    ./dev/build-sys-package.sh
)

