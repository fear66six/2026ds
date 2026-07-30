#!/usr/bin/env bash
# Install optional systemd unit for Jetson K230 TTL camera health monitor.
# Does NOT enable by default — prints next steps.
set -euo pipefail
UNIT_NAME=k230-ttl-camera.service
DEST_DIR="${HOME}/k230_ttl_camera"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BY_ID="/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A028646-if00"

mkdir -p "$DEST_DIR/logs" "$DEST_DIR/captures"
cp -a "$SCRIPT_DIR"/*.py "$DEST_DIR/" 2>/dev/null || true

if [[ ! -e "$BY_ID" ]]; then
  echo "WARN: TTL by-id not present now: $BY_ID"
fi
if ! id -nG | tr ' ' '\n' | grep -qx dialout; then
  echo "WARN: user not in dialout group"
fi

UNIT_PATH="/tmp/${UNIT_NAME}"
cat >"$UNIT_PATH" <<EOF
[Unit]
Description=K230 TTL camera health monitor (460800 / 1280x720)
After=network.target
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
User=${USER}
WorkingDirectory=${DEST_DIR}
ExecStart=/usr/bin/python3 ${DEST_DIR}/camera_smoke_test.py --count 1
Restart=on-failure
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Wrote unit draft to $UNIT_PATH"
echo "To install (requires sudo, NOT auto-enabled):"
echo "  sudo cp $UNIT_PATH /etc/systemd/system/${UNIT_NAME}"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now ${UNIT_NAME}   # only when you intend"
echo "Status: sudo systemctl status ${UNIT_NAME}"
echo "Logs:   journalctl -u ${UNIT_NAME} -f"
