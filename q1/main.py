#!/usr/bin/env python3
"""
E题 第一问 — 独立入口

固定四片 10×6 图2模板，黑底白片：

  python -m q1.main --image test.png --simulate
  python -m q1.main --camera --camera-index 1    # 实时监测 4/4
  python -m q1.main --run --dry-run --camera-index 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

from q1 import config
from q1 import run_pipeline
from q1.animator import play_motion_animation
from q1.camera_run import configure_camera, run_camera_q1
from q1.device_run import run_live
from q1.executor import DeviceExecutor
from q1.simulator import (
    DEFAULT_SCATTERED_LAYOUT,
    SCATTERED_LAYOUTS,
    generate_scattered_image,
)
from q1.vision import segment_pieces


def parse_hsv_arg(hsv_str: str | None, default):
    if hsv_str:
        vals = [int(x) for x in hsv_str.split(",")]
        if len(vals) != 6:
            raise ValueError("HSV 格式: low_h,low_s,low_v,high_h,high_s,high_v")
        return [((vals[0], vals[1], vals[2]), (vals[3], vals[4], vals[5]))]
    return default


def open_camera(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)
    configure_camera(cap)
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
    parser = argparse.ArgumentParser(description="E题 第一问 — 图2四片拼图")
    parser.add_argument("--run", action="store_true", help="摄像头一键检测+执行+复检")
    parser.add_argument("--port", type=str, help="下位机串口，如 COM3")
    parser.add_argument("--dry-run", action="store_true", help="不连硬件，模拟执行延时")
    parser.add_argument("--record", type=str, help="录制运行过程视频")
    parser.add_argument("--camera", action="store_true", help="摄像头检测预览")
    parser.add_argument("--camera-index", type=int, default=None, help="摄像头编号，默认 0；USB 外接多为 1")
    parser.add_argument("--list-cameras", action="store_true", help="列出可用摄像头编号后退出")
    parser.add_argument("--image", type=str, help="离线测试图片路径")
    parser.add_argument(
        "--scattered",
        nargs="?",
        const=DEFAULT_SCATTERED_LAYOUT,
        choices=list(SCATTERED_LAYOUTS.keys()),
        metavar="LAYOUT",
        help="生成 scattered_bw.png (a/b)",
    )
    parser.add_argument("--simulate", action="store_true", help="离线搬运动画仿真")
    parser.add_argument("--save", type=str, help="保存检测叠加图")
    parser.add_argument("--gcode", type=str, help="导出 G-code 文件")
    parser.add_argument("--hsv", type=str, help="自定义 HSV 阈值")
    parser.add_argument("--save-mask", type=str, help="保存分割掩码")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    if args.list_cameras:
        list_cameras()
        return

    cam_index = args.camera_index if args.camera_index is not None else config.CAMERA_INDEX

    hsv_ranges = parse_hsv_arg(args.hsv, config.DEFAULT_HSV_RANGES)

    if args.run:
        cap = open_camera(cam_index)
        if not cap.isOpened():
            sys.exit(f"无法打开摄像头 index={cam_index}，请先运行 --list-cameras 查看编号")
        executor = DeviceExecutor(
            port=args.port,
            dry_run=args.dry_run or config.FORCE_DRY_RUN or not (args.port or config.SERIAL_PORT),
        )
        if executor.dry_run:
            print(">>> 模拟模式：碎片不会真正移动")
        run_live(
            cap,
            lambda frame, hsv, verbose=False: run_pipeline(frame, hsv, verbose=verbose),
            hsv_ranges,
            executor,
            record_path=args.record,
        )
        cap.release()
        return

    if args.camera:
        cap = open_camera(cam_index)
        if not cap.isOpened():
            sys.exit(f"无法打开摄像头 index={cam_index}，请先运行 --list-cameras 查看编号")

        def on_run(result, frame):
            if args.simulate:
                play_motion_animation(
                    frame,
                    result["paper"],
                    result["divider_y_cm"],
                    result["pieces"],
                    result["steps"],
                    result["assignments"],
                )

        run_camera_q1(
            cap,
            lambda frame, hsv, verbose=False: run_pipeline(frame, hsv, verbose=verbose),
            hsv_ranges,
            on_run=on_run if args.simulate else None,
        )
        cap.release()
        return

    if args.scattered:
        layout = args.scattered
        frame = generate_scattered_image(layout=layout)
        out_path = Path("scattered_bw.png")
        cv2.imwrite(str(out_path), frame)
        print(f"已生成分散测试图 [布局 {layout}] -> {out_path}")
    elif args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            sys.exit(f"无法读取: {args.image}")
    else:
        parser.print_help()
        print("\n示例:")
        print("  python -m q1.main --image test.png --simulate")
        print("  python -m q1.main --scattered b --simulate")
        print("  python -m q1.main --run --dry-run")
        sys.exit(0)

    result = run_pipeline(frame, hsv_ranges)
    if not result.get("ok"):
        sys.exit(result.get("error", "失败"))

    if args.save_mask:
        mask = segment_pieces(
            frame,
            result["paper"],
            hsv_ranges,
            divider_y_cm=result["divider_y_cm"],
        )
        cv2.imwrite(args.save_mask, mask)

    if args.save:
        cv2.imwrite(args.save, result["overlay"])
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
            )
        else:
            show = cv2.resize(result["overlay"], None, fx=config.DISPLAY_SCALE, fy=config.DISPLAY_SCALE)
            cv2.imshow("Q1 Detection", show)
            cv2.waitKey(0)
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
