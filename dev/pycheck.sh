#!/usr/bin/env bash
SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

print_header "---===== Check code for errors  =====----"

(
    cd ${ROOT_DIR}
    ruff check ./src --select I --fix
    pyright ./src

)

