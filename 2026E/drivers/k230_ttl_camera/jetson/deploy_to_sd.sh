#!/usr/bin/env bash
# Deploy production files to K230 SD via MTP and verify.
set -euo pipefail
ROOT="${HOME}/k230_ttl_camera"
fuser -k /dev/ttyACM0 2>/dev/null || true
sleep 1
timeout 30 gio mount gphoto2://Kendryte_CanMV_001000000/ >/dev/null 2>&1 || true
SD="/run/user/1000/gvfs/gphoto2:host=Kendryte_CanMV_001000000/store_ffff0001"
for i in $(seq 1 20); do
  if [[ -d "$SD" ]]; then echo "MOUNTED"; break; fi
  sleep 1
  timeout 10 gio mount gphoto2://Kendryte_CanMV_001000000/ >/dev/null 2>&1 || true
done
if [[ ! -d "$SD" ]]; then
  echo "MTP mount failed" >&2
  exit 1
fi
mkdir -p "$SD/experiments/k230_ttl_jpeg"
cp -f "$ROOT/k230_payload/protocol.py" "$SD/experiments/k230_ttl_jpeg/protocol.py"
cp -f "$ROOT/k230_payload/k230_camera_server.py" "$SD/experiments/k230_ttl_jpeg/k230_camera_server.py"
cp -f "$ROOT/k230_payload/main_launcher.py" "$SD/main.py"
sync || true
python3 - <<PY
from pathlib import Path
sd = Path("$SD")
print("main.py:")
print((sd / "main.py").read_text()[:300])
print("sizes", (sd/"experiments/k230_ttl_jpeg/protocol.py").stat().st_size,
      (sd/"experiments/k230_ttl_jpeg/k230_camera_server.py").stat().st_size)
PY
gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null || true
echo "Deploy OK. Press K230 RESET now."
