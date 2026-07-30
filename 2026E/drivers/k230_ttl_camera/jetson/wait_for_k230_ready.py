#!/usr/bin/env python3
"""Poll until K230 V2 READY appears on TTL (after RESET / autostart)."""

from __future__ import annotations

import argparse
import os
import struct
import sys
import time

import serial

TTL = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A028646-if00"
CDC = "/dev/serial/by-id/usb-Kendryte_CanMV_001000000-if00"


def probe_usbdbg() -> bool:
    """Non-destructive presence check — do not fuser-kill CDC while polling."""
    if not os.path.exists(CDC):
        return False
    try:
        s = serial.Serial(CDC, 921600, timeout=0.3, write_timeout=1, dsrdtr=False, rtscts=False)
        try:
            s.dtr = False
            s.rts = False
        except Exception:
            pass
        s.write(struct.pack("<BBI", 48, 0x80, 12))
        r = s.read(12)
        s.close()
        return bool(r) and len(r) >= 4
    except Exception:
        # port busy / hung still counts as present
        return True


def probe_ttl_ready(timeout_s: float = 2.0) -> str:
    if not os.path.exists(TTL):
        return ""
    ser = serial.Serial(TTL, 460800, timeout=0.1, write_timeout=2, dsrdtr=False, rtscts=False)
    try:
        end = time.perf_counter() + timeout_s
        buf = b""
        # also poke STATUS in case READY already sent
        ser.write(b"STATUS 00000001\n")
        ser.flush()
        while time.perf_counter() < end:
            chunk = ser.read(256)
            if chunk:
                buf += chunk
                if b"READY" in buf or b"STATUS_OK" in buf or b"PONG" in buf:
                    break
            else:
                time.sleep(0.05)
        return buf.decode("ascii", "replace")
    finally:
        ser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-wait", type=float, default=300.0)
    args = ap.parse_args()
    t0 = time.time()
    while time.time() - t0 < args.max_wait:
        usb = probe_usbdbg()
        text = probe_ttl_ready(1.5)
        print(
            f"t={time.time()-t0:.0f}s usbdbg={usb} ttl={text[:120]!r}",
            flush=True,
        )
        if "READY" in text or "STATUS_OK" in text or "PONG" in text:
            print("K230_PROTOCOL_UP", flush=True)
            return 0
        # USBDBG up without TTL means board alive but camera server not on UART yet.
        # Keep waiting (user may press RESET to load main.py launcher).
        time.sleep(2.0)
    print("TIMEOUT_WAITING_RESET", flush=True)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
