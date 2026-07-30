#!/usr/bin/env python3
"""Production Jetson client for K230 TTL JPEG protocol V2."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
import serial

from protocol import (
    BAUDRATE,
    DEFAULT_TTL_BY_ID,
    HEIGHT,
    JPG_HEADER_SIZE,
    MAGIC_JPG,
    MAX_JPEG_BYTES,
    PROTOCOL_VERSION,
    STATUS_OK,
    TTL_PID,
    TTL_VID,
    WIDTH,
    crc32,
    format_request_id,
    unpack_jpg_header,
)

TOTAL_TIMEOUT_S = 7.0
RETRY_COUNT = 1
SERIAL_IDLE_RECOVERY_MS = 300
PING_TIMEOUT_S = 2.0
READY_TIMEOUT_S = 8.0
MAX_JPEG = MAX_JPEG_BYTES

logger = logging.getLogger("k230_ttl_camera")


@dataclass
class CaptureMeta:
    session_id: int
    request_id: int
    frame_id: int
    capture_timestamp_ms: int
    jpeg_bytes: int
    capture_ms: int
    encode_ms: int
    receive_ms: float
    decode_ms: float
    total_ms: float
    crc_ok: bool
    retry_count: int = 0


class K230CameraError(RuntimeError):
    pass


class K230TtlSnapshotCamera:
    """Fixed 1280x720 @460800 TTL snapshot camera. No resolution/baud knobs."""

    def __init__(
        self,
        port: str = DEFAULT_TTL_BY_ID,
        *,
        total_timeout_s: float = TOTAL_TIMEOUT_S,
        retry_count: int = RETRY_COUNT,
        idle_recovery_ms: int = SERIAL_IDLE_RECOVERY_MS,
        log_path: Optional[Path] = None,
    ) -> None:
        if not port.startswith("/dev/serial/by-id/"):
            raise ValueError("port must be /dev/serial/by-id/...")
        if "Kendryte" in port or "CanMV" in port:
            raise ValueError("refusing K230 native CDC as TTL")
        self.port = port
        self.total_timeout_s = total_timeout_s
        self.retry_count = retry_count
        self.idle_recovery_ms = idle_recovery_ms
        self._ser: Optional[serial.Serial] = None
        self._request_id = 0
        self._session_id: Optional[int] = None
        self._last_frame_id: Optional[int] = None
        self._ready = False
        self._last_meta: Optional[CaptureMeta] = None
        self._log_path = log_path
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ---- logging ----
    def _event(self, event: str, **fields: Any) -> None:
        row = {"timestamp": time.time(), "event": event, **fields}
        logger.info("%s", json.dumps(row, ensure_ascii=False))
        if self._log_path is not None:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # ---- serial helpers ----
    def _assert_ttl_identity(self) -> None:
        if not Path(self.port).exists():
            raise K230CameraError(f"TTL by-id missing: {self.port}")
        real = os.path.realpath(self.port)
        if real.endswith("ttyACM0") and "1a86" not in self.port.lower():
            # soft check; by-id name is authoritative
            pass
        if "1a86" not in self.port.lower() and "USB_Single_Serial" not in self.port:
            raise K230CameraError(f"port does not look like CH343 TTL: {self.port}")
        # occupancy
        try:
            import subprocess

            out = subprocess.check_output(["fuser", self.port], stderr=subprocess.STDOUT, text=True)
            if out.strip():
                raise K230CameraError(f"port busy: {self.port} -> {out.strip()}")
        except FileNotFoundError:
            pass
        except subprocess.CalledProcessError:
            pass  # not busy
        except Exception as e:
            self._event("occupancy_check_warn", error=str(e))

    def _open_serial(self) -> None:
        self._assert_ttl_identity()
        self._ser = serial.Serial(
            port=self.port,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
            write_timeout=5.0,
            dsrdtr=False,
            rtscts=False,
        )
        try:
            self._ser.dtr = False
            self._ser.rts = False
        except Exception:
            pass
        self._drain(0.2)

    def _drain(self, seconds: float = 0.2) -> bytes:
        assert self._ser is not None
        buf = bytearray()
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            chunk = self._ser.read(4096)
            if chunk:
                buf.extend(chunk)
            else:
                time.sleep(0.005)
        try:
            self._ser.reset_input_buffer()
        except Exception:
            pass
        return bytes(buf)

    def _wait_idle(self, ms: int) -> None:
        assert self._ser is not None
        need = ms / 1000.0
        quiet_start = time.perf_counter()
        deadline = time.perf_counter() + max(1.0, need * 3)
        while time.perf_counter() < deadline:
            chunk = self._ser.read(1024)
            if chunk:
                quiet_start = time.perf_counter()
            elif time.perf_counter() - quiet_start >= need:
                break
            else:
                time.sleep(0.005)
        try:
            self._ser.reset_input_buffer()
        except Exception:
            pass

    def _next_rid(self) -> int:
        self._request_id = (self._request_id + 1) & 0xFFFFFFFF
        if self._request_id == 0:
            self._request_id = 1
        return self._request_id

    def _write_line(self, line: str) -> None:
        assert self._ser is not None
        self._ser.write(line.encode("ascii"))
        self._ser.flush()

    def _read_line(self, deadline: float) -> str:
        assert self._ser is not None
        buf = bytearray()
        while time.perf_counter() < deadline:
            b = self._ser.read(1)
            if not b:
                time.sleep(0.002)
                continue
            if b == b"\n":
                break
            buf.extend(b)
            if len(buf) > 512:
                break
        return buf.decode("ascii", "replace").strip()

    def _read_exact(self, n: int, deadline: float) -> bytes:
        assert self._ser is not None
        buf = bytearray()
        while len(buf) < n and time.perf_counter() < deadline:
            chunk = self._ser.read(min(8192, n - len(buf)))
            if chunk:
                buf.extend(chunk)
            else:
                time.sleep(0.001)
        return bytes(buf)

    def _find_magic(self, deadline: float) -> bool:
        assert self._ser is not None
        window = bytearray()
        while time.perf_counter() < deadline:
            b = self._ser.read(1)
            if not b:
                time.sleep(0.001)
                continue
            window.extend(b)
            if len(window) > 4:
                del window[:-4]
            if bytes(window) == MAGIC_JPG:
                return True
        return False

    # ---- handshake ----
    def _parse_session_from_text(self, text: str) -> Optional[int]:
        m = re.search(r"session=(\d+)", text)
        if not m:
            return None
        return int(m.group(1))

    def _wait_ready(self) -> int:
        assert self._ser is not None
        deadline = time.perf_counter() + READY_TIMEOUT_S
        saw = ""
        next_poll = time.perf_counter() + 0.8
        while time.perf_counter() < deadline:
            line = self._read_line(min(deadline, time.perf_counter() + 0.25))
            if line:
                saw += line + "\n"
                if line.startswith("READY") or line.startswith("STATUS_OK"):
                    sid = self._parse_session_from_text(line)
                    if sid is not None:
                        return sid
            if time.perf_counter() >= next_poll:
                rid = self._next_rid()
                self._write_line(f"STATUS {format_request_id(rid)}\n")
                next_poll = time.perf_counter() + 1.0
        raise K230CameraError(f"READY/STATUS timeout; saw={saw!r}")

    def _ping(self) -> None:
        rid = self._next_rid()
        self._write_line(f"PING {format_request_id(rid)}\n")
        line = self._read_line(time.perf_counter() + PING_TIMEOUT_S)
        expect = f"PONG {format_request_id(rid)}"
        if line != expect and not line.startswith(expect):
            raise K230CameraError(f"PING failed: {line!r}")

    def _status(self) -> int:
        rid = self._next_rid()
        self._write_line(f"STATUS {format_request_id(rid)}\n")
        line = self._read_line(time.perf_counter() + PING_TIMEOUT_S)
        if not line.startswith("STATUS_OK"):
            raise K230CameraError(f"STATUS failed: {line!r}")
        sid = self._parse_session_from_text(line)
        if sid is None:
            raise K230CameraError(f"STATUS missing session: {line!r}")
        return sid

    def initialize(self) -> None:
        if self._ready and self._ser is not None:
            return
        self.close()
        self._open_serial()
        # allow K230 READY to arrive; drain garbage then handshake
        time.sleep(0.15)
        self._drain(0.25)
        try:
            sid = self._wait_ready()
        except K230CameraError:
            # K230 may already be running without fresh READY; try ping/status
            self._ping()
            sid = self._status()
        self._session_id = sid
        self._last_frame_id = None
        self._ping()
        sid2 = self._status()
        if sid2 != self._session_id:
            self._session_id = sid2
            self._last_frame_id = None
        # warmup capture discarded
        frame, meta = self._capture_once(retry_count=0)
        del frame
        self._event(
            "initialize_ok",
            session_id=self._session_id,
            warmup_frame_id=meta.frame_id,
            jpeg_bytes=meta.jpeg_bytes,
            total_ms=meta.total_ms,
        )
        self._ready = True

    def health_check(self) -> bool:
        try:
            if not self._ready:
                self.initialize()
            self._ping()
            sid = self._status()
            if self._session_id is not None and sid != self._session_id:
                self._event("session_changed_on_health", old=self._session_id, new=sid)
                self._session_id = sid
                self._last_frame_id = None
            return True
        except Exception as e:
            self._event("health_check_fail", error=str(e))
            return False

    def close(self) -> None:
        self._ready = False
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    # ---- capture ----
    def _is_flat(self, frame: np.ndarray) -> Optional[str]:
        mean = float(frame.mean())
        std = float(frame.std())
        if mean < 5 and std < 2.0:
            return "all_black"
        if mean > 250 and std < 2.0:
            return "all_white"
        return None

    def _capture_once(self, retry_count: int = 0) -> tuple[np.ndarray, CaptureMeta]:
        if self._ser is None:
            raise K230CameraError("serial not open")
        rid = self._next_rid()
        t0 = time.perf_counter()
        deadline = t0 + self.total_timeout_s
        self._write_line(f"CAPTURE {format_request_id(rid)}\n")
        if not self._find_magic(deadline):
            raise K230CameraError("KJPG magic timeout")
        rest = self._read_exact(JPG_HEADER_SIZE - 4, deadline)
        if len(rest) != JPG_HEADER_SIZE - 4:
            raise K230CameraError("header short read")
        meta = unpack_jpg_header(MAGIC_JPG + rest)
        if meta["magic"] != MAGIC_JPG:
            raise K230CameraError("bad magic")
        if meta["version"] != PROTOCOL_VERSION:
            raise K230CameraError(f"bad version {meta['version']}")
        if meta["header_length"] != JPG_HEADER_SIZE:
            raise K230CameraError(f"bad header_length {meta['header_length']}")
        if meta["status"] != STATUS_OK:
            raise K230CameraError(f"status={meta['status']}")
        if self._session_id is not None and meta["session_id"] != self._session_id:
            raise K230CameraError(
                f"session_mismatch got={meta['session_id']} expect={self._session_id}"
            )
        if meta["request_id"] != rid:
            raise K230CameraError(f"request_id mismatch {meta['request_id']}!={rid}")
        if meta["width"] != WIDTH or meta["height"] != HEIGHT:
            raise K230CameraError(f"bad size {meta['width']}x{meta['height']}")
        jlen = meta["jpeg_length"]
        if jlen <= 0 or jlen > MAX_JPEG:
            raise K230CameraError(f"bad jpeg_length {jlen}")
        if self._last_frame_id is not None and meta["frame_id"] <= self._last_frame_id:
            raise K230CameraError(
                f"stale frame_id {meta['frame_id']} <= {self._last_frame_id}"
            )
        t_rx0 = time.perf_counter()
        jpeg = self._read_exact(jlen, deadline)
        t_rx1 = time.perf_counter()
        if len(jpeg) != jlen:
            raise K230CameraError("jpeg short read")
        if crc32(jpeg) != meta["crc32"]:
            raise K230CameraError("CRC32 mismatch")
        t_d0 = time.perf_counter()
        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        t_d1 = time.perf_counter()
        if frame is None:
            raise K230CameraError("OpenCV imdecode failed")
        if frame.dtype != np.uint8:
            raise K230CameraError("bad dtype")
        hh, ww = frame.shape[:2]
        if ww != WIDTH or hh != HEIGHT:
            raise K230CameraError(f"decoded shape {ww}x{hh}")
        flat = self._is_flat(frame)
        if flat:
            raise K230CameraError(flat)
        self._last_frame_id = meta["frame_id"]
        if self._session_id is None:
            self._session_id = meta["session_id"]
        cm = CaptureMeta(
            session_id=meta["session_id"],
            request_id=meta["request_id"],
            frame_id=meta["frame_id"],
            capture_timestamp_ms=meta["capture_timestamp_ms"],
            jpeg_bytes=jlen,
            capture_ms=meta["capture_ms"],
            encode_ms=meta["encode_ms"],
            receive_ms=(t_rx1 - t_rx0) * 1000.0,
            decode_ms=(t_d1 - t_d0) * 1000.0,
            total_ms=(t_d1 - t0) * 1000.0,
            crc_ok=True,
            retry_count=retry_count,
        )
        self._last_meta = cm
        self._event(
            "capture_ok",
            session_id=cm.session_id,
            request_id=cm.request_id,
            frame_id=cm.frame_id,
            jpeg_bytes=cm.jpeg_bytes,
            capture_ms=cm.capture_ms,
            encode_ms=cm.encode_ms,
            receive_ms=round(cm.receive_ms, 2),
            decode_ms=round(cm.decode_ms, 2),
            total_ms=round(cm.total_ms, 2),
            retry_count=retry_count,
            result="ok",
            error_type="",
            capture_timestamp_ms=cm.capture_timestamp_ms,
        )
        return frame, cm

    def _resync(self) -> None:
        self._event("resync_begin", session_id=self._session_id)
        self._wait_idle(self.idle_recovery_ms)
        self._ping()
        sid = self._status()
        if self._session_id is not None and sid != self._session_id:
            self._event("session_changed", old=self._session_id, new=sid)
            self._session_id = sid
            self._last_frame_id = None
            # re-warmup after K230 restart
            frame, meta = self._capture_once(retry_count=0)
            del frame
            self._event("resync_warmup_ok", frame_id=meta.frame_id)
        else:
            self._session_id = sid
        self._event("resync_ok", session_id=self._session_id)

    def capture_snapshot(self) -> np.ndarray:
        if not self._ready:
            self.initialize()
        assert self._ser is not None
        try:
            frame, _meta = self._capture_once(retry_count=0)
            return frame
        except Exception as first_err:
            self._event(
                "capture_fail",
                session_id=self._session_id,
                result="fail",
                error_type=type(first_err).__name__,
                error=str(first_err),
                retry_count=0,
            )
            if self.retry_count < 1:
                raise K230CameraError(str(first_err)) from first_err
            try:
                self._resync()
                frame, meta = self._capture_once(retry_count=1)
                self._event(
                    "capture_retry_ok",
                    session_id=meta.session_id,
                    request_id=meta.request_id,
                    frame_id=meta.frame_id,
                    first_error=str(first_err),
                )
                return frame
            except Exception as second_err:
                self._event(
                    "capture_retry_fail",
                    first_error=str(first_err),
                    second_error=str(second_err),
                    result="fail",
                )
                raise K230CameraError(
                    f"capture failed after resync: first={first_err}; second={second_err}"
                ) from second_err

    @property
    def last_meta(self) -> Optional[CaptureMeta]:
        return self._last_meta
