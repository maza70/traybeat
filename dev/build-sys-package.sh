#!/bin/bash
set -e
SCRIPT_NAME=$(basename "${BASH_SOURCE[0]}")
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

(
      FULL=false
      for ARG in "$@"; do
            case "$ARG" in
                  --full) FULL=true ;;
                  *)
                        echo "Usage: $0 [--full]"
                        exit 1
                        ;;
            esac
      done
      export VERSION=$(sed -n 's/^version *= *"\(.*\)"/\1/p' ${ROOT_DIR}/pyproject.toml | head -n1)
      export YEAR=$(date +%Y)      
      export FULLDATE=$(LC_ALL=C date -R)
      export SUBST='$FULLDATE,$VERSION,$FULLDATE,$WHEEL_FILE' 
     
      source ${ROOT_DIR}/.venv/bin/activate

      cd ${ROOT_DIR}/dev

      SOURCE_DIR="./nfpm/src"

      print_header "----===== Build =====----"
      print_info "Version: ${VERSION}"
      print_info "current directory: ${PWD}"
      print_info "project directory: ${ROOT_DIR}"
      
     
      print_header "----===== Clean =====----"
      rm -f ./dist/*.rpm
      rm -f ./dist/*.deb

      rsync -av $SOURCE_DIR/usr ./build/
      mkdir -p ./build/usr/local/bin
      cp -v  ./dist/*.AppImage   ./build/usr/local/bin/traybeat
     
      print_header "----===== Build deb package =====----"
    
      mkdir -p ./build/usr/share/doc/traybeat
      
      envsubst $SUBST < $SOURCE_DIR/files/changelog.in  | gzip -n -9  > "./build/usr/share/doc/traybeat/changelog.gz"
      envsubst $SUBST < $SOURCE_DIR/files/copyright.in > "./build/usr/share/doc/traybeat/copyright"
      envsubst $SUBST < $SOURCE_DIR/files/nfpm.yaml > "./build/nfpm.yaml"

      find ./build -type d -exec chmod 755 {} +
      find ./build -type f -exec chmod 644 {} +
      chmod +x ./build/usr/local/bin/traybeat
      chmod 644  ./build/usr/share/applications/de.maza.traybeat.desktop

      mkdir -p ./bin
      if [ ! -f "./bin/nfpm" ]; then
            print_header "----===== Install nfpm =====----"
            curl -sfL https://github.com/goreleaser/nfpm/releases/download/v2.48.0/nfpm_2.48.0_Linux_x86_64.tar.gz  | tar -xz -C ./bin nfpm
      fi
      


      ./bin/nfpm package --packager rpm --config ./build/nfpm.yaml --target ./dist/
      ./bin/nfpm package --packager deb --config ./build/nfpm.yaml --target ./dist/

      
      print_info "-----------------------------------------------------------"
      print_info "Successfully build pakages"
      ls -hal ./dist/*.deb   
      ls -hal ./dist/*.rpm
      print_info "-----------------------------------------------------------"

      
      

)

