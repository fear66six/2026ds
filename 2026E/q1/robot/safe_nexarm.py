"""Safety-gated wrapper around the existing NexArm UART SDK."""

from __future__ import annotations

import importlib.util
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


MIN_FEEDBACK_CHANGE_MM = 1.0
POST_DURATION_SETTLE_S = 0.35
POLL_INTERVAL_S = 0.20


class StaleFeedbackError(RuntimeError):
    """Raised when post-command telemetry cannot be proven fresh."""


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float
    pitch: float
    roll: float
    claw: float

    @classmethod
    def from_sequence(cls, values) -> "Pose":
        if len(values) != 6:
            raise ValueError(f"Pose must contain 6 values, got {len(values)}")
        return cls(*(float(value) for value in values))

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class PoseError:
    x_mm: float
    y_mm: float
    z_mm: float
    position_mm: float
    pitch_deg: float | None
    roll_deg: float | None
    claw_deg: float | None

    def as_dict(self) -> dict[str, float | None]:
        return asdict(self)


def pose_error(actual: Pose, target: Pose) -> PoseError:
    dx = actual.x - target.x
    dy = actual.y - target.y
    dz = actual.z - target.z
    return PoseError(
        x_mm=dx,
        y_mm=dy,
        z_mm=dz,
        position_mm=math.sqrt(dx * dx + dy * dy + dz * dz),
        pitch_deg=actual.pitch - target.pitch,
        roll_deg=actual.roll - target.roll,
        claw_deg=actual.claw - target.claw,
    )


class NexArmResetController:
    """No connection at import or construction; movement is an explicit call."""

    def __init__(
        self,
        project_root: Path,
        port: str,
        *,
        move_duration_ms: int,
        global_acceleration: int,
        position_tolerance_mm: float,
        orientation_tolerance_deg: float,
        stable_samples: int,
        motion_timeout_s: float,
    ) -> None:
        self.project_root = project_root
        self.port = port
        self.move_duration_ms = move_duration_ms
        self.global_acceleration = global_acceleration
        self.position_tolerance_mm = position_tolerance_mm
        self.orientation_tolerance_deg = orientation_tolerance_deg
        self.stable_samples = stable_samples
        self.motion_timeout_s = motion_timeout_s
        self._module: ModuleType | None = None
        self._client: Any = None
        self.last_target: Pose | None = None
        self.last_actual: Pose | None = None
        self.last_error: PoseError | None = None
        self.last_servo_positions: tuple[int, ...] = ()
        self.last_feedback_meta: dict[str, Any] = {}
        self.feedback_samples: list[dict[str, Any]] = []
        self.max_observed_feedback_delta_mm = 0.0
        self.max_observed_servo_delta = 0
        self.command_started_s: float | None = None
        self.command_start_pose: Pose | None = None
        self.command_start_servos: tuple[int, ...] = ()
        self.arrival_result: str | None = None

    def _load_sdk(self) -> ModuleType:
        sdk_dir = (
            self.project_root
            / "hardware"
            / "nexarm"
            / "jetson_to_nexarm"
        )
        sdk_path = sdk_dir / "nexarm_sdk.py"
        if not sdk_path.is_file():
            raise RuntimeError(f"NexArm SDK missing: {sdk_path}")
        if str(sdk_dir) not in sys.path:
            sys.path.insert(0, str(sdk_dir))
        spec = importlib.util.spec_from_file_location("q1_deployed_nexarm_sdk", sdk_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load NexArm SDK: {sdk_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def open_and_check(self) -> dict[str, Any]:
        self._module = self._load_sdk()
        self._client = self._module.NexArmClient(self.port)
        self._client.open()
        version = self._client.get_firmware_version(timeout=1.0)
        current = self.read_pose(timeout=1.0)
        return {
            "port": self.port,
            "firmware_version": version,
            "current_pose": current.as_dict(),
        }

    def configure_low_acceleration(self) -> None:
        if self._client is None:
            raise RuntimeError("NexArm is not open")
        if not 1 <= self.global_acceleration <= 255:
            raise ValueError("global_acceleration must be in [1, 255]")
        self._client.set_global_acceleration(self.global_acceleration)

    def read_pose(self, timeout: float = 0.5) -> Pose:
        if self._client is None:
            raise RuntimeError("NexArm is not open")
        # get_current_coords flushes RX before the request when the deployed SDK
        # exposes flush_input_buffer; replies still have no sequence id.
        coords = self._client.get_current_coords(timeout=timeout)
        if coords.pitch is None or coords.roll is None or coords.claw is None:
            raise RuntimeError("NexArm coordinate feedback lacks orientation fields")
        meta = dict(getattr(coords, "meta", {}) or {})
        if meta.get("request_started_s") is None or meta.get("response_received_s") is None:
            raise StaleFeedbackError(
                "STALE_FEEDBACK_HARDWARE_FAULT: coordinate reply lacks request/response "
                f"timestamps; meta={meta}"
            )
        pose = Pose(
            float(coords.x),
            float(coords.y),
            float(coords.z),
            float(coords.pitch),
            float(coords.roll),
            float(coords.claw),
        )
        self.last_actual = pose
        self.last_servo_positions = tuple(
            int(value) for value in getattr(coords, "servo_positions", ())
        )
        self.last_feedback_meta = meta
        return pose

    def send_pose(self, target: Pose) -> None:
        if self._client is None:
            raise RuntimeError("NexArm is not open")
        # Fresh pre-command snapshot; get_current_coords already flushes RX.
        self.command_start_pose = self.read_pose(timeout=0.5)
        self.command_start_servos = self.last_servo_positions
        self.last_target = target
        self.feedback_samples = []
        self.max_observed_feedback_delta_mm = 0.0
        self.max_observed_servo_delta = 0
        self.arrival_result = None
        self._client.set_pose(
            target.x,
            target.y,
            target.z,
            target.pitch,
            target.roll,
            target.claw,
            self.move_duration_ms,
        )
        # Stamp after the fire-and-forget write, matching production executor.
        self.command_started_s = time.monotonic()

    def wait_until_idle(self, target: Pose) -> tuple[Pose, PoseError]:
        """Require stable XYZ and orientation feedback, with a hard timeout."""

        if self.command_started_s is None:
            raise RuntimeError("No pose command timestamp is available")
        duration_s = self.move_duration_ms / 1000.0
        timeout_s = max(self.motion_timeout_s, duration_s + 3.0)
        deadline = self.command_started_s + timeout_s
        completion_not_before = self.command_started_s + duration_s
        stable = 0
        last_actual: Pose | None = None
        last_error: PoseError | None = None
        first_post_duration_read = True
        while time.monotonic() < deadline:
            now = time.monotonic()
            # Avoid mid-move spam; only settle-read after the commanded duration.
            if now < completion_not_before:
                time.sleep(min(POLL_INTERVAL_S, completion_not_before - now))
                continue
            if first_post_duration_read:
                time.sleep(POST_DURATION_SETTLE_S)
                first_post_duration_read = False
            actual = self.read_pose(timeout=min(0.5, max(0.1, deadline - time.monotonic())))
            error = pose_error(actual, target)
            now = time.monotonic()
            elapsed = max(0.0, now - self.command_started_s)
            if self.command_start_pose is not None:
                movement = pose_error(actual, self.command_start_pose).position_mm
                self.max_observed_feedback_delta_mm = max(
                    self.max_observed_feedback_delta_mm, movement
                )
            if (
                self.command_start_servos
                and self.last_servo_positions
                and len(self.command_start_servos) == len(self.last_servo_positions)
            ):
                servo_delta = max(
                    abs(int(a) - int(b))
                    for a, b in zip(self.last_servo_positions, self.command_start_servos)
                )
                self.max_observed_servo_delta = max(
                    self.max_observed_servo_delta, servo_delta
                )
            self.feedback_samples.append(
                {
                    "elapsed_s": round(elapsed, 3),
                    "actual": actual.as_dict(),
                    "error": error.as_dict(),
                    "servo_positions": list(self.last_servo_positions),
                    "feedback_meta": dict(self.last_feedback_meta),
                }
            )
            orientation_ok = (
                abs(error.pitch_deg or 0.0) <= self.orientation_tolerance_deg
                and abs(error.roll_deg or 0.0) <= self.orientation_tolerance_deg
                and abs(error.claw_deg or 0.0) <= self.orientation_tolerance_deg
            )
            if error.position_mm <= self.position_tolerance_mm and orientation_ok:
                stable += 1
            else:
                stable = 0
            last_actual, last_error = actual, error
            self.last_error = error
            if stable >= self.stable_samples:
                start_error = (
                    pose_error(self.command_start_pose, target).position_mm
                    if self.command_start_pose is not None
                    else None
                )
                if (
                    start_error is not None
                    and start_error > self.position_tolerance_mm
                    and self.max_observed_feedback_delta_mm < MIN_FEEDBACK_CHANGE_MM
                    and self.max_observed_servo_delta < 1
                ):
                    self.arrival_result = "STALE_FEEDBACK_HARDWARE_FAULT"
                    raise StaleFeedbackError(
                        "STALE_FEEDBACK_HARDWARE_FAULT: out-of-tolerance command produced no "
                        "fresh coordinate/servo change after the command; "
                        f"target={target.as_dict()}, "
                        f"last_actual={actual.as_dict()}, "
                        f"max_observed_feedback_delta_mm={self.max_observed_feedback_delta_mm:.3f}"
                    )
                if (
                    self.max_observed_feedback_delta_mm < MIN_FEEDBACK_CHANGE_MM
                    and start_error is not None
                    and start_error <= self.position_tolerance_mm
                ):
                    self.arrival_result = (
                        "ALREADY_IN_TOLERANCE_NO_FEEDBACK_CHANGE"
                    )
                else:
                    self.arrival_result = "REACHED_WITH_FEEDBACK_CHANGE"
                return actual, error
            time.sleep(POLL_INTERVAL_S)
        start_error = (
            pose_error(self.command_start_pose, target).position_mm
            if self.command_start_pose is not None
            else None
        )
        if (
            start_error is not None
            and start_error > self.position_tolerance_mm
            and self.max_observed_feedback_delta_mm < MIN_FEEDBACK_CHANGE_MM
            and self.max_observed_servo_delta < 1
        ):
            self.arrival_result = "STALE_FEEDBACK_HARDWARE_FAULT"
            raise StaleFeedbackError(
                "STALE_FEEDBACK_HARDWARE_FAULT: out-of-tolerance command produced no "
                "fresh coordinate/servo change after the command; "
                f"target={target.as_dict()}, "
                f"last_actual={None if last_actual is None else last_actual.as_dict()}, "
                f"max_observed_feedback_delta_mm={self.max_observed_feedback_delta_mm:.3f}"
            )
        self.arrival_result = (
            "NO_FEEDBACK_CHANGE_TIMEOUT"
            if self.max_observed_feedback_delta_mm < MIN_FEEDBACK_CHANGE_MM
            else "TIMEOUT_AFTER_FEEDBACK_CHANGE"
        )
        raise TimeoutError(
            "NexArm arrival timeout: "
            f"target={target.as_dict()}, "
            f"last_actual={None if last_actual is None else last_actual.as_dict()}, "
            f"last_error={None if last_error is None else last_error.as_dict()}, "
            f"result={self.arrival_result}, "
            "feedback does not independently prove physical motion; "
            f"max_observed_feedback_delta_mm={self.max_observed_feedback_delta_mm:.3f}"
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
