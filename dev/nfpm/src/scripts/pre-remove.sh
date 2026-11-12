#!/bin/bash
set -e

echo "Remove system link /usr/local/bin/traybeat"
rm -f /usr/local/bin/traybeat

echo "Remove installed data in /usr/share/traybeat"
rm -rf /usr/share/traybeat

echo "Traybeat was successfully uninstalled."