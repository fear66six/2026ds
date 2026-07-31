#!/usr/bin/env python3
"""Watch wrist roll direction: HOME roll=0 then HOME XY/Z/pitch with roll=+90.

No magnet. Without the exact confirm token, prints the plan and exits with no
serial open and no motion.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

CONFIRM_TOKEN = "RUN_ROLL_PLUS90"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Send one +90 deg wrist roll at HOME XYZ/pitch so you can see "
            "whether positive roll is clockwise or counter-clockwise from above."
        )
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"exactly {CONFIRM_TOKEN} authorizes motion",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="robot_config.json path (default: q1/config/robot_config.json)",
    )
    parser.add_argument(
        "--duration-ms",
        type=int,
        default=3000,
        help="set_pose duration for each step (default 3000)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[2]
    cfg_path = args.config or (project_root / "q1" / "config" / "robot_config.json")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    home = list(cfg["home_pose"])
    if len(home) < 6:
        raise SystemExit(f"home_pose needs at least 6 values: {home}")

    x, y, z, pitch, _roll0, claw = (float(v) for v in home[:6])
    duration_ms = int(args.duration_ms)
    pose_zero = (x, y, z, pitch, 0.0, claw, duration_ms)
    pose_plus90 = (x, y, z, pitch, 90.0, claw, duration_ms)

    plan = {
        "mode": "ROLL_DIRECTION_PLUS90",
        "config": str(cfg_path),
        "port": cfg.get("nexarm_port"),
        "convention_in_config": cfg.get("sources", {}).get("wrist"),
        "step1_home_roll0": pose_zero,
        "step2_same_xyz_roll_plus90": pose_plus90,
        "how_to_read": (
            "Look down at the paper/table. After step2, if the wrist/magnet "
            "turned clockwise, positive roll is clockwise; if counter-clockwise, "
            "positive roll is counter-clockwise and wrist_roll_sign should be -1."
        ),
        "confirmation_token": CONFIRM_TOKEN,
    }

    if args.confirm != CONFIRM_TOKEN:
        plan["status"] = "NO_MOTION"
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        print(
            f"\nNo serial opened. To move:\n"
            f"  python3 -m q1.scripts.test_roll_direction --confirm {CONFIRM_TOKEN}",
            file=sys.stderr,
        )
        return 0

    # Lazy import only after confirm so dry-run never touches SDK/hardware.
    from q1.robot import NexArmResetController, Pose

    port = str(cfg["nexarm_port"])
    controller = NexArmResetController(
        project_root,
        port,
        move_duration_ms=duration_ms,
        position_tolerance_mm=float(cfg.get("position_tolerance_mm", 10.0)),
        orientation_tolerance_deg=float(cfg.get("orientation_tolerance_deg", 3.0)),
        stable_samples=int(cfg.get("stable_samples", 3)),
        motion_timeout_s=float(cfg.get("motion_timeout_s", 12.0)),
    )
    opened = controller.open_and_check()
    print(json.dumps({"opened": opened}, ensure_ascii=False, indent=2))
    try:
        print("STEP1: HOME with roll=0 ...", flush=True)
        controller.send_pose(Pose(x, y, z, pitch, 0.0, claw))
        time.sleep(duration_ms / 1000.0 + 0.5)
        print("STEP1 done. Watch the wrist, then STEP2 starts.", flush=True)
        time.sleep(1.0)

        print("STEP2: same XYZ/pitch, roll=+90 ...", flush=True)
        controller.send_pose(Pose(x, y, z, pitch, 90.0, claw))
        time.sleep(duration_ms / 1000.0 + 0.5)
        print(
            "STEP2 done. From above the table: clockwise => +roll is CW; "
            "counter-clockwise => +roll is CCW.",
            flush=True,
        )
    finally:
        controller.close()

    plan["status"] = "MOTION_COMMANDS_SENT"
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
