"""后台线程检测：主循环只负责读帧与显示，避免检测阻塞帧率"""

from __future__ import annotations

import threading
import time
from typing import Optional, Tuple

import numpy as np

from . import config
from .pipeline import run_pipeline
from .vision import PaperFrame, resize_for_live_detect


class LiveDetector:
    def __init__(self, hsv_ranges) -> None:
        self._hsv = hsv_ranges
        self._lock = threading.Lock()
        self._pending: Optional[np.ndarray] = None
        self._result: Optional[dict] = None
        self._overlay: Optional[np.ndarray] = None
        self._cached_paper: Optional[PaperFrame] = None
        self._cached_divider_y: Optional[float] = None
        self._paper_refresh_counter = 0
        self._stop = threading.Event()
        self._busy = False
        self._thread = threading.Thread(target=self._worker, name="q1-live-detect", daemon=True)
        self._thread.start()

    def submit(self, frame: np.ndarray) -> None:
        with self._lock:
            self._pending = frame

    def snapshot(self) -> Tuple[Optional[dict], Optional[np.ndarray]]:
        with self._lock:
            return self._result, self._overlay

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def _worker(self) -> None:
        last_detect_t = 0.0
        while not self._stop.is_set():
            frame = None
            with self._lock:
                if self._pending is not None:
                    frame = self._pending
                    self._pending = None

            if frame is None:
                time.sleep(0.003)
                continue

            now = time.perf_counter()
            if self._busy or now - last_detect_t < config.LIVE_DETECT_MIN_INTERVAL_S:
                continue
            last_detect_t = now
            self._busy = True

            try:
                self._paper_refresh_counter += 1
                refresh_paper = (
                    self._cached_paper is None
                    or self._paper_refresh_counter >= config.LIVE_PAPER_REFRESH
                )
                if refresh_paper:
                    self._paper_refresh_counter = 0

                small, _scale = resize_for_live_detect(frame, config.LIVE_DETECT_MAX_WIDTH)
                result = run_pipeline(
                    small,
                    self._hsv,
                    verbose=False,
                    live=True,
                    cached_paper=self._cached_paper,
                    refresh_paper=refresh_paper,
                    cached_divider_y=self._cached_divider_y,
                )
                if not result.get("ok"):
                    with self._lock:
                        self._result = result
                        self._overlay = None
                    continue

                self._cached_paper = result["paper"]
                self._cached_divider_y = result.get("divider_y_cm")

                with self._lock:
                    self._result = result
                    # 保持检测分辨率 overlay，显示时再放大，避免每帧全分辨率 copy
                    self._overlay = result["overlay"]
            finally:
                self._busy = False
