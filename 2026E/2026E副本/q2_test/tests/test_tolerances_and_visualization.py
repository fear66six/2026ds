import matplotlib

matplotlib.use("Agg")

import pytest
import matplotlib.image as mpimg
import numpy as np
from PIL import Image

from puzzle_solver import Piece, PuzzleSolver, SolverConfig
from puzzle_solver.models import OpenEdge
from puzzle_solver.sample_data import (
    board_scattered_four_piece_rectangle,
    simple_four_piece_rectangle,
)
from puzzle_solver.validation import check_length_match, check_vertex_distance
from puzzle_solver.visualization import save_board_animation, save_board_solution


def test_length_and_vertex_checks_use_configured_tolerances() -> None:
    assert check_length_match(30.0, 31.4, tolerance=1.5)
    assert not check_length_match(30.0, 31.6, tolerance=1.5)

    edge = OpenEdge(0, 0, Piece(0, [(0, 0), (30, 0), (0, 20)]).vertices[0], Piece(1, [(0, 0), (30, 0), (0, 20)]).vertices[1])
    valid, maximum = check_vertex_distance(
        edge,
        transformed_p1=edge.p1,
        transformed_p2=type(edge.p2)(edge.p2.x + 19.9, edge.p2.y),
        mapping="direct",
        maximum_mm=20.0,
    )
    assert valid
    assert maximum == pytest.approx(19.9)


def test_configuration_rejects_invalid_ranges() -> None:
    with pytest.raises(ValueError):
        SolverConfig(min_short_side_mm=91.0, max_short_side_mm=90.0)


def test_solution_visualization_can_be_saved(tmp_path) -> None:
    solver = PuzzleSolver()
    solution = solver.solve(simple_four_piece_rectangle())
    figure, axes = solver.plot_solution(solution)
    output = tmp_path / "solution.png"
    figure.savefig(output)

    assert axes.get_xlabel() == "x (mm)"
    assert output.exists()
    assert output.stat().st_size > 0


def test_board_visualization_places_fragments_on_both_sides_of_divider(tmp_path) -> None:
    pieces = board_scattered_four_piece_rectangle()
    solution = PuzzleSolver().solve(pieces)
    output = tmp_path / "board.png"
    save_board_solution(output, pieces, solution, dpi=80)
    image = mpimg.imread(output)

    assert output.stat().st_size > 0
    assert image.shape[0] > image.shape[1]
    grayscale = image[..., :3].mean(axis=2)
    midpoint = grayscale.shape[0] // 2
    assert (grayscale[midpoint - 1 : midpoint + 2] > 0.8).mean() > 0.9
    assert (grayscale[: midpoint - 3] > 0.8).sum() > 1000
    assert (grayscale[midpoint + 3 :] > 0.8).sum() > 1000


def test_board_animation_exports_multiple_gif_frames(tmp_path) -> None:
    pieces = board_scattered_four_piece_rectangle()
    solution = PuzzleSolver().solve(pieces)
    output = tmp_path / "assembly.gif"
    save_board_animation(
        output,
        pieces,
        solution,
        frames_per_piece=4,
        hold_frames=2,
        fps=12,
        dpi=45,
    )

    with Image.open(output) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames >= 12
        animation.seek(animation.n_frames - 1)
        final_frame = np.asarray(animation.convert("RGB"))
    midpoint = final_frame.shape[0] // 2
    assert (final_frame[midpoint + 3 :] > 220).all(axis=2).sum() > 1000
