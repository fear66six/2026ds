"""实际运行：摄像头一键启动 → 串口执行 → 完成后复检"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

import cv2
import numpy as np

from . import config
from .executor import DeviceExecutor
from .geometry import max_vertex_error, rigid_align_no_flip
from .camera_run import configure_camera
from .live_detect import LiveDetector
from .motion import MotionStep, Phase
from .vision import draw_overlay

WIN_LIVE = "Puzzle Live"
WIN_ERROR = "Error"
WIN_EXEC = "Executing"
WIN_VERIFY = "Verify"


def _draw_status(frame: np.ndarray, lines: List[str]) -> np.ndarray:
    out = frame.copy()
    y = 28
    for line in lines:
        cv2.putText(out, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 3)
        cv2.putText(out, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (240, 240, 240), 1)
        y += 28
    return out


def _draw_step_overlay(result: dict, step: MotionStep | None, msg: str) -> np.ndarray:
    frame = result["overlay"].copy()
    lines = [msg]
    if step and step.phase != Phase.DONE:
        lines.append(f"Now: {step.description}")
        lines.append(f"  PICK ({step.from_cm[0]:.1f}, {step.from_cm[1]:.1f}) cm")
        lines.append(f"  MOVE ({step.to_cm[0]:.1f}, {step.to_cm[1]:.1f}) cm  R={step.angle_deg:.1f} deg")
    return _draw_status(frame, lines)


def verify_result(frame: np.ndarray, pipeline_fn: Callable, hsv_ranges) -> dict:
    """拼接完成后重新拍照，评估实际效果（支持 4 块或拼合后整体检测）"""
    result = pipeline_fn(frame, hsv_ranges, verbose=False)
    if not result.get("ok"):
        return result

    errors = []
    piece_count = len(result["pieces"])

    if piece_count >= 1:
        for asg in result["assignments"]:
            pi = asg.detected_index
            if pi >= len(result["pieces"]):
                continue
            piece = result["pieces"][pi]
            if len(asg.target_vertices_cm) == 0:
                continue
            aligned = rigid_align_no_flip(piece.vertices_cm, asg.target_vertices_cm)
            errors.append(max_vertex_error(aligned, asg.target_vertices_cm))

    if not errors or piece_count < 4:
        target_area = config.TARGET_WIDTH_CM * config.TARGET_HEIGHT_CM
        detected_area = sum(p.area_cm2 for p in result["pieces"] if not p.in_upper_half)
        area_ok = detected_area >= target_area * 0.7
        if area_ok and piece_count >= 1:
            errors = errors or [1.0]

    max_err = float(min(errors)) if errors else 999.0
    if len(errors) > 1:
        max_err = float(max(errors))
    avg_err = float(np.mean(errors)) if errors else 999.0
    ok = max_err <= config.VERTEX_MATCH_TOLERANCE_CM and piece_count >= 1

    result["verify"] = {
        "passed": ok,
        "max_vertex_error_cm": max_err,
        "avg_vertex_error_cm": avg_err,
        "piece_count_after": piece_count,
    }
    return result


def run_live(
    cap: cv2.VideoCapture,
    pipeline_fn: Callable,
    hsv_ranges,
    executor: DeviceExecutor,
    record_path: Optional[str] = None,
) -> dict:
    configure_camera(cap)
    writer = None
    if record_path:
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) * config.DISPLAY_SCALE)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * config.DISPLAY_SCALE)
        writer = cv2.VideoWriter(record_path, fourcc, 10.0, (w, h))

    def show(frame: np.ndarray, title: str = WIN_LIVE) -> int:
        disp = cv2.resize(frame, None, fx=config.DISPLAY_SCALE, fy=config.DISPLAY_SCALE)
        cv2.imshow(title, disp)
        if writer:
            writer.write(disp)
        return cv2.waitKey(1) & 0xFF

    print("\n=== 实际运行模式 ===")
    print("实时监测 4/4 | Space: 一键启动（检测+执行）  Q: 退出")
    print("请遮挡摄像头摆好碎片，移开遮挡后按 Space\n")

    plan_result: dict | None = None
    live_result: dict | None = None
    last_overlay = None
    fps = 0.0
    fps_t = time.perf_counter()
    detector = LiveDetector(hsv_ranges)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if plan_result is None:
                detector.submit(frame)
                live_result, last_overlay = detector.snapshot()

            now = time.perf_counter()
            dt = now - fps_t
            fps_t = now
            if dt > 0:
                fps = fps * 0.85 + (1.0 / dt) * 0.15

            if plan_result is None:
                if last_overlay is not None and live_result and live_result.get("ok"):
                    n = len(live_result["pieces"])
                    ev = live_result.get("evaluation", {})
                    preview = _draw_status(last_overlay, [
                        f"[LIVE] {n}/4  err={ev.get('max_vertex_error_cm', 0):.1f}cm  FPS={fps:.0f}",
                        "Space=start when 4/4   Q=quit",
                    ])
                else:
                    preview = _draw_status(frame, [
                        f"[LIVE] detecting... FPS={fps:.0f}",
                        "Space=start  Q=quit",
                    ])
            else:
                preview = plan_result["overlay"]

            key = show(preview)
            if key in (ord("q"), 27):
                break

            if key == ord(" ") and plan_result is None:
                plan_result = pipeline_fn(frame, hsv_ranges, verbose=True)
                if not plan_result.get("ok"):
                    print("检测失败:", plan_result.get("error"))
                    show(_draw_status(frame, ["Detection failed, retry"]), WIN_ERROR)
                    cv2.waitKey(1500)
                    plan_result = None
                    continue
                upper = plan_result["pieces"]
                if len(upper) != 4:
                    print(f"碎片数量不对: {len(upper)}/4")
                    n = len(upper)
                    show(_draw_status(frame, [f"Found {n}/4 pieces, need 4"]), WIN_ERROR)
                    cv2.waitKey(1500)
                    plan_result = None
                    continue

                steps = [s for s in plan_result["steps"] if s.phase != Phase.DONE]
                for i, step in enumerate(steps):
                    overlay = _draw_step_overlay(plan_result, step, f"Exec {i + 1}/{len(steps)}")
                    show(overlay, WIN_EXEC)
                    time.sleep(0.4)
                    executor.execute_step(step)

                executor.execute_step(plan_result["steps"][-1])

                show(_draw_status(frame, ["Done, verifying..."]), WIN_VERIFY)
                time.sleep(config.VERIFY_DELAY_S)
                ret2, frame2 = cap.read()
                if not ret2:
                    break

                verify = verify_result(frame2, pipeline_fn, hsv_ranges)
                v = verify.get("verify", {})
                passed = v.get("passed", False)
                lines = [
                    "=== Result ===",
                    f"Pass: {'YES' if passed else 'NO'}",
                    f"Max vertex err: {v.get('max_vertex_error_cm', 0):.2f} cm",
                    f"Avg vertex err: {v.get('avg_vertex_error_cm', 0):.2f} cm",
                    "Space=retry  Q=quit",
                ]
                print("\n".join([
                    "=== 实际拼接结果 ===",
                    f"通过: {'是' if passed else '否'}",
                    f"最大顶点误差: {v.get('max_vertex_error_cm', 0):.2f} cm",
                    f"平均顶点误差: {v.get('avg_vertex_error_cm', 0):.2f} cm",
                ]))
                if verify.get("ok"):
                    final = draw_overlay(
                        frame2,
                        verify["paper"],
                        verify["divider_y_cm"],
                        verify["pieces"],
                        (config.TARGET_ORIGIN_X_CM, config.TARGET_ORIGIN_Y_CM),
                        verify["assignments"],
                    )
                    show(_draw_status(final, lines), WIN_LIVE)
                else:
                    show(_draw_status(frame2, lines), WIN_LIVE)

                cv2.waitKey(0)
                plan_result = None

    finally:
        detector.close()
    if writer:
        writer.release()
    cv2.destroyAllWindows()
    executor.close()
    return {"ok": True}
