#!/usr/bin/env python3
"""Inject k230_camera_server.py via USBDBG (dev only). Prefer SD auto-start for contest."""

from __future__ import annotations

import os
import struct
import time

import serial

USBDBG_CMD = 48
SCRIPT_EXEC = 0x05
SCRIPT_STOP = 0x06
FB_ENABLE = 0x0D
SCRIPT_RUNNING = 0x87
TX_BUF_LEN = 0x8E
TX_BUF = 0x8F
CDC = "/dev/serial/by-id/usb-Kendryte_CanMV_001000000-if00"
SCRIPT = "/sdcard/experiments/k230_ttl_jpeg/k230_camera_server.py"


def cmd(ser, c, size, payload=b""):
    ser.write(struct.pack("<BBI", USBDBG_CMD, c, size))
    if payload:
        ser.write(payload)


def tx_read(ser):
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


def running(ser):
    cmd(ser, SCRIPT_RUNNING, 4)
    r = ser.read(4)
    return struct.unpack("I", r)[0] if len(r) == 4 else None


def main() -> int:
    os.system("fuser -k /dev/ttyACM0 2>/dev/null")
    os.system("gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null")
    time.sleep(0.5)
    ser = serial.Serial(CDC, baudrate=921600, timeout=0.4, write_timeout=8, dsrdtr=False, rtscts=False)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    cmd(ser, FB_ENABLE, 4, struct.pack("<I", 1))
    time.sleep(0.2)
    buf = b""
    for _ in range(5):
        cmd(ser, SCRIPT_STOP, 0)
        t_end = time.perf_counter() + 8
        while time.perf_counter() < t_end:
            c = tx_read(ser)
            if c:
                buf += c
                print("TX", c[:120], flush=True)
            else:
                time.sleep(0.05)
        if b"CanMV v" in buf and b"app_manager" not in buf[buf.rfind(b"CanMV v") :]:
            break
    code = (
        "import sys\n"
        "sys.path.append('/sdcard/experiments/k230_ttl_jpeg')\n"
        f"p={SCRIPT!r}\n"
        "print('EXEC_FILE', p)\n"
        "g={'__name__':'__main__','__file__':p}\n"
        "exec(compile(open(p).read(), p, 'exec'), g)\n"
    )
    cmd(ser, SCRIPT_EXEC, len(code), code.encode())
    time.sleep(2.5)
    ready = b""
    for _ in range(80):
        c = tx_read(ser)
        if c:
            ready += c
            print("TXe", c[:160], flush=True)
        if b"SERVER_READY" in ready or b"READY session=" in ready:
            # READY also goes to TTL; USBDBG may only show SERVER_READY debug
            pass
        if b"SERVER_READY" in ready:
            break
        if b"Traceback" in ready:
            break
        time.sleep(0.1)
    print("RUN", running(ser), flush=True)
    print("HAS_DEBUG_READY", b"SERVER_READY" in ready, flush=True)
    ok = running(ser) == 1
    ser.close()
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
