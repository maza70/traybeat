#!/usr/bin/env bash
echo "---===== Check code for errors  =====----"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
(
    cd ${ROOT_DIR}
    ruff check . --select I --fix
    pyright .

)

