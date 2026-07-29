"""Q1 单步视觉闭环的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from .geometry import RigidTransformResult


class PieceTaskStatus(str, Enum):
    UNPLACED = "UNPLACED"
    PLACED_OK = "PLACED_OK"
    PLACED_OFFSET = "PLACED_OFFSET"
    RELEASE_UNCONFIRMED = "RELEASE_UNCONFIRMED"
    RELEASE_FAILED = "RELEASE_FAILED"
    PICK_FAILED = "PICK_FAILED"
    DROPPED_DURING_TRANSFER = "DROPPED_DURING_TRANSFER"
    PIECE_TEMPORARILY_MISSING = "PIECE_TEMPORARILY_MISSING"
    PIECE_IDENTITY_AMBIGUOUS = "PIECE_IDENTITY_AMBIGUOUS"
    PIECE_OUTSIDE_EXPECTED_REGION = "PIECE_OUTSIDE_EXPECTED_REGION"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


@dataclass
class PaperPose:
    x_mm: float
    y_mm: float
    angle_deg: float = 0.0


@dataclass
class RobotPose:
    x: float
    y: float
    z: float
    pitch: float
    roll: float
    claw: float
    duration_ms: int


@dataclass
class PieceGeometry:
    detected_id: int
    template_id: str | None
    contour_px: np.ndarray
    vertices_px: np.ndarray
    vertices_mm: np.ndarray
    edge_lengths_mm: list[float]
    inner_angles_deg: list[float]
    center_mm: tuple[float, float]
    angle_deg: float
    area_mm2: float
    edge_fit_rmse_mm: float
    template_match_score: float
    confidence: float
    region: str
    touches_boundary: bool
    rough_vertices_mm: np.ndarray | None = None
    max_edge_residual_mm: float = 0.0
    inside_ratio: float = 1.0
    rejection_reason: str | None = None


@dataclass
class TemplateState:
    template_id: str
    status: PieceTaskStatus
    detected_piece: PieceGeometry | None
    expected_target_vertices_mm: np.ndarray
    center_error_mm: float | None
    angle_error_deg: float | None
    max_vertex_error_mm: float | None
    last_seen_cycle: int
    retry_count: int = 0
    rms_vertex_error_mm: float | None = None
    recovery_hint: str | None = None


@dataclass
class SceneAnalysis:
    cycle_index: int
    image_path: str
    pieces: list[PieceGeometry]
    templates: dict[str, TemplateState]
    placed_templates: set[str]
    remaining_templates: set[str]
    image_quality: dict[str, float]
    paper_valid: bool
    scene_valid: bool
    warnings: list[str] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    assignment_margin: float | None = None
    assignment_total_cost: float | None = None


@dataclass
class Snapshot:
    frame: np.ndarray
    timestamp: float
    sharpness: float
    brightness: float
    motion_score: float
    path: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SingleMovePlan:
    cycle_index: int
    template_id: str
    source_pose_paper: PaperPose
    target_pose_paper: PaperPose
    source_pose_robot: RobotPose | None
    target_pose_robot: RobotPose | None
    pick_point_paper: tuple[float, float]
    pick_point_robot: RobotPose | None
    approach_pose: RobotPose | None
    transfer_pose: RobotPose | None
    release_pose: RobotPose | None
    rotation_delta_deg: float
    confidence: float
    reason_selected: str
    retry_index: int
    source_vertices_mm: np.ndarray | None = None
    target_vertices_mm: np.ndarray | None = None
    rigid_transform: RigidTransformResult | None = None
    pick_point_source_mm: np.ndarray | None = None
    release_point_target_mm: np.ndarray | None = None
    pick_roll_deg: float | None = None
    release_roll_deg: float | None = None
    rotate_pose: RobotPose | None = None


@dataclass
class ExecutionResult:
    ok: bool
    template_id: str | None
    reason: str = ""
    release_confirmed: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditResult:
    all_complete: bool
    placed_ok: set[str]
    placed_offset: set[str]
    remaining: set[str]
    moved_remaining: set[str]
    release_failed_template: str | None
    missing_templates: set[str]
    requires_reanalysis: bool
    warnings: list[str] = field(default_factory=list)
    pick_failed_template: str | None = None
    dropped_template: str | None = None
    temporarily_missing_template: str | None = None
    recovery_template: str | None = None
    recovery_mode: str | None = None
