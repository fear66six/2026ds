"""第一问摄像头：实时检测监测"""

from __future__ import annotations

import time
from typing import Callable, Optional

import cv2
import numpy as np

from . import config
from .live_detect import LiveDetector

WIN = "Q1 Camera"


def _draw_status_inplace(frame: np.ndarray, lines: list[str]) -> None:
    y = 24
    for line in lines:
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 3)
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1)
        y += 24


def _to_display(frame: np.ndarray, overlay: np.ndarray | None) -> np.ndarray:
    """缩放到显示尺寸；overlay 为检测分辨率时直接放大，不做全图 intermediate copy"""
    fh, fw = frame.shape[:2]
    dw = max(1, int(fw * config.DISPLAY_SCALE))
    dh = max(1, int(fh * config.DISPLAY_SCALE))
    src = overlay if overlay is not None else frame
    if src.shape[0] == fh and src.shape[1] == fw:
        return cv2.resize(src, (dw, dh), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(src, (dw, dh), interpolation=cv2.INTER_LINEAR)


def _show(frame: np.ndarray, title: str = WIN) -> int:
    cv2.imshow(title, frame)
    return cv2.waitKey(1) & 0xFF


def configure_camera(cap: cv2.VideoCapture) -> None:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)


def run_camera_q1(
    cap: cv2.VideoCapture,
    pipeline_fn: Callable,
    hsv_ranges,
    *,
    on_run: Optional[Callable[[dict, object], None]] = None,
) -> None:
    """
    实时监测：后台线程检测，主循环只读帧+显示
    按键:
      空格 - 4/4 且拼合通过时触发 on_run（如动画/执行）
      S    - 保存当前 overlay
      Q/ESC - 退出
    """
    configure_camera(cap)
    detector = LiveDetector(hsv_ranges)
    last_frame = None
    fps = 0.0
    fps_t = time.perf_counter()
    disp_buf: np.ndarray | None = None

    print("\n=== 第一问 实时监测 ===")
    print("实时显示检测数 4/4 | 空格=确认执行/动画 | S=保存 | Q=退出\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("无法读取摄像头画面")
                break

            last_frame = frame
            detector.submit(frame)
            last_result, last_overlay = detector.snapshot()

            now = time.perf_counter()
            dt = now - fps_t
            fps_t = now
            if dt > 0:
                fps = fps * 0.85 + (1.0 / dt) * 0.15

            disp = _to_display(frame, last_overlay if last_result and last_result.get("ok") else None)
            if disp_buf is None or disp_buf.shape != disp.shape:
                disp_buf = disp
            else:
                np.copyto(disp_buf, disp)

            if last_overlay is not None and last_result and last_result.get("ok"):
                n = len(last_result["pieces"])
                ev = last_result["evaluation"]
                ok = ev.get("assembly_ok", False)
                lower = last_result.get("lower_piece_count", 0)
                extra = f" ({lower} below)" if lower and n < 4 else ""
                status = (
                    f"[Q1] {n}/4 upper{extra}  "
                    f"{'OK' if ok and n == 4 else 'wait'}  FPS={fps:.0f}"
                )
                hint = f"Space={'GO' if ok and n == 4 else 'need 4'}  S=save  Q=quit"
                _draw_status_inplace(disp_buf, [status, hint])
            else:
                err = (last_result or {}).get("error", "detecting...")
                _draw_status_inplace(disp_buf, [f"[Q1] detecting... FPS={fps:.0f}", str(err)[:36]])

            key = _show(disp_buf)
            if key in (ord("q"), ord("Q"), 27):
                break

            if key in (ord("s"), ord("S")) and last_overlay is not None:
                cv2.imwrite("q1_camera_result.png", last_overlay)
                print("已保存: q1_camera_result.png")

            if key == ord(" ") and last_result and last_result.get("ok"):
                n = len(last_result["pieces"])
                ev = last_result["evaluation"]
                if n == 4 and ev.get("assembly_ok") and on_run and last_frame is not None:
                    full = pipeline_fn(last_frame, hsv_ranges, verbose=False)
                    if full.get("ok"):
                        on_run(full, last_frame)
                elif n != 4:
                    print(f"当前 {n}/4 片，请调整摆放")
    finally:
        detector.close()
        cv2.destroyAllWindows()
