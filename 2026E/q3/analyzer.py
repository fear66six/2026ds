"""Q3 card-fragment analysis using Q1 paper detection and rectification."""

from __future__ import annotations

import time

import numpy as np

from q1.vision import detect_paper, rectify_paper

from .card_solver import CardPuzzleSolver, PatternConfig, SolverConfig
from .card_solver.image_input import card_puzzle_from_rectified
from .models import CardPieceState, CardScene


class CardSceneAnalyzer:
    def __init__(
        self,
        *,
        layout: str = "top-bottom",
        solver_config: SolverConfig | None = None,
        pattern_config: PatternConfig | None = None,
    ) -> None:
        self.layout = layout
        self.solver_config = solver_config or SolverConfig()
        self.pattern_config = pattern_config or PatternConfig()
        self.last_paper = None
        self.last_puzzle = None
        self.last_solution = None

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
        try:
            puzzle = card_puzzle_from_rectified(
                rectified,
                paper_size_mm=(210.0, 297.0),
                pixels_per_mm=pixels_per_mm,
                layout=self.layout,
                solver_config=self.solver_config,
                pattern_config=self.pattern_config,
                image_path=snapshot.path,
            )
            solution = CardPuzzleSolver(
                config=self.solver_config,
                pattern_config=self.pattern_config,
            ).solve(puzzle.observations)
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
        return CardScene(
            cycle_index=cycle_index,
            image_path=snapshot.path,
            pieces=pieces,
            layout=puzzle.layout,
            divider_mm=puzzle.divider_mm,
            paper_valid=True,
            scene_valid=bool(solution.success),
            solution_success=bool(solution.success),
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
            warnings=[] if solution.success else [solution.reason or "CARD_SOLVE_FAILED"],
            timings_ms={
                "paper_rectify_ms": (detection_finished - started) * 1000.0,
                "card_detect_and_solve_ms": (time.perf_counter() - detection_finished)
                * 1000.0,
                "total_ms": (time.perf_counter() - started) * 1000.0,
            },
        )
