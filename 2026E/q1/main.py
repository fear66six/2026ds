"""Q1单步视觉闭环入口。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2

from .analyzer import SceneAnalyzer
from .calibration import ArmCoordinateMapper, PaperCalibration
from .camera import SnapshotCamera, StaticImageCamera
from .controller import Q1Controller
from .executors.nexarm import NexArmRobotExecutor
from .executors.simulation import SimulationRobotExecutor, SimulationWorld
from .magnet import STM32MagnetController, SimulationMagnetController
from .models import Snapshot
from .preview import wait_for_space
from .runtime_config import Q1RuntimeConfig


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Q1每轮观察、只规划一块的视觉闭环")
    parser.add_argument("--mode", choices=("simulate", "dry-run", "run"), default="simulate")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--paper-calibration", type=Path)
    parser.add_argument("--arm-calibration", type=Path)
    parser.add_argument("--nexarm-port")
    parser.add_argument("--magnet-port")
    parser.add_argument("--capture-burst", type=int, default=8)
    parser.add_argument("--settle-time-ms", type=int, default=200)
    parser.add_argument("--max-cycles", type=int, default=16)
    parser.add_argument("--simulate-place-offset", choices=("P1", "P2", "P3", "P4"))
    parser.add_argument("--simulate-release-failure", choices=("P1", "P2", "P3", "P4"))
    parser.add_argument("--simulate-piece-shift", choices=("P1", "P2", "P3", "P4"))
    parser.add_argument("--simulate-camera-shift", action="store_true")
    parser.add_argument("--auto-start", action="store_true", help="跳过SPACE预览，供自动测试使用")
    return parser.parse_args(argv)


def build_controller(args) -> Q1Controller:
    config = Q1RuntimeConfig(
        mode=args.mode,
        camera_index=args.camera_index,
        capture_burst=args.capture_burst,
        settle_time_ms=args.settle_time_ms,
        max_cycles=args.max_cycles,
        paper_calibration=args.paper_calibration,
        arm_calibration=args.arm_calibration,
        nexarm_port=args.nexarm_port,
        magnet_port=args.magnet_port,
    )
    mapper = ArmCoordinateMapper(config.arm_calibration)
    paper_calibration = (
        PaperCalibration.load(config.paper_calibration)
        if config.paper_calibration is not None and config.paper_calibration.exists()
        else None
    )
    analyzer = SceneAnalyzer(
        target_origin_mm=config.target_origin_mm,
        center_tolerance_mm=config.place_center_tolerance_mm,
        angle_tolerance_deg=config.place_angle_tolerance_deg,
        vertex_tolerance_mm=config.vertex_max_error_mm,
        paper_calibration=paper_calibration,
    )

    if args.mode in ("simulate", "dry-run"):
        world = SimulationWorld(
            target_origin_mm=config.target_origin_mm,
            place_offset_template=args.simulate_place_offset,
            release_failure_template=args.simulate_release_failure,
            shift_after_move_template=args.simulate_piece_shift,
            camera_shift=args.simulate_camera_shift,
        )
        camera = StaticImageCamera(world.snapshot)
        robot = SimulationRobotExecutor(world, dry_run=False)
        magnet = SimulationMagnetController()
    else:
        blockers = config.real_run_blockers()
        if blockers:
            raise RuntimeError("RealRun禁止启动: " + "; ".join(blockers))
        camera = SnapshotCamera(
            config.camera_index,
            burst=config.capture_burst,
            settle_ms=config.settle_time_ms,
        )
        robot = NexArmRobotExecutor(Path(__file__).resolve().parents[2], config)
        magnet = STM32MagnetController(config.magnet_port or "")
    return Q1Controller(camera=camera, analyzer=analyzer, robot=robot, magnet=magnet, mapper=mapper, config=config)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.image is not None:
        frame = cv2.imread(str(args.image))
        if frame is None:
            raise SystemExit(f"无法读取图像: {args.image}")
        # 兼容离线图片入口：只做一次静态整景分析，不执行任何动作。
        analyzer = SceneAnalyzer()
        snapshot = Snapshot(frame, time.time(), 0.0, 0.0, 0.0, str(args.image))
        scene = analyzer.analyze(snapshot, 0)
        print(json.dumps({
            "paper_valid": scene.paper_valid,
            "scene_valid": scene.scene_valid,
            "pieces": len(scene.pieces),
            "placed": sorted(scene.placed_templates),
            "remaining": sorted(scene.remaining_templates),
            "timings_ms": scene.timings_ms,
            "warnings": scene.warnings,
        }, ensure_ascii=False, indent=2))
        return 0 if scene.paper_valid else 2
    controller = build_controller(args)
    if not args.auto_start and not wait_for_space(controller.camera):
        print("Q1 SAFE STOP: 用户退出预览")
        return 0
    final_scene = controller.run()
    print(f"Q1 COMPLETED: cycle={final_scene.cycle_index}, run={controller.recorder.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
