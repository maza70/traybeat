#!/bin/bash
set -e


# Pfad, an den nfpm die .whl-Datei im Zielsystem kopiert hat
WHL_PATH="/usr/share/traybeat/${WHEEL_FILE}"
APP_DIR="/usr/share/traybeat"
VENV_DIR="$APP_DIR/venv"

echo "----===== traybeat install  =====----" 
echo "VENV_DIR: ${VENV_DIR}" 
echo "APP_DIR: ${APP_DIR}" 
echo "WHL_PATH: ${WHL_PATH}" 
echo "----===== create venv =====----" 

python3 -m venv --system-site-packages "$VENV_DIR" 
echo "----===== install whl =====----" 
"$VENV_DIR/bin/pip" install --prefer-binary --no-cache-dir "$WHL_PATH"


# 3. Den Konsolenbefehl systemweit verlinken, damit er im Terminal verfügbar ist
ln -sf "$VENV_DIR/bin/traybeat" /usr/local/bin/traybeat

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    echo "----===== update icon cache =====----" 
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor
fi

echo "TrayBeat Wheel erfolgreich installiert!"