#!/usr/bin/env python3
"""Start a K230 experiment script via OpenMV/CanMV USBDBG SCRIPT_EXEC.

Uses K230 native CDC only for control. TTL traffic stays on CH343.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import time

import serial

USBDBG_CMD = 48
SCRIPT_EXEC = 0x05
SCRIPT_STOP = 0x06
FW_VERSION = 0x80
SCRIPT_RUNNING = 0x87
TX_BUF_LEN = 0x8E
TX_BUF = 0x8F

DEFAULT_CDC = "/dev/serial/by-id/usb-Kendryte_CanMV_001000000-if00"


def cmd(ser: serial.Serial, c: int, size: int, payload: bytes = b"") -> None:
    ser.write(struct.pack("<BBI", USBDBG_CMD, c, size))
    if payload:
        ser.write(payload)


def tx_read(ser: serial.Serial) -> bytes:
    cmd(ser, TX_BUF_LEN, 4)
    r = ser.read(4)
    if len(r) != 4:
        return b""
    n = struct.unpack("I", r)[0]
    if n <= 0:
        return b""
    n = min(n, 8192)
    cmd(ser, TX_BUF, n)
    return ser.read(n)


def running(ser: serial.Serial):
    cmd(ser, SCRIPT_RUNNING, 4)
    r = ser.read(4)
    return struct.unpack("I", r)[0] if len(r) == 4 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdc", default=DEFAULT_CDC)
    ap.add_argument("--script", required=True, help="absolute path on K230, e.g. /sdcard/experiments/.../uart_ping_server.py")
    ap.add_argument("--ready-token", default="")
    ap.add_argument("--wait", type=float, default=2.0)
    args = ap.parse_args()

    os.system("gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null")
    time.sleep(0.5)

    ser = serial.Serial(
        port=args.cdc,
        baudrate=921600,
        timeout=0.5,
        write_timeout=3,
        dsrdtr=False,
        rtscts=False,
    )
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass

    cmd(ser, FW_VERSION, 12)
    fw = ser.read(12)
    print("FW", fw.hex(), flush=True)
    print("RUN0", running(ser), flush=True)
    cmd(ser, SCRIPT_STOP, 0)
    time.sleep(0.5)
    print("RUN_stop", running(ser), flush=True)

    # Prefer execfile so edits on SD are picked up; fall back to importlib-style
    code = (
        "import sys\n"
        "sys.path.append('/sdcard/experiments/k230_ttl_jpeg')\n"
        f"p={args.script!r}\n"
        "print('EXEC', p)\n"
        "g={'__name__':'__main__','__file__':p}\n"
        "with open(p,'r') as f: src=f.read()\n"
        "exec(compile(src, p, 'exec'), g)\n"
    )
    cmd(ser, SCRIPT_EXEC, len(code), code.encode())
    time.sleep(args.wait)
    print("RUN1", running(ser), flush=True)

    buf = b""
    for _ in range(40):
        c = tx_read(ser)
        if c:
            buf += c
            print("TX", c[:200], flush=True)
        if args.ready_token and args.ready_token.encode() in buf:
            break
        time.sleep(0.05)
    print("READY", (args.ready_token.encode() in buf) if args.ready_token else None, flush=True)
    ser.close()
    # leave script running
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
