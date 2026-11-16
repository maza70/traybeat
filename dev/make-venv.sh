#!/bin/bash
set -e
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
(
      cd ${ROOT_DIR}
      python3 -m venv --system-site-packages .venv
      .venv/bin/python -m pip install --upgrade pip
      .venv/bin/python -m pip install -e ".[dev]"
      .venv/bin/python -m pip install -e ".[appimage]"
      .venv/bin/python -m pip install -e  .
      
      

)

