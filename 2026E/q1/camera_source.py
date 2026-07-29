"""跨平台摄像头配置与 latest-frame 采集。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import sys
import threading
import time
from typing import Optional

import cv2
import numpy as np

from . import config

LOG = logging.getLogger(__name__)


def fourcc_text(value: float) -> str:
    number = int(value)
    text = "".join(chr((number >> (8 * i)) & 0xFF) for i in range(4))
    return text.replace("\x00", "").strip() or "unknown"


def _safe_get(cap, prop: int) -> Optional[float]:
    try:
        value = float(cap.get(prop))
    except Exception:
        return None
    return value if np.isfinite(value) else None


def _backend_name(cap) -> str:
    try:
        return str(cap.getBackendName())
    except Exception:
        return "unknown"


def camera_properties(cap) -> dict:
    return {
        "backend": _backend_name(cap),
        "width": _safe_get(cap, cv2.CAP_PROP_FRAME_WIDTH),
        "height": _safe_get(cap, cv2.CAP_PROP_FRAME_HEIGHT),
        "fps": _safe_get(cap, cv2.CAP_PROP_FPS),
        "fourcc": fourcc_text(_safe_get(cap, cv2.CAP_PROP_FOURCC) or 0),
        "buffersize": _safe_get(cap, cv2.CAP_PROP_BUFFERSIZE),
        "auto_exposure": _safe_get(cap, cv2.CAP_PROP_AUTO_EXPOSURE),
        "exposure": _safe_get(cap, cv2.CAP_PROP_EXPOSURE),
        "gain": _safe_get(cap, cv2.CAP_PROP_GAIN),
        "white_balance": _safe_get(
            cap, getattr(cv2, "CAP_PROP_WB_TEMPERATURE", cv2.CAP_PROP_GAIN)
        ),
        "auto_white_balance": _safe_get(
            cap,
            getattr(cv2, "CAP_PROP_AUTO_WB", cv2.CAP_PROP_GAIN),
        ),
    }


def configure_camera(
    cap,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: Optional[float] = None,
    fourcc: Optional[str] = None,
    auto_exposure: Optional[float] = None,
    exposure: Optional[float] = None,
    gain: Optional[float] = None,
    print_diagnostics: bool = True,
) -> dict:
    """请求参数并返回后端实际协商值；不把 set() 返回值当作最终事实。"""
    requested = {
        "width": config.CAMERA_WIDTH if width is None else width,
        "height": config.CAMERA_HEIGHT if height is None else height,
        "fps": config.CAMERA_FPS if fps is None else fps,
        "fourcc": config.CAMERA_FOURCC if fourcc is None else fourcc,
        "auto_exposure": (
            config.CAMERA_AUTO_EXPOSURE
            if auto_exposure is None
            else auto_exposure
        ),
        "exposure": config.CAMERA_EXPOSURE if exposure is None else exposure,
        "gain": config.CAMERA_GAIN if gain is None else gain,
        "buffersize": 1,
    }

    if requested["fourcc"]:
        code = str(requested["fourcc"]).upper()
        if len(code) != 4:
            raise ValueError("camera FOURCC must contain exactly four characters")
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*code))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(requested["width"]))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(requested["height"]))
    cap.set(cv2.CAP_PROP_FPS, float(requested["fps"]))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    for name, prop in (
        ("auto_exposure", cv2.CAP_PROP_AUTO_EXPOSURE),
        ("exposure", cv2.CAP_PROP_EXPOSURE),
        ("gain", cv2.CAP_PROP_GAIN),
    ):
        value = requested[name]
        if value is not None:
            cap.set(prop, float(value))

    actual = camera_properties(cap)
    result = {"requested": requested, "actual": actual}
    mismatches = []
    for key in ("width", "height", "fps"):
        got = actual[key]
        want = float(requested[key])
        tolerance = 1.0 if key != "fps" else 0.5
        if got is not None and got > 0 and abs(got - want) > tolerance:
            mismatches.append(f"{key}: requested={want:g}, actual={got:g}")
    requested_fourcc = str(requested["fourcc"] or "").upper()
    if (
        requested_fourcc
        and actual["fourcc"] != "unknown"
        and actual["fourcc"].upper() != requested_fourcc
    ):
        mismatches.append(
            f"fourcc: requested={requested_fourcc}, actual={actual['fourcc']}"
        )
    result["mismatches"] = mismatches

    if print_diagnostics:
        print(
            "Camera actual: "
            f"backend={actual['backend']} "
            f"{actual['width'] or 0:.0f}x{actual['height'] or 0:.0f} "
            f"fps={actual['fps'] or 0:.2f} fourcc={actual['fourcc']} "
            f"buffersize={actual['buffersize']} exposure={actual['exposure']} "
            f"gain={actual['gain']} auto_exposure={actual['auto_exposure']}"
        )
        for mismatch in mismatches:
            print(f"Camera setting not negotiated: {mismatch}")
    return result


def gstreamer_available() -> bool:
    text = cv2.getBuildInformation()
    return any(
        "GStreamer" in line and "YES" in line.upper()
        for line in text.splitlines()
    )


def make_gstreamer_pipeline(
    index: int,
    width: int,
    height: int,
    fps: float,
    fourcc: str,
) -> str:
    device = f"/dev/video{int(index)}"
    if str(fourcc).upper() == "MJPG":
        source_caps = (
            f"image/jpeg,width={int(width)},height={int(height)},"
            f"framerate={int(round(fps))}/1 ! jpegdec"
        )
    else:
        source_caps = (
            f"video/x-raw,format=YUY2,width={int(width)},height={int(height)},"
            f"framerate={int(round(fps))}/1"
        )
    return (
        f"v4l2src device={device} ! {source_caps} ! videoconvert ! "
        "video/x-raw,format=BGR ! appsink drop=true max-buffers=1 sync=false"
    )


def backend_candidates(name: str, platform: Optional[str] = None) -> list[int]:
    platform = sys.platform if platform is None else platform
    normalized = name.lower()
    explicit = {
        "dshow": cv2.CAP_DSHOW,
        "msmf": cv2.CAP_MSMF,
        "v4l2": cv2.CAP_V4L2,
    }
    if normalized in explicit:
        return [explicit[normalized]]
    if normalized not in {"auto", "gstreamer"}:
        raise ValueError(f"unsupported camera backend: {name}")
    if normalized == "gstreamer":
        return [cv2.CAP_GSTREAMER]
    if platform.startswith("win"):
        return [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    if platform.startswith("linux"):
        return [cv2.CAP_V4L2, cv2.CAP_ANY]
    return [cv2.CAP_ANY]


def open_camera(
    index: int,
    *,
    backend: str = "auto",
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: Optional[float] = None,
    fourcc: Optional[str] = None,
):
    width = config.CAMERA_WIDTH if width is None else width
    height = config.CAMERA_HEIGHT if height is None else height
    fps = config.CAMERA_FPS if fps is None else fps
    fourcc = config.CAMERA_FOURCC if fourcc is None else fourcc

    if backend.lower() == "gstreamer":
        if not gstreamer_available():
            raise RuntimeError("OpenCV build does not report GStreamer support")
        source = make_gstreamer_pipeline(index, width, height, fps, fourcc)
        cap = cv2.VideoCapture(source, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(
                "GStreamer camera open failed; verify v4l2src/plugins and camera format"
            )
        configure_camera(
            cap,
            width=width,
            height=height,
            fps=fps,
            fourcc="",
        )
        return cap

    attempts = []
    for api in backend_candidates(backend):
        cap = cv2.VideoCapture(index, api)
        if cap.isOpened():
            configure_camera(
                cap,
                width=width,
                height=height,
                fps=fps,
                fourcc=fourcc,
            )
            return cap
        attempts.append(str(api))
        cap.release()
    raise RuntimeError(
        f"cannot open camera index={index}, backend={backend}, attempts={attempts}"
    )


@dataclass(frozen=True)
class LatestFrame:
    frame: np.ndarray
    timestamp: float
    sequence: int
    repeated: bool


class LatestFrameCamera:
    """独立线程持续读取，只保留最新一帧。"""

    def __init__(
        self,
        cap,
        *,
        failure_limit: int = config.CAMERA_READ_FAILURE_LIMIT,
        retry_delay_s: float = config.CAMERA_READ_RETRY_DELAY_S,
    ) -> None:
        self._cap = cap
        self._failure_limit = max(1, int(failure_limit))
        self._retry_delay_s = max(0.0, float(retry_delay_s))
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frame: Optional[np.ndarray] = None
        self._timestamp = 0.0
        self._sequence = 0
        self._capture_count = 0
        self._failed_reads = 0
        self._consecutive_failures = 0
        self._read_times_ms: deque[float] = deque(maxlen=1000)
        self._started_t: Optional[float] = None
        self._last_error: Optional[str] = None

    def start(self) -> "LatestFrameCamera":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop.clear()
        self._started_t = time.perf_counter()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="q1-camera-capture",
            daemon=True,
        )
        self._thread.start()
        return self

    def _capture_loop(self) -> None:
        while not self._stop.is_set():
            started = time.perf_counter()
            try:
                ok, frame = self._cap.read()
            except Exception as exc:
                ok, frame = False, None
                self._last_error = f"{type(exc).__name__}: {exc}"
            finished = time.perf_counter()
            read_ms = (finished - started) * 1000.0

            if not ok or frame is None:
                with self._condition:
                    self._failed_reads += 1
                    self._consecutive_failures += 1
                    if self._last_error is None:
                        self._last_error = "camera read failed"
                    self._condition.notify_all()
                if self._consecutive_failures >= self._failure_limit:
                    LOG.error(
                        "camera stopped after %d consecutive read failures",
                        self._consecutive_failures,
                    )
                    self._stop.set()
                    break
                self._stop.wait(self._retry_delay_s)
                continue

            timestamp = finished
            with self._condition:
                self._frame = frame
                self._timestamp = timestamp
                self._sequence += 1
                self._capture_count += 1
                self._consecutive_failures = 0
                self._read_times_ms.append(read_ms)
                self._last_error = None
                self._condition.notify_all()

    def read_latest(
        self,
        last_sequence: Optional[int] = None,
        *,
        wait_timeout: float = 0.0,
        copy_frame: bool = True,
    ) -> Optional[LatestFrame]:
        deadline = time.perf_counter() + max(0.0, wait_timeout)
        with self._condition:
            while (
                not self._stop.is_set()
                and (
                    self._frame is None
                    or (
                        last_sequence is not None
                        and self._sequence == last_sequence
                        and wait_timeout > 0
                    )
                )
            ):
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=remaining)
            if self._frame is None:
                return None
            repeated = last_sequence is not None and self._sequence == last_sequence
            frame = self._frame.copy() if copy_frame else self._frame
            return LatestFrame(frame, self._timestamp, self._sequence, repeated)

    def metrics(self) -> dict:
        now = time.perf_counter()
        with self._condition:
            elapsed = max(
                0.0,
                now - self._started_t if self._started_t is not None else 0.0,
            )
            values = np.asarray(self._read_times_ms, dtype=np.float64)
            return {
                "capture_fps": self._capture_count / elapsed if elapsed else 0.0,
                "captured_frames": self._capture_count,
                "failed_reads": self._failed_reads,
                "last_sequence": self._sequence,
                "read_ms_average": float(values.mean()) if values.size else 0.0,
                "read_ms_p50": float(np.percentile(values, 50)) if values.size else 0.0,
                "read_ms_p95": float(np.percentile(values, 95)) if values.size else 0.0,
                "read_ms_p99": float(np.percentile(values, 99)) if values.size else 0.0,
                "last_error": self._last_error,
                "thread_alive": bool(self._thread and self._thread.is_alive()),
            }

    def close(self, *, release: bool = True) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if release:
            try:
                self._cap.release()
            except Exception:
                LOG.exception("camera release failed")
        if self._thread is not None:
            self._thread.join(timeout=config.CAMERA_THREAD_JOIN_TIMEOUT_S)
            if self._thread.is_alive():
                LOG.error("camera capture thread did not stop within timeout")

    @property
    def thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())
