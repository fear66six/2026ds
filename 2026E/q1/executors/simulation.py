"""不访问硬件的场景与单块执行器。"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from ..models import ExecutionResult, SingleMovePlan
from ..pieces import PIECE_TEMPLATES


def _rotate_translate(vertices: np.ndarray, center: tuple[float, float], angle_deg: float) -> np.ndarray:
    pts = np.asarray(vertices, np.float64) * 10.0
    pts -= np.mean(pts, axis=0)
    radians = np.deg2rad(angle_deg)
    rotation = np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])
    return pts @ rotation.T + np.asarray(center)


@dataclass
class SimulationWorld:
    target_origin_mm: tuple[float, float] = (55.0, 168.5)
    pieces: dict[str, dict] = field(default_factory=dict)
    place_offset_template: str | None = None
    release_failure_template: str | None = None
    shift_after_move_template: str | None = None
    camera_shift: bool = False

    def __post_init__(self) -> None:
        if not self.pieces:
            centers = [(38.0, 48.0), (91.0, 92.0), (155.0, 48.0), (166.0, 105.0)]
            angles = [17.0, -28.0, 42.0, -12.0]
            for index, template in enumerate(PIECE_TEMPLATES):
                template_id = f"P{index + 1}"
                self.pieces[template_id] = {
                    "template_id": template_id,
                    "vertices_mm": _rotate_translate(np.asarray(template.local_vertices), centers[index], angles[index]),
                    "angle_deg": angles[index],
                    "region": "UPPER_SOURCE",
                    "confidence": 0.98 - index * 0.03,
                }

    def snapshot(self, _: int) -> tuple[np.ndarray, dict]:
        frame = np.full((1188, 840, 3), 28, dtype=np.uint8)
        cv2.rectangle(frame, (1, 1), (838, 1186), (90, 90, 90), 3)
        cv2.line(frame, (0, 594), (839, 594), (180, 180, 180), 2)
        records = []
        for record in self.pieces.values():
            copied = dict(record)
            copied["vertices_mm"] = np.asarray(record["vertices_mm"]).copy()
            records.append(copied)
            polygon = np.rint(copied["vertices_mm"] * 4.0).astype(np.int32)
            cv2.fillPoly(frame, [polygon], (235, 235, 235))
        if self.camera_shift:
            frame = np.roll(frame, 12, axis=1)
        return frame, {"simulation_pieces": records}

    def place(self, plan: SingleMovePlan) -> tuple[bool, str]:
        if self.release_failure_template == plan.template_id:
            self.release_failure_template = None
            return False, "SIMULATED_RELEASE_FAILURE"
        index = int(plan.template_id[1:]) - 1
        template = PIECE_TEMPLATES[index]
        target = template.world_vertices(
            (self.target_origin_mm[0] / 10.0, self.target_origin_mm[1] / 10.0)
        ) * 10.0
        if self.place_offset_template == plan.template_id:
            target = target + np.array([8.0, 0.0])
            self.place_offset_template = None
        self.pieces[plan.template_id].update(
            vertices_mm=target,
            angle_deg=0.0,
            region="LOWER_TARGET",
        )
        if self.shift_after_move_template and self.shift_after_move_template in self.pieces:
            shifted = self.pieces[self.shift_after_move_template]
            if shifted["region"] == "UPPER_SOURCE":
                shifted["vertices_mm"] = np.asarray(shifted["vertices_mm"]) + np.array([5.0, 1.0])
        return True, "SIMULATED_PLACEMENT"


class SimulationRobotExecutor:
    def __init__(self, world: SimulationWorld, *, dry_run: bool = False) -> None:
        self.world = world
        self.dry_run = dry_run
        self.initialized = False
        self.observe_count = 0
        self.executed_templates: list[str] = []
        self.phase_log: list[str] = []

    def initialize(self) -> None:
        self.initialized = True

    def move_to_observe_pose(self) -> None:
        self.observe_count += 1
        self.phase_log.append("MOVE_TO_OBSERVE")

    def wait_until_idle(self, timeout_s: float) -> bool:
        del timeout_s
        self.phase_log.append("WAIT_ARM_STABLE")
        return True

    def execute_single_move(self, plan: SingleMovePlan, magnet) -> ExecutionResult:
        self.executed_templates.append(plan.template_id)
        phases = [
            "MOVE_ABOVE_SOURCE",
            "MOVE_TO_PICK_HEIGHT",
            "MAGNET_HOLD_START",
            "WAIT_MAGNET_SETTLE",
            "LIFT_TO_SAFE_HEIGHT",
            "TRANSFER",
            "ROTATE",
            "MOVE_ABOVE_TARGET",
            "LOWER_TO_RELEASE_HEIGHT",
        ]
        self.phase_log.extend(phases)
        with magnet.hold_session():
            if not magnet.is_holding:
                return ExecutionResult(False, plan.template_id, "MAGNET_HOLD_NOT_ACTIVE")
            if self.dry_run:
                ok, reason = True, "DRY_RUN_NO_WORLD_MUTATION"
            else:
                ok, reason = self.world.place(plan)
        self.phase_log.extend(["MAGNET_HOLD_STOP", "RELEASE_PEEL", "LIFT"])
        return ExecutionResult(ok, plan.template_id, reason, release_confirmed=ok)

    def execute_release_recovery(self, plan: SingleMovePlan, attempt: int) -> ExecutionResult:
        self.phase_log.append(f"RELEASE_RECOVERY_{attempt}")
        ok, reason = self.world.place(plan)
        return ExecutionResult(ok, plan.template_id, reason, release_confirmed=ok)

    def emergency_stop(self) -> None:
        self.phase_log.append("EMERGENCY_STOP")

    def close(self) -> None:
        self.initialized = False

