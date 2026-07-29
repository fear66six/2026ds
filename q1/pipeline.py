"""第一问核心流程：检测 → 匹配 → 规划 → 评估"""

from __future__ import annotations

from typing import Optional

from . import config
from .motion import format_gcode, plan_motions
from .puzzle_solver import assign_pieces, evaluate_assembly
from .vision import (
    PaperFrame,
    detect_divider_line,
    detect_paper,
    detect_pieces,
    draw_overlay,
    draw_overlay_live,
    filter_upper_half_pieces,
)


def run_pipeline(
    frame,
    hsv_ranges=None,
    verbose: bool = True,
    *,
    live: bool = False,
    cached_paper: Optional[PaperFrame] = None,
    refresh_paper: bool = True,
    cached_divider_y: Optional[float] = None,
) -> dict:
    if hsv_ranges is None:
        hsv_ranges = config.DEFAULT_HSV_RANGES

    if live and cached_paper is not None and not refresh_paper:
        paper = cached_paper
        divider_y = cached_divider_y if cached_divider_y is not None else config.DIVIDER_Y_CM
    else:
        paper = detect_paper(frame)
        if paper is None:
            return {"ok": False, "error": "未检测到 A4 纸张"}
        divider_y = detect_divider_line(frame, paper)

    if paper is None:
        return {"ok": False, "error": "未检测到 A4 纸张"}

    all_pieces = detect_pieces(frame, paper, divider_y, hsv_ranges, live=live)
    pieces = filter_upper_half_pieces(all_pieces, paper, divider_y)
    target_origin = (config.TARGET_ORIGIN_X_CM, config.TARGET_ORIGIN_Y_CM)
    lower_count = sum(1 for p in all_pieces if not p.in_upper_half)

    if live:
        # 实时预览不做 assign_pieces（约 2~3s/次），按空格再跑完整流程
        evaluation = {
            "assembly_ok": len(pieces) == 4,
            "max_vertex_error_cm": 0.0 if len(pieces) == 4 else 99.0,
        }
        overlay = draw_overlay_live(
            frame, paper, divider_y, pieces, target_origin, all_pieces=all_pieces
        )
        return {
            "ok": True,
            "paper": paper,
            "divider_y_cm": divider_y,
            "pieces": pieces,
            "all_pieces": all_pieces,
            "lower_piece_count": lower_count,
            "assignments": [],
            "evaluation": evaluation,
            "overlay": overlay,
        }

    assignments = assign_pieces(pieces, target_origin)
    evaluation = evaluate_assembly(pieces, assignments, target_origin)

    steps = plan_motions(pieces, assignments, paper)
    gcode = format_gcode(steps)
    overlay = draw_overlay(frame, paper, divider_y, pieces, target_origin, assignments)

    result = {
        "ok": True,
        "paper": paper,
        "divider_y_cm": divider_y,
        "pieces": pieces,
        "assignments": assignments,
        "evaluation": evaluation,
        "steps": steps,
        "gcode": gcode,
        "overlay": overlay,
    }

    if verbose:
        ev = evaluation
        print("\n========== 第一问 检测结果 ==========")
        print(f"检测到碎片: {len(pieces)}/4")
        print(f"拼合评估: {'通过' if ev['assembly_ok'] else '未通过'}")
        print(f"最大顶点误差: {ev['max_vertex_error_cm']:.2f} cm (要求 ≤ {config.VERTEX_MATCH_TOLERANCE_CM} cm)")
        print("\n========== 运动规划 ==========")
        for i, step in enumerate(steps):
            print(f"  {i + 1}. [{step.phase.name}] {step.description}")
        print("\n========== G-code ==========")
        print(gcode)

    return result
