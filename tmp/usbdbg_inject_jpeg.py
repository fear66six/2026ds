#!/usr/bin/env python3
"""Inject JPEG UART server at configurable baud."""

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

JPEG_CODE = r'''
from machine import UART, FPIOA
import time, gc, sys
try:
    from ubinascii import crc32 as _crc32
except Exception:
    import binascii
    _crc32 = binascii.crc32
import ustruct as struct
from media.sensor import *
from media.media import *

BAUDRATE=__BAUD__
UART_CHUNK=4096
DISCARD=2
MAX_BUF=4096
JPG_HDR='<4sBBHIIHHII'
JPG_SZ=struct.calcsize(JPG_HDR)
ALLOWED={(320,240),(640,480),(1280,720)}
LOG='/sdcard/experiments/k230_ttl_jpeg/jpeg_server_log.txt'
TEMP='/sdcard/experiments/k230_ttl_jpeg/temp'
sensor=None; cam_w=0; cam_h=0; frame_id=0

def crc32(d):
    return _crc32(d)&0xffffffff if d else 0

def log(m):
    try:
        with open(LOG,'a') as f: f.write(str(m)+'\n')
    except Exception: pass

def pack_jpg(status, rid, fid, w, h, jlen, c):
    return struct.pack(JPG_HDR, b'KJPG', 1, status, JPG_SZ, rid&0xffffffff, fid&0xffffffff, w&0xffff, h&0xffff, jlen&0xffffffff, c&0xffffffff)

def enc(img,q):
    try:
        j=img.to_jpeg(quality=q)
    except TypeError:
        j=img.to_jpeg()
    for g in (lambda x: bytes(x), lambda x: bytes(x.bytearray()[:x.size()])):
        try:
            d=g(j)
            if d and d[:2]==b'\xff\xd8': return d
        except Exception: pass
    p=TEMP+'/_tx.jpg'
    try: j.save(p, quality=q)
    except TypeError: j.save(p)
    with open(p,'rb') as f: return f.read()

def close_cam():
    global sensor, cam_w, cam_h
    try:
        if sensor: sensor.stop()
    except Exception: pass
    sensor=None; cam_w=0; cam_h=0
    try: MediaManager.deinit()
    except Exception: pass
    gc.collect(); time.sleep_ms(80)

def ensure(w,h):
    global sensor, cam_w, cam_h
    if sensor is not None and cam_w==w and cam_h==h: return
    close_cam()
    sensor=Sensor(); sensor.reset()
    sensor.set_framesize(width=w, height=h)
    sensor.set_pixformat(Sensor.RGB888)
    sensor.run(); time.sleep_ms(350)
    cam_w, cam_h = w, h

def send(uart, status, rid, fid, w, h, data):
    data=data or b''
    uart.write(pack_jpg(status, rid, fid, w, h, len(data), crc32(data)))
    i=0
    while i < len(data):
        uart.write(data[i:i+UART_CHUNK]); i+=UART_CHUNK

def handle_capture(uart, rid, w, h, q):
    global frame_id, sensor
    if (w,h) not in ALLOWED or q<10 or q>95:
        send(uart,2,rid,frame_id,0,0,b''); return
    try:
        ensure(w,h)
    except Exception as e:
        log('cam '+str(e)); send(uart,3,rid,frame_id,0,0,b''); return
    try:
        for _ in range(DISCARD): sensor.snapshot()
        img=sensor.snapshot()
        if img is None:
            send(uart,4,rid,frame_id,w,h,b''); return
        try:
            jpeg=enc(img,q)
        except Exception as e:
            log('jpeg '+str(e)); send(uart,5,rid,frame_id,w,h,b''); return
        frame_id += 1
        send(uart,0,rid,frame_id,w,h,jpeg)
        log('ok rid=%d fid=%d %dx%d q=%d len=%d'%(rid,frame_id,w,h,q,len(jpeg)))
        gc.collect()
    except Exception as e:
        log('cap '+str(e)); send(uart,6,rid,frame_id,w,h,b'')

try:
    import uos as os
    for d in ['/sdcard/experiments','/sdcard/experiments/k230_ttl_jpeg',TEMP]:
        try: os.mkdir(d)
        except Exception: pass
    with open(LOG,'w') as f: f.write('jpeg_server\n')
except Exception: pass

fpioa=FPIOA()
fpioa.set_function(50, FPIOA.UART3_TXD, oe=1)
fpioa.set_function(51, FPIOA.UART3_RXD, ie=1)
uart=UART(UART.UART3, baudrate=BAUDRATE, bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
print('JPEG_SERVER_READY baud=%d hdr=%d'%(BAUDRATE, JPG_SZ))
buf=b''
try:
    while True:
        try:
            import os
            if hasattr(os,'exitpoint'): os.exitpoint()
        except Exception: pass
        chunk=uart.read()
        if chunk:
            buf += chunk
            if len(buf)>MAX_BUF: buf=buf[-MAX_BUF:]
            while b'\n' in buf:
                line, buf = buf.split(b'\n',1)
                parts=line.decode('ascii','ignore').strip().split()
                if not parts: continue
                if parts[0]=='PING' and len(parts)>=2:
                    uart.write(('PONG %s\n'%parts[1]).encode())
                elif parts[0]=='STATUS' and len(parts)>=2:
                    uart.write(('READY %s\n'%parts[1]).encode())
                elif parts[0]=='CAPTURE' and len(parts)>=5:
                    handle_capture(uart, int(parts[1],10), int(parts[2],10), int(parts[3],10), int(parts[4],10))
                else:
                    rid=int(parts[1],10) if len(parts)>=2 else 0
                    send(uart,1,rid,frame_id,0,0,b'')
        else:
            time.sleep_ms(2)
finally:
    close_cam()
    try: uart.deinit()
    except Exception: pass
    print('JPEG_SERVER_STOP')
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
    ap.add_argument("--baud", type=int, default=460800)
    args = ap.parse_args()
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
    for attempt in range(4):
        cmd(ser, SCRIPT_STOP, 0)
        t_end = time.perf_counter() + 7
        while time.perf_counter() < t_end:
            c = tx_read(ser)
            if c:
                buf += c
                print("TX", c[:140], flush=True)
            else:
                time.sleep(0.05)
        if b"CanMV v" in buf and b"app_manager" not in buf[buf.rfind(b"CanMV v") :]:
            break
    code = JPEG_CODE.replace("__BAUD__", str(args.baud))
    cmd(ser, SCRIPT_EXEC, len(code), code.encode())
    time.sleep(1.2)
    ready = b""
    for _ in range(60):
        c = tx_read(ser)
        if c:
            ready += c
            print("TXe", c[:180], flush=True)
        if b"JPEG_SERVER_READY" in ready:
            break
        time.sleep(0.08)
    ok = b"JPEG_SERVER_READY" in ready and running(ser) == 1
    print("READY", ok, "RUN", running(ser), flush=True)
    Path.home().joinpath("k230_ttl_jpeg_probe/logs/inject_jpeg_%d.json" % args.baud).write_text(
        json.dumps({"ok": ok, "baud": args.baud}, indent=2)
    )
    ser.close()
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
