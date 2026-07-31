"""NexArm executor for the production Q1 pick-and-place sequence."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import numpy as np

from ..models import ExecutionResult, RobotPose, SingleMovePlan
from ..runtime_config import Q1RuntimeConfig
from ..wrist import normalize_angle_deg


SDK_RELATIVE_PATH = Path("hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py")
ROLL_EPS_DEG = 1.0


class NexArmRobotExecutor:
    def __init__(self, project_root: Path, config: Q1RuntimeConfig) -> None:
        self.project_root = project_root
        self.config = config
        self.client = None
        self._last_pose: np.ndarray | None = None
        self._last_actual = None
        self._initial_status: dict | None = None
        self._last_command_started_s: float | None = None
        self._motion_attempts: list[dict] = []
        self._active_motion_attempt: dict | None = None

    def initialize(self) -> None:
        blockers = self.config.real_run_blockers()
        if blockers:
            raise RuntimeError("; ".join(blockers))
        sdk_path = self.project_root / SDK_RELATIVE_PATH
        spec = importlib.util.spec_from_file_location("q1_nexarm_vendor_sdk", sdk_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load NexArm SDK: {sdk_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.client = module.NexArmClient(self.config.nexarm_port)
        self.client.open()
        try:
            self.move_to_observe_pose()
            self._initial_status = {
                "home_command_completed": True,
                "arrival_basis": "controller duration plus settle elapsed",
            }
        except BaseException:
            self.close()
            raise

    def move_to_observe_pose(self) -> None:
        if self.client is None:
            raise RuntimeError("NexArm is not initialized")
        values = self.config.observe_pose
        self._move_and_wait(
            RobotPose(
                float(values[0]),
                float(values[1]),
                float(values[2]),
                float(values[3]),
                float(values[4]),
                float(values[5]),
                int(values[6]),
            )
        )

    def _move(self, pose: RobotPose) -> None:
        if self.client is None:
            raise RuntimeError("NexArm is not initialized")
        if pose.duration_ms <= 0:
            raise RuntimeError("NexArm move duration must be positive")

        self.client.set_pose(
            pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw, pose.duration_ms
        )
        self._last_pose = np.asarray(
            [pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw],
            dtype=np.float64,
        )
        self._last_command_started_s = time.monotonic()
        self._active_motion_attempt = {
            "target": self._last_pose.tolist(),
            "duration_ms": int(pose.duration_ms),
            "command_outcome": "COMMAND_SENT",
            "command_sent_s": self._last_command_started_s,
            "telemetry_outcome": "NOT_USED_FOR_SEQUENCE_CONTROL",
            "physical_evidence": "UNPROVEN",
            "result": "WAITING",
        }
        self._motion_attempts.append(self._active_motion_attempt)

    def _move_and_wait(self, pose: RobotPose) -> None:
        self._move(pose)
        command_started = self._last_command_started_s or time.monotonic()
        duration_s = pose.duration_ms / 1000.0
        settle_s = self.config.post_move_settle_ms / 1000.0
        remaining_s = max(0.0, command_started + duration_s - time.monotonic())
        if remaining_s > 0:
            time.sleep(remaining_s)
        if settle_s > 0:
            time.sleep(settle_s)
        if self._active_motion_attempt is not None:
            self._active_motion_attempt.update(
                {
                    "result": "DURATION_AND_SETTLE_ELAPSED",
                    "post_move_settle_s": settle_s,
                    "elapsed_s": round(
                        max(0.0, time.monotonic() - command_started), 3
                    ),
                }
            )

    def execute_single_move(self, plan: SingleMovePlan, magnet) -> ExecutionResult:
        required = (
            plan.source_pose_robot,
            plan.approach_pose,
            plan.transfer_pose,
            plan.release_pose,
        )
        if any(pose is None for pose in required):
            return ExecutionResult(False, plan.template_id, "CALIBRATION_REQUIRED")

        pick = plan.source_pose_robot
        pick_ready = plan.approach_pose
        transit = plan.transfer_pose
        release = plan.release_pose
        assert pick is not None and pick_ready is not None
        assert transit is not None and release is not None

        lift = RobotPose(
            pick.x,
            pick.y,
            float(self.config.transfer_transit_z),
            pick.pitch,
            pick.roll,
            pick.claw,
            int(self.config.transfer_lift_duration_ms),
        )
        place_ready = RobotPose(
            release.x,
            release.y,
            release.z + float(self.config.transfer_approach_dz_mm),
            release.pitch,
            release.roll,
            release.claw,
            int(self.config.transfer_move_duration_ms),
        )
        done_lift = RobotPose(
            release.x,
            release.y,
            float(self.config.transfer_transit_z),
            release.pitch,
            release.roll,
            release.claw,
            int(self.config.transfer_lift_duration_ms),
        )

        magnet_event_start = len(getattr(magnet, "events", []))
        trajectory: list[str] = []
        phase_log: list[dict] = []

        def move_phase(phase: str, pose: RobotPose) -> None:
            entry = {"phase": phase, "status": "COMMAND_SENT"}
            phase_log.append(entry)
            self._move_and_wait(pose)
            entry["status"] = (
                self._active_motion_attempt.get("result")
                if self._active_motion_attempt
                else "UNKNOWN"
            )
            entry["attempt"] = dict(self._active_motion_attempt or {})
            trajectory.append(phase)

        move_phase("MOVE_TO_PICK_READY", pick_ready)
        move_phase("DESCEND_PICK", pick)

        phase_log.append({"phase": "MAGNET_ON", "status": "REQUESTED"})
        with magnet.hold_session():
            if self.config.magnet_settle_ms is None:
                raise RuntimeError("Missing magnet settle duration")
            time.sleep(self.config.magnet_settle_ms / 1000.0)
            magnet.assert_healthy()
            phase_log[-1]["status"] = "CONFIRMED"

            move_phase("LIFT_PICK", lift)
            roll_delta = normalize_angle_deg(release.roll - pick.roll)
            if abs(roll_delta) >= ROLL_EPS_DEG:
                if plan.rotate_pose is None:
                    raise RuntimeError("Missing rotate pose")
                move_phase("ROTATE_IN_AIR", plan.rotate_pose)
            else:
                phase_log.append({"phase": "ROTATE_IN_AIR", "status": "SKIPPED"})

            magnet.assert_healthy()
            move_phase("TRANSIT_TO_PLACE", transit)
            move_phase("MOVE_TO_PLACE_READY", place_ready)
            move_phase("DESCEND_PLACE", release)
            magnet.assert_healthy()

        phase_log.append({"phase": "MAGNET_OFF", "status": "CONFIRMED"})
        if self.config.magnet_release_settle_ms is None:
            raise RuntimeError("Missing magnet release settle duration")
        time.sleep(self.config.magnet_release_settle_ms / 1000.0)
        move_phase("DONE_LIFT", done_lift)

        return ExecutionResult(
            True,
            plan.template_id,
            "pintu transfer sequence completed",
            False,
            {
                "magnet_backend": self.config.magnet_backend,
                "physical_pick_enabled": True,
                "physical_pick_verified": False,
                "physical_pick_verification": (
                    "NOT_PERFORMED_BY_SINGLE_OBSERVATION_WORKFLOW"
                ),
                "physical_evidence": "UNPROVEN",
                "trajectory_steps": trajectory,
                "phase_log": phase_log,
                "motion_attempts": list(self._motion_attempts),
                "magnet_events": list(getattr(magnet, "events", []))[
                    magnet_event_start:
                ],
            },
        )

    def emergency_stop(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
