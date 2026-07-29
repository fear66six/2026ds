import numpy as np

from q1.pieces import (
    TARGET_RECT_HEIGHT_MM,
    TARGET_RECT_WIDTH_MM,
    template_target_vertices_mm,
    target_rectangle_vertices_mm,
    verify_geometry_invariants,
)


def test_figure2_area_and_diagonal_markers():
    report = verify_geometry_invariants()
    assert report["area_ok"]
    assert report["diag_markers_ok"]
    assert report["total_area_cm2"] == 60.0


def test_four_templates_tile_target_rectangle_without_gap():
    origin = (55.0, 168.5)
    rect = target_rectangle_vertices_mm(origin)
    pieces = [template_target_vertices_mm(i, origin) for i in range(4)]

    assert rect[1, 0] - rect[0, 0] == TARGET_RECT_WIDTH_MM
    assert rect[2, 1] - rect[0, 1] == TARGET_RECT_HEIGHT_MM

    total_area = sum(abs(_polygon_area_mm(verts)) for verts in pieces)
    assert abs(total_area - TARGET_RECT_WIDTH_MM * TARGET_RECT_HEIGHT_MM) < 0.5

    xs = np.concatenate([verts[:, 0] for verts in pieces])
    ys = np.concatenate([verts[:, 1] for verts in pieces])
    assert abs(xs.min() - rect[:, 0].min()) < 0.5
    assert abs(xs.max() - rect[:, 0].max()) < 0.5
    assert abs(ys.min() - rect[:, 1].min()) < 0.5
    assert abs(ys.max() - rect[:, 1].max()) < 0.5


def _polygon_area_mm(vertices: np.ndarray) -> float:
    pts = np.asarray(vertices, dtype=np.float64)
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
