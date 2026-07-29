"""第一问摄像头：当前帧显示与低频后台检测解耦。"""

from __future__ import annotations

import time
from typing import Callable, Optional

import cv2
import numpy as np

from . import config
from .camera_source import (
    LatestFrameCamera,
    configure_camera as _configure_camera,
)
from .live_detect import LiveDetector
from .vision import PaperFrame, draw_overlay_live

WIN = "Q1 Camera"


def _draw_status_inplace(frame: np.ndarray, lines: list[str]) -> None:
    y = 24
    for line in lines:
        cv2.putText(
            frame,
            line,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (20, 20, 20),
            3,
        )
        cv2.putText(
            frame,
            line,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (240, 240, 240),
            1,
        )
        y += 24


def configure_camera(cap: cv2.VideoCapture, **kwargs) -> dict:
    """兼容旧入口；实际配置与协商值诊断由 camera_source 统一实现。"""
    return _configure_camera(cap, **kwargs)


def _scaled_paper_for_frame(
    result: dict,
    target_shape: tuple[int, ...],
) -> Optional[PaperFrame]:
    shape = result.get("detect_frame_shape")
    paper = result.get("paper")
    if not shape or paper is None or len(shape) < 2:
        return None
    source_h, source_w = int(shape[0]), int(shape[1])
    target_h, target_w = int(target_shape[0]), int(target_shape[1])
    if min(source_h, source_w, target_h, target_w) <= 0:
        return None
    source_aspect = source_w / source_h
    target_aspect = target_w / target_h
    if abs(source_aspect - target_aspect) / max(source_aspect, 1e-9) > 0.01:
        return None
    scale_x = target_w / source_w
    scale_y = target_h / source_h
    corners = paper.corners_px.astype(np.float32).copy()
    corners[:, 0] *= scale_x
    corners[:, 1] *= scale_y
    return PaperFrame(
        corners_px=corners,
        px_per_cm=float(paper.px_per_cm) * (scale_x + scale_y) * 0.5,
        divider_y_cm=float(paper.divider_y_cm),
        landscape_in_image=bool(paper.landscape_in_image),
    )


def render_live_result(
    current_frame: np.ndarray,
    result: Optional[dict],
) -> tuple[np.ndarray, bool]:
    """始终以 current_frame 为底图；尺寸不兼容时忽略旧检测坐标。"""
    if not result or not result.get("ok"):
        return current_frame.copy(), False
    paper = _scaled_paper_for_frame(result, current_frame.shape)
    if paper is None:
        return current_frame.copy(), False
    preview = draw_overlay_live(
        current_frame,
        paper,
        float(result.get("divider_y_cm", config.DIVIDER_Y_CM)),
        result.get("pieces", []),
        (config.TARGET_ORIGIN_X_CM, config.TARGET_ORIGIN_Y_CM),
        all_pieces=result.get("all_pieces"),
    )
    return preview, True


def _to_display(frame: np.ndarray) -> np.ndarray:
    fh, fw = frame.shape[:2]
    dw = max(1, int(fw * config.DISPLAY_SCALE))
    dh = max(1, int(fh * config.DISPLAY_SCALE))
    return cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_LINEAR)


def _show(frame: np.ndarray, title: str = WIN) -> int:
    cv2.imshow(title, frame)
    return cv2.waitKey(1) & 0xFF


def run_camera_q1(
    cap: cv2.VideoCapture,
    pipeline_fn: Callable,
    hsv_ranges,
    *,
    on_run: Optional[Callable[[dict, object], None]] = None,
    use_threaded_capture: bool = True,
) -> None:
    """
    实时监测：采集、显示和检测相互解耦。

    空格运行完整 pipeline；S 保存当前帧上的实时标注；Q/ESC 退出。
    """
    configure_camera(cap)
    detector = LiveDetector(hsv_ranges)
    camera = LatestFrameCamera(cap).start() if use_threaded_capture else None
    last_frame = None
    last_sequence: Optional[int] = None
    sync_capture_count = 0
    sync_capture_t = time.perf_counter()
    display_fps = 0.0
    display_t = time.perf_counter()

    print("\n=== 第一问 实时监测 ===")
    print("当前画面持续刷新；检测结果低频更新 | 空格=完整检测 | S=保存 | Q=退出\n")

    try:
        while True:
            capture_timestamp = time.perf_counter()
            if camera is not None:
                latest = camera.read_latest(
                    last_sequence,
                    wait_timeout=0.05,
                    copy_frame=True,
                )
                if latest is None:
                    if not camera.thread_alive:
                        print("摄像头采集线程已停止:", camera.metrics().get("last_error"))
                        break
                    continue
                if latest.repeated:
                    continue
                frame = latest.frame
                capture_timestamp = latest.timestamp
                last_sequence = latest.sequence
                capture_metrics = camera.metrics()
                capture_fps = capture_metrics["capture_fps"]
            else:
                ret, frame = cap.read()
                if not ret:
                    print("无法读取摄像头画面")
                    break
                sync_capture_count += 1
                elapsed = time.perf_counter() - sync_capture_t
                capture_fps = sync_capture_count / elapsed if elapsed else 0.0

            last_frame = frame
            detector.submit(frame, capture_timestamp)
            last_result, detect_metrics = detector.snapshot()
            preview, coordinates_valid = render_live_result(frame, last_result)

            now = time.perf_counter()
            dt = now - display_t
            display_t = now
            if dt > 0:
                display_fps = display_fps * 0.85 + (1.0 / dt) * 0.15

            n = len(last_result.get("pieces", [])) if last_result else 0
            ev = last_result.get("evaluation", {}) if last_result else {}
            ok = bool(ev.get("assembly_ok", False))
            result_age = detect_metrics["result_age_ms"]
            age_text = f"{result_age:.0f}" if np.isfinite(result_age) else "-"
            lines = [
                (
                    f"CAP {capture_fps:.1f}  DISPLAY {display_fps:.1f}  "
                    f"DETECT {detect_metrics['detect_fps']:.1f}"
                ),
                (
                    f"DETECT {detect_metrics['last_detect_ms']:.0f} ms  "
                    f"RESULT AGE {age_text} ms  PIECES {n}/4"
                ),
                f"Space={'GO' if ok and n == 4 else 'need 4'}  S=save  Q=quit",
            ]
            if last_result and not last_result.get("ok"):
                lines.append(str(last_result.get("error", "detecting..."))[:48])
            elif last_result and not coordinates_valid:
                lines.append("Detection coordinates ignored: frame shape changed")

            disp = _to_display(preview)
            _draw_status_inplace(disp, lines)
            key = _show(disp)
            if key in (ord("q"), ord("Q"), 27):
                break

            if key in (ord("s"), ord("S")):
                cv2.imwrite("q1_camera_result.png", preview)
                print("已保存当前帧标注: q1_camera_result.png")

            if key == ord(" ") and last_result and last_result.get("ok"):
                if n == 4 and ok and on_run and last_frame is not None:
                    full = pipeline_fn(last_frame, hsv_ranges, verbose=False)
                    if full.get("ok"):
                        on_run(full, last_frame)
                elif n != 4:
                    print(f"当前 {n}/4 片，请调整摆放")
    finally:
        if camera is not None:
            camera.close(release=True)
        detector.close()
        cv2.destroyAllWindows()
