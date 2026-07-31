"""Q2 white-fragment analysis using Q1 paper detection and rectification."""

from __future__ import annotations

import time

import numpy as np

from q1.vision import detect_paper, rectify_paper

from .models import WhitePieceState, WhitePuzzleScene
from .puzzle_solver import PuzzleSolver
from .puzzle_solver.image_input import (
    image_solver_config,
    q2_puzzle_from_rectified,
)
from .puzzle_solver.models import Solution


RECTIFIED_PIXELS_PER_MM = 5.0


def is_executable_solution(solution: Solution) -> bool:
    """Return whether a solver result is valid for physical motion planning."""

    return bool(
        solution.success
        and not solution.best_effort
        and solution.official_dimensions_valid is True
    )


class WhitePuzzleAnalyzer:
    def __init__(self, *, pixels_per_mm: float = RECTIFIED_PIXELS_PER_MM) -> None:
        self.pixels_per_mm = float(pixels_per_mm)
        self.last_paper = None
        self.last_puzzle = None
        self.last_solution = None

    def analyze(self, snapshot, cycle_index: int) -> WhitePuzzleScene:
        started = time.perf_counter()
        paper = detect_paper(snapshot.frame)
        if paper is None:
            return WhitePuzzleScene(
                cycle_index=cycle_index,
                image_path=snapshot.path,
                pieces=[],
                divider_y_mm=None,
                paper_valid=False,
                scene_valid=False,
                solution_success=False,
                exact_solution=False,
                official_dimensions_valid=None,
                warnings=["A4_PAPER_NOT_DETECTED"],
                timings_ms={"total_ms": (time.perf_counter() - started) * 1000.0},
            )

        self.last_paper = paper
        rectified = rectify_paper(
            snapshot.frame,
            paper,
            output_size=(
                int(round(210.0 * self.pixels_per_mm)),
                int(round(297.0 * self.pixels_per_mm)),
            ),
        )
        rectified_at = time.perf_counter()

        try:
            puzzle = q2_puzzle_from_rectified(
                rectified,
                paper_size_mm=(210.0, 297.0),
                pixels_per_mm=self.pixels_per_mm,
                image_path=snapshot.path,
            )
        except ValueError as exc:
            return WhitePuzzleScene(
                cycle_index=cycle_index,
                image_path=snapshot.path,
                pieces=[],
                divider_y_mm=None,
                paper_valid=True,
                scene_valid=False,
                solution_success=False,
                exact_solution=False,
                official_dimensions_valid=None,
                warnings=[str(exc)],
                timings_ms={
                    "paper_rectify_ms": (rectified_at - started) * 1000.0,
                    "total_ms": (time.perf_counter() - started) * 1000.0,
                },
            )

        solver = PuzzleSolver(image_solver_config(puzzle.pieces))
        solution = solver.solve(puzzle.pieces)
        self.last_puzzle = puzzle
        self.last_solution = solution
        executable = is_executable_solution(solution)
        pieces = [
            WhitePieceState(
                piece_id=piece.id,
                vertices_mm=np.asarray(
                    [point.as_tuple() for point in piece.vertices],
                    dtype=np.float64,
                ),
                center_mm=piece.centroid.as_tuple(),
                area_mm2=float(piece.area),
            )
            for piece in puzzle.pieces
        ]
        rectangle_size = None
        if solution.rectangle_width_mm is not None and solution.rectangle_height_mm is not None:
            rectangle_size = (
                float(solution.rectangle_width_mm),
                float(solution.rectangle_height_mm),
            )

        warnings: list[str] = []
        if not solution.success:
            warnings.append(solution.reason or "Q2_GEOMETRIC_SOLVE_FAILED")
        if solution.best_effort:
            warnings.append(solution.validation_warning or "Q2_BEST_EFFORT_REJECTED")
        if solution.success and solution.official_dimensions_valid is not True:
            warnings.append("Q2_OFFICIAL_DIMENSIONS_INVALID")

        solver_stats = {
            key: value
            for key, value in vars(solver.stats).items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
        return WhitePuzzleScene(
            cycle_index=cycle_index,
            image_path=snapshot.path,
            pieces=pieces,
            divider_y_mm=puzzle.divider_y_mm,
            paper_valid=True,
            scene_valid=executable,
            solution_success=bool(solution.success),
            exact_solution=bool(solution.success and not solution.best_effort),
            official_dimensions_valid=solution.official_dimensions_valid,
            best_effort=bool(solution.best_effort),
            rectangle_size_mm=rectangle_size,
            solution_score=solution.score,
            detected_candidate_count=puzzle.detected_candidate_count,
            warnings=warnings,
            solver_stats=solver_stats,
            timings_ms={
                "paper_rectify_ms": (rectified_at - started) * 1000.0,
                "piece_detect_and_solve_ms": (time.perf_counter() - rectified_at)
                * 1000.0,
                "total_ms": (time.perf_counter() - started) * 1000.0,
            },
        )

