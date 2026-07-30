"""Single production Q1 closed-loop entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyzer import SceneAnalyzer
from .calibration import ArmCoordinateMapper
from .camera import SnapshotCamera
from .controller import Q1Controller
from .executors.nexarm import NexArmRobotExecutor
from .magnet import STM32MagnetController
from .runtime_config import Q1RuntimeConfig


CONFIRM_TOKEN = "RUN_Q1"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Q1 HOME -> per-piece vision -> real-arm closed loop"
    )
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument(
        "--camera-backend",
        choices=("opencv", "k230_ttl"),
        default="opencv",
    )
    parser.add_argument(
        "--robot-config",
        type=Path,
        default=Path("q1/config/robot_config.json"),
        help="single source for NexArm port, calibration, HOME, motion and safety",
    )
    parser.add_argument(
        "--magnet-backend",
        choices=("stm32",),
        default="stm32",
        help="production Q1 is real STM32 magnet only",
    )
    parser.add_argument("--magnet-port")
    parser.add_argument("--capture-burst", type=int, default=8)
    parser.add_argument("--settle-time-ms", type=int, default=200)
    parser.add_argument("--observe-stabilize-ms", type=int, default=300)
    parser.add_argument("--max-cycles", type=int, default=4)
    parser.add_argument(
        "--confirm",
        default="",
        help=f"exactly {CONFIRM_TOKEN} authorizes the complete real-arm Q1 loop",
    )
    return parser.parse_args(argv)


def _apply_robot_fields(config: Q1RuntimeConfig, data: dict) -> None:
    keys = (
        "motion_mode",
        "direct_pick_release_pose_verified",
        "motion_calibration_status",
        "physical_pick_verified",
        "physical_pick_enabled",
        "pick_height",
        "release_height",
        "move_duration_ms",
        "global_acceleration",
        "magnet_settle_ms",
        "magnet_release_settle_ms",
        "magnet_lease_ms",
        "position_tolerance_mm",
        "orientation_tolerance_deg",
        "motion_timeout_s",
        "vertex_max_error_mm",
        "paper_corner_drift_limit_px",
    )
    for key in keys:
        if key in data and data[key] is not None:
            setattr(config, key, data[key])
    if "stable_samples" in data:
        config.idle_stable_samples = int(data["stable_samples"])
    if "workspace_limits" in data:
        config.workspace_limits = {
            axis: (float(bounds[0]), float(bounds[1]))
            for axis, bounds in data["workspace_limits"].items()
        }
    if data.get("nexarm_port"):
        config.nexarm_port = str(data["nexarm_port"])
    if data.get("magnet_port") and not config.magnet_port:
        config.magnet_port = str(data["magnet_port"])

    raw_home = data.get("home_pose")
    if raw_home is not None:
        values = [float(value) for value in raw_home]
        if len(values) == 6:
            values.append(int(config.move_duration_ms or 6000))
        elif len(values) != 7:
            raise ValueError("home_pose must have 6 or 7 numbers")
        config.observe_pose = tuple(values)


def build_controller(args) -> Q1Controller:
    if args.confirm != CONFIRM_TOKEN:
        raise RuntimeError(
            f"CONFIRMATION_REQUIRED: use --confirm {CONFIRM_TOKEN}; no hardware opened"
        )
    robot_data = (
        json.loads(args.robot_config.read_text(encoding="utf-8"))
        if args.robot_config.exists()
        else {}
    )
    config = Q1RuntimeConfig(
        camera_index=args.camera_index,
        capture_burst=args.capture_burst,
        settle_time_ms=args.settle_time_ms,
        max_cycles=args.max_cycles,
        robot_config=args.robot_config,
        magnet_backend=args.magnet_backend,
        magnet_port=args.magnet_port,
    )
    _apply_robot_fields(config, robot_data)
    if robot_data and robot_data.get("magnet_backend") != "stm32":
        raise RuntimeError("ROBOT_CONFIG_REQUIRES_STM32_MAGNET")
    if (
        robot_data
        and config.magnet_backend == "stm32"
        and config.magnet_port == robot_data.get("camera_port")
    ):
        raise RuntimeError("MAGNET_PORT_CONFLICTS_WITH_CAMERA")
    blockers = config.real_run_blockers()
    if blockers:
        raise RuntimeError("RealRun禁止启动 / blocked: " + "; ".join(blockers))

    mapper = ArmCoordinateMapper(config.robot_config)
    analyzer = SceneAnalyzer(
        target_origin_mm=config.target_origin_mm,
        center_tolerance_mm=config.place_center_tolerance_mm,
        angle_tolerance_deg=config.place_angle_tolerance_deg,
        vertex_tolerance_mm=config.vertex_max_error_mm,
        paper_corner_drift_limit_px=config.paper_corner_drift_limit_px,
    )
    if args.camera_backend == "k230_ttl":
        from .k230_ttl_camera_adapter import K230TtlQ1Camera

        camera = K230TtlQ1Camera(
            stabilization_s=max(0, args.observe_stabilize_ms) / 1000.0,
        )
    else:
        camera = SnapshotCamera(
            config.camera_index,
            burst=config.capture_burst,
            settle_ms=config.settle_time_ms,
        )
    robot = NexArmRobotExecutor(Path(__file__).resolve().parents[1], config)
    magnet = STM32MagnetController(
        config.magnet_port or "",
        lease_ms=config.magnet_lease_ms,
    )
    return Q1Controller(
        camera=camera,
        analyzer=analyzer,
        robot=robot,
        magnet=magnet,
        mapper=mapper,
        config=config,
    )


def main(argv=None) -> int:
    controller = build_controller(parse_args(argv))
    final_scene = controller.run()
    print(
        f"Q1 FINISHED: cycle={final_scene.cycle_index}, "
        f"run={controller.recorder.directory}"
    )
    controller.recorder.announce(prefix="Q1_FINISHED_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
