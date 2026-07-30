#!/usr/bin/env bash
set -euo pipefail
UNIT_NAME=k230-ttl-camera.service
sudo systemctl disable --now "$UNIT_NAME" 2>/dev/null || true
sudo rm -f "/etc/systemd/system/${UNIT_NAME}"
sudo systemctl daemon-reload
echo "uninstalled $UNIT_NAME"
