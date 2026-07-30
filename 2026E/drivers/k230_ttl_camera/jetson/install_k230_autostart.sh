#!/usr/bin/env bash
# Replace /sdcard/main.py with minimal launcher that runs k230_camera_server.
# Requires existing backup. Does not modify boot.py. Does not flash firmware.
set -euo pipefail
ROOT="${HOME}/k230_ttl_camera"
BAK="${ROOT}/k230_backups/main.py.bak"
EXPECTED_SHA="0ab6673a5d5eea37e86abe40d68d1352335b7e96e71879aeab276b11c88017ca"
LAUNCHER="${ROOT}/k230_payload/main_launcher.py"
if [[ ! -f "$BAK" ]]; then
  echo "missing backup; abort" >&2
  exit 1
fi
sha=$(sha256sum "$BAK" | awk '{print $1}')
if [[ "$sha" != "$EXPECTED_SHA" ]]; then
  echo "backup SHA mismatch" >&2
  exit 2
fi
if [[ ! -f "$LAUNCHER" ]]; then
  echo "missing launcher $LAUNCHER" >&2
  exit 3
fi
timeout 25 gio mount gphoto2://Kendryte_CanMV_001000000/ >/dev/null 2>&1 || true
SD="/run/user/1000/gvfs/gphoto2:host=Kendryte_CanMV_001000000/store_ffff0001"
# ensure server files present
cp -f "${ROOT}/k230_payload/protocol.py" "$SD/experiments/k230_ttl_jpeg/protocol.py"
cp -f "${ROOT}/k230_payload/k230_camera_server.py" "$SD/experiments/k230_ttl_jpeg/k230_camera_server.py"
cp -f "$LAUNCHER" "$SD/main.py"
sync || true
echo "installed launcher main.py sha=$(sha256sum "$SD/main.py" | awk '{print $1}')"
gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null || true
echo "Press K230 RESET to start camera server."
