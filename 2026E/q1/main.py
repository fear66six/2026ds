"""Q1 command line entry points for planning and full execution."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .analyzer import SceneAnalyzer
from .calibration import ArmCoordinateMapper
from .camera import SnapshotCamera
from .controller import Q1Controller
from .runtime_config import Q1RuntimeConfig
from .workflow import capture_and_plan


PLAN_CONFIRM_TOKEN = "CAPTURE_AND_PLAN"
RUN_CONFIRM_TOKEN = "RUN_Q1"


def _add_camera_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--camera-backend",
        choices=("k230_ttl", "opencv"),
        default="k230_ttl",
    )
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--camera-port")
    parser.add_argument(
        "--robot-config",
        type=Path,
        default=Path("q1/config/robot_config.json"),
        help="camera endpoint, paper-to-arm calibration and motion planning data",
    )
    parser.add_argument("--capture-burst", type=int, default=8)
    parser.add_argument("--settle-time-ms", type=int, default=200)
    parser.add_argument("--observe-stabilize-ms", type=int, default=300)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Q1 single capture/solve followed by optional real execution"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser(
        "plan",
        help="capture once and generate capture.png, plan.png and planning JSON",
    )
    _add_camera_arguments(plan)
    plan.add_argument(
        "--output-dir",
        type=Path,
        help="new output directory; default is output/plans/q1/<timestamp>",
    )
    plan.add_argument(
        "--confirm",
        default="",
        help=f"exactly {PLAN_CONFIRM_TOKEN} authorizes opening the camera",
    )

    run = commands.add_parser(
        "run",
        help="HOME, capture/plan once, then execute the complete piece queue",
    )
    _add_camera_arguments(run)
    run.add_argument(
        "--magnet-backend",
        choices=("stm32",),
        default="stm32",
    )
    run.add_argument("--magnet-port")
    run.add_argument(
        "--confirm",
        default="",
        help=f"exactly {RUN_CONFIRM_TOKEN} authorizes the complete real Q1 run",
    )
    return parser


def parse_args(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] not in {"plan", "run"}:
        values.insert(0, "run")
    return _build_parser().parse_args(values)


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
        "magnet_settle_ms",
        "magnet_release_settle_ms",
        "magnet_lease_ms",
        "position_tolerance_mm",
        "orientation_tolerance_deg",
        "motion_timeout_s",
        "vertex_max_error_mm",
        "target_scale",
    )
    for key in keys:
        if key in data and data[key] is not None:
            setattr(config, key, data[key])
    if "stable_samples" in data:
        config.idle_stable_samples = int(data["stable_samples"])
    if data.get("camera_port"):
        config.camera_port = str(data["camera_port"])
    if data.get("nexarm_port"):
        config.nexarm_port = str(data["nexarm_port"])
    if data.get("magnet_port") and not config.magnet_port:
        config.magnet_port = str(data["magnet_port"])
    if "target_origin_mm" in data:
        origin = [float(value) for value in data["target_origin_mm"]]
        if len(origin) != 2:
            raise ValueError("target_origin_mm must have 2 numbers")
        config.target_origin_mm = (origin[0], origin[1])

    raw_buffer = data.get("buffer_pose")
    if raw_buffer is not None:
        values = [float(value) for value in raw_buffer]
        if len(values) != 7:
            raise ValueError("buffer_pose must have 7 numbers")
        config.buffer_pose = (*values[:6], int(values[6]))

    raw_home = data.get("home_pose")
    if raw_home is not None:
        values = [float(value) for value in raw_home]
        if len(values) == 6:
            values.append(int(config.move_duration_ms or 6000))
        elif len(values) != 7:
            raise ValueError("home_pose must have 6 or 7 numbers")
        config.observe_pose = tuple(values)


def _load_runtime(args, *, mode: str, authorization: str) -> tuple[dict, Q1RuntimeConfig]:
    robot_data = (
        json.loads(args.robot_config.read_text(encoding="utf-8"))
        if args.robot_config.exists()
        else {}
    )
    config = Q1RuntimeConfig(
        mode=mode,
        authorization=authorization,
        camera_index=args.camera_index,
        camera_port=args.camera_port,
        capture_burst=args.capture_burst,
        settle_time_ms=args.settle_time_ms,
        robot_config=args.robot_config,
        magnet_backend=getattr(args, "magnet_backend", "stm32"),
        magnet_port=getattr(args, "magnet_port", None),
    )
    _apply_robot_fields(config, robot_data)
    if args.camera_port:
        config.camera_port = args.camera_port
    return robot_data, config


def _build_analyzer(config: Q1RuntimeConfig) -> SceneAnalyzer:
    return SceneAnalyzer(
        target_origin_mm=config.target_origin_mm,
        target_scale=config.target_scale,
        center_tolerance_mm=config.place_center_tolerance_mm,
        angle_tolerance_deg=config.place_angle_tolerance_deg,
        vertex_tolerance_mm=config.vertex_max_error_mm,
    )


def _build_camera(args, config: Q1RuntimeConfig):
    if args.camera_backend == "k230_ttl":
        from .k230_ttl_camera_adapter import K230TtlQ1Camera

        options = {
            "stabilization_s": max(0, args.observe_stabilize_ms) / 1000.0,
        }
        if config.camera_port:
            options["port"] = config.camera_port
        return K230TtlQ1Camera(**options)
    return SnapshotCamera(
        config.camera_index,
        burst=config.capture_burst,
        settle_ms=config.settle_time_ms,
    )


def _new_plan_directory(requested: Path | None) -> Path:
    output_dir = (
        requested
        if requested is not None
        else Path("output/plans/q1") / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def run_plan(args) -> Path:
    if args.confirm != PLAN_CONFIRM_TOKEN:
        raise RuntimeError(
            f"CONFIRMATION_REQUIRED: use --confirm {PLAN_CONFIRM_TOKEN}; "
            "camera not opened"
        )
    _, config = _load_runtime(
        args,
        mode="plan",
        authorization=PLAN_CONFIRM_TOKEN,
    )
    blockers = config.planning_blockers()
    if blockers:
        raise RuntimeError("PLAN_BLOCKED: " + "; ".join(blockers))

    mapper = ArmCoordinateMapper(config.robot_config)
    camera = _build_camera(args, config)
    output_dir = _new_plan_directory(args.output_dir)
    try:
        camera.open()
        _, moves = capture_and_plan(
            camera=camera,
            analyzer=_build_analyzer(config),
            mapper=mapper,
            config=config,
            output_dir=output_dir,
        )
    finally:
        camera.close()
    print(f"Q1_PLAN_READY: moves={len(moves)}, output={output_dir}")
    return output_dir


def build_controller(args) -> Q1Controller:
    if args.confirm != RUN_CONFIRM_TOKEN:
        raise RuntimeError(
            f"CONFIRMATION_REQUIRED: use --confirm {RUN_CONFIRM_TOKEN}; "
            "no hardware opened"
        )
    robot_data, config = _load_runtime(
        args,
        mode="run",
        authorization=RUN_CONFIRM_TOKEN,
    )
    if robot_data and robot_data.get("magnet_backend") != "stm32":
        raise RuntimeError("ROBOT_CONFIG_REQUIRES_STM32_MAGNET")
    if config.magnet_port and config.magnet_port == config.camera_port:
        raise RuntimeError("MAGNET_PORT_CONFLICTS_WITH_CAMERA")
    blockers = config.production_run_blockers()
    if blockers:
        raise RuntimeError("REAL_RUN_BLOCKED: " + "; ".join(blockers))

    from .executors.nexarm import NexArmRobotExecutor
    from .magnet import STM32MagnetController

    mapper = ArmCoordinateMapper(config.robot_config)
    camera = _build_camera(args, config)
    robot = NexArmRobotExecutor(Path(__file__).resolve().parents[1], config)
    magnet = STM32MagnetController(
        config.magnet_port or "",
        lease_ms=config.magnet_lease_ms,
    )
    return Q1Controller(
        camera=camera,
        analyzer=_build_analyzer(config),
        robot=robot,
        magnet=magnet,
        mapper=mapper,
        config=config,
    )


def run_full(args) -> Path:
    controller = build_controller(args)
    controller.run()
    print(
        f"Q1 FINISHED: moves={len(controller.move_queue)}, "
        f"run={controller.recorder.directory}"
    )
    controller.recorder.announce(prefix="Q1_FINISHED_RUN")
    return controller.recorder.directory


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "plan":
        run_plan(args)
    else:
        run_full(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
