"""NexArm controller state diagnostic.

Default mode does not open hardware.  With READ_NEXARM_STATE it opens only the
NexArm UART and sends read/query commands.  A HOME SET probe is available, but
it requires a second explicit token and a separate clearance flag.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Any


READ_TOKEN = "READ_NEXARM_STATE"
HOME_SET_TOKEN = "SEND_HOME_READ_GOAL"
SYSTEM_ID = 0xFF


class Cmd:
    FIRMWARE_VERSION_CHECK = 1
    CHECK_BAT_LEVEL = 2
    FKINE_RESULT_GET = 6
    IKINE_RESULT_GET = 7
    COORDINATE_SET = 8
    GET_CUR_COORDS = 11
    SET_POS_OFFSET = 57
    GET_POS_OFFSET = 58
    GET_KINEMATICS_PARAM = 64
    GET_REAL_JOINT_ANGLES = 65
    GET_REAL_TCP_POSE = 66
    GET_COORD_LIMITS = 80
    ACTION_EDIT_STATUS = 127
    SYNC_TEACH_STATUS = 135


class ServoCmd:
    READ = 2


class ServoReg:
    MODE = 33
    TORQUE_ENABLE = 40
    ACC = 41
    GOAL_POSITION_L = 42
    PRESENT_POSITION_L = 56
    PRESENT_VOLTAGE = 62
    PRESENT_TEMPERATURE = 63
    MOVING_STATUS = 66
    PRESENT_CURRENT_L = 69


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "NexArm no-motion controller/servo state diagnostic. Without the "
            f"exact --confirm {READ_TOKEN} token, no serial port is opened."
        )
    )
    parser.add_argument("--confirm", default="")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--nexarm-port")
    parser.add_argument(
        "--home-set-confirm",
        default="",
        help=(
            f"extra token {HOME_SET_TOKEN}; sends the configured HOME pose once "
            "after baseline reads, then reads target/current registers"
        ),
    )
    parser.add_argument(
        "--operator-cleared-home-motion",
        action="store_true",
        help="required together with --home-set-confirm because HOME SET can move the arm",
    )
    return parser.parse_args(argv)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(root: Path, requested: Path | None) -> dict[str, Any]:
    path = requested or root / "q1" / "config" / "robot_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_path"] = str(path)
    return data


def load_sdk(root: Path):
    sdk_path = root / "hardware" / "nexarm" / "jetson_to_nexarm" / "nexarm_sdk.py"
    spec = importlib.util.spec_from_file_location("diag_nexarm_sdk", sdk_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load SDK: {sdk_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_output_path(root: Path) -> Path:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_dir = root / "output" / "diagnostics" / "nexarm_readonly"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{run_id}.json"


def payload_i16(values: list[int | float]) -> bytes:
    return b"".join(struct.pack("<h", int(round(value))) for value in values)


def request_payload(client, cmd: int, payload: bytes = b"", timeout: float = 0.8) -> dict[str, Any]:
    started = time.monotonic()
    try:
        packet = client.request(
            SYSTEM_ID,
            cmd,
            payload,
            expect_reply=True,
            expected_cmd=cmd,
            expected_ids=(SYSTEM_ID, 0x5A),
            timeout=timeout,
            flush_before=True,
        )
        return {
            "ok": True,
            "payload_hex": packet.payload.hex(),
            "payload_len": len(packet.payload),
            "meta": dict(getattr(client, "last_rx_diagnostics", {}) or {}),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics must preserve all failures
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(time.monotonic() - started, 4),
            "meta": dict(getattr(client, "last_rx_diagnostics", {}) or {}),
        }


def decode_i16_list(payload_hex: str) -> list[int]:
    data = bytes.fromhex(payload_hex)
    count = len(data) // 2
    return list(struct.unpack("<" + "h" * count, data[: count * 2]))


def decode_float32_list(payload_hex: str) -> list[float]:
    data = bytes.fromhex(payload_hex)
    count = len(data) // 4
    return [round(value, 5) for value in struct.unpack("<" + "f" * count, data[: count * 4])]


def add_decoded(name: str, item: dict[str, Any]) -> None:
    if not item.get("ok"):
        return
    payload_hex = item["payload_hex"]
    if name in {"current_coords", "ik_home"}:
        vals = decode_i16_list(payload_hex)
        if len(vals) >= 6:
            item["decoded"] = {
                "pose": {
                    "x": vals[1],
                    "y": vals[2],
                    "z": vals[3],
                    "pitch": vals[0] / 10.0,
                    "roll": vals[4],
                    "claw": vals[5],
                },
                "servos": vals[6:12],
            }
    elif name == "real_joint_angles":
        vals = decode_i16_list(payload_hex)
        if len(vals) >= 12:
            item["decoded"] = [
                {"pulse": vals[i * 2], "angle_deg": vals[i * 2 + 1] / 10.0}
                for i in range(6)
            ]
    elif name == "real_tcp_pose":
        vals = decode_i16_list(payload_hex)
        if len(vals) >= 7:
            item["decoded"] = {
                "x": vals[0],
                "y": vals[1],
                "z": vals[2],
                "yaw": vals[3] / 10.0,
                "pitch": vals[4] / 10.0,
                "roll": vals[5] / 10.0,
                "claw": vals[6] / 10.0,
            }
    elif name == "kinematics":
        item["decoded"] = decode_float32_list(payload_hex)
    elif name == "coord_limits":
        vals = decode_i16_list(payload_hex)
        if len(vals) >= 12:
            item["decoded"] = {
                "x": vals[0:2],
                "y": vals[2:4],
                "z": vals[4:6],
                "pitch": [vals[6] / 10.0, vals[7] / 10.0],
                "roll": vals[8:10],
                "claw": vals[10:12],
            }
    elif name == "action_edit_status":
        data = bytes.fromhex(payload_hex)
        if len(data) >= 5:
            item["decoded"] = {
                "edit_mode": data[0],
                "recording": data[1],
                "playback": data[2],
                "frames": data[3] | (data[4] << 8),
            }
    elif name == "sync_teach_status":
        data = bytes.fromhex(payload_hex)
        if len(data) >= 6:
            item["decoded"] = {
                "mode": data[0],
                "recording": data[1],
                "playback": data[2],
                "frames": data[3] | (data[4] << 8),
                "overflow": data[5],
            }


def read_servo_reg(client, servo_id: int, reg: int, length: int, timeout: float = 0.3) -> dict[str, Any]:
    started = time.monotonic()
    try:
        packet = client.request(
            servo_id,
            ServoCmd.READ,
            bytes([reg, length]),
            expect_reply=True,
            expected_cmd=ServoCmd.READ,
            expected_ids=(servo_id,),
            timeout=timeout,
            flush_before=True,
        )
        data = packet.payload
        value: int | None = None
        raw = b""
        if len(data) >= length:
            raw = data[:length]
            if len(data) >= length + 1 and data[0] == reg:
                raw = data[1 : 1 + length]
        if len(raw) == length:
            if length == 1:
                value = raw[0]
            elif length == 2:
                value = struct.unpack("<h", raw)[0]
        return {
            "ok": True,
            "reg": reg,
            "length": length,
            "payload_hex": data.hex(),
            "value": value,
            "meta": dict(getattr(client, "last_rx_diagnostics", {}) or {}),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "reg": reg,
            "length": length,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(time.monotonic() - started, 4),
            "meta": dict(getattr(client, "last_rx_diagnostics", {}) or {}),
        }


def read_servo_matrix(client) -> dict[str, Any]:
    regs = {
        "mode": (ServoReg.MODE, 1),
        "torque_enable": (ServoReg.TORQUE_ENABLE, 1),
        "acc": (ServoReg.ACC, 1),
        "goal_position": (ServoReg.GOAL_POSITION_L, 2),
        "present_position": (ServoReg.PRESENT_POSITION_L, 2),
        "voltage": (ServoReg.PRESENT_VOLTAGE, 1),
        "temperature": (ServoReg.PRESENT_TEMPERATURE, 1),
        "moving_status": (ServoReg.MOVING_STATUS, 1),
        "present_current": (ServoReg.PRESENT_CURRENT_L, 2),
    }
    result: dict[str, Any] = {}
    for servo_id in range(1, 7):
        per_servo = {}
        for label, (reg, length) in regs.items():
            per_servo[label] = read_servo_reg(client, servo_id, reg, length)
        result[str(servo_id)] = per_servo
    return result


def run_readonly(client, home_pose: list[float]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    firmware = client.get_firmware_version(timeout=1.0)
    checks["firmware_version"] = firmware
    try:
        checks["battery_raw"] = client.get_battery_voltage(timeout=1.0)
    except Exception as exc:  # noqa: BLE001
        checks["battery_raw_error"] = f"{type(exc).__name__}: {exc}"

    current = client.get_current_coords(timeout=1.0)
    checks["current_coords_sdk"] = {
        "pose": {
            "x": current.x,
            "y": current.y,
            "z": current.z,
            "pitch": current.pitch,
            "roll": current.roll,
            "claw": current.claw,
        },
        "servos": list(getattr(current, "servo_positions", ()) or ()),
        "meta": dict(getattr(current, "meta", {}) or {}),
    }

    requests = {
        "current_coords": (Cmd.GET_CUR_COORDS, b""),
        "real_joint_angles": (Cmd.GET_REAL_JOINT_ANGLES, b""),
        "real_tcp_pose": (Cmd.GET_REAL_TCP_POSE, b""),
        "pos_offset": (Cmd.GET_POS_OFFSET, b""),
        "kinematics": (Cmd.GET_KINEMATICS_PARAM, b""),
        "coord_limits": (Cmd.GET_COORD_LIMITS, b""),
        "action_edit_status": (Cmd.ACTION_EDIT_STATUS, b""),
        "sync_teach_status": (Cmd.SYNC_TEACH_STATUS, b""),
        "ik_home": (
            Cmd.IKINE_RESULT_GET,
            payload_i16(
                [
                    home_pose[3] * 10.0,
                    home_pose[0],
                    home_pose[1],
                    home_pose[2],
                    home_pose[4],
                    home_pose[5],
                ]
            ),
        ),
    }
    raw_requests = {}
    for name, (cmd, payload) in requests.items():
        item = request_payload(client, cmd, payload, timeout=1.0)
        add_decoded(name, item)
        raw_requests[name] = item
        time.sleep(0.03)
    checks["controller_queries"] = raw_requests
    checks["direct_servo_register_reads"] = read_servo_matrix(client)
    return checks


def send_home_and_probe(client, home_pose: list[float]) -> dict[str, Any]:
    before = read_servo_matrix(client)
    client.set_pose(
        home_pose[0],
        home_pose[1],
        home_pose[2],
        home_pose[3],
        home_pose[4],
        home_pose[5],
        int(home_pose[6]) if len(home_pose) >= 7 else 6000,
    )
    immediate = read_servo_matrix(client)
    time.sleep(0.5)
    after_500ms = read_servo_matrix(client)
    return {
        "target_home": home_pose,
        "before": before,
        "immediate_after_set": immediate,
        "after_500ms": after_500ms,
        "note": "This phase sends CMD_COORDINATE_SET and may move the arm.",
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = project_root()
    cfg = load_config(root, args.config)
    port = args.nexarm_port or cfg["nexarm_port"]
    home_pose = [float(value) for value in cfg["home_pose"]]
    output_path = make_output_path(root)
    report: dict[str, Any] = {
        "mode": "NEXARM_CONTROLLER_STATE_DIAG",
        "created_at": datetime.now().astimezone().isoformat(),
        "output_path": str(output_path),
        "config_path": cfg["_path"],
        "port": port,
        "home_pose": home_pose,
        "hardware_opened": False,
        "motion_command_sent": False,
        "safety": {
            "magnet_called": False,
            "full_q1_executed": False,
            "requires_read_token": READ_TOKEN,
            "requires_home_set_token": HOME_SET_TOKEN,
        },
    }

    if args.confirm != READ_TOKEN:
        report["status"] = "PLAN_ONLY_NO_HARDWARE"
        report["planned_checks"] = [
            "firmware, battery, current coords",
            "real joint angles, real TCP pose",
            "IK result for configured HOME",
            "position offsets, kinematics, board coordinate limits",
            "ACTION_EDIT_STATUS and SYNC_TEACH_STATUS",
            "best-effort direct servo register reads: mode, torque, goal/current position, voltage, temperature, moving status, current",
        ]
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    do_home_set = args.home_set_confirm == HOME_SET_TOKEN
    if do_home_set and not args.operator_cleared_home_motion:
        report["status"] = "REFUSED_HOME_SET_WITHOUT_CLEARANCE"
        report["error"] = (
            "HOME SET can move the arm; pass --operator-cleared-home-motion "
            "after physical clearance inspection."
        )
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    mod = load_sdk(root)
    client = mod.NexArmClient(port)
    client.open()
    report["hardware_opened"] = True
    try:
        report["readonly"] = run_readonly(client, home_pose)
        if do_home_set:
            report["motion_command_sent"] = True
            report["home_set_probe"] = send_home_and_probe(client, home_pose)
        report["status"] = "COMPLETED"
        return 0
    except Exception as exc:  # noqa: BLE001
        report["status"] = "FAILED"
        report["error"] = f"{type(exc).__name__}: {exc}"
        return 1
    finally:
        try:
            client.close()
        finally:
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
