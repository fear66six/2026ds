"""第二问核心流程"""

from __future__ import annotations

from typing import Optional

from .motion import format_gcode, plan_motions
from .vision import detect_divider_line, detect_paper

from . import config
from .detect import detect_pieces_q2
from .overlay import draw_overlay_q2
from .piece import analyze_pieces
from .solver import _select_seed, build_assignments, evaluate_assembly_q2, solve_assembly
from .template_matcher import try_template_fallback
from .testcase import load_q2_meta
from .vision_refine import refine_detected_pieces


def run_pipeline_q2(
    frame,
    hsv_ranges=None,
    verbose: bool = True,
    target_width: Optional[float] = None,
    target_height: Optional[float] = None,
    allow_template_fallback: bool = False,
    image_path: Optional[str] = None,
) -> dict:
    if hsv_ranges is None:
        hsv_ranges = config.DEFAULT_HSV_RANGES

    meta = None
    if image_path:
        meta = load_q2_meta(image_path)
    if (target_width is None or target_height is None) and meta:
        target_width = target_width or meta.width_cm
        target_height = target_height or meta.height_cm

    paper = detect_paper(frame)
    if paper is None:
        return {"ok": False, "error": "未检测到 A4 纸张"}

    divider_y = detect_divider_line(frame, paper)
    pieces = detect_pieces_q2(frame, paper, divider_y, hsv_ranges)
    pieces = [p for p in pieces if p.in_upper_half and p.center_cm[1] < divider_y - 0.5]
    pieces = refine_detected_pieces(pieces, paper)
    if not pieces:
        return {"ok": False, "error": "未检测到碎片"}

    analyzed = analyze_pieces(pieces)
    if not analyzed:
        return {"ok": False, "error": "碎片分析失败（边长/面积不符合约束）"}
    if len(analyzed) > config.MAX_PIECES:
        return {"ok": False, "error": f"碎片过多: {len(analyzed)} > {config.MAX_PIECES}"}

    use_template = False
    solution = None
    explicit_target = target_width is not None and target_height is not None
    if explicit_target:
        solution = solve_assembly(analyzed, target_width, target_height)
    if solution is None and not explicit_target:
        solution = solve_assembly(analyzed, None, None)

    if solution is not None:
        tw, th, target_origin, placed = solution
        assignments = build_assignments(pieces, analyzed, placed)
    elif allow_template_fallback and len(pieces) == 4:
        fallback = try_template_fallback(pieces, target_width, target_height)
        if fallback is not None:
            tw, th, target_origin, assignments = fallback
            use_template = True
        else:
            return {"ok": False, "error": "无法求解拼图（直角种子 + 互补角拼接失败）"}
    else:
        return {"ok": False, "error": "无法求解拼图（直角种子 + 互补角拼接失败）"}

    evaluation = evaluate_assembly_q2(pieces, assignments, (tw, th), target_origin)
    steps = plan_motions(pieces, assignments, paper)
    gcode = format_gcode(steps)
    overlay = draw_overlay_q2(frame, paper, divider_y, pieces, target_origin, (tw, th), assignments)

    result = {
        "ok": True,
        "paper": paper,
        "divider_y_cm": divider_y,
        "pieces": pieces,
        "analyzed": analyzed,
        "assignments": assignments,
        "evaluation": evaluation,
        "steps": steps,
        "gcode": gcode,
        "overlay": overlay,
        "target_origin": target_origin,
        "target_size": (tw, th),
        "solver": "template" if use_template else "corner_greedy",
    }

    if verbose:
        ev = evaluation
        seed = _select_seed(analyzed)
        print("\n========== 第二问 检测结果 ==========")
        print(f"检测到碎片: {len(pieces)} (有效 {len(analyzed)})")
        print(f"求解器: {result['solver']}")
        if seed and not use_template:
            si, ci = seed
            print(f"种子碎片: #{analyzed[si].index} (直角顶点 #{ci}, 面积 {analyzed[si].area_cm2:.1f} cm2)")
        print(f"目标矩形: {tw:.2f} x {th:.2f} cm @ ({target_origin[0]:.1f}, {target_origin[1]:.1f})")
        print(f"拼合评估: {'通过' if ev['assembly_ok'] else '未通过'}")
        print(f"几何验证: {'通过' if ev.get('geometry_ok') else '未通过'} (覆盖率 {ev.get('coverage_ratio', 0):.1%})")
        print(f"最大顶点误差: {ev['max_vertex_error_cm']:.2f} cm (要求 ≤ {config.VERTEX_MATCH_TOLERANCE_CM} cm)")
        print("\n========== 运动规划 ==========")
        for i, step in enumerate(steps):
            print(f"  {i + 1}. [{step.phase.name}] {step.description}")
        print("\n========== G-code ==========")
        print(gcode)

    return result
