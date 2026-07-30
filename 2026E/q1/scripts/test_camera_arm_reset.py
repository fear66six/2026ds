#!/usr/bin/env python3
"""No-pick, no-magnet K230 + NexArm HOME reset/photo test."""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2

from q1.camera import K230SnapshotAdapter
from q1.robot import NexArmResetController, Pose, StaleFeedbackError, pose_error


CONFIRM_TOKEN = "RUN_ARM_RESET"
MAGNET_PROCESS_TERMS = (
    "stm32_magnet",
    "magnet_control",
    "jetson_control_magnet",
    "magnet_uart",
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "K230 snapshot + low-speed NexArm reset test. Without "
            "--confirm RUN_ARM_RESET it performs checks and one warm-up capture only."
        )
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"exactly {CONFIRM_TOKEN} authorizes the fixed arm reset sequence",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--nexarm-port",
        help="override only when the current NexArm endpoint has been physically verified",
    )
    return parser.parse_args(argv)


def load_config(project_root: Path, requested: Path | None) -> dict[str, Any]:
    path = requested or project_root / "q1" / "config" / "robot_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_path"] = str(path)
    return data


def make_run_layout(project_root: Path) -> tuple[str, Path, logging.Logger]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = project_root / "output"
    run_dir = output / "runs" / run_id
    for child in (
        run_dir / "captures",
        run_dir / "logs",
        output / "captures",
        output / "detection",
        output / "logs",
    ):
        child.mkdir(parents=True, exist_ok=True)
    for parent, target in (
        (output / "captures", run_dir / "captures"),
        (output / "logs", run_dir / "logs"),
    ):
        link = parent / run_id
        if not link.exists():
            link.symlink_to(target)

    logger = logging.getLogger(f"q1.arm_reset.{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S"
    )
    file_handler = logging.FileHandler(
        run_dir / "logs" / "arm_reset.log", encoding="utf-8"
    )
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return run_id, run_dir, logger


def result(ok: bool, detail: Any, *, manual: bool = False) -> dict[str, Any]:
    return {
        "status": "PASS" if ok else ("PENDING" if manual else "FAIL"),
        "detail": detail,
    }


def device_users(device: str) -> list[str]:
    resolved = str(Path(device).resolve())
    users: list[str] = []
    for fd_dir in glob.glob("/proc/[0-9]*/fd"):
        pid = Path(fd_dir).parent.name
        if int(pid) == os.getpid():
            continue
        try:
            for fd in Path(fd_dir).iterdir():
                try:
                    if str(fd.resolve()) == resolved:
                        cmdline = (
                            Path(fd_dir).parent.joinpath("cmdline").read_bytes()
                            .replace(b"\0", b" ")
                            .decode("utf-8", errors="replace")
                            .strip()
                        )
                        users.append(f"pid={pid} {cmdline}")
                        break
                except (FileNotFoundError, PermissionError, OSError):
                    continue
        except (FileNotFoundError, PermissionError):
            continue
    return users


def check_device(path: str) -> dict[str, Any]:
    device = Path(path)
    if not device.exists():
        return result(False, f"missing: {path}")
    resolved = str(device.resolve())
    users = device_users(path)
    return result(
        not users,
        {"path": path, "resolved": resolved, "users": users},
    )


def discover_nexarm_port(configured: str | None) -> tuple[str | None, dict[str, Any]]:
    if configured:
        return configured, {"source": "configured", "stable_by_id": "/by-id/" in configured}
    by_id = [
        path
        for path in sorted(glob.glob("/dev/serial/by-id/*"))
        if "5B7A028646" not in path and "Kendryte_CanMV" not in path
    ]
    if len(by_id) == 1:
        return by_id[0], {"source": "auto_by_id", "stable_by_id": True}
    tty_usb = sorted(glob.glob("/dev/ttyUSB*"))
    if not by_id and len(tty_usb) == 1:
        return tty_usb[0], {
            "source": "existing_nexarm_module_fallback",
            "stable_by_id": False,
        }
    return None, {"source": "not_found", "by_id_candidates": by_id, "tty_usb": tty_usb}


def magnet_processes() -> list[str]:
    completed = subprocess.run(
        ["ps", "-eo", "pid=,user=,args="],
        check=True,
        text=True,
        capture_output=True,
    )
    found = []
    for line in completed.stdout.splitlines():
        lower = line.lower()
        if any(term in lower for term in MAGNET_PROCESS_TERMS):
            found.append(line.strip())
    return found


def write_image(path: Path, frame) -> None:
    if frame is None or getattr(frame, "shape", None) is None:
        raise RuntimeError(f"invalid image for {path.name}")
    if not cv2.imwrite(str(path), frame):
        raise RuntimeError(f"cv2.imwrite failed: {path}")


def write_report(run_dir: Path, report: dict[str, Any]) -> None:
    report["updated_at"] = datetime.now().astimezone().isoformat()
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    checks = report.get("checks", {})
    lines = [
        "# K230 + NexArm 机械臂安全复位测试报告",
        "",
        f"- 运行 ID：`{report['run_id']}`",
        f"- 状态：**{report.get('status', 'UNKNOWN')}**",
        f"- 是否机械运动：{'是' if report.get('motion_executed') else '否'}",
        "- 是否调用电磁铁：否",
        "- 是否运行完整 Q1：否",
        "",
        "## 预检",
        "",
    ]
    for name, value in checks.items():
        lines.append(f"- `{name}`：{value.get('status')} — {value.get('detail')}")
    lines.extend(
        [
            "",
            "## 位姿记录",
            "",
            "```json",
            json.dumps(report.get("poses", []), ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "## 错误",
            "",
            report.get("error") or "无",
            "",
        ]
    )
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def print_checks(checks: dict[str, dict[str, Any]]) -> None:
    print("\n=== 无运动预检结果 ===")
    for name, value in checks.items():
        print(f"[{value['status']}] {name}: {value['detail']}")


def main(argv=None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[2]
    config = load_config(project_root, args.config)
    run_id, run_dir, logger = make_run_layout(project_root)
    report: dict[str, Any] = {
        "run_id": run_id,
        "project_root": str(project_root),
        "run_dir": str(run_dir),
        "config": config,
        "status": "INITIALIZING",
        "motion_executed": False,
        "magnet_called": False,
        "full_q1_executed": False,
        "checks": {},
        "poses": [],
        "images": {},
        "last_target_pose": None,
        "error": None,
    }
    checks = report["checks"]
    camera: K230SnapshotAdapter | None = None
    arm: NexArmResetController | None = None
    motion_started = False

    home = Pose.from_sequence(config["home_pose"][:6])
    if "observe_pose" in config:
        raise RuntimeError(
            "robot_config.json must not define observe_pose; home_pose is the only reset/photo pose"
        )
    camera_port = str(config["camera_port"])
    nexarm_port, port_info = discover_nexarm_port(
        args.nexarm_port or config.get("nexarm_port")
    )

    try:
        logger.info("run initialized: %s", run_dir)
        checks["k230_fixed_by_id"] = result(
            camera_port
            == "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A028646-if00"
            and str(Path(camera_port).resolve()) != "/dev/ttyACM0",
            camera_port,
        )
        checks["k230_device_free"] = check_device(camera_port)
        if nexarm_port is None:
            checks["nexarm_device_free"] = result(False, port_info)
        else:
            checks["nexarm_device_free"] = check_device(nexarm_port)
            checks["nexarm_device_free"]["detail"]["discovery"] = port_info

        running_magnets = magnet_processes()
        checks["no_magnet_process"] = result(
            not running_magnets, running_magnets or "no matching process"
        )

        checks["motion_duration_config"] = result(
            int(config["move_duration_ms"]) > 0,
            {
                "move_duration_ms": config["move_duration_ms"],
                "pre_home_controller_writes": [],
            },
        )

        if checks["k230_device_free"]["status"] == "PASS":
            try:
                camera = K230SnapshotAdapter(project_root, camera_port)
                camera_info = camera.open_and_check()
                checks["k230_ping_status"] = result(True, camera_info)
                frame = camera.capture()
                height, width = frame.shape[:2]
                checks["k230_warm_capture_1280x720"] = result(
                    (width, height) == (1280, 720),
                    {
                        "actual": [width, height],
                        "meta": camera.last_meta,
                    },
                )
                warmup_path = run_dir / "captures" / "warmup.jpg"
                write_image(warmup_path, frame)
                report["images"]["warmup"] = str(warmup_path)
            except Exception as exc:
                checks["k230_ping_status"] = result(False, repr(exc))
                checks["k230_warm_capture_1280x720"] = result(False, "not captured")
                logger.exception("K230 preflight failed")
        else:
            checks["k230_ping_status"] = result(False, "device precheck failed")
            checks["k230_warm_capture_1280x720"] = result(False, "device precheck failed")

        if nexarm_port and checks["nexarm_device_free"]["status"] == "PASS":
            try:
                arm = NexArmResetController(
                    project_root,
                    nexarm_port,
                    move_duration_ms=int(config["move_duration_ms"]),
                    position_tolerance_mm=float(config["position_tolerance_mm"]),
                    orientation_tolerance_deg=float(
                        config["orientation_tolerance_deg"]
                    ),
                    stable_samples=int(config["stable_samples"]),
                    motion_timeout_s=float(config["motion_timeout_s"]),
                )
                arm_info = arm.open_and_check()
                checks["nexarm_communication"] = result(True, arm_info)
            except Exception as exc:
                checks["nexarm_communication"] = result(False, repr(exc))
                logger.exception("NexArm communication preflight failed")
        else:
            checks["nexarm_communication"] = result(False, "device precheck failed")

        confirmed = args.confirm == CONFIRM_TOKEN
        checks["human_camera_bracket_and_cable_clearance"] = result(
            confirmed,
            (
                "operator attested by RUN_ARM_RESET"
                if confirmed
                else "inspect bracket/cable clearance before confirmation"
            ),
            manual=not confirmed,
        )
        checks["human_workspace_clear"] = result(
            confirmed,
            (
                "operator attested by RUN_ARM_RESET"
                if confirmed
                else "remove people and obstacles before confirmation"
            ),
            manual=not confirmed,
        )
        print_checks(checks)

        automated_failures = [
            name
            for name, value in checks.items()
            if not name.startswith("human_") and value["status"] != "PASS"
        ]
        if automated_failures:
            report["status"] = "PREFLIGHT_FAILED_NO_MOTION"
            report["error"] = "failed checks: " + ", ".join(automated_failures)
            logger.error(report["error"])
            return 1
        if not confirmed:
            report["status"] = "PREFLIGHT_PASSED_AWAITING_RUN_ARM_RESET"
            logger.info(
                "Automated preflight passed. Re-run with --confirm %s after physical checks.",
                CONFIRM_TOKEN,
            )
            return 0
        if arm is None or camera is None:
            raise RuntimeError("internal preflight error: camera or arm is not open")

        logger.warning("RUN_ARM_RESET accepted; starting fixed low-speed sequence")
        report["last_target_pose"] = home.as_dict()
        motion_started = True
        report["motion_executed"] = True
        arm.send_pose(home)
        try:
            actual, error = arm.wait_until_idle(home)
        except (TimeoutError, StaleFeedbackError):
            # The command has already exceeded its hard timeout. Send no further
            # motion, but preserve a photo and structured feedback for pose tuning.
            try:
                actual = arm.read_pose(timeout=1.0)
                error = pose_error(actual, home)
                report["poses"].append(
                    {
                        "name": "home_timeout",
                        "target": home.as_dict(),
                        "actual": actual.as_dict(),
                        "error": error.as_dict(),
                        "arrival_result": arm.arrival_result,
                        "max_observed_feedback_delta_mm": arm.max_observed_feedback_delta_mm,
                        "max_observed_servo_delta": arm.max_observed_servo_delta,
                        "command_start_pose": (
                            None
                            if arm.command_start_pose is None
                            else arm.command_start_pose.as_dict()
                        ),
                        "feedback_samples": list(arm.feedback_samples),
                        "last_feedback_meta": dict(arm.last_feedback_meta),
                    }
                )
                time.sleep(float(config.get("capture_settle_s", 1.0)))
                frame = camera.capture()
                image_path = run_dir / "captures" / "home_timeout.jpg"
                write_image(image_path, frame)
                report["images"]["home_timeout"] = str(image_path)
                logger.warning(
                    "HOME arrival timed out; fault image saved: %s", image_path
                )
            except Exception:
                logger.exception("failed to capture HOME timeout evidence")
            raise
        report["poses"].append(
            {
                "name": "home",
                "target": home.as_dict(),
                "actual": actual.as_dict(),
                "error": error.as_dict(),
                "arrival_result": arm.arrival_result,
                "max_observed_feedback_delta_mm": arm.max_observed_feedback_delta_mm,
                "max_observed_servo_delta": arm.max_observed_servo_delta,
                "command_start_pose": (
                    None
                    if arm.command_start_pose is None
                    else arm.command_start_pose.as_dict()
                ),
                "feedback_samples": list(arm.feedback_samples),
                "last_feedback_meta": dict(arm.last_feedback_meta),
            }
        )
        time.sleep(float(config.get("capture_settle_s", 1.0)))
        frame = camera.capture()
        image_path = run_dir / "captures" / "home.jpg"
        write_image(image_path, frame)
        report["images"]["home"] = str(image_path)
        logger.info("home reached: error=%s", error.as_dict())

        report["status"] = "COMPLETED"
        logger.info("HOME reset/photo completed")
        return 0
    except KeyboardInterrupt:
        report["status"] = "ABORTED_NO_FURTHER_POSE"
        report["error"] = "KeyboardInterrupt; no further pose commands sent"
        logger.error(report["error"])
        return 130
    except Exception as exc:
        report["status"] = (
            "MOTION_ABORTED_NO_FURTHER_POSE"
            if motion_started
            else "PREFLIGHT_EXCEPTION_NO_MOTION"
        )
        report["error"] = f"{type(exc).__name__}: {exc}"
        logger.error("%s\n%s", report["error"], traceback.format_exc())
        # Deliberately no automatic recovery move: after an unknown fault, clearance
        # cannot be confirmed by software. Closing communication is the safe default.
        return 1
    finally:
        if arm is not None:
            report["last_target_pose"] = (
                None if arm.last_target is None else arm.last_target.as_dict()
            )
        try:
            if camera is not None:
                camera.close()
        except Exception:
            logger.exception("camera close failed")
        try:
            if arm is not None:
                arm.close()
        except Exception:
            logger.exception("arm close failed")
        write_report(run_dir, report)
        logger.info("report written: %s", run_dir / "report.md")


if __name__ == "__main__":
    raise SystemExit(main())
