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

# Feedback that never leaves the pre-command snapshot after a large move is a
# hardware/firmware freshness fault, not proof that the arm stayed still.
MIN_FEEDBACK_CHANGE_MM = 1.0
POST_DURATION_SETTLE_S = 0.35
POLL_INTERVAL_S = 0.20


class StaleFeedbackError(RuntimeError):
    """Raised when post-command telemetry cannot be proven fresh."""


class NexArmRobotExecutor:
    def __init__(self, project_root: Path, config: Q1RuntimeConfig) -> None:
        self.project_root = project_root
        self.config = config
        self.client = None
        self._last_pose: np.ndarray | None = None
        self._last_actual: np.ndarray | None = None
        self._last_servos: tuple[int, ...] = ()
        self._last_error: dict | None = None
        self._last_feedback_meta: dict | None = None
        self._initial_status: dict | None = None
        self._last_command_started_s: float | None = None
        self._last_command_duration_s: float = 0.0
        self._motion_attempts: list[dict] = []
        self._active_motion_attempt: dict | None = None
        self._motion_health_check = None

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
            if self.config.global_acceleration is None:
                raise RuntimeError("missing global_acceleration")
            if not 1 <= int(self.config.global_acceleration) <= 255:
                raise RuntimeError(
                    f"global_acceleration outside SDK range: {self.config.global_acceleration}"
                )
            self.client.set_global_acceleration(int(self.config.global_acceleration))
            self._initial_status = {
                "firmware_version": firmware,
                "initial_pose": initial.tolist(),
                "initial_servo_positions": list(self._last_servos),
                "global_acceleration": int(self.config.global_acceleration),
                "feedback_meta": self._last_feedback_meta,
            }
        except BaseException:
            self.close()
            raise

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

    def _read_feedback(self, timeout: float) -> tuple[np.ndarray, tuple[int, ...], dict]:
        if self.client is None:
            raise RuntimeError("NexArm未初始化")
        current = self.client.get_current_coords(timeout=timeout)
        coords = self._coords_array(current)
        servos = tuple(int(value) for value in getattr(current, "servo_positions", ()))
        meta = dict(getattr(current, "meta", {}) or {})
        # A reply whose request timestamp is missing cannot prove freshness.
        if meta.get("request_started_s") is None or meta.get("response_received_s") is None:
            raise StaleFeedbackError(
                "STALE_FEEDBACK_HARDWARE_FAULT: coordinate reply lacks request/response "
                f"timestamps; meta={meta}"
            )
        self._last_actual = coords
        self._last_servos = servos
        self._last_feedback_meta = meta
        return coords, servos, meta

    def _move(self, pose: RobotPose) -> None:
        if self.client is None:
            raise RuntimeError("NexArm未初始化")
        if pose.duration_ms <= 0:
            raise RuntimeError("缺少经验证的动作持续时间")
        limits = self.config.workspace_limits or {}
        axes = (
            ("x", pose.x),
            ("y", pose.y),
            ("z", pose.z),
            ("pitch", pose.pitch),
            ("roll", pose.roll),
            ("claw", pose.claw),
        )
        for axis, value in axes:
            if axis not in limits or not limits[axis][0] <= value <= limits[axis][1]:
                raise RuntimeError(f"坐标越界或缺少{axis}工作区限制: {value}")

        # Capture a fresh pre-command snapshot after flushing RX.
        start_coords, start_servos, start_meta = self._read_feedback(timeout=0.5)
        flushed_before_command = 0
        if hasattr(self.client, "flush_input_buffer"):
            flushed_before_command = int(self.client.flush_input_buffer())

        self.client.set_pose(
            pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw, pose.duration_ms
        )
        self._last_pose = np.array(
            [pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw],
            dtype=np.float64,
        )
        self._last_command_started_s = time.monotonic()
        self._last_command_duration_s = pose.duration_ms / 1000.0
        start_error = float(np.linalg.norm(start_coords[:3] - self._last_pose[:3]))
        self._active_motion_attempt = {
            "target": self._last_pose.tolist(),
            "duration_ms": int(pose.duration_ms),
            "command_outcome": "COMMAND_SENT",
            "command_sent_s": self._last_command_started_s,
            "command_start_actual": start_coords.tolist(),
            "command_start_servos": list(start_servos),
            "command_start_feedback_meta": start_meta,
            "command_start_target_position_error_mm": start_error,
            "rx_flushed_before_command": flushed_before_command,
            "max_observed_feedback_delta_mm": 0.0,
            "max_observed_servo_delta": 0,
            "samples": [],
            "telemetry_outcome": "WAITING",
            "physical_evidence": "UNPROVEN",
            "result": "WAITING",
        }
        self._motion_attempts.append(self._active_motion_attempt)

    def _classify_success(self, start_error: float | None, max_delta: float) -> str:
        if start_error is None:
            return "REACHED_FEEDBACK_CONFIRMED"
        if (
            max_delta < MIN_FEEDBACK_CHANGE_MM
            and start_error <= self.config.position_tolerance_mm
        ):
            return "ALREADY_IN_TOLERANCE_NO_FEEDBACK_CHANGE"
        return "REACHED_WITH_FEEDBACK_CHANGE"

    def _move_and_wait(self, pose: RobotPose) -> None:
        self._move(pose)
        timeout_s = max(self.config.motion_timeout_s, pose.duration_ms / 1000.0 + 3.0)
        if not self.wait_until_idle(timeout_s):
            result = (
                self._active_motion_attempt.get("result")
                if self._active_motion_attempt is not None
                else "TIMEOUT"
            )
            if result == "STALE_FEEDBACK_HARDWARE_FAULT":
                raise StaleFeedbackError(
                    "STALE_FEEDBACK_HARDWARE_FAULT: out-of-tolerance command produced no "
                    "fresh coordinate/servo change after the command; magnet remains off "
                    "and no subsequent pose will be sent; "
                    f"last_target={self._last_pose.tolist() if self._last_pose is not None else None}; "
                    f"last_actual={self._last_actual.tolist() if self._last_actual is not None else None}; "
                    f"last_error={self._last_error}; attempt={self._active_motion_attempt}"
                )
            prefix = (
                "NEXARM_NO_FEEDBACK_CHANGE"
                if result == "NO_FEEDBACK_CHANGE_TIMEOUT"
                else "NEXARM_TIMEOUT"
            )
            raise TimeoutError(
                f"{prefix}: target not confirmed by fresh feedback; "
                "no subsequent pose will be sent; "
                f"last_target={self._last_pose.tolist() if self._last_pose is not None else None}; "
                f"last_actual={self._last_actual.tolist() if self._last_actual is not None else None}; "
                f"last_error={self._last_error}; result={result}"
            )

    def move_to_observe_pose(self) -> None:
        values = self.config.observe_pose
        duration_ms = int(self.config.move_duration_ms or values[6])
        self._move_and_wait(
            RobotPose(
                float(values[0]),
                float(values[1]),
                float(values[2]),
                float(values[3]),
                float(values[4]),
                float(values[5]),
                duration_ms,
            )
        )

    def wait_until_idle(self, timeout_s: float) -> bool:
        if self.client is None or self._last_pose is None:
            return False
        command_started = (
            self._last_command_started_s
            if self._last_command_started_s is not None
            else time.monotonic()
        )
        deadline = command_started + timeout_s
        completion_not_before = command_started + self._last_command_duration_s
        stable = 0
        last_recorded_elapsed = -1.0
        while time.monotonic() < deadline:
            if self._motion_health_check is not None:
                self._motion_health_check()
            now = time.monotonic()
            # Prefer post-duration settle reads; mid-move polling is diagnostic only.
            if now < completion_not_before:
                time.sleep(min(POLL_INTERVAL_S, completion_not_before - now))
                continue

            # One flush-backed read after the commanded duration completes.
            if last_recorded_elapsed < 0.0:
                time.sleep(POST_DURATION_SETTLE_S)

            coords, servos, meta = self._read_feedback(
                timeout=min(0.5, max(0.1, deadline - time.monotonic()))
            )
            delta = coords - self._last_pose
            position_error = float(np.linalg.norm(delta[:3]))
            pitch_error = float(delta[3])
            roll_error = float(delta[4])
            claw_error = float(delta[5])
            self._last_error = {
                "position_mm": position_error,
                "x": float(delta[0]),
                "y": float(delta[1]),
                "z": float(delta[2]),
                "pitch_deg": pitch_error,
                "roll_deg": roll_error,
                "claw_deg": claw_error,
            }
            position_ok = position_error <= self.config.position_tolerance_mm
            orientation_ok = (
                max(abs(pitch_error), abs(roll_error))
                <= self.config.orientation_tolerance_deg
            )
            claw_ok = abs(claw_error) <= self.config.orientation_tolerance_deg
            stable = stable + 1 if position_ok and orientation_ok and claw_ok else 0
            now = time.monotonic()
            elapsed = max(0.0, now - command_started)
            if self._active_motion_attempt is not None:
                start_actual = self._active_motion_attempt.get("command_start_actual")
                start_servos = self._active_motion_attempt.get("command_start_servos") or []
                if start_actual is not None:
                    observed = float(
                        np.linalg.norm(
                            coords[:3] - np.asarray(start_actual, dtype=np.float64)[:3]
                        )
                    )
                    self._active_motion_attempt["max_observed_feedback_delta_mm"] = max(
                        float(
                            self._active_motion_attempt.get(
                                "max_observed_feedback_delta_mm", 0.0
                            )
                        ),
                        observed,
                    )
                if start_servos and servos and len(start_servos) == len(servos):
                    servo_delta = max(
                        abs(int(a) - int(b)) for a, b in zip(servos, start_servos)
                    )
                    self._active_motion_attempt["max_observed_servo_delta"] = max(
                        int(
                            self._active_motion_attempt.get(
                                "max_observed_servo_delta", 0
                            )
                        ),
                        servo_delta,
                    )
                if (
                    last_recorded_elapsed < 0.0
                    or elapsed - last_recorded_elapsed >= 0.25
                ):
                    self._active_motion_attempt["samples"].append(
                        {
                            "elapsed_s": round(elapsed, 3),
                            "actual": coords.tolist(),
                            "error": dict(self._last_error),
                            "servo_positions": list(servos),
                            "feedback_meta": meta,
                        }
                    )
                    last_recorded_elapsed = elapsed

            if stable >= self.config.idle_stable_samples:
                if self._active_motion_attempt is not None:
                    max_delta = float(
                        self._active_motion_attempt.get(
                            "max_observed_feedback_delta_mm", 0.0
                        )
                    )
                    servo_delta = int(
                        self._active_motion_attempt.get(
                            "max_observed_servo_delta", 0
                        )
                    )
                    start_error = self._active_motion_attempt.get(
                        "command_start_target_position_error_mm"
                    )
                    required_travel = (
                        float(start_error)
                        if start_error is not None
                        else 0.0
                    )
                    if (
                        required_travel > self.config.position_tolerance_mm
                        and max_delta < MIN_FEEDBACK_CHANGE_MM
                        and servo_delta < 1
                    ):
                        self._active_motion_attempt["result"] = (
                            "STALE_FEEDBACK_HARDWARE_FAULT"
                        )
                        self._active_motion_attempt["telemetry_outcome"] = (
                            "FEEDBACK_STATIC_AFTER_LARGE_COMMAND"
                        )
                        self._active_motion_attempt["physical_evidence"] = "UNPROVEN"
                        self._active_motion_attempt["elapsed_s"] = round(elapsed, 3)
                        return False
                    result = self._classify_success(
                        None if start_error is None else float(start_error),
                        max_delta,
                    )
                    self._active_motion_attempt["result"] = result
                    self._active_motion_attempt["telemetry_outcome"] = result
                    self._active_motion_attempt["physical_evidence"] = "UNPROVEN"
                    self._active_motion_attempt["elapsed_s"] = round(elapsed, 3)
                return True
            time.sleep(POLL_INTERVAL_S)

        if self._active_motion_attempt is not None:
            max_delta = float(
                self._active_motion_attempt.get("max_observed_feedback_delta_mm", 0.0)
            )
            servo_delta = int(
                self._active_motion_attempt.get("max_observed_servo_delta", 0)
            )
            start_error = self._active_motion_attempt.get(
                "command_start_target_position_error_mm"
            )
            required_travel = float(start_error) if start_error is not None else 0.0
            if (
                required_travel > self.config.position_tolerance_mm
                and max_delta < MIN_FEEDBACK_CHANGE_MM
                and servo_delta < 1
            ):
                result = "STALE_FEEDBACK_HARDWARE_FAULT"
                telemetry = "FEEDBACK_STATIC_AFTER_LARGE_COMMAND"
            elif max_delta < MIN_FEEDBACK_CHANGE_MM:
                result = "NO_FEEDBACK_CHANGE_TIMEOUT"
                telemetry = "FEEDBACK_STATIC"
            else:
                result = "TIMEOUT_AFTER_FEEDBACK_CHANGE"
                telemetry = "FEEDBACK_CHANGED_BUT_TARGET_NOT_CONFIRMED"
            self._active_motion_attempt["result"] = result
            self._active_motion_attempt["telemetry_outcome"] = telemetry
            self._active_motion_attempt["physical_evidence"] = "UNPROVEN"
            self._active_motion_attempt["elapsed_s"] = round(
                max(0.0, time.monotonic() - command_started),
                3,
            )
        return False

    def execute_single_move(self, plan: SingleMovePlan, magnet) -> ExecutionResult:
        required = (plan.source_pose_robot, plan.target_pose_robot, plan.release_pose)
        if any(pose is None for pose in required):
            return ExecutionResult(False, plan.template_id, "CALIBRATION_REQUIRED")
        magnet_event_start = len(getattr(magnet, "events", []))
        trajectory: list[str] = []
        phase_log: list[dict] = []

        # 1) Reach source pose and confirm fresh feedback before any magnet ON.
        phase_log.append({"phase": "MOVE_TO_PICK", "status": "COMMAND_SENT"})
        self._move_and_wait(plan.source_pose_robot)
        phase_log.append(
            {
                "phase": "PICK_POSE_FEEDBACK_CONFIRMED",
                "status": self._active_motion_attempt.get("result")
                if self._active_motion_attempt
                else "UNKNOWN",
                "attempt": dict(self._active_motion_attempt or {}),
            }
        )
        trajectory.append("direct_home_to_pick_pose_feedback_confirmed")

        # 2) Magnet ON only after pick pose confirmation; OFF only after release.
        phase_log.append({"phase": "MAGNET_ON", "status": "REQUESTED"})
        with magnet.hold_session():
            if self.config.magnet_settle_ms is None:
                raise RuntimeError("缺少电磁铁吸合稳定时间")
            time.sleep(self.config.magnet_settle_ms / 1000.0)
            magnet.assert_healthy()
            phase_log.append({"phase": "MAGNET_ON", "status": "CONFIRMED"})
            self._motion_health_check = magnet.assert_healthy
            try:
                magnet.assert_healthy()
                phase_log.append({"phase": "MOVE_TO_RELEASE", "status": "COMMAND_SENT"})
                self._move_and_wait(plan.release_pose)
                phase_log.append(
                    {
                        "phase": "RELEASE_POSE_FEEDBACK_CONFIRMED",
                        "status": self._active_motion_attempt.get("result")
                        if self._active_motion_attempt
                        else "UNKNOWN",
                        "attempt": dict(self._active_motion_attempt or {}),
                    }
                )
                trajectory.append("direct_pick_to_release_pose_feedback_confirmed")
            finally:
                self._motion_health_check = None
        phase_log.append({"phase": "MAGNET_OFF", "status": "CONFIRMED"})
        if self.config.magnet_release_settle_ms is None:
            raise RuntimeError("缺少电磁铁释放稳定时间")
        time.sleep(self.config.magnet_release_settle_ms / 1000.0)
        trajectory.append("magnet_off_at_reached_release_pose")
        return ExecutionResult(
            True,
            plan.template_id,
            "trajectory feedback-confirmed; physical pick still requires visual verification",
            False,
            {
                "magnet_backend": self.config.magnet_backend,
                "physical_pick_enabled": True,
                "physical_pick_verified": False,
                "physical_pick_verification": "PENDING_POST_MOVE_VISUAL_AUDIT",
                "physical_evidence": "UNPROVEN",
                "trajectory_steps": trajectory,
                "phase_log": phase_log,
                "motion_attempts": list(self._motion_attempts),
                "magnet_events": list(getattr(magnet, "events", []))[magnet_event_start:],
            },
        )

    def execute_release_recovery(self, plan: SingleMovePlan, attempt: int) -> ExecutionResult:
        return ExecutionResult(
            False,
            plan.template_id,
            "DIRECT_POSE_MODE: release recovery is disabled until a non-axis-separated "
            "recovery trajectory is calibrated",
            False,
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
