"""Q3 card-fragment analysis using Q1 paper detection and rectification."""

from __future__ import annotations

import time
from dataclasses import replace

import numpy as np

from q1.vision import detect_paper, rectify_paper

from .card_solver import CardPuzzleSolver, PatternConfig, SolverConfig
from .card_solver.config import production_solver_config
from .card_solver.image_input import card_puzzle_from_rectified
from .card_solver.models import Solution
from .models import CardPieceState, CardScene

PRODUCTION_SOLVE_TIMEOUT_S = 25.0
_LAYOUT_FALLBACKS = {
    "auto": ("auto", "top-bottom", "left-right"),
    "top-bottom": ("top-bottom", "left-right"),
    "left-right": ("left-right", "top-bottom"),
}


class CardSceneAnalyzer:
    def __init__(
        self,
        *,
        layout: str = "top-bottom",
        solver_config: SolverConfig | None = None,
        pattern_config: PatternConfig | None = None,
        solve_timeout_s: float = PRODUCTION_SOLVE_TIMEOUT_S,
    ) -> None:
        self.layout = layout
        active_solver_config = solver_config or production_solver_config()
        self.solver_config = replace(
            active_solver_config,
            max_search_seconds=float(solve_timeout_s),
        )
        self.pattern_config = pattern_config or PatternConfig()
        self.solve_timeout_s = float(solve_timeout_s)
        self.last_paper = None
        self.last_puzzle = None
        self.last_solution = None
        self.last_solver_stats: dict[str, float | int] = {}

    def _solve_observations(
        self,
        observations,
    ) -> tuple[Solution, CardPuzzleSolver]:
        solver = CardPuzzleSolver(
            config=self.solver_config,
            pattern_config=self.pattern_config,
        )
        solution = solver.solve(observations)
        self.last_solver_stats = {
            "dfs_calls": solver.stats.dfs_calls,
            "candidate_attempts": solver.stats.candidate_attempts,
            "expanded_searches": solver.stats.expanded_searches,
            "grid_candidate_attempts": solver.stats.grid_candidate_attempts,
            "strip_candidate_attempts": solver.stats.strip_candidate_attempts,
            "elapsed_seconds": solver.stats.elapsed_seconds,
            "best_effort_updates": solver.stats.best_effort_updates,
        }
        return solution, solver

    def analyze(self, snapshot, cycle_index: int) -> CardScene:
        started = time.perf_counter()
        paper = detect_paper(snapshot.frame)
        if paper is None:
            return CardScene(
                cycle_index=cycle_index,
                image_path=snapshot.path,
                pieces=[],
                layout=None,
                divider_mm=None,
                paper_valid=False,
                scene_valid=False,
                solution_success=False,
                warnings=["A4_PAPER_NOT_DETECTED"],
                timings_ms={"total_ms": (time.perf_counter() - started) * 1000.0},
            )

        self.last_paper = paper
        pixels_per_mm = float(self.solver_config.canonical_pixels_per_mm)
        rectified = rectify_paper(
            snapshot.frame,
            paper,
            output_size=(
                int(round(210.0 * pixels_per_mm)),
                int(round(297.0 * pixels_per_mm)),
            ),
        )
        detection_finished = time.perf_counter()

        puzzle = None
        solution = None
        layout_warnings: list[str] = []
        layouts = _LAYOUT_FALLBACKS.get(self.layout, (self.layout,))
        try:
            for layout in layouts:
                puzzle = card_puzzle_from_rectified(
                    rectified,
                    paper_size_mm=(210.0, 297.0),
                    pixels_per_mm=pixels_per_mm,
                    layout=layout,
                    solver_config=self.solver_config,
                    pattern_config=self.pattern_config,
                    image_path=snapshot.path,
                )
                solution, _solver = self._solve_observations(puzzle.observations)
                if solution.success and not solution.best_effort:
                    if layout != self.layout:
                        layout_warnings.append(
                            f"CARD_LAYOUT_FALLBACK: requested={self.layout}, used={layout}"
                        )
                    break
                if solution.best_effort or _solver.stats.budget_exhausted:
                    break
        except ValueError as exc:
            return CardScene(
                cycle_index=cycle_index,
                image_path=snapshot.path,
                pieces=[],
                layout=self.layout,
                divider_mm=None,
                paper_valid=True,
                scene_valid=False,
                solution_success=False,
                warnings=[str(exc)],
                timings_ms={
                    "paper_rectify_ms": (detection_finished - started) * 1000.0,
                    "total_ms": (time.perf_counter() - started) * 1000.0,
                },
            )

        if puzzle is None or solution is None:
            raise RuntimeError("CARD_ANALYSIS_STATE_MISSING")

        self.last_puzzle = puzzle
        self.last_solution = solution
        pieces = [
            CardPieceState(
                piece_id=observation.piece.id,
                vertices_mm=np.asarray(
                    [point.as_tuple() for point in observation.piece.vertices],
                    dtype=float,
                ),
                center_mm=observation.piece.centroid.as_tuple(),
                area_mm2=observation.piece.area,
                red_ink_area_mm2=observation.red_ink_area_mm2,
                black_ink_area_mm2=observation.black_ink_area_mm2,
            )
            for observation in puzzle.observations
        ]
        rectangle_size = None
        if solution.rectangle_width_mm is not None and solution.rectangle_height_mm is not None:
            rectangle_size = (
                float(solution.rectangle_width_mm),
                float(solution.rectangle_height_mm),
            )

        warnings = list(layout_warnings)
        executable_solution = bool(solution.success and not solution.best_effort)
        if solution.best_effort:
            warnings.append(
                solution.validation_warning
                or "CARD_SOLVE_BEST_EFFORT_REJECTED_FOR_EXECUTION"
            )
        if not executable_solution:
            warnings.append(solution.reason or "CARD_SOLVE_FAILED")
            if self.last_solver_stats:
                warnings.append(
                    "CARD_SOLVE_STATS: "
                    f"dfs={self.last_solver_stats.get('dfs_calls', 0)}, "
                    f"candidates={self.last_solver_stats.get('candidate_attempts', 0)}, "
                    f"expanded={self.last_solver_stats.get('expanded_searches', 0)}"
                )

        return CardScene(
            cycle_index=cycle_index,
            image_path=snapshot.path,
            pieces=pieces,
            layout=puzzle.layout,
            divider_mm=puzzle.divider_mm,
            paper_valid=True,
            scene_valid=executable_solution,
            solution_success=executable_solution,
            used_piece_ids=[item.piece_id for item in solution.placed_pieces],
            ignored_piece_ids=list(solution.ignored_piece_ids),
            rectangle_size_mm=rectangle_size,
            geometry_score=solution.geometry_score,
            pattern_score=solution.pattern_score,
            pattern_confidence=solution.pattern_confidence,
            corner_layout_score=solution.corner_layout_score,
            corner_layout_confidence=solution.corner_layout_confidence,
            symmetry_score=solution.symmetry_score,
            symmetry_confidence=solution.symmetry_confidence,
            best_effort=bool(solution.best_effort),
            detected_candidate_count=puzzle.detected_candidate_count,
            discarded_candidate_ids=list(puzzle.discarded_candidate_ids),
            warnings=warnings,
            timings_ms={
                "paper_rectify_ms": (detection_finished - started) * 1000.0,
                "card_detect_and_solve_ms": (time.perf_counter() - detection_finished)
                * 1000.0,
                "total_ms": (time.perf_counter() - started) * 1000.0,
                **{
                    f"solver_{key}": float(value)
                    for key, value in self.last_solver_stats.items()
                },
            },
        )
