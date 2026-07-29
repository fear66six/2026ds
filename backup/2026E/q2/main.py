#!/usr/bin/env python3
"""
E题 第二问 — 黑底白片，1~4 片不规则碎片拼矩形

  python -m q2.main --camera          # 摄像头识别
  python -m q2.main                   # 本地选图
  python -m q2.main --image photo.png
  python -m q2.main --run --dry-run   # 摄像头 + 硬件执行（仿真）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

from q2 import config
from q2.animator import play_motion_animation
from q2.camera_run import run_camera_q2
from q2.device_run import run_live_q2
from q2.executor import DeviceExecutor
from q2.local_ui import pick_image_path
from q2.pipeline import run_pipeline_q2
from q2.testcase import save_q2_test_case


def parse_hsv_arg(hsv_str: str | None, default):
    if hsv_str:
        vals = [int(x) for x in hsv_str.split(",")]
        if len(vals) != 6:
            raise ValueError("HSV 格式: low_h,low_s,low_v,high_h,high_s,high_v")
        return [((vals[0], vals[1], vals[2]), (vals[3], vals[4], vals[5]))]
    return default


def open_camera(index: int) -> cv2.VideoCapture:
    """Windows 上 USB 摄像头优先用 DirectShow 后端"""
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def list_cameras(max_index: int = 5) -> None:
    print("可用摄像头索引：")
    found = False
    for i in range(max_index):
        cap = open_camera(i)
        if not cap.isOpened():
            print(f"  [{i}] 不可用")
            cap.release()
            continue
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"  [{i}] {w} x {h}")
        found = True
        cap.release()
    if not found:
        print("  未检测到摄像头，请检查 USB 连接与驱动")


def main():
    parser = argparse.ArgumentParser(description="E题 第二问 — 本地选图自动拼矩形")
    parser.add_argument("--target-width", type=float, help="目标宽 (cm)，可省略并自动推断")
    parser.add_argument("--target-height", type=float, help="目标高 (cm)，可省略并自动推断")
    parser.add_argument("--q2-pieces", type=int, default=4, choices=[1, 2, 3, 4, 5], help="测试图碎片数")
    parser.add_argument("--camera", action="store_true", help="摄像头识别（空格检测，无需串口）")
    parser.add_argument("--camera-index", type=int, default=None, help="摄像头编号，默认 0；USB 外接多为 1")
    parser.add_argument("--list-cameras", action="store_true", help="列出可用摄像头编号后退出")
    parser.add_argument("--run", action="store_true", help="摄像头 + 串口执行完整流程")
    parser.add_argument("--port", type=str, help="串口")
    parser.add_argument("--dry-run", action="store_true", help="不连硬件")
    parser.add_argument("--record", type=str, help="录制视频")
    parser.add_argument("--image", type=str, help="离线图片路径")
    parser.add_argument("--pick", action="store_true", help="打开本地文件选择框（无 --image 时默认）")
    parser.add_argument("--fig2-fallback", action="store_true", help="失败时回退图2四片模板（仅测试用）")
    parser.add_argument("--q2-scattered", action="store_true", help="生成 q2_scattered.png")
    parser.add_argument("--q2-output", type=str, default="q2_scattered", help="测试图输出前缀（默认 q2_scattered）")
    parser.add_argument("--seed", type=int, default=42, help="测试图随机种子")
    parser.add_argument("--simulate", action="store_true", help="仿真动画")
    parser.add_argument("--save", type=str, help="保存检测图")
    parser.add_argument("--gcode", type=str, help="导出 G-code")
    parser.add_argument("--hsv", type=str, help="自定义 HSV")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    if args.list_cameras:
        list_cameras()
        return

    cam_index = args.camera_index if args.camera_index is not None else config.CAMERA_INDEX

    hsv_ranges = parse_hsv_arg(args.hsv, config.DEFAULT_HSV_RANGES)

    def pipeline_fn(frame, h, verbose=False, image_path=None):
        return run_pipeline_q2(
            frame,
            h,
            verbose=verbose,
            target_width=args.target_width,
            target_height=args.target_height,
            allow_template_fallback=args.fig2_fallback,
            image_path=image_path,
        )

    if args.camera:
        cap = open_camera(cam_index)
        if not cap.isOpened():
            sys.exit(f"无法打开摄像头 index={cam_index}，请先运行 --list-cameras 查看编号")

        def on_animate(result, frame):
            play_motion_animation(
                frame,
                result["paper"],
                result["divider_y_cm"],
                result["pieces"],
                result["steps"],
                result["assignments"],
                target_origin=result.get("target_origin"),
                target_size=result.get("target_size"),
                window_name="Q2 Simulation",
            )

        run_camera_q2(cap, pipeline_fn, hsv_ranges, on_success=on_animate)
        cap.release()
        return

    if args.run:
        cap = open_camera(cam_index)
        if not cap.isOpened():
            sys.exit(f"无法打开摄像头 index={cam_index}，请先运行 --list-cameras 查看编号")
        executor = DeviceExecutor(
            port=args.port,
            dry_run=args.dry_run or config.FORCE_DRY_RUN or not (args.port or config.SERIAL_PORT),
        )
        run_live_q2(cap, pipeline_fn, hsv_ranges, executor, record_path=args.record)
        cap.release()
        return

    if args.q2_scattered:
        w = args.target_width or 10.0
        h = args.target_height or 6.0
        prefix = args.q2_output
        _, meta = save_q2_test_case(prefix, w, h, args.q2_pieces, seed=args.seed)
        out_png = f"{prefix}.png" if not prefix.endswith(".png") else prefix
        print(f"已生成 {out_png} + .json ({meta.n_pieces} 片, {w}x{h} cm, seed={meta.seed})")
        image_path = out_png
    elif args.image:
        image_path = args.image
    else:
        image_path = pick_image_path(Path.cwd())
        if not image_path:
            sys.exit("未选择图片")

    frame = cv2.imread(image_path)
    if frame is None:
        sys.exit(f"无法读取: {image_path}")

    result = pipeline_fn(frame, hsv_ranges, verbose=True, image_path=image_path)
    if not result.get("ok"):
        sys.exit(result.get("error", "失败"))

    if args.save:
        out = args.save if args.save.endswith(".png") else args.save + ".png"
        cv2.imwrite(out, result["overlay"])
        print(f"已保存: {out}")
    if args.gcode:
        Path(args.gcode).write_text(result["gcode"], encoding="utf-8")

    if not args.no_show:
        if args.simulate:
            play_motion_animation(
                frame,
                result["paper"],
                result["divider_y_cm"],
                result["pieces"],
                result["steps"],
                result["assignments"],
                target_origin=result.get("target_origin"),
                target_size=result.get("target_size"),
                window_name="Q2 Simulation",
            )
        else:
            show = cv2.resize(result["overlay"], None, fx=config.DISPLAY_SCALE, fy=config.DISPLAY_SCALE)
            cv2.imshow("Q2 Detection", show)
            cv2.waitKey(0)
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
