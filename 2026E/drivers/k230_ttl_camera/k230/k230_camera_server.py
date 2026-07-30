# k230_camera_server.py — production K230 TTL JPEG service (protocol V2)
# Fixed: UART3 TX50/RX51 @460800, GC2093 1280x720 q=65, discard=2, chunk=4096
# Protocol UART must carry ONLY protocol bytes (no print/traceback).

from machine import UART, FPIOA
import time
import sys
import gc
import os

sys.path.append("/sdcard/experiments/k230_ttl_jpeg")
from protocol import (
    BAUDRATE,
    UART_TX_PIN,
    UART_RX_PIN,
    WIDTH,
    HEIGHT,
    JPEG_QUALITY,
    DISCARD_FRAMES,
    CHUNK_SIZE,
    MAX_JPEG_BYTES,
    STATUS_OK,
    STATUS_BAD_COMMAND,
    STATUS_CAMERA_NOT_READY,
    STATUS_CAPTURE_FAILED,
    STATUS_JPEG_ENCODE_FAILED,
    STATUS_INTERNAL_ERROR,
    STATUS_SEND_FAILED,
    crc32,
    pack_jpg_header,
    parse_request_id,
    format_request_id,
    JPG_HEADER_SIZE,
)

from media.sensor import Sensor
from media.media import MediaManager

MAX_BUF = 4096
IDLE_MS = 2
WARMUP_FRAMES = 2
EXPOSURE_WAIT_MS = 400

uart = None
sensor = None
session_id = 0
frame_id = 0
_started_ms = 0


def _mono_ms():
    return time.ticks_ms() & 0xFFFFFFFF


def debug(msg):
    # USBDBG / IDE only — never write to protocol UART
    try:
        print(msg)
    except Exception:
        pass


def write_all(u, data, timeout_ms=5000):
    """Send all bytes; return True on success.

    CanMV/MicroPython UART.write() often returns None after accepting the
    buffer (official UART.py ignores the return). Treat None as full-chunk
    success; handle 0 / short writes / negative without spinning forever.
    """
    if not data:
        return True
    sent = 0
    t0 = time.ticks_ms()
    n = len(data)
    while sent < n:
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            return False
        try:
            w = u.write(data[sent:])
        except Exception:
            return False
        if w is None:
            # None => driver accepted remaining bytes (WonderMK UART pattern)
            return True
        if w == 0:
            time.sleep_ms(1)
            continue
        if w < 0:
            return False
        sent += int(w)
    return True


def init_uart():
    global uart
    fpioa = FPIOA()
    fpioa.set_function(UART_TX_PIN, FPIOA.UART3_TXD, oe=1)
    fpioa.set_function(UART_RX_PIN, FPIOA.UART3_RXD, ie=1)
    uart = UART(
        UART.UART3,
        baudrate=BAUDRATE,
        bits=UART.EIGHTBITS,
        parity=UART.PARITY_NONE,
        stop=UART.STOPBITS_ONE,
    )
    return uart


def encode_jpeg(img):
    """Require quality=65; fail hard if API ignores/rejects quality."""
    try:
        jpg = img.to_jpeg(quality=JPEG_QUALITY)
    except TypeError:
        raise Exception("to_jpeg(quality=) unsupported on this firmware")
    except Exception as e:
        raise Exception("to_jpeg failed: %s" % e)
    data = None
    for getter in (
        lambda j: bytes(j),
        lambda j: bytes(j.bytearray()[: j.size()]),
    ):
        try:
            data = getter(jpg)
            if data and data[:2] == b"\xff\xd8":
                break
        except Exception:
            data = None
    if not data or data[:2] != b"\xff\xd8":
        raise Exception("jpeg bytes unavailable")
    if len(data) > MAX_JPEG_BYTES:
        raise Exception("jpeg too large")
    return data


def close_camera():
    global sensor
    try:
        if sensor is not None:
            sensor.stop()
    except Exception:
        pass
    sensor = None
    try:
        MediaManager.deinit()
    except Exception:
        pass
    gc.collect()
    time.sleep_ms(80)


def init_camera():
    global sensor
    close_camera()
    sensor = Sensor()
    sensor.reset()
    sensor.set_framesize(width=WIDTH, height=HEIGHT)
    sensor.set_pixformat(Sensor.RGB888)
    sensor.run()
    time.sleep_ms(EXPOSURE_WAIT_MS)
    for _ in range(WARMUP_FRAMES):
        sensor.snapshot()
    gc.collect()


def send_error_frame(status, request_id, capture_ts=0, cap_ms=0, enc_ms=0):
    hdr = pack_jpg_header(
        status,
        session_id,
        request_id,
        frame_id,
        capture_ts,
        0,
        0,
        cap_ms,
        enc_ms,
    )
    write_all(uart, hdr, timeout_ms=2000)


def handle_capture(request_id):
    global frame_id, sensor
    if sensor is None:
        send_error_frame(STATUS_CAMERA_NOT_READY, request_id)
        return
    try:
        t_cmd = _mono_ms()
        for _ in range(DISCARD_FRAMES):
            sensor.snapshot()
        t0 = time.ticks_ms()
        img = sensor.snapshot()
        capture_ts = _mono_ms()
        t1 = time.ticks_ms()
        if img is None:
            send_error_frame(STATUS_CAPTURE_FAILED, request_id, capture_ts)
            return
        # freshness: capture must be after command handling started
        if time.ticks_diff(capture_ts, t_cmd) < 0:
            # ticks wrap; ignore
            pass
        try:
            jpeg = encode_jpeg(img)
        except Exception as e:
            debug("jpeg_err %s" % e)
            send_error_frame(STATUS_JPEG_ENCODE_FAILED, request_id, capture_ts)
            return
        t2 = time.ticks_ms()
        cap_ms = time.ticks_diff(t1, t0) & 0xFFFF
        enc_ms = time.ticks_diff(t2, t1) & 0xFFFF
        frame_id = (frame_id + 1) & 0xFFFFFFFF
        c = crc32(jpeg)
        hdr = pack_jpg_header(
            STATUS_OK,
            session_id,
            request_id,
            frame_id,
            capture_ts,
            len(jpeg),
            c,
            cap_ms,
            enc_ms,
        )
        if not write_all(uart, hdr, timeout_ms=3000):
            debug("hdr_send_fail")
            return
        i = 0
        while i < len(jpeg):
            end = i + CHUNK_SIZE
            if end > len(jpeg):
                end = len(jpeg)
            if not write_all(uart, jpeg[i:end], timeout_ms=8000):
                debug("jpeg_send_fail")
                return
            i = end
        gc.collect()
    except Exception as e:
        debug("cap_internal %s" % e)
        send_error_frame(STATUS_INTERNAL_ERROR, request_id)


def handle_line(line):
    parts = line.strip().split()
    if not parts:
        return
    cmd = parts[0]
    try:
        if cmd == "PING" and len(parts) >= 2:
            rid = parse_request_id(parts[1])
            write_all(uart, ("PONG %s\n" % format_request_id(rid)).encode(), 1000)
            return
        if cmd == "STATUS" and len(parts) >= 2:
            rid = parse_request_id(parts[1])
            msg = "STATUS_OK %s session=%u frame=%u width=%u height=%u q=%u\n" % (
                format_request_id(rid),
                session_id,
                frame_id,
                WIDTH,
                HEIGHT,
                JPEG_QUALITY,
            )
            write_all(uart, msg.encode(), 1000)
            return
        if cmd == "CAPTURE" and len(parts) >= 2:
            # ignore extra args if any — production ignores width/height/quality
            rid = parse_request_id(parts[1])
            handle_capture(rid)
            return
        rid = parse_request_id(parts[1]) if len(parts) >= 2 else 0
        send_error_frame(STATUS_BAD_COMMAND, rid)
    except Exception as e:
        debug("handle_err %s" % e)
        try:
            rid = parse_request_id(parts[1]) if len(parts) >= 2 else 0
        except Exception:
            rid = 0
        send_error_frame(STATUS_INTERNAL_ERROR, rid)


def shutdown():
    global uart
    close_camera()
    try:
        if uart is not None:
            uart.deinit()
    except Exception:
        pass
    uart = None


def main():
    global session_id, frame_id, _started_ms
    _started_ms = _mono_ms()
    session_id = (_started_ms ^ 0xA5A5A5A5) & 0xFFFFFFFF
    if session_id == 0:
        session_id = 1
    frame_id = 0

    init_uart()
    try:
        init_camera()
    except Exception as e:
        debug("cam_init_fail %s" % e)
        shutdown()
        raise

    # Structured READY on protocol UART (allowed protocol text)
    ready = "READY session=%u width=%u height=%u q=%u baud=%u ver=%u\n" % (
        session_id,
        WIDTH,
        HEIGHT,
        JPEG_QUALITY,
        BAUDRATE,
        2,
    )
    write_all(uart, ready.encode(), 2000)
    debug("SERVER_READY session=%u" % session_id)

    buf = b""
    try:
        while True:
            try:
                if hasattr(os, "exitpoint"):
                    os.exitpoint()
            except Exception:
                pass
            chunk = uart.read()
            if chunk:
                buf += chunk
                if len(buf) > MAX_BUF:
                    buf = buf[-MAX_BUF:]
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("ascii", "ignore")
                    if text.strip():
                        handle_line(text)
            else:
                time.sleep_ms(IDLE_MS)
    except KeyboardInterrupt:
        debug("KeyboardInterrupt")
    except Exception as e:
        debug("fatal %s" % e)
        raise
    finally:
        shutdown()
        debug("SERVER_STOP")


if __name__ == "__main__":
    main()
