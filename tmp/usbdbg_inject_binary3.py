#!/usr/bin/env python3
"""Force-stop then inject binary server at given baud."""

from __future__ import annotations

import argparse
import json
import os
import struct
import time
from pathlib import Path

import serial

USBDBG_CMD = 48
SCRIPT_EXEC = 0x05
SCRIPT_STOP = 0x06
FB_ENABLE = 0x0D
FW_VERSION = 0x80
SCRIPT_RUNNING = 0x87
TX_BUF_LEN = 0x8E
TX_BUF = 0x8F
CDC = "/dev/serial/by-id/usb-Kendryte_CanMV_001000000-if00"

BINARY_CODE = r'''
from machine import UART, FPIOA
import time
try:
    from ubinascii import crc32 as _crc32
except Exception:
    import binascii
    _crc32 = binascii.crc32
import ustruct as struct
BAUDRATE = __BAUD__
CHUNK = 2048
MAX_BUF = 4096
BIN_HDR = '<4sBBHIII'
BIN_SZ = struct.calcsize(BIN_HDR)
def crc32(data):
    return _crc32(data) & 0xffffffff
def pack_hdr(status, rid, plen, c):
    return struct.pack(BIN_HDR, b'KBIN', 1, status, BIN_SZ, rid & 0xffffffff, plen & 0xffffffff, c & 0xffffffff)
def make_payload(n):
    pat = bytes(range(256)); out = bytearray()
    while len(out) < n: out.extend(pat)
    return bytes(out[:n])
fpioa = FPIOA()
fpioa.set_function(50, FPIOA.UART3_TXD, oe=1)
fpioa.set_function(51, FPIOA.UART3_RXD, ie=1)
uart = UART(UART.UART3, baudrate=BAUDRATE, bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
print('BINARY_SERVER_READY baud=%d hdr=%d' % (BAUDRATE, BIN_SZ))
buf = b''
try:
    while True:
        try:
            import os
            if hasattr(os, 'exitpoint'): os.exitpoint()
        except Exception: pass
        chunk = uart.read()
        if chunk:
            buf += chunk
            if len(buf) > MAX_BUF: buf = buf[-MAX_BUF:]
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                parts = line.decode('ascii', 'ignore').strip().split()
                if not parts: continue
                if parts[0] == 'PING' and len(parts) >= 2:
                    uart.write(('PONG %s\n' % parts[1]).encode())
                elif parts[0] == 'BINARY' and len(parts) >= 3:
                    rid = int(parts[1], 10); nbytes = int(parts[2], 10)
                    payload = make_payload(nbytes); c = crc32(payload)
                    uart.write(pack_hdr(0, rid, len(payload), c))
                    i = 0
                    while i < len(payload):
                        uart.write(payload[i:i+CHUNK]); i += CHUNK
        else:
            time.sleep_ms(2)
finally:
    try: uart.deinit()
    except Exception: pass
    print('BINARY_SERVER_STOP')
'''


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baud", type=int, required=True)
    args = ap.parse_args()
    os.system("fuser -k /dev/ttyACM0 2>/dev/null")
    os.system("gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null")
    time.sleep(0.5)
    ser = serial.Serial(CDC, baudrate=921600, timeout=0.4, write_timeout=5, dsrdtr=False, rtscts=False)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    cmd(ser, FW_VERSION, 12)
    print("FW", ser.read(12).hex(), flush=True)
    cmd(ser, FB_ENABLE, 4, struct.pack("<I", 1))
    time.sleep(0.2)

    # stop up to 4 times until we see soft reboot banner without app_manager afterward
    buf = b""
    for attempt in range(4):
        print("STOP_ATTEMPT", attempt, "RUN", running(ser), flush=True)
        cmd(ser, SCRIPT_STOP, 0)
        t_end = time.perf_counter() + 8
        while time.perf_counter() < t_end:
            c = tx_read(ser)
            if c:
                buf += c
                print("TX", c[:140], flush=True)
            else:
                time.sleep(0.05)
        if b"CanMV v" in buf[buf.rfind(b"MPY: soft reboot") if b"MPY: soft reboot" in buf else 0 :]:
            # if main restarted after banner, stop again
            if b"app_manager" in buf[buf.rfind(b"CanMV v") :]:
                continue
            break

    code = BINARY_CODE.replace("__BAUD__", str(args.baud))
    cmd(ser, SCRIPT_EXEC, len(code), code.encode())
    time.sleep(1.0)
    ready_buf = b""
    for _ in range(50):
        c = tx_read(ser)
        if c:
            ready_buf += c
            print("TXe", c[:180], flush=True)
        if b"BINARY_SERVER_READY" in ready_buf:
            break
        time.sleep(0.08)
    ok = b"BINARY_SERVER_READY" in ready_buf and running(ser) == 1
    print("READY", ok, "RUN", running(ser), flush=True)
    Path.home().joinpath("k230_ttl_jpeg_probe/logs/inject_binary_%d.json" % args.baud).write_text(
        json.dumps({"ok": ok, "baud": args.baud, "tx": ready_buf[-400:].decode("latin1", "replace")}, indent=2)
    )
    ser.close()
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
