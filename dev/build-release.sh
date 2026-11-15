#!/usr/bin/env bash
set -e
echo "---===== Build Relaese  =====---- "
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
(
    cd ${ROOT_DIR}
    ./dev/clean.sh
    ./dev/make-venv.sh
    source .venv/bin/activate
    ./dev/pycheck.sh
    ./dev/build-appimage.sh --lock
    ./dev/build-sys-package.sh
    ./dev/build-flatpak.sh
)


