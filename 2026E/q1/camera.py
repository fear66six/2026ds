"""低负载预览和突发静态抓图；完整分析不在视频帧循环中运行。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .models import Snapshot


def frame_quality(frames: list[np.ndarray]) -> list[dict[str, float]]:
    if not frames:
        return []
    grays = [cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) for frame in frames]
    result: list[dict[str, float]] = []
    for index, gray in enumerate(grays):
        motion = 0.0 if index == 0 else float(cv2.mean(cv2.absdiff(gray, grays[index - 1]))[0])
        result.append(
            {
                "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
                "brightness": float(cv2.mean(gray)[0]),
                "highlight_ratio": float(np.mean(gray >= 250)),
                "dark_ratio": float(np.mean(gray <= 15)),
                "motion_score": motion,
            }
        )
    return result


def select_best_frame(frames: list[np.ndarray]) -> tuple[int, list[dict[str, float]]]:
    metrics = frame_quality(frames)
    if not metrics:
        raise RuntimeError("CAPTURE_FAILED: 没有可用帧")
    scores = np.array(
        [
            m["sharpness"]
            - 2.0 * m["motion_score"]
            - 500.0 * (m["highlight_ratio"] + m["dark_ratio"])
            for m in metrics
        ],
        dtype=np.float64,
    )
    return int(np.argmax(scores)), metrics


class SnapshotCamera:
    def __init__(
        self,
        index: int,
        *,
        burst: int = 8,
        settle_ms: int = 200,
        output_dir: Path | None = None,
        backend: int | None = None,
    ) -> None:
        self.index = index
        self.burst = burst
        self.settle_ms = settle_ms
        self.output_dir = output_dir
        self.backend = backend
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> None:
        if self._capture is not None and self._capture.isOpened():
            return
        self._capture = cv2.VideoCapture(self.index) if self.backend is None else cv2.VideoCapture(self.index, self.backend)
        if not self._capture.isOpened():
            raise RuntimeError("CAPTURE_FAILED: 摄像头无法打开")
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read_preview(self) -> np.ndarray | None:
        if self._capture is None:
            return None
        ok, frame = self._capture.read()
        return frame if ok else None

    def capture_snapshot(self, cycle_index: int) -> Snapshot:
        if self._capture is None:
            raise RuntimeError("CAPTURE_FAILED: 摄像头尚未打开")
        capture_started = time.perf_counter()
        for _ in range(3):
            self._capture.grab()
        time.sleep(self.settle_ms / 1000.0)
        frames: list[np.ndarray] = []
        for _ in range(self.burst):
            ok, frame = self._capture.read()
            if ok and frame is not None:
                frames.append(frame)
        select_started = time.perf_counter()
        index, metrics = select_best_frame(frames)
        select_ms = (time.perf_counter() - select_started) * 1000.0
        frame = frames[index]
        path = ""
        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            target = self.output_dir / f"cycle_{cycle_index:02d}_raw.png"
            cv2.imwrite(str(target), frame)
            path = str(target)
        m = metrics[index]
        return Snapshot(
            frame,
            time.time(),
            m["sharpness"],
            m["brightness"],
            m["motion_score"],
            path,
            {
                "capture_burst_ms": (time.perf_counter() - capture_started) * 1000.0,
                "select_best_frame_ms": select_ms,
            },
        )

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class StaticImageCamera:
    """离线图和仿真均通过同一个 Snapshot 接口进入控制器。"""

    def __init__(self, supplier: Callable[[int], tuple[np.ndarray, dict]], output_dir: Path | None = None) -> None:
        self.supplier = supplier
        self.output_dir = output_dir
        self.capture_count = 0

    def open(self) -> None:
        return None

    def read_preview(self) -> np.ndarray | None:
        frame, _ = self.supplier(-1)
        return frame

    def capture_snapshot(self, cycle_index: int) -> Snapshot:
        start = time.perf_counter()
        frame, metadata = self.supplier(cycle_index)
        select_started = time.perf_counter()
        index, metrics = select_best_frame([frame])
        metadata["select_best_frame_ms"] = (time.perf_counter() - select_started) * 1000.0
        del index
        self.capture_count += 1
        path = ""
        if self.output_dir:
            cycle_dir = self.output_dir / f"cycle_{cycle_index:02d}"
            cycle_dir.mkdir(parents=True, exist_ok=True)
            target = cycle_dir / "raw.png"
            cv2.imwrite(str(target), frame)
            path = str(target)
        m = metrics[0]
        metadata["capture_burst_ms"] = (time.perf_counter() - start) * 1000.0
        return Snapshot(frame.copy(), time.time(), m["sharpness"], m["brightness"], m["motion_score"], path, metadata)

    def close(self) -> None:
        return None
