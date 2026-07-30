import ast
from pathlib import Path

import pytest

from puzzle_solver import PuzzleSolver
from puzzle_solver.image_input import image_solver_config, load_q2_image_pieces


def test_package_does_not_import_parent_q2_code() -> None:
    """Keep the standalone package independent from the parent implementation."""

    package_directory = Path(__file__).resolve().parents[1] / "puzzle_solver"
    for source_path in package_directory.glob("*.py"):
        syntax_tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_roots: set[str] = set()
        for node in ast.walk(syntax_tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        assert "q2" not in imported_roots, source_path


@pytest.mark.parametrize(
    ("filename", "piece_count", "expected_long", "expected_short"),
    [
        ("q2_1.png", 3, 79.7, 60.4),
        ("q2_2.png", 2, 104.6, 69.4),
        ("q2_3.png", 3, 94.6, 92.0),
        ("q2_4.png", 4, 120.2, 70.5),
        ("q2_5.png", 4, 107.7, 67.7),
        ("test.png", 4, 100.1, 53.7),
    ],
)
def test_existing_q2_images_are_detected_and_solved(
    filename: str,
    piece_count: int,
    expected_long: float,
    expected_short: float,
) -> None:
    image_path = Path(__file__).resolve().parents[2] / filename
    if not image_path.exists():
        pytest.skip(f"image fixture {filename} is unavailable")

    detected = load_q2_image_pieces(image_path)
    solution = PuzzleSolver(image_solver_config(detected.pieces)).solve(detected.pieces)

    assert len(detected.pieces) == piece_count
    assert detected.divider_y_mm == pytest.approx(147.0, abs=2.0)
    assert solution.success, solution.reason
    assert solution.rectangle_width_mm == pytest.approx(expected_long, abs=1.0)
    assert solution.rectangle_height_mm == pytest.approx(expected_short, abs=1.0)
