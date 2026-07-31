"""NexArm真实SDK适配层；实例化不连接，且不含虚构文本协议。"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import numpy as np

from ..models import ExecutionResult, RobotPose, SingleMovePlan
from ..runtime_config import Q1RuntimeConfig


SDK_RELATIVE_PATH = Path(
    "hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py"
)

class NexArmRobotExecutor:
    def __init__(self, project_root: Path, config: Q1RuntimeConfig) -> None:
        self.project_root = project_root
        self.config = config
        self.client = None
        self._last_pose: np.ndarray | None = None
        self._last_actual: np.ndarray | None = None
        self._last_servos: tuple[int, ...] = ()
        self._last_feedback_meta: dict | None = None
        self._initial_status: dict | None = None
        self._last_command_started_s: float | None = None
        self._last_command_duration_s: float = 0.0
        self._motion_attempts: list[dict] = []
        self._active_motion_attempt: dict | None = None

    def initialize(self) -> None:
        blockers = self.config.real_run_blockers()
        if blockers:
            raise RuntimeError("; ".join(blockers))
        sdk_path = self.project_root / SDK_RELATIVE_PATH
        spec = importlib.util.spec_from_file_location("q1_nexarm_vendor_sdk", sdk_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"NexArm SDK无法加载: {sdk_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.client = module.NexArmClient(self.config.nexarm_port)
        self.client.open()
        self.move_to_observe_pose()
        try:
            firmware = self.client.get_firmware_version(timeout=1.0)
            current = self.client.get_current_coords(timeout=1.0)
            initial = self._coords_array(current)
            if not np.all(np.isfinite(initial)):
                raise RuntimeError(f"invalid initial pose feedback: {initial.tolist()}")
            self._last_actual = initial.copy()
            self._last_servos = tuple(
                int(value) for value in getattr(current, "servo_positions", ())
            )
            self._last_feedback_meta = dict(getattr(current, "meta", {}) or {})
            self._initial_status = {
                "firmware_version": firmware,
                "initial_pose": initial.tolist(),
                "initial_servo_positions": list(self._last_servos),
                "feedback_meta": self._last_feedback_meta,
            }
        except BaseException:
            self.close()
            raise

    def move_to_observe_pose(self) -> None:
        if self.client is None:
            raise RuntimeError("NexArm未初始化")
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

    @staticmethod
    def _coords_array(current) -> np.ndarray:
        if all(
            hasattr(current, name)
            for name in ("x", "y", "z", "pitch", "roll", "claw")
        ):
            values = [
                current.x,
                current.y,
                current.z,
                current.pitch,
                current.roll,
                current.claw,
            ]
        else:
            values = np.asarray(current, dtype=np.float64).reshape(-1)[:6]
        if len(values) != 6 or any(value is None for value in values):
            raise RuntimeError(f"NexArm coordinate feedback incomplete: {values}")
        return np.asarray(values, dtype=np.float64)

    def _move(self, pose: RobotPose) -> None:
        if self.client is None:
            raise RuntimeError("NexArm未初始化")
        if pose.duration_ms <= 0:
            raise RuntimeError("缺少经验证的动作持续时间")

        self.client.set_pose(
            pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw, pose.duration_ms
        )
        self._last_pose = np.array(
            [pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw],
            dtype=np.float64,
        )
        self._last_command_started_s = time.monotonic()
        self._last_command_duration_s = pose.duration_ms / 1000.0
        self._active_motion_attempt = {
            "target": self._last_pose.tolist(),
            "duration_ms": int(pose.duration_ms),
            "command_outcome": "COMMAND_SENT",
            "command_sent_s": self._last_command_started_s,
            "telemetry_outcome": "WAITING",
            "physical_evidence": "UNPROVEN",
            "result": "WAITING",
        }
        self._motion_attempts.append(self._active_motion_attempt)

    def _move_and_wait(self, pose: RobotPose) -> None:
        self._move(pose)
        command_started = self._last_command_started_s or time.monotonic()
        duration_s = pose.duration_ms / 1000.0
        remaining_s = max(0.0, command_started + duration_s - time.monotonic())
        if remaining_s > 0:
            time.sleep(remaining_s)
        if self._active_motion_attempt is not None:
            self._active_motion_attempt["result"] = "DURATION_ELAPSED"
            self._active_motion_attempt["telemetry_outcome"] = (
                "NOT_USED_FOR_SEQUENCE_CONTROL"
            )
            self._active_motion_attempt["physical_evidence"] = "UNPROVEN"
            self._active_motion_attempt["elapsed_s"] = round(
                max(0.0, time.monotonic() - command_started),
                3,
            )

    def execute_single_move(self, plan: SingleMovePlan, magnet) -> ExecutionResult:
        required = (
            plan.source_pose_robot,
            plan.transfer_pose,
            plan.release_pose,
        )
        if any(pose is None for pose in required):
            return ExecutionResult(False, plan.template_id, "CALIBRATION_REQUIRED")
        magnet_event_start = len(getattr(magnet, "events", []))
        trajectory: list[str] = []
        phase_log: list[dict] = []

        if plan.cycle_index > 0:
            phase_log.append(
                {"phase": "RETURN_TO_BUFFER_BEFORE_PICK", "status": "COMMAND_SENT"}
            )
            self._move_and_wait(plan.transfer_pose)
            trajectory.append("returned_to_buffer_before_pick")

        phase_log.append({"phase": "MOVE_TO_PICK", "status": "COMMAND_SENT"})
        self._move_and_wait(plan.source_pose_robot)
        phase_log.append(
            {
                "phase": "PICK_POSE_DURATION_ELAPSED",
                "status": self._active_motion_attempt.get("result")
                if self._active_motion_attempt
                else "UNKNOWN",
                "attempt": dict(self._active_motion_attempt or {}),
            }
        )
        trajectory.append("pick_pose_duration_elapsed")

        phase_log.append({"phase": "MAGNET_ON", "status": "REQUESTED"})
        with magnet.hold_session():
            if self.config.magnet_settle_ms is None:
                raise RuntimeError("缺少电磁铁吸合稳定时间")
            time.sleep(self.config.magnet_settle_ms / 1000.0)
            magnet.assert_healthy()
            phase_log.append({"phase": "MAGNET_ON", "status": "CONFIRMED"})
            phase_log.append(
                {"phase": "MOVE_TO_BUFFER_WITH_PIECE", "status": "COMMAND_SENT"}
            )
            self._move_and_wait(plan.transfer_pose)
            magnet.assert_healthy()
            phase_log.append({"phase": "MOVE_TO_RELEASE", "status": "COMMAND_SENT"})
            self._move_and_wait(plan.release_pose)
            magnet.assert_healthy()
            phase_log.append(
                {
                    "phase": "RELEASE_POSE_DURATION_ELAPSED",
                    "status": self._active_motion_attempt.get("result")
                    if self._active_motion_attempt
                    else "UNKNOWN",
                    "attempt": dict(self._active_motion_attempt or {}),
                }
            )
            trajectory.append("buffer_then_release_pose_durations_elapsed")
        phase_log.append({"phase": "MAGNET_OFF", "status": "CONFIRMED"})
        if self.config.magnet_release_settle_ms is None:
            raise RuntimeError("缺少电磁铁释放稳定时间")
        time.sleep(self.config.magnet_release_settle_ms / 1000.0)
        trajectory.append("magnet_off_after_release_pose_duration")
        return ExecutionResult(
            True,
            plan.template_id,
            "trajectory durations elapsed; physical pick still requires visual verification",
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
                "magnet_events": list(getattr(magnet, "events", []))[magnet_event_start:],
            },
        )

    def emergency_stop(self) -> None:
        # 厂商Python SDK未暴露急停/扭矩关闭接口；关闭通信，硬件急停由上层门禁处理。
        if self.client is not None:
            self.client.close()
            self.client = None

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
