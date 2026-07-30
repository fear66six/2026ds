"""Q1 adapter: K230 TTL snapshot camera exposing SnapshotCamera-compatible API."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

from .camera import frame_quality
from .models import Snapshot

_DRIVER = (
    Path(__file__).resolve().parents[1]
    / "drivers"
    / "k230_ttl_camera"
    / "jetson"
)
if str(_DRIVER) not in sys.path:
    sys.path.insert(0, str(_DRIVER))

from protocol import DEFAULT_TTL_BY_ID, HEIGHT, WIDTH  # noqa: E402


class K230TtlQ1Camera:
    """Wraps production K230TtlSnapshotCamera for Q1 controller interface.

    Does not accept width/height/baud overrides. Preview is a still snapshot.
    """

    def __init__(
        self,
        port: str = DEFAULT_TTL_BY_ID,
        *,
        output_dir: Path | None = None,
        stabilization_s: float = 0.0,
    ) -> None:
        self.port = port
        self.output_dir = output_dir
        self.stabilization_s = stabilization_s
        self._cam = None
        self._preview: np.ndarray | None = None

    def open(self) -> None:
        from k230_camera import K230TtlSnapshotCamera

        self._cam = K230TtlSnapshotCamera(port=self.port)
        self._cam.initialize()
        if not self._cam.health_check():
            raise RuntimeError("CAPTURE_FAILED: K230 TTL health_check failed")

    def read_preview(self) -> np.ndarray | None:
        if self._cam is None:
            raise RuntimeError("CAPTURE_FAILED: K230 TTL camera is not open")
        # Still capture used as preview — not a live video stream.
        # Never return a previous frame on failure (no stale-frame fallback).
        self._preview = self._cam.capture_snapshot()
        return self._preview

    def capture_snapshot(self, cycle_index: int) -> Snapshot:
        if self._cam is None:
            raise RuntimeError("CAPTURE_FAILED: K230 TTL camera is not open")
        if self.stabilization_s > 0:
            time.sleep(self.stabilization_s)
        start = time.perf_counter()
        frame = self._cam.capture_snapshot()
        meta = self._cam.last_meta
        metrics = frame_quality([frame])[0]
        path = ""
        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            target = self.output_dir / f"cycle_{cycle_index:02d}_raw.png"
            cv2.imwrite(str(target), frame)
            path = str(target)
        timing = {
            "capture_burst_ms": (time.perf_counter() - start) * 1000.0,
            "select_best_frame_ms": 0.0,
            "k230_ttl": None if meta is None else meta.__dict__,
            "image_size": [WIDTH, HEIGHT],
        }
        return Snapshot(
            frame,
            time.time(),
            metrics["sharpness"],
            metrics["brightness"],
            metrics["motion_score"],
            path,
            timing,
        )

    def close(self) -> None:
        if self._cam is not None:
            self._cam.close()
            self._cam = None
