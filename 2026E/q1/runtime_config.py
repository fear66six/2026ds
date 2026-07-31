"""Q1 runtime configuration loaded from one robot configuration file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Q1RuntimeConfig:
    mode: str = "full_q1"
    authorization: str = "RUN_Q1"
    camera_index: int = 0
    capture_burst: int = 8
    settle_time_ms: int = 200
    place_center_tolerance_mm: float = 5.0
    place_angle_tolerance_deg: float = 5.0
    vertex_max_error_mm: float = 8.0
    target_origin_mm: tuple[float, float] = (55.0, 168.5)
    target_scale: float = 1.0
    edge_gap_mm: float = 0.0
    robot_config: Path | None = None
    run_root: Path = Path("output/runs/q1")
    camera_port: str | None = None
    nexarm_port: str | None = None
    magnet_backend: str = "stm32"
    magnet_port: str | None = None
    magnet_lease_ms: int | None = None

    observe_pose: tuple[float, float, float, float, float, float, int] = (
        168.0,
        0.0,
        230.0,
        -88.0,
        1.0,
        1.0,
        6000,
    )
    motion_mode: str = "direct_pose"
    direct_pick_release_pose_verified: bool = False
    pick_height: float | None = None
    release_height: float | None = None
    pick_robot_xy_offset_mm: tuple[float, float] = (0.0, 0.0)
    swing_roll_compensate: bool = True
    swing_roll_sign: float = -1.0
    transfer_approach_dz_mm: float = 40.0
    transfer_transit_z: float = 120.0
    transfer_move_duration_ms: int = 1500
    transfer_descend_duration_ms: int = 800
    transfer_lift_duration_ms: int = 800
    transfer_rotate_duration_ms: int = 1200
    post_move_settle_ms: int = 200
    magnet_settle_ms: int | None = None
    magnet_release_settle_ms: int | None = None

    position_tolerance_mm: float = 10.0
    orientation_tolerance_deg: float = 3.0
    idle_stable_samples: int = 3
    physical_pick_enabled: bool = True
    physical_pick_verified: bool = False
    motion_calibration_status: str = (
        "UNVERIFIED: direct HOME-to-pick and pick-to-release six-axis targets at "
        "Z=15, including every XY/Z/Pitch/Roll combination, have not been validated; "
        "separate Z=250 and source-XY/Z=226 waypoints were rejected"
    )

    def report_metadata(self) -> dict:
        return {
            "authorization": self.authorization,
            "magnet_backend": self.magnet_backend,
            "magnet_port": self.magnet_port,
            "magnet_lease_ms": self.magnet_lease_ms,
            "physical_pick_enabled": self.physical_pick_enabled,
            "physical_pick_verified": self.physical_pick_verified,
            "direct_pick_release_pose_verified": self.direct_pick_release_pose_verified,
            "motion_calibration_status": self.motion_calibration_status,
            "target_scale": self.target_scale,
            "edge_gap_mm": self.edge_gap_mm,
            "swing_roll_compensate": self.swing_roll_compensate,
            "swing_roll_sign": self.swing_roll_sign,
            "transfer_approach_dz_mm": self.transfer_approach_dz_mm,
            "transfer_transit_z": self.transfer_transit_z,
            "transfer_move_duration_ms": self.transfer_move_duration_ms,
            "transfer_descend_duration_ms": self.transfer_descend_duration_ms,
            "transfer_lift_duration_ms": self.transfer_lift_duration_ms,
            "transfer_rotate_duration_ms": self.transfer_rotate_duration_ms,
            "post_move_settle_ms": self.post_move_settle_ms,
        }

    def real_run_blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.robot_config is None or not self.robot_config.exists():
            blockers.append("ROBOT_CONFIG_REQUIRED")

        if self.robot_config is not None and self.robot_config.exists():
            mapper = None
            try:
                from .calibration import ArmCoordinateMapper

                mapper = ArmCoordinateMapper(self.robot_config)
            except (OSError, ValueError) as exc:
                blockers.append(f"ROBOT_CONFIG_INVALID: {exc}")
            if mapper is not None and not mapper.wrist_mapping_ready():
                blockers.append("CALIBRATION_REQUIRED: 腕部 roll mapping incomplete")

        if not self.nexarm_port:
            blockers.append("NEXARM_PORT_REQUIRED")
        if self.magnet_backend != "stm32":
            blockers.append(
                f"REAL_STM32_MAGNET_REQUIRED: got {self.magnet_backend}"
            )
        if not self.physical_pick_enabled:
            blockers.append("PHYSICAL_PICK_DISABLED")
        if self.magnet_backend == "stm32" and not self.magnet_port:
            blockers.append("MAGNET_PORT_REQUIRED: stm32 backend selected")
        if self.magnet_backend == "stm32" and self.magnet_port:
            if "/dev/serial/by-id/" not in self.magnet_port:
                blockers.append("MAGNET_BY_ID_PORT_REQUIRED")
            if self.magnet_port == self.nexarm_port:
                blockers.append("MAGNET_PORT_CONFLICTS_WITH_NEXARM")
            if self.magnet_lease_ms is None:
                blockers.append("MAGNET_LEASE_REQUIRED")
            elif not 50 <= int(self.magnet_lease_ms) <= 500:
                blockers.append("MAGNET_LEASE_OUT_OF_PROTOCOL_RANGE")
        if self.motion_mode != "direct_pose":
            blockers.append(
                f"INVALID_MOTION_MODE: expected direct_pose, got {self.motion_mode}"
            )
        required = {
            "pick_height": self.pick_height,
            "release_height": self.release_height,
            "transfer_approach_dz_mm": self.transfer_approach_dz_mm,
            "transfer_transit_z": self.transfer_transit_z,
            "transfer_move_duration_ms": self.transfer_move_duration_ms,
            "transfer_descend_duration_ms": self.transfer_descend_duration_ms,
            "transfer_lift_duration_ms": self.transfer_lift_duration_ms,
            "transfer_rotate_duration_ms": self.transfer_rotate_duration_ms,
            "post_move_settle_ms": self.post_move_settle_ms,
            "magnet_settle_ms": self.magnet_settle_ms,
            "magnet_release_settle_ms": self.magnet_release_settle_ms,
            "position_tolerance_mm": self.position_tolerance_mm,
            "orientation_tolerance_deg": self.orientation_tolerance_deg,
            "idle_stable_samples": self.idle_stable_samples,
            "vertex_max_error_mm": self.vertex_max_error_mm,
        }
        for name, value in required.items():
            if value is None:
                blockers.append(f"ROBOT_CONFIG_REQUIRED: missing {name}")
        return blockers

    def planning_blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.robot_config is None or not self.robot_config.exists():
            return ["ROBOT_CONFIG_REQUIRED"]

        try:
            from .calibration import ArmCoordinateMapper

            mapper = ArmCoordinateMapper(self.robot_config)
        except (OSError, ValueError) as exc:
            return [f"ROBOT_CONFIG_INVALID: {exc}"]

        if not mapper.is_calibrated():
            blockers.append("CALIBRATION_REQUIRED: paper_to_robot_matrix")
        if not mapper.wrist_mapping_ready():
            blockers.append("CALIBRATION_REQUIRED: wrist roll mapping incomplete")
        if self.motion_mode != "direct_pose":
            blockers.append(
                f"INVALID_MOTION_MODE: expected direct_pose, got {self.motion_mode}"
            )
        required = {
            "pick_height": self.pick_height,
            "release_height": self.release_height,
            "transfer_approach_dz_mm": self.transfer_approach_dz_mm,
            "transfer_transit_z": self.transfer_transit_z,
            "transfer_move_duration_ms": self.transfer_move_duration_ms,
            "transfer_descend_duration_ms": self.transfer_descend_duration_ms,
            "transfer_lift_duration_ms": self.transfer_lift_duration_ms,
            "transfer_rotate_duration_ms": self.transfer_rotate_duration_ms,
            "post_move_settle_ms": self.post_move_settle_ms,
            "vertex_max_error_mm": self.vertex_max_error_mm,
        }
        for name, value in required.items():
            if value is None:
                blockers.append(f"ROBOT_CONFIG_REQUIRED: missing {name}")
        return blockers

    def production_run_blockers(self) -> list[str]:
        """Checks required before the full camera/arm/magnet Q1 entry opens hardware."""
        blockers = self.real_run_blockers()
        if not self.direct_pick_release_pose_verified:
            blockers.append("DIRECT_PICK_RELEASE_POSE_UNVERIFIED")
        return blockers
