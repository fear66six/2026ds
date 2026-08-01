#!/usr/bin/env bash
# Install the touch visualization launcher shortcut onto the Jetson desktop.
set -euo pipefail

PROJECT_ROOT="/home/jetson/2026E"
DESKTOP_DIR="${HOME}/Desktop"
DESKTOP_FILE="${DESKTOP_DIR}/2026E-visualization.desktop"

chmod +x "${PROJECT_ROOT}/tools/jetson_launch_visualization.sh"
chmod +x "${PROJECT_ROOT}/tools/jetson_touch_launcher.py"
chmod +x "${PROJECT_ROOT}/tools/install_jetson_desktop_launcher.sh"

mkdir -p "${DESKTOP_DIR}"
cp "${PROJECT_ROOT}/tools/2026E-visualization.desktop" "${DESKTOP_FILE}"
chmod +x "${DESKTOP_FILE}"

if command -v gio >/dev/null 2>&1; then
  gio set "${DESKTOP_FILE}" metadata::trusted true >/dev/null 2>&1 || true
fi

echo "Installed desktop launcher: ${DESKTOP_FILE}"
