#!/usr/bin/env python3
"""Inject camera_local_test via USBDBG; collect READY/DONE from TX."""

from __future__ import annotations

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

# Compact local camera test based on WonderMK Sensor/DataCollectionCamera
CODE = r'''
import time, gc, sys
from media.sensor import *
from media.media import *

LOG='/sdcard/experiments/k230_ttl_jpeg/camera_local_log.txt'
TEMP='/sdcard/experiments/k230_ttl_jpeg/temp'
RESOLUTIONS=[(320,240),(640,480),(1280,720)]
N=20
DISCARD=3
Q=70

def log(m):
    print(m)
    try:
        with open(LOG,'a') as f: f.write(str(m)+'\n')
    except Exception: pass

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
    p=TEMP+'/_e.jpg'
    try: j.save(p, quality=q)
    except TypeError: j.save(p)
    with open(p,'rb') as f: return f.read()

try:
    import uos as os
    for d in ['/sdcard/experiments','/sdcard/experiments/k230_ttl_jpeg',TEMP]:
        try: os.mkdir(d)
        except Exception: pass
    with open(LOG,'w') as f: f.write('start\n')
except Exception: pass

print('CAMERA_LOCAL_START')
log('sensor=GC2093')
save_left=3
for w,h in RESOLUTIONS:
    sensor=None
    oks=[]; sizes=[]; caps=[]; encs=[]
    try:
        sensor=Sensor(); sensor.reset()
        sensor.set_framesize(width=w, height=h)
        sensor.set_pixformat(Sensor.RGB888)
        sensor.run(); time.sleep_ms(400)
        for _ in range(DISCARD): sensor.snapshot()
        for i in range(N):
            t0=time.ticks_ms(); img=sensor.snapshot(); t1=time.ticks_ms()
            if img is None:
                log('fail snapshot %dx%d #%d'%(w,h,i)); continue
            try:
                data=enc(img,Q); t2=time.ticks_ms()
                oks.append(1); sizes.append(len(data)); caps.append(time.ticks_diff(t1,t0)); encs.append(time.ticks_diff(t2,t1))
                if save_left>0 and i==0:
                    with open(TEMP+'/local_%dx%d.jpg'%(w,h),'wb') as f: f.write(data)
                    save_left-=1
            except Exception as e:
                log('enc fail %dx%d #%d %s'%(w,h,i,e))
            gc.collect()
    except Exception as e:
        log('res fail %dx%d %s'%(w,h,e)); sys.print_exception(e)
    finally:
        try:
            if sensor: sensor.stop()
        except Exception: pass
        try: MediaManager.deinit()
        except Exception: pass
        gc.collect(); time.sleep_ms(200)
    if sizes:
        log('RES %dx%d ok=%d/%d jpeg min/avg/max=%d/%d/%d cap_ms avg=%d enc_ms avg=%d'%(
            w,h,len(oks),N,min(sizes),sum(sizes)//len(sizes),max(sizes),sum(caps)//len(caps),sum(encs)//len(encs)))
    else:
        log('RES %dx%d ok=0/%d'%(w,h,N))
print('CAMERA_LOCAL_DONE')
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
    time.sleep(0.5)
    ser = serial.Serial(CDC, baudrate=921600, timeout=0.4, write_timeout=8, dsrdtr=False, rtscts=False)
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    cmd(ser, FB_ENABLE, 4, struct.pack("<I", 1))
    time.sleep(0.2)
    for _ in range(3):
        cmd(ser, SCRIPT_STOP, 0)
        t_end = time.perf_counter() + 6
        while time.perf_counter() < t_end:
            c = tx_read(ser)
            if c:
                print("TX", c[:140], flush=True)
            else:
                time.sleep(0.05)
        if running(ser) in (0, None):
            break
    cmd(ser, SCRIPT_EXEC, len(CODE), CODE.encode())
    time.sleep(1.0)
    buf = b""
    # camera test can take a while (3 res * 20 frames)
    t_end = time.perf_counter() + 240
    while time.perf_counter() < t_end:
        c = tx_read(ser)
        if c:
            buf += c
            print("TX", c[:200], flush=True)
        if b"CAMERA_LOCAL_DONE" in buf:
            break
        if b"Traceback" in buf and running(ser) == 0:
            break
        time.sleep(0.1)
    Path.home().joinpath("k230_ttl_jpeg_probe/logs/camera_local_tx.txt").write_bytes(buf)
    print("DONE_TOKEN", b"CAMERA_LOCAL_DONE" in buf, "RUN", running(ser), flush=True)
    ser.close()
    return 0 if b"CAMERA_LOCAL_DONE" in buf else 2


if __name__ == "__main__":
    raise SystemExit(main())
