#!/usr/bin/env bash
# Restore original Hiwonder /sdcard/main.py. Does not touch boot.py.
set -euo pipefail
BAK="${HOME}/k230_ttl_camera/k230_backups/main.py.bak"
EXPECTED_SHA="0ab6673a5d5eea37e86abe40d68d1352335b7e96e71879aeab276b11c88017ca"
if [[ ! -f "$BAK" ]]; then
  echo "missing backup $BAK" >&2
  exit 1
fi
sha=$(sha256sum "$BAK" | awk '{print $1}')
if [[ "$sha" != "$EXPECTED_SHA" ]]; then
  echo "backup SHA mismatch: $sha != $EXPECTED_SHA" >&2
  exit 2
fi
timeout 25 gio mount gphoto2://Kendryte_CanMV_001000000/ >/dev/null 2>&1 || true
SD="/run/user/1000/gvfs/gphoto2:host=Kendryte_CanMV_001000000/store_ffff0001"
cp -f "$BAK" "$SD/main.py"
sync || true
echo "restored main.py -> $(sha256sum "$SD/main.py")"
gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null || true
echo "Press K230 RESET (or power-cycle) to apply."
