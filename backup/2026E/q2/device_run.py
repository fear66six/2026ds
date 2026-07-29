"""第二问现场运行（1~4 片，可变目标矩形）"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

import cv2
import numpy as np

from .executor import DeviceExecutor
from .geometry import max_vertex_error, rigid_align_no_flip
from .motion import MotionStep, Phase

from . import config
from .overlay import draw_overlay_q2

WIN_LIVE = "Q2 Puzzle Live"
WIN_ERROR = "Q2 Error"
WIN_EXEC = "Q2 Executing"
WIN_VERIFY = "Q2 Verify"


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


def verify_result_q2(frame: np.ndarray, pipeline_fn: Callable, hsv_ranges) -> dict:
    result = pipeline_fn(frame, hsv_ranges, verbose=False)
    if not result.get("ok"):
        return result

    errors = []
    for asg in result["assignments"]:
        pi = asg.detected_index
        if pi >= len(result["pieces"]):
            continue
        piece = result["pieces"][pi]
        if len(asg.target_vertices_cm) == 0:
            continue
        aligned = rigid_align_no_flip(piece.vertices_cm, asg.target_vertices_cm)
        errors.append(max_vertex_error(aligned, asg.target_vertices_cm))

    tw, th = result["target_size"]
    target_area = tw * th
    detected_area = sum(p.area_cm2 for p in result["pieces"] if not p.in_upper_half)
    area_ok = detected_area >= target_area * 0.65
    max_err = float(max(errors)) if errors else 999.0
    piece_count = len(result["pieces"])
    ok = max_err <= config.VERTEX_MATCH_TOLERANCE_CM and piece_count >= 1 and area_ok

    result["verify"] = {
        "passed": ok,
        "max_vertex_error_cm": max_err,
        "avg_vertex_error_cm": float(np.mean(errors)) if errors else 999.0,
        "piece_count_after": piece_count,
    }
    return result


def run_live_q2(
    cap: cv2.VideoCapture,
    pipeline_fn: Callable,
    hsv_ranges,
    executor: DeviceExecutor,
    record_path: Optional[str] = None,
) -> dict:
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

    print("\n=== 第二问 实际运行模式 ===")
    print("Space: 一键启动  Q: 退出")
    print("现场 1~4 片未知碎片，目标矩形自动推断\n")

    plan_result: dict | None = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if plan_result is None:
            preview = _draw_status(frame, [
                "[Q2 LIVE] Press Space to start",
                "Place 1-4 pieces -> remove cover -> Space",
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

            n = len(plan_result["pieces"])
            if n < config.MIN_PIECES or n > config.MAX_PIECES:
                print(f"碎片数量: {n} (需要 {config.MIN_PIECES}~{config.MAX_PIECES})")
                show(_draw_status(frame, [f"Found {n} pieces, need 1-4"]), WIN_ERROR)
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

            verify = verify_result_q2(frame2, pipeline_fn, hsv_ranges)
            v = verify.get("verify", {})
            passed = v.get("passed", False)
            lines = [
                "=== Q2 Result ===",
                f"Pass: {'YES' if passed else 'NO'}",
                f"Max vertex err: {v.get('max_vertex_error_cm', 0):.2f} cm",
                f"Pieces: {v.get('piece_count_after', 0)}",
                "Space=retry  Q=quit",
            ]
            print("\n".join([
                "=== 第二问拼接结果 ===",
                f"通过: {'是' if passed else '否'}",
                f"最大顶点误差: {v.get('max_vertex_error_cm', 0):.2f} cm",
            ]))
            if verify.get("ok"):
                final = draw_overlay_q2(
                    frame2,
                    verify["paper"],
                    verify["divider_y_cm"],
                    verify["pieces"],
                    verify["target_origin"],
                    verify["target_size"],
                    verify["assignments"],
                )
                show(_draw_status(final, lines), WIN_LIVE)
            else:
                show(_draw_status(frame2, lines), WIN_LIVE)

            cv2.waitKey(0)
            plan_result = None

    if writer:
        writer.release()
    cv2.destroyAllWindows()
    executor.close()
    return {"ok": True}
