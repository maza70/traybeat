#!/usr/bin/env bash
set -euo pipefail
SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
INSTALL_RUN=false
FULL=false

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
print_header "---===== build Flatpak  =====---- "

(
    for ARG in "$@"; do
        case "$ARG" in
            --full) FULL=true ;;

            -ir) INSTALL_RUN=true ;;
            *)
                print_info "Usage: $0 [--full] [-ir]"
                exit 1
                ;;
        esac
    done


    cd ${ROOT_DIR}
    mkdir -p ./dev/dist
    export VERSION=$(sed -n 's/^version *= *"\(.*\)"/\1/p' ${ROOT_DIR}/pyproject.toml | head -n1)
    echo "FULL= $FULL"
    echo "INSTALL_RUN       = $INSTALL_RUN"
    if [[ "$FULL" == true ]]; then
        echo "---===== run flatpak-pip-generator =====---- "
        PIP_GENERATOR="./dev/flatpak/flatpak-pip-generator.py"
        if [[ ! -f "$PIP_GENERATOR" ]]; then
            curl -L  https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator.py  -o $PIP_GENERATOR
        fi
        rm -rf ./dev/flatpak/.flatpak-builder/build
        rm -rf ./dev/build
        print_header "---===== create python-dependencies.json =====---- "
        python3 ./dev/flatpak/flatpak-pip-generator.py \
            --runtime=org.gnome.Sdk//51 \
            --pyproject-file=pyproject.toml \
            --prefer-wheels=pillow,setproctitle \
            --output=./dev/flatpak/python-dependencies.json
    else
        print_info "---===== skip dependency generation =====----"
    fi


    print_header "---===== run flatpak-builder  =====---- "
    flatpak run org.flatpak.Builder \
        --force-clean \
        --state-dir=./dev/flatpak/.flatpak-builder \
        --install-deps-from=flathub \
        --repo=./dev/build/repo \
        ./dev/build \
        ./dev/flatpak/de.maza.traybeat.yml
    print_header "---===== run build-bundle  =====---- "
    flatpak build-bundle \
        ./dev/build/repo \
        dev/dist/de.maza.traybeat_$VERSION.flatpak \
        de.maza.traybeat
    

    if [[ "$INSTALL_RUN" == true ]]; then
        flatpak install --reinstall -y  ./dev/dist/de.maza.traybeat_$VERSION.flatpak && flatpak run de.maza.traybeat -p     
    fi    
    print_info "-----------------------------------------------------------"
    print_info "finish flatpak created successfully."
    ls -al ./dev/dist/*.flatpak
    print_info "-----------------------------------------------------------"
)