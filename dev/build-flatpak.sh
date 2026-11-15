#!/usr/bin/env bash
set -euo pipefail
echo "---===== build Flatpak  =====---- "
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 

SKIP_PIP_GENERATOR=false
INSTALL_RUN=false
for ARG in "$@"; do
    case "$ARG" in
        -sp) SKIP_PIP_GENERATOR=true ;;
        -ir) INSTALL_RUN=true ;;
        *)
            echo "Usage: $0 [-sp] [-ir]"
            exit 1
            ;;
    esac
done

(
    #flatpak install --user flathub \
    #org.gnome.Platform//51 \
    #org.gnome.Sdk//51

    cd ${ROOT_DIR}
    export VERSION=$(sed -n 's/^version *= *"\(.*\)"/\1/p' ${ROOT_DIR}/pyproject.toml | head -n1)
    echo "SKIP_PIP_GENERATOR= $SKIP_PIP_GENERATOR"
    echo "INSTALL_RUN       = $INSTALL_RUN"
    if [[ "$SKIP_PIP_GENERATOR" == false ]]; then

        PIP_GENERATOR="./dev/flatpak/flatpak-pip-generator.py"
        if [[ ! -f "$PIP_GENERATOR" ]]; then
            curl -L  https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator.py  -o $PIP_GENERATOR
        fi
        rm -rf ./dev/flatpak/.flatpak-builder/build
        rm -rf ./dev/build
        echo "---===== create python-dependencies.json =====---- "
        python3 ./dev/flatpak/flatpak-pip-generator.py \
            --runtime=org.gnome.Sdk//51 \
            --pyproject-file=pyproject.toml \
            --prefer-wheels=pillow,setproctitle \
            --output=./dev/flatpak/python-dependencies.json
    else
        echo "---===== skip dependency generation =====----"
    fi


    echo "---===== run flatpak-builder  =====---- "
    flatpak-builder \
        --force-clean \
        --user \
        --state-dir=./dev/flatpak/.flatpak-builder \
        --install-deps-from=flathub \
        --repo=./dev/build/repo \
        ./dev/build \
        ./dev/flatpak/de.maza.traybeat.yml
    echo "---===== run build-bundle  =====---- "
    flatpak build-bundle \
        ./dev/build/repo \
        dev/dist/de.maza.traybeat_$VERSION.flatpak \
        de.maza.traybeat
    echo "---===== builded flatpak  =====---- "
    ls -al ./dev/dist/*.flatpak

    if [[ "$INSTALL_RUN" == true ]]; then
        flatpak install --user  --reinstall -y  ./dev/dist/traybeat.flatpak && flatpak run de.maza.traybeat -p     
    fi    
)