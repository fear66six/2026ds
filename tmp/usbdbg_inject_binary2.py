#!/usr/bin/env python3
"""Reliable USBDBG inject: wait for REPL after stop, then exec long-running server."""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
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
UART_TX_PIN = 50
UART_RX_PIN = 51
CHUNK = 2048
MAX_BUF = 4096
BIN_HDR = '<4sBBHIII'
BIN_SZ = struct.calcsize(BIN_HDR)

def crc32(data):
    return _crc32(data) & 0xffffffff

def pack_hdr(status, rid, plen, c):
    return struct.pack(BIN_HDR, b'KBIN', 1, status, BIN_SZ, rid & 0xffffffff, plen & 0xffffffff, c & 0xffffffff)

def make_payload(n):
    pat = bytes(range(256))
    out = bytearray()
    while len(out) < n:
        out.extend(pat)
    return bytes(out[:n])

fpioa = FPIOA()
fpioa.set_function(UART_TX_PIN, FPIOA.UART3_TXD, oe=1)
fpioa.set_function(UART_RX_PIN, FPIOA.UART3_RXD, ie=1)
uart = UART(UART.UART3, baudrate=BAUDRATE, bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
print('BINARY_SERVER_READY baud=%d hdr=%d' % (BAUDRATE, BIN_SZ))
buf = b''
try:
    while True:
        try:
            import os
            if hasattr(os, 'exitpoint'):
                os.exitpoint()
        except Exception:
            pass
        chunk = uart.read()
        if chunk:
            buf += chunk
            if len(buf) > MAX_BUF:
                buf = buf[-MAX_BUF:]
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                parts = line.decode('ascii', 'ignore').strip().split()
                if not parts:
                    continue
                if parts[0] == 'PING' and len(parts) >= 2:
                    uart.write(('PONG %s\n' % parts[1]).encode())
                elif parts[0] == 'BINARY' and len(parts) >= 3:
                    rid = int(parts[1], 10)
                    nbytes = int(parts[2], 10)
                    payload = make_payload(nbytes)
                    c = crc32(payload)
                    uart.write(pack_hdr(0, rid, len(payload), c))
                    i = 0
                    while i < len(payload):
                        uart.write(payload[i:i+CHUNK])
                        i += CHUNK
        else:
            time.sleep_ms(2)
finally:
    try:
        uart.deinit()
    except Exception:
        pass
    print('BINARY_SERVER_STOP')
'''


def drain_tx(ser, seconds=3.0):
    buf = b""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        c = tx_read(ser)
        if c:
            buf += c
            print("TX", c[:160], flush=True)
        else:
            time.sleep(0.05)
    return buf


def wait_repl(ser, timeout=25.0) -> bool:
    """Stop current script and wait until soft reboot reaches REPL (not main suite)."""
    cmd(ser, FB_ENABLE, 4, struct.pack("<I", 1))
    time.sleep(0.2)
    cmd(ser, SCRIPT_STOP, 0)
    buf = b""
    end = time.perf_counter() + timeout
    saw_canmv = False
    while time.perf_counter() < end:
        c = tx_read(ser)
        if c:
            buf += c
            print("TXw", c[:160], flush=True)
            if b"CanMV v" in c or b"CanMV v" in buf:
                saw_canmv = True
            # main suite noise
            if b"app_manager" in c:
                # main restarted; stop again
                cmd(ser, SCRIPT_STOP, 0)
        else:
            time.sleep(0.05)
        # prefer idle REPL: saw banner and running==0 or 1 after short hello capability
        if saw_canmv and b"Cleanup done" in buf:
            # continue until another CanMV banner after cleanup
            pass
        if saw_canmv and running(ser) in (0, 1) and b"app_manager" not in buf[-800:]:
            # if last banner after soft reboot without app_manager recently
            if buf.rfind(b"CanMV v") > buf.rfind(b"app_manager"):
                time.sleep(0.5)
                return True
    return saw_canmv


def inject(code: str, ready: str) -> dict:
    os.system("fuser -k /dev/ttyACM0 2>/dev/null")
    os.system("gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null")
    time.sleep(0.6)
    ser = serial.Serial(CDC, baudrate=921600, timeout=0.4, write_timeout=5, dsrdtr=False, rtscts=False)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    cmd(ser, FW_VERSION, 12)
    print("FW", ser.read(12).hex(), flush=True)
    print("RUN0", running(ser), flush=True)

    ok_repl = wait_repl(ser, timeout=30.0)
    print("REPL_WAIT", ok_repl, "RUN", running(ser), flush=True)

    # force another stop to kill main if it came back
    for _ in range(3):
        cmd(ser, SCRIPT_STOP, 0)
        time.sleep(0.8)
        drain_tx(ser, 1.5)
        # if main still starting, loop
        probe = b""
        for __ in range(10):
            c = tx_read(ser)
            if c:
                probe += c
                print("TXp", c[:120], flush=True)
            time.sleep(0.05)
        if b"app_manager" not in probe and b"Starting cleanup" not in probe:
            break

    cmd(ser, SCRIPT_EXEC, len(code), code.encode())
    time.sleep(1.0)
    buf = b""
    for _ in range(60):
        c = tx_read(ser)
        if c:
            buf += c
            print("TX", c[:200], flush=True)
        if ready.encode() in buf:
            break
        time.sleep(0.08)
    ready_ok = ready.encode() in buf
    runv = running(ser)
    print("READY", ready_ok, "RUN", runv, flush=True)
    ser.close()
    return {"ready": ready_ok, "running": runv, "tx_tail": buf[-600:].decode("latin1", "replace")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()
    code = BINARY_CODE.replace("__BAUD__", str(args.baud))
    res = inject(code, "BINARY_SERVER_READY")
    res["baud"] = args.baud
    Path.home().joinpath("k230_ttl_jpeg_probe/logs/inject_binary_%d.json" % args.baud).write_text(
        json.dumps(res, indent=2)
    )
    return 0 if res["ready"] and res.get("running") == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
