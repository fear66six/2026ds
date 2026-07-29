#!/usr/bin/env python3
"""Run Q1 camera benchmarks without importing or accessing unrelated hardware."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
Q1_ROOT = PROJECT_ROOT / "2026E"
sys.path.insert(0, str(Q1_ROOT))

from q1 import config  # noqa: E402
from q1.camera_benchmark import run_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("capture_only", "capture_display", "capture_display_detect"),
    )
    parser.add_argument("--camera-index", type=int, default=config.CAMERA_INDEX)
    parser.add_argument(
        "--camera-backend",
        choices=("auto", "dshow", "msmf", "v4l2", "gstreamer"),
        default=config.CAMERA_BACKEND,
    )
    parser.add_argument("--camera-width", type=int, default=config.CAMERA_WIDTH)
    parser.add_argument("--camera-height", type=int, default=config.CAMERA_HEIGHT)
    parser.add_argument("--camera-fps", type=float, default=config.CAMERA_FPS)
    parser.add_argument("--camera-fourcc", default=config.CAMERA_FOURCC)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--opencv-threads", type=int)
    args = parser.parse_args()

    if args.opencv_threads is not None:
        if args.opencv_threads < 1:
            parser.error("--opencv-threads must be >= 1")
        import cv2

        cv2.setNumThreads(args.opencv_threads)

    run_benchmark(
        camera_index=args.camera_index,
        backend=args.camera_backend,
        width=args.camera_width,
        height=args.camera_height,
        fps=args.camera_fps,
        fourcc=args.camera_fourcc,
        mode=args.mode,
        frames=args.frames,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
