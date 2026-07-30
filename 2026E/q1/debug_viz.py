"""调试图像输出：每轮静态分析可视化。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .models import SceneAnalysis, SingleMovePlan
from .puzzle_solver import TemplateAssignmentResult
from .vision import cm_to_px


def save_debug_overlays(
    cycle_dir: Path,
    *,
    rectified: np.ndarray | None,
    scene: SceneAnalysis,
    assignment: TemplateAssignmentResult | None = None,
    plan: SingleMovePlan | None = None,
    selection: dict | None = None,
    paper=None,
) -> None:
    cycle_dir.mkdir(parents=True, exist_ok=True)
    base = rectified.copy() if rectified is not None else np.full((400, 400, 3), 32, dtype=np.uint8)

    # refined_edges
    edges = base.copy()
    for piece in scene.pieces:
        cnt = np.asarray(piece.contour_px, dtype=np.int32).reshape(-1, 1, 2)
        cv2.drawContours(edges, [cnt], -1, (80, 80, 80), 1)
        if piece.rough_vertices_mm is not None:
            rough_mm = np.asarray(piece.rough_vertices_mm, dtype=np.float64)
            rough = (
                np.rint(
                    [cm_to_px(tuple(point / 10.0), paper) for point in rough_mm]
                ).astype(np.int32)
                if paper is not None
                else np.rint(rough_mm * 4.0).astype(np.int32)
            )
            for i, p in enumerate(rough):
                cv2.circle(edges, tuple(p), 4, (0, 165, 255), -1)
                cv2.putText(edges, f"r{i}", tuple(p + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 165, 255), 1)
        refined = np.rint(np.asarray(piece.vertices_px)).astype(np.int32)
        cv2.polylines(edges, [refined.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
        for i, p in enumerate(refined):
            cv2.circle(edges, tuple(p), 5, (0, 255, 255), -1)
            cv2.putText(edges, str(i), tuple(p + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        label = f"{piece.template_id or '?'} rmse={piece.edge_fit_rmse_mm:.2f}"
        center = tuple(np.rint(np.mean(refined, axis=0)).astype(int))
        cv2.putText(edges, label, center, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.imwrite(str(cycle_dir / "refined_edges.png"), edges)

    # template_assignment
    assign_img = base.copy()
    if assignment is not None:
        for piece in scene.pieces:
            color = (0, 220, 0) if piece.detected_id in assignment.selected_candidate_ids else (0, 0, 220)
            pts = np.rint(piece.vertices_px).astype(np.int32)
            cv2.polylines(assign_img, [pts.reshape(-1, 1, 2)], True, color, 2)
            c = tuple(np.rint(np.mean(pts, axis=0)).astype(int))
            cv2.putText(
                assign_img,
                f"c{piece.detected_id}:{piece.template_id or 'x'}",
                c,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
            )
        cv2.putText(
            assign_img,
            f"cost={assignment.total_cost:.2f} 2nd={assignment.second_best_cost:.2f} m={assignment.confidence_margin:.2f}",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
        )
    cv2.imwrite(str(cycle_dir / "template_assignment.png"), assign_img)

    # rigid_transform
    rigid = base.copy()
    if plan is not None and plan.rigid_transform is not None:
        def points_to_px(points_mm) -> np.ndarray:
            points = np.asarray(points_mm, dtype=np.float64)
            if paper is None:
                return np.rint(points * 4.0).astype(np.int32)
            return np.rint(
                [cm_to_px(tuple(point / 10.0), paper) for point in points]
            ).astype(np.int32)

        src = points_to_px(plan.source_vertices_mm)
        tgt = points_to_px(plan.target_vertices_mm)
        xf = points_to_px(plan.rigid_transform.transformed_vertices_mm)
        cv2.polylines(rigid, [src.reshape(-1, 1, 2)], True, (255, 128, 0), 2)
        cv2.polylines(rigid, [tgt.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
        cv2.polylines(rigid, [xf.reshape(-1, 1, 2)], True, (0, 255, 255), 1)
        if plan.pick_point_source_mm is not None:
            p = tuple(points_to_px([plan.pick_point_source_mm])[0])
            cv2.circle(rigid, p, 6, (0, 0, 255), -1)
        if plan.release_point_target_mm is not None:
            r = tuple(points_to_px([plan.release_point_target_mm])[0])
            cv2.circle(rigid, r, 6, (255, 0, 255), -1)
        cv2.putText(
            rigid,
            f"rot={plan.rotation_delta_deg:.1f} max={plan.rigid_transform.max_error_mm:.2f} rms={plan.rigid_transform.rms_error_mm:.2f}",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )
    cv2.imwrite(str(cycle_dir / "rigid_transform.png"), rigid)

    # selection_geometry
    sel = base.copy()
    if plan is not None and plan.pick_point_source_mm is not None and plan.release_point_target_mm is not None:
        if paper is None:
            a = tuple(np.rint(plan.pick_point_source_mm * 4.0).astype(int))
            b = tuple(np.rint(plan.release_point_target_mm * 4.0).astype(int))
        else:
            a = tuple(
                np.rint(
                    cm_to_px(tuple(np.asarray(plan.pick_point_source_mm) / 10.0), paper)
                ).astype(int)
            )
            b = tuple(
                np.rint(
                    cm_to_px(tuple(np.asarray(plan.release_point_target_mm) / 10.0), paper)
                ).astype(int)
            )
        cv2.line(sel, a, b, (0, 255, 255), 2)
        cv2.circle(sel, a, int(8 * 4 / 4), (0, 128, 255), 1)
    if selection is not None:
        cv2.putText(
            sel,
            str(selection.get("reason", "")),
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )
    cv2.imwrite(str(cycle_dir / "selection_geometry.png"), sel)

    # final_audit placeholder overlay
    audit = base.copy()
    for tid, state in scene.templates.items():
        if state.detected_piece is None:
            continue
        pts = np.rint(state.detected_piece.vertices_px).astype(np.int32)
        color = {
            "PLACED_OK": (0, 220, 0),
            "PLACED_OFFSET": (0, 165, 255),
            "UNPLACED": (0, 220, 255),
        }.get(state.status.value, (128, 128, 128))
        cv2.polylines(audit, [pts.reshape(-1, 1, 2)], True, color, 2)
        c = tuple(np.rint(np.mean(pts, axis=0)).astype(int))
        cv2.putText(audit, f"{tid}:{state.status.value}", c, cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    cv2.imwrite(str(cycle_dir / "final_audit.png"), audit)
