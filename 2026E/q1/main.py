"""Q1单步视觉闭环入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyzer import SceneAnalyzer
from .calibration import ArmCoordinateMapper, PaperCalibration
from .camera import SnapshotCamera
from .controller import Q1Controller
from .executors.nexarm import NexArmRobotExecutor
from .magnet import STM32MagnetController
from .preview import wait_for_space
from .runtime_config import Q1RuntimeConfig


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Q1每轮观察、只规划一块的视觉闭环（仅真实摄像头+机械臂运行）")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument(
        "--camera-backend",
        choices=("opencv", "k230_ttl"),
        default="opencv",
        help="opencv=本机UVC索引；k230_ttl=正式K230 TTL 1280x720@460800",
    )
    parser.add_argument("--paper-calibration", type=Path)
    parser.add_argument("--arm-calibration", type=Path, help="含 paper_to_robot_matrix 与腕部 roll 标定的 JSON")
    parser.add_argument("--safety-config", type=Path, help="实机安全高度/工作区/电磁铁时序 JSON")
    parser.add_argument("--nexarm-port")
    parser.add_argument("--magnet-port")
    parser.add_argument("--capture-burst", type=int, default=8)
    parser.add_argument("--settle-time-ms", type=int, default=200)
    parser.add_argument(
        "--observe-stabilize-ms",
        type=int,
        default=300,
        help="机械臂回观察位并 idle 后、CAPTURE 前额外稳定等待",
    )
    parser.add_argument("--max-cycles", type=int, default=16)
    parser.add_argument("--auto-start", action="store_true", help="跳过SPACE预览（风险自测：仅你确认安全后使用）")
    return parser.parse_args(argv)


def _apply_json_fields(config: Q1RuntimeConfig, data: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        if key in data and data[key] is not None:
            setattr(config, key, data[key])


def _normalize_home_observe_pose(data: dict, move_duration_ms: int | None) -> tuple | None:
    """Prefer home_pose; observe_pose is accepted only as a HOME alias."""
    raw = data.get("home_pose")
    if raw is None:
        raw = data.get("observe_pose")
    if raw is None:
        return None
    values = [float(v) for v in raw]
    if len(values) == 6:
        duration = int(move_duration_ms if move_duration_ms is not None else 6000)
        values.append(duration)
    elif len(values) != 7:
        raise ValueError("home_pose/observe_pose must have 6 or 7 numbers")
    return tuple(values)


def _load_run_parameters(config: Q1RuntimeConfig, args) -> None:
    safety_keys = (
        "safe_height",
        "pick_height",
        "release_height",
        "move_duration_ms",
        "magnet_settle_ms",
        "release_peel_delta",
        "workspace_limits",
    )
    payloads: list[dict] = []
    if args.safety_config is not None and args.safety_config.exists():
        payloads.append(json.loads(args.safety_config.read_text(encoding="utf-8")))
    if args.arm_calibration is not None and args.arm_calibration.exists():
        payloads.append(json.loads(args.arm_calibration.read_text(encoding="utf-8")))
    for data in payloads:
        _apply_json_fields(config, data, safety_keys)
        pose = _normalize_home_observe_pose(data, config.move_duration_ms)
        if pose is not None:
            config.observe_pose = pose


def build_controller(args) -> Q1Controller:
    config = Q1RuntimeConfig(
        mode="run",
        camera_index=args.camera_index,
        capture_burst=args.capture_burst,
        settle_time_ms=args.settle_time_ms,
        max_cycles=args.max_cycles,
        paper_calibration=args.paper_calibration,
        arm_calibration=args.arm_calibration,
        nexarm_port=args.nexarm_port,
        magnet_port=args.magnet_port,
    )
    _load_run_parameters(config, args)
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

    blockers = config.real_run_blockers()
    if blockers:
        raise RuntimeError("RealRun禁止启动: " + "; ".join(blockers))
    if getattr(args, "camera_backend", "opencv") == "k230_ttl":
        from .k230_ttl_camera_adapter import K230TtlQ1Camera

        camera = K230TtlQ1Camera(
            stabilization_s=max(0, getattr(args, "observe_stabilize_ms", 300)) / 1000.0,
        )
    else:
        camera = SnapshotCamera(
            config.camera_index,
            burst=config.capture_burst,
            settle_ms=config.settle_time_ms,
        )
    robot = NexArmRobotExecutor(Path(__file__).resolve().parents[1], config)
    magnet = STM32MagnetController(config.magnet_port or "")
    return Q1Controller(camera=camera, analyzer=analyzer, robot=robot, magnet=magnet, mapper=mapper, config=config)


def main(argv=None) -> int:
    args = parse_args(argv)
    controller = build_controller(args)
    if not args.auto_start and not wait_for_space(controller.camera):
        print("Q1 SAFE STOP: 用户退出预览")
        return 0
    final_scene = controller.run()
    print(f"Q1 COMPLETED: cycle={final_scene.cycle_index}, run={controller.recorder.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
