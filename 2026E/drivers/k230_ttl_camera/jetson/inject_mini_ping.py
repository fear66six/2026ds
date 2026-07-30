#!/usr/bin/env python3
"""Reliable: wait REPL after stop, inject UART ping @460800, verify TTL."""

from __future__ import annotations

import os
import struct
import time

import serial

CDC = "/dev/serial/by-id/usb-Kendryte_CanMV_001000000-if00"
TTL = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A028646-if00"
USBDBG_CMD = 48
SCRIPT_EXEC = 0x05
SCRIPT_STOP = 0x06
FB_ENABLE = 0x0D
SCRIPT_RUNNING = 0x87
TX_BUF_LEN = 0x8E
TX_BUF = 0x8F

CODE = r"""
from machine import UART, FPIOA
import time
print("BOOT_MINI")
fp = FPIOA()
fp.set_function(50, FPIOA.UART3_TXD, oe=1)
fp.set_function(51, FPIOA.UART3_RXD, ie=1)
u = UART(UART.UART3, baudrate=460800, bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
n = u.write(b"READY_MINI\n")
print("wrote", n)
buf = b""
while True:
    c = u.read()
    if c:
        buf += c
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            t = line.decode("ascii", "ignore").strip()
            print("line", t)
            if t.startswith("PING"):
                rid = t.split()[1] if len(t.split()) > 1 else "?"
                w = u.write(("PONG %s\n" % rid).encode())
                print("pong_w", w)
    else:
        time.sleep_ms(2)
"""


def wait_cdc(timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(CDC):
            return True
        time.sleep(0.5)
    return False


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


def open_cdc():
    os.system("fuser -k /dev/ttyACM0 2>/dev/null")
    os.system("gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null")
    time.sleep(0.5)
    if not wait_cdc(30):
        raise SystemExit("CDC missing")
    ser = serial.Serial(CDC, 921600, timeout=0.5, write_timeout=8, dsrdtr=False, rtscts=False)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    return ser


def main() -> int:
    ser = open_cdc()
    print("FW probe...", flush=True)
    cmd(ser, 0x80, 12)
    print("FW", ser.read(12), flush=True)
    cmd(ser, FB_ENABLE, 4, struct.pack("<I", 1))
    time.sleep(0.2)
    print("RUN_before", running(ser), flush=True)

    # stop and wait for REPL token
    buf = b""
    for attempt in range(4):
        cmd(ser, SCRIPT_STOP, 0)
        t_end = time.perf_counter() + 10
        while time.perf_counter() < t_end:
            if not os.path.exists(CDC):
                print("CDC lost; waiting", flush=True)
                ser.close()
                if not wait_cdc(60):
                    raise SystemExit("CDC gone")
                ser = open_cdc()
                break
            try:
                c = tx_read(ser)
            except Exception as e:
                print("tx err", e, flush=True)
                time.sleep(0.5)
                continue
            if c:
                buf += c
                print("TX", c[:120], flush=True)
            else:
                time.sleep(0.05)
            if b"CanMV v" in buf and b"app_manager" not in buf[buf.rfind(b"CanMV v") :]:
                print("REPL-ish ready", flush=True)
                break
        else:
            continue
        break

    # re-open if needed
    if not os.path.exists(CDC):
        ser.close()
        wait_cdc(60)
        ser = open_cdc()

    cmd(ser, SCRIPT_EXEC, len(CODE), CODE.encode())
    print("EXEC len", len(CODE), flush=True)
    ready = b""
    for _ in range(80):
        try:
            c = tx_read(ser)
        except Exception as e:
            print("tx err2", e, flush=True)
            break
        if c:
            ready += c
            print("TXe", c[:160], flush=True)
        if b"BOOT_MINI" in ready and b"wrote" in ready:
            break
        time.sleep(0.1)
    print("HAS_BOOT", b"BOOT_MINI" in ready, "HAS_WROTE", b"wrote" in ready, "RUN", running(ser), flush=True)
    ser.close()

    if not os.path.exists(TTL):
        print("TTL missing", flush=True)
        return 3
    ttl = serial.Serial(TTL, 460800, timeout=0.4, write_timeout=2)
    ttl.reset_input_buffer()
    time.sleep(0.2)
    drain = ttl.read(512)
    print("TTL_DRAIN", drain, flush=True)
    ok = 0
    for i in range(10):
        ttl.write(("PING %d\n" % i).encode())
        ttl.flush()
        time.sleep(0.2)
        r = ttl.read(256)
        print("PING", i, "->", r, flush=True)
        if b"PONG" in r:
            ok += 1
    ttl.close()
    print("PONG_OK", ok, "/10", flush=True)
    return 0 if ok >= 5 else 4


if __name__ == "__main__":
    raise SystemExit(main())
