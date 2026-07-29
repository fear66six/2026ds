"""Latest-frame 后台检测；检测频率与摄像头显示频率解耦。"""

from __future__ import annotations

import copy
import logging
import threading
import time
from typing import Callable, Optional, Tuple

import cv2
import numpy as np

from . import config
from .pipeline import run_pipeline
from .vision import PaperFrame, resize_for_live_detect

LOG = logging.getLogger(__name__)


class LiveDetector:
    """只处理最新待检帧，不保留历史队列。"""

    def __init__(
        self,
        hsv_ranges,
        *,
        detector_fn: Optional[Callable] = None,
        min_interval_s: Optional[float] = None,
    ) -> None:
        self._hsv = hsv_ranges
        self._detector_fn = detector_fn or run_pipeline
        self._min_interval_s = (
            config.LIVE_DETECT_MIN_INTERVAL_S
            if min_interval_s is None
            else max(0.0, float(min_interval_s))
        )
        self._condition = threading.Condition()
        self._pending: Optional[Tuple[np.ndarray, float, int]] = None
        self._result: Optional[dict] = None
        self._result_monotonic: Optional[float] = None
        self._cached_paper: Optional[PaperFrame] = None
        self._cached_divider_y: Optional[float] = None
        self._paper_signature: Optional[np.ndarray] = None
        self._paper_last_refresh = 0.0
        self._force_paper_refresh = True
        self._stop = threading.Event()

        self._submitted_frames = 0
        self._processed_frames = 0
        self._dropped_frames = 0
        self._detect_total_s = 0.0
        self._last_detect_ms = 0.0
        self._first_detect_t: Optional[float] = None
        self._last_exception: Optional[str] = None

        self._thread = threading.Thread(
            target=self._worker,
            name="q1-live-detect",
            daemon=True,
        )
        self._thread.start()

    def submit(self, frame: np.ndarray, timestamp: Optional[float] = None) -> None:
        """提交引用；调用方在检测完成前不得原地修改该 ndarray。"""
        now = time.perf_counter() if timestamp is None else float(timestamp)
        with self._condition:
            self._submitted_frames += 1
            if self._pending is not None:
                self._dropped_frames += 1
            self._pending = (frame, now, self._submitted_frames)
            self._condition.notify()

    def force_refresh(self) -> None:
        with self._condition:
            self._force_paper_refresh = True
            self._condition.notify()

    def snapshot(self) -> Tuple[Optional[dict], dict]:
        """返回与工作线程隔离的结果副本和指标快照。"""
        now = time.perf_counter()
        with self._condition:
            result = copy.deepcopy(self._result)
            elapsed = (
                max(now - self._first_detect_t, 1e-9)
                if self._first_detect_t is not None
                else 0.0
            )
            metrics = {
                "submitted_frames": self._submitted_frames,
                "processed_frames": self._processed_frames,
                "dropped_frames": self._dropped_frames,
                "detect_fps": self._processed_frames / elapsed if elapsed else 0.0,
                "last_detect_ms": self._last_detect_ms,
                "average_detect_ms": (
                    self._detect_total_s * 1000.0 / self._processed_frames
                    if self._processed_frames
                    else 0.0
                ),
                "result_age_ms": (
                    max(0.0, (now - self._result_monotonic) * 1000.0)
                    if self._result_monotonic is not None
                    else float("inf")
                ),
                "last_exception": self._last_exception,
                "thread_alive": self._thread.is_alive(),
            }
        return result, metrics

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=config.CAMERA_THREAD_JOIN_TIMEOUT_S)
        if self._thread.is_alive():
            LOG.error("LiveDetector thread did not stop within timeout")

    @property
    def thread_alive(self) -> bool:
        return self._thread.is_alive()

    @staticmethod
    def _scene_signature(frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (32, 24), interpolation=cv2.INTER_AREA)

    def _needs_paper_refresh(self, frame: np.ndarray, now: float) -> tuple[bool, np.ndarray]:
        signature = self._scene_signature(frame)
        with self._condition:
            forced = self._force_paper_refresh
            self._force_paper_refresh = False
        changed = False
        if self._paper_signature is not None:
            changed = float(
                np.mean(
                    cv2.absdiff(signature, self._paper_signature)
                )
            ) >= config.LIVE_PAPER_CHANGE_THRESHOLD
        stale = now - self._paper_last_refresh >= config.LIVE_PAPER_MAX_AGE_S
        return self._cached_paper is None or forced or changed or stale, signature

    def _detect(self, frame: np.ndarray, refresh_paper: bool) -> dict:
        return self._detector_fn(
            frame,
            self._hsv,
            verbose=False,
            live=True,
            cached_paper=self._cached_paper,
            refresh_paper=refresh_paper,
            cached_divider_y=self._cached_divider_y,
            render_overlay=False,
        )

    @staticmethod
    def _structured_result(
        result: dict,
        *,
        frame_shape: tuple[int, ...],
        detect_timestamp: float,
        detect_duration_ms: float,
    ) -> dict:
        keys = (
            "ok",
            "error",
            "paper",
            "divider_y_cm",
            "pieces",
            "all_pieces",
            "lower_piece_count",
            "evaluation",
        )
        out = {key: result[key] for key in keys if key in result}
        out["detect_timestamp"] = detect_timestamp
        out["detect_duration_ms"] = detect_duration_ms
        out["detect_frame_shape"] = tuple(int(v) for v in frame_shape)
        return out

    def _worker(self) -> None:
        last_detect_t = 0.0
        while not self._stop.is_set():
            with self._condition:
                while self._pending is None and not self._stop.is_set():
                    self._condition.wait(timeout=0.05)
                if self._stop.is_set():
                    return

                wait_s = self._min_interval_s - (time.perf_counter() - last_detect_t)
                if wait_s > 0:
                    self._condition.wait(timeout=min(wait_s, 0.05))
                    continue

                pending = self._pending
                self._pending = None

            if pending is None:
                continue
            frame, _capture_timestamp, _sequence = pending
            small, _scale = resize_for_live_detect(
                frame, config.LIVE_DETECT_MAX_WIDTH
            )
            started = time.perf_counter()
            refresh_paper, signature = self._needs_paper_refresh(small, started)
            detect_timestamp = time.time()

            try:
                raw = self._detect(small, refresh_paper)
                finished = time.perf_counter()
                duration_ms = (finished - started) * 1000.0
                structured = self._structured_result(
                    raw,
                    frame_shape=small.shape,
                    detect_timestamp=detect_timestamp,
                    detect_duration_ms=duration_ms,
                )

                if raw.get("ok"):
                    self._cached_paper = raw["paper"]
                    self._cached_divider_y = raw.get("divider_y_cm")
                    if refresh_paper:
                        self._paper_signature = signature
                        self._paper_last_refresh = finished

                with self._condition:
                    if self._first_detect_t is None:
                        self._first_detect_t = started
                    self._processed_frames += 1
                    self._detect_total_s += finished - started
                    self._last_detect_ms = duration_ms
                    self._last_exception = None
                    self._result = structured
                    self._result_monotonic = finished
                last_detect_t = started
            except Exception as exc:
                finished = time.perf_counter()
                duration_ms = (finished - started) * 1000.0
                LOG.exception("Q1 live detector failed")
                with self._condition:
                    if self._first_detect_t is None:
                        self._first_detect_t = started
                    self._processed_frames += 1
                    self._detect_total_s += finished - started
                    self._last_detect_ms = duration_ms
                    self._last_exception = f"{type(exc).__name__}: {exc}"
                    self._result = self._structured_result(
                        {"ok": False, "error": self._last_exception},
                        frame_shape=small.shape,
                        detect_timestamp=detect_timestamp,
                        detect_duration_ms=duration_ms,
                    )
                    self._result_monotonic = finished
                last_detect_t = started
