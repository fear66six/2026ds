"""Q2 white-paper puzzle planning and full execution entry points."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

from q1.calibration import ArmCoordinateMapper
from q1.camera import SnapshotCamera
from q1.main import _apply_robot_fields

from .runtime_config import Q2RuntimeConfig


PLAN_CONFIRM_TOKEN = "CAPTURE_AND_PLAN"
RUN_CONFIRM_TOKEN = "RUN_Q2"


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
        help="reuse the completed Q1 camera, calibration and motion configuration",
    )
    parser.add_argument("--capture-burst", type=int, default=8)
    parser.add_argument("--settle-time-ms", type=int, default=200)
    parser.add_argument("--observe-stabilize-ms", type=int, default=300)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Q2 single-capture white-paper puzzle solve and execution"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan", help="capture once and solve the Q2 puzzle")
    _add_camera_arguments(plan)
    plan.add_argument("--output-dir", type=Path)
    plan.add_argument("--confirm", default="")

    run = commands.add_parser("run", help="HOME, solve once, then place every fragment")
    _add_camera_arguments(run)
    run.add_argument("--magnet-backend", choices=("stm32",), default="stm32")
    run.add_argument("--magnet-port")
    run.add_argument("--confirm", default="")
    return parser


def parse_args(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] not in {"plan", "run"}:
        values.insert(0, "run")
    return _build_parser().parse_args(values)


def _require_solver_dependencies() -> None:
    if importlib.util.find_spec("shapely") is None:
        raise RuntimeError(
            "Q2_DEPENDENCY_REQUIRED: shapely>=2.0 is not installed; "
            "no camera or hardware opened"
        )


def _load_runtime(
    args,
    *,
    mode: str,
    authorization: str,
) -> tuple[dict, Q2RuntimeConfig]:
    robot_data = (
        json.loads(args.robot_config.read_text(encoding="utf-8"))
        if args.robot_config.exists()
        else {}
    )
    config = Q2RuntimeConfig(
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
    config.run_root = Path("output/runs/q2")
    if args.camera_port:
        config.camera_port = args.camera_port
    return robot_data, config


def _build_analyzer():
    from .analyzer import WhitePuzzleAnalyzer

    return WhitePuzzleAnalyzer()


def _build_camera(args, config: Q2RuntimeConfig):
    if args.camera_backend == "k230_ttl":
        from q1.k230_ttl_camera_adapter import K230TtlQ1Camera

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
        else Path("output/plans/q2") / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def run_plan(args) -> Path:
    if args.confirm != PLAN_CONFIRM_TOKEN:
        raise RuntimeError(
            f"CONFIRMATION_REQUIRED: use --confirm {PLAN_CONFIRM_TOKEN}; "
            "camera not opened"
        )
    _require_solver_dependencies()
    _, config = _load_runtime(args, mode="plan", authorization=PLAN_CONFIRM_TOKEN)
    blockers = config.planning_blockers()
    if blockers:
        raise RuntimeError("PLAN_BLOCKED: " + "; ".join(blockers))

    from .workflow import capture_and_plan

    mapper = ArmCoordinateMapper(config.robot_config)
    camera = _build_camera(args, config)
    output_dir = _new_plan_directory(args.output_dir)
    try:
        camera.open()
        _, moves = capture_and_plan(
            camera=camera,
            analyzer=_build_analyzer(),
            mapper=mapper,
            config=config,
            output_dir=output_dir,
        )
    finally:
        camera.close()
    print(f"Q2_PLAN_READY: moves={len(moves)}, output={output_dir}")
    return output_dir


def build_controller(args):
    if args.confirm != RUN_CONFIRM_TOKEN:
        raise RuntimeError(
            f"CONFIRMATION_REQUIRED: use --confirm {RUN_CONFIRM_TOKEN}; "
            "no hardware opened"
        )
    _require_solver_dependencies()
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

    from q1.executors.nexarm import NexArmRobotExecutor
    from q1.magnet import STM32MagnetController

    from .controller import Q2Controller

    mapper = ArmCoordinateMapper(config.robot_config)
    return Q2Controller(
        camera=_build_camera(args, config),
        analyzer=_build_analyzer(),
        robot=NexArmRobotExecutor(Path(__file__).resolve().parents[1], config),
        magnet=STM32MagnetController(
            config.magnet_port or "",
            lease_ms=config.magnet_lease_ms,
        ),
        mapper=mapper,
        config=config,
    )


def run_full(args) -> Path:
    controller = build_controller(args)
    controller.run()
    print(
        f"Q2 FINISHED: moves={len(controller.move_queue)}, "
        f"run={controller.recorder.directory}"
    )
    controller.recorder.announce(prefix="Q2_FINISHED_RUN")
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

