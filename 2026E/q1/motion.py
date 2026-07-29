"""运动规划：从当前位置一步刚性拼接到目标矩形（不中转、不翻转）"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple

import numpy as np

from .geometry import compute_rigid_align_error, polygon_centroid
from .puzzle_solver import PieceAssignment
from .vision import DetectedPiece, PaperFrame


class Phase(Enum):
    ASSEMBLE = auto()
    DONE = auto()


@dataclass
class MotionStep:
    piece_index: int
    phase: Phase
    from_cm: Tuple[float, float]
    to_cm: Tuple[float, float]
    angle_deg: float
    description: str
    from_vertices_cm: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    to_vertices_cm: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))


def _piece_label(template_name: str) -> str:
    """OpenCV 仅支持 ASCII，取模板前缀如 P1/P2"""
    return template_name.split("_")[0]


def plan_motions(
    pieces: List[DetectedPiece],
    assignments: List[PieceAssignment],
    paper: PaperFrame | None = None,
) -> List[MotionStep]:
    """
    每块碎片从当前位置直接一步拼接到目标矩形对应槽位。
    仅允许平面内平移 + 旋转，禁止翻转（镜像）。
    """
    steps: List[MotionStep] = []

    for asg in sorted(assignments, key=lambda a: a.template_name):
        pi = asg.detected_index
        piece = pieces[pi]
        source_v = np.asarray(piece.vertices_cm, dtype=np.float64)
        target_v = asg.target_vertices_cm
        if len(target_v) == 0:
            continue

        _, rot_deg = compute_rigid_align_error(source_v, target_v)
        from_center = polygon_centroid(source_v)
        to_center = polygon_centroid(target_v)

        steps.append(
            MotionStep(
                piece_index=pi,
                phase=Phase.ASSEMBLE,
                from_cm=(float(from_center[0]), float(from_center[1])),
                to_cm=(float(to_center[0]), float(to_center[1])),
                angle_deg=rot_deg,
                description=f"Piece #{pi} {_piece_label(asg.template_name)} -> target",
                from_vertices_cm=source_v.copy(),
                to_vertices_cm=target_v.copy(),
            )
        )

    steps.append(
        MotionStep(
            piece_index=-1,
            phase=Phase.DONE,
            from_cm=(0, 0),
            to_cm=(0, 0),
            angle_deg=0,
            description="Done - signal",
        )
    )
    return steps


def format_gcode(steps: List[MotionStep]) -> str:
    lines = ["; E题拼图装置运动序列（直接拼接，不翻转）", "G28 ; 回零"]
    for i, step in enumerate(steps):
        if step.phase == Phase.DONE:
            lines.append("M999 ; 完成指示（蜂鸣器/LED）")
            continue
        x0, y0 = step.from_cm
        x1, y1 = step.to_cm
        lines.append(f"; Step {i + 1}: {step.description}")
        lines.append(f"G0 X{x0:.2f} Y{y0:.2f} ; 抓取碎片 #{step.piece_index}")
        lines.append("M3 ; 吸盘/夹爪下降")
        lines.append(f"G1 X{x1:.2f} Y{y1:.2f} ; 搬运至目标槽位")
        lines.append(f"G2 A{step.angle_deg:.1f} ; 旋转（禁止翻转）")
        lines.append("M5 ; 释放")
    return "\n".join(lines)
