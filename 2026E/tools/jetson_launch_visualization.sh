#!/usr/bin/env bash
# One-click entry for the Jetson touch visualization launcher.
set -euo pipefail

PROJECT_ROOT="/home/jetson/2026E"
LAUNCHER="${PROJECT_ROOT}/tools/jetson_touch_launcher.py"

if [[ -f "/home/jetson/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "/home/jetson/miniconda3/etc/profile.d/conda.sh"
  conda activate env >/dev/null 2>&1 || true
fi

cd "${PROJECT_ROOT}"
exec python3 "${LAUNCHER}"
