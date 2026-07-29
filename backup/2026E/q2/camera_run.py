"""第二问摄像头识别：实时预览 → 按键检测 → 显示拼合结果（无需串口）"""

from __future__ import annotations

from typing import Callable, Optional

import cv2

from . import config


WIN = "Q2 Camera"


def _draw_status(frame, lines: list[str]):
    out = frame.copy()
    y = 28
    for line in lines:
        cv2.putText(out, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 3)
        cv2.putText(out, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (240, 240, 240), 1)
        y += 28
    return out


def _show(frame, title: str = WIN) -> int:
    disp = cv2.resize(frame, None, fx=config.DISPLAY_SCALE, fy=config.DISPLAY_SCALE)
    cv2.imshow(title, disp)
    return cv2.waitKey(1) & 0xFF


def _print_result(result: dict) -> None:
    tw, th = result["target_size"]
    ev = result["evaluation"]
    print("\n========== 摄像头识别结果 ==========")
    print(f"碎片: {len(result['pieces'])}  求解器: {result['solver']}")
    print(f"目标矩形: {tw:.2f} x {th:.2f} cm")
    print(f"拼合: {'通过' if ev['assembly_ok'] else '未通过'}")
    print(f"最大顶点误差: {ev['max_vertex_error_cm']:.2f} cm")


def run_camera_q2(
    cap: cv2.VideoCapture,
    pipeline_fn: Callable,
    hsv_ranges,
    *,
    on_success: Optional[Callable[[dict, object], None]] = None,
) -> None:
    """
    按键:
      空格 - 对当前画面检测拼合
      A    - 播放拼合动画（需先检测成功）
      S    - 保存 overlay 为 q2_camera_result.png
      Q/ESC - 退出
    """
    last_frame = None
    last_result: dict | None = None

    print("\n=== 第二问 摄像头识别 ===")
    print("空格: 检测拼合   A: 动画   S: 保存   Q: 退出\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("无法读取摄像头画面")
            break

        last_frame = frame
        if last_result and last_result.get("ok"):
            preview = last_result["overlay"]
            hint = [
                "[Q2 Camera] Space=redetect  A=animate  S=save  Q=quit",
                f"OK: {len(last_result['pieces'])} pcs, "
                f"{last_result['target_size'][0]:.1f}x{last_result['target_size'][1]:.1f} cm",
            ]
            preview = _draw_status(preview, hint)
        else:
            preview = _draw_status(frame, [
                "[Q2 Camera] 对准 A4，碎片放上半区",
                "Space=检测拼合   Q=退出",
            ])

        key = _show(preview)
        if key in (ord("q"), ord("Q"), 27):
            break

        if key == ord(" "):
            last_result = pipeline_fn(frame, hsv_ranges, verbose=True, image_path=None)
            if not last_result.get("ok"):
                print("检测失败:", last_result.get("error"))
                show_err = _draw_status(frame, [
                    "Detection failed",
                    str(last_result.get("error", ""))[:48],
                    "Space=retry",
                ])
                _show(show_err)
                cv2.waitKey(800)
                last_result = None
            else:
                _print_result(last_result)
            continue

        if key in (ord("a"), ord("A")) and last_result and last_result.get("ok") and on_success:
            on_success(last_result, last_frame)
            continue

        if key in (ord("s"), ord("S")) and last_result and last_result.get("ok"):
            path = "q2_camera_result.png"
            cv2.imwrite(path, last_result["overlay"])
            print(f"已保存: {path}")

    cv2.destroyAllWindows()
