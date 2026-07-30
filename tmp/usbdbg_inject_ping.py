#!/usr/bin/env python3
"""Inject inline K230 UART ping server via USBDBG and verify TX token."""

from __future__ import annotations

import json
import os
import struct
import sys
import time

import serial

USBDBG_CMD = 48
SCRIPT_EXEC = 0x05
SCRIPT_STOP = 0x06
FB_ENABLE = 0x0D
FW_VERSION = 0x80
SCRIPT_RUNNING = 0x87
TX_BUF_LEN = 0x8E
TX_BUF = 0x8F
ARCH_STR = 0x83
QUERY_STATUS = 0x8D

CDC = "/dev/serial/by-id/usb-Kendryte_CanMV_001000000-if00"

PING_SERVER = r'''
from machine import UART, FPIOA
import time

BAUDRATE = 115200
UART_TX_PIN = 50
UART_RX_PIN = 51
MAX_BUF = 4096
IDLE_MS = 5

fpioa = FPIOA()
fpioa.set_function(UART_TX_PIN, FPIOA.UART3_TXD, oe=1)
fpioa.set_function(UART_RX_PIN, FPIOA.UART3_RXD, ie=1)
uart = UART(UART.UART3, baudrate=BAUDRATE, bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
print('PING_SERVER_READY baud=%d' % BAUDRATE)
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
                text = line.decode('ascii', 'ignore').strip()
                parts = text.split()
                if len(parts) >= 2 and parts[0] == 'PING':
                    uart.write(('PONG %s\n' % parts[1]).encode())
                elif len(parts) >= 2 and parts[0] == 'STATUS':
                    uart.write(('READY %s\n' % parts[1]).encode())
        else:
            time.sleep_ms(IDLE_MS)
finally:
    try:
        uart.deinit()
    except Exception:
        pass
    print('PING_SERVER_STOP')
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
    os.system("fuser -k /dev/ttyACM0 2>/dev/null")
    os.system("gio mount -u gphoto2://Kendryte_CanMV_001000000/ 2>/dev/null")
    time.sleep(0.8)

    ser = serial.Serial(CDC, baudrate=921600, timeout=0.5, write_timeout=3, dsrdtr=False, rtscts=False)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass

    cmd(ser, FW_VERSION, 12)
    print("FW", ser.read(12).hex(), flush=True)
    cmd(ser, ARCH_STR, 64)
    print("ARCH", ser.read(64).split(b"\0")[0], flush=True)
    cmd(ser, QUERY_STATUS, 4)
    print("QS", ser.read(4).hex(), flush=True)

    print("RUN0", running(ser), flush=True)
    cmd(ser, FB_ENABLE, 4, struct.pack("<I", 1))
    time.sleep(0.3)
    cmd(ser, SCRIPT_STOP, 0)
    time.sleep(1.0)
    print("RUN_stop", running(ser), flush=True)
    for _ in range(15):
        c = tx_read(ser)
        if c:
            print("TXs", c[:160], flush=True)
        time.sleep(0.05)

    # sanity hello
    hello = "print('HELLO_INLINE')\n"
    cmd(ser, SCRIPT_EXEC, len(hello), hello.encode())
    time.sleep(0.8)
    print("RUN_hello", running(ser), flush=True)
    buf = b""
    for _ in range(20):
        c = tx_read(ser)
        if c:
            buf += c
            print("TXh", c[:160], flush=True)
        time.sleep(0.05)
    print("HAS_HELLO", b"HELLO_INLINE" in buf, flush=True)

    cmd(ser, SCRIPT_STOP, 0)
    time.sleep(0.4)

    code = PING_SERVER
    cmd(ser, SCRIPT_EXEC, len(code), code.encode())
    time.sleep(1.2)
    print("RUN_ping", running(ser), flush=True)
    buf = b""
    for _ in range(40):
        c = tx_read(ser)
        if c:
            buf += c
            print("TX", c[:200], flush=True)
        if b"PING_SERVER_READY" in buf:
            break
        time.sleep(0.08)
    print("READY", b"PING_SERVER_READY" in buf, flush=True)
    print("RUN_final", running(ser), flush=True)
    ser.close()
    Path = __import__("pathlib").Path
    Path.home().joinpath("k230_ttl_jpeg_probe/logs/usbdbg_ping_inject.json").write_text(
        json.dumps(
            {
                "ready": b"PING_SERVER_READY" in buf,
                "running": True,  # best-effort; script left running if ready
                "tx_tail": buf[-500:].decode("latin1", "replace"),
            },
            indent=2,
        )
    )
    return 0 if b"PING_SERVER_READY" in buf else 2


if __name__ == "__main__":
    raise SystemExit(main())
