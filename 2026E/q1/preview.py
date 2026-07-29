"""低负载预览：只显示最新帧和按键，不运行完整视觉流水线。"""

from __future__ import annotations

from pathlib import Path

import cv2


def wait_for_space(camera, save_path: Path = Path("runs/q1/preview.png")) -> bool:
    camera.open()
    print("SPACE：启动单步视觉闭环  R：刷新预览  S：保存当前帧  Q：安全退出")
    while True:
        frame = camera.read_preview()
        if frame is None:
            raise RuntimeError("CAPTURE_FAILED: 预览无法读取摄像头帧")
        display = frame.copy()
        cv2.putText(
            display,
            "SPACE start | R refresh | S save | Q quit",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.imshow("Q1 Preview (no full analysis)", display)
        key = cv2.waitKey(1) & 0xFF
        if key == 32:
            cv2.destroyWindow("Q1 Preview (no full analysis)")
            return True
        if key in (ord("q"), ord("Q")):
            cv2.destroyWindow("Q1 Preview (no full analysis)")
            camera.close()
            return False
        if key in (ord("s"), ord("S")):
            save_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(save_path), frame)
            print(f"已保存预览原图: {save_path}")
        # R只丢弃当前帧并继续；不触发完整分析。
