"""DFS and backtracking search for rigid polygon assembly."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

from .config import SolverConfig
from .geometry import Point, RigidTransform, normalize_angle, polygon_corner_angles_deg
from .models import (
    Connection,
    Edge,
    OpenEdge,
    Piece,
    PlacedPiece,
    Solution,
    SolverState,
)
from .validation import (
    FinalValidation,
    check_bbox,
    check_correct_side,
    check_final_rectangle,
    check_length_match,
    check_overlap,
    check_vertex_distance,
)


@dataclass
class SearchStats:
    """Counters useful for diagnostics and regression tests."""

    dfs_calls: int = 0
    candidate_attempts: int = 0
    placements: int = 0
    backtracks: int = 0
    length_rejections: int = 0
    side_rejections: int = 0
    vertex_rejections: int = 0
    bbox_rejections: int = 0
    overlap_rejections: int = 0
    final_rejections: int = 0
    direct_mapping_attempts: int = 0
    reversed_mapping_attempts: int = 0


@dataclass(frozen=True)
class _Candidate:
    score: float
    open_edge: OpenEdge
    piece: Piece
    edge: Edge
    mapping: str
    anchor: str
    partial: bool
    transform: RigidTransform


def calculate_pose(
    open_edge: OpenEdge,
    candidate_edge: Edge,
    mapping: str,
) -> RigidTransform:
    """Calculate a rigid pose for one of the two endpoint mappings.

    Reversed mapping uses ``theta_open + pi - theta_candidate`` so the
    directed edges oppose one another.  Direct mapping is also searched
    because independently extracted polygons may use opposite winding.
    Trying both endpoint correspondences never reflects or scales a piece.
    """

    if mapping == "direct":
        target = open_edge.p1
        target_angle = open_edge.angle
    elif mapping == "reversed":
        target = open_edge.p2
        target_angle = open_edge.angle + math.pi
    else:
        raise ValueError(f"unknown endpoint mapping: {mapping}")

    rotation = normalize_angle(target_angle - candidate_edge.angle)
    rotated_anchor = RigidTransform(rotation_rad=rotation).apply(candidate_edge.p1)
    translation = (target.x - rotated_anchor.x, target.y - rotated_anchor.y)
    return RigidTransform(rotation_rad=rotation, translation=translation)


def _calculate_anchored_pose(
    open_edge: OpenEdge,
    candidate_edge: Edge,
    mapping: str,
    anchor: str,
) -> RigidTransform:
    """Align one candidate endpoint to either end of an open-edge segment."""

    if mapping not in ("direct", "reversed"):
        raise ValueError(f"unknown endpoint mapping: {mapping}")
    if anchor not in ("start", "end"):
        raise ValueError(f"unknown edge anchor: {anchor}")
    same_direction = mapping == "direct"
    target_angle = open_edge.angle if same_direction else open_edge.angle + math.pi
    rotation = normalize_angle(target_angle - candidate_edge.angle)

    if anchor == "start":
        target = open_edge.p1
        candidate_anchor = candidate_edge.p1 if same_direction else candidate_edge.p2
    else:
        target = open_edge.p2
        candidate_anchor = candidate_edge.p2 if same_direction else candidate_edge.p1
    rotated_anchor = RigidTransform(rotation_rad=rotation).apply(candidate_anchor)
    return RigidTransform(
        rotation_rad=rotation,
        translation=(target.x - rotated_anchor.x, target.y - rotated_anchor.y),
    )


def _point_segment_distance(point: Point, edge: OpenEdge) -> float:
    dx = edge.p2.x - edge.p1.x
    dy = edge.p2.y - edge.p1.y
    denominator = dx * dx + dy * dy
    if denominator <= 1e-18:
        return math.dist(point.as_tuple(), edge.p1.as_tuple())
    projection = (
        (point.x - edge.p1.x) * dx + (point.y - edge.p1.y) * dy
    ) / denominator
    projection = min(1.0, max(0.0, projection))
    closest = Point(edge.p1.x + projection * dx, edge.p1.y + projection * dy)
    return math.dist(point.as_tuple(), closest.as_tuple())


def _partial_vertex_error(first: OpenEdge, second: OpenEdge) -> float:
    """Measure endpoints of the shorter segment against the longer segment."""

    shorter, longer = (first, second) if first.length <= second.length else (second, first)
    return max(
        _point_segment_distance(shorter.p1, longer),
        _point_segment_distance(shorter.p2, longer),
    )


def _subtract_collinear_overlap(
    parent: OpenEdge,
    covering: OpenEdge,
    tolerance: float,
) -> list[OpenEdge]:
    """Return unmatched parent portions, preserving its directed orientation."""

    dx = parent.p2.x - parent.p1.x
    dy = parent.p2.y - parent.p1.y
    length = parent.length
    unit_x, unit_y = dx / length, dy / length

    def coordinate(point: Point) -> float:
        return (point.x - parent.p1.x) * unit_x + (point.y - parent.p1.y) * unit_y

    covering_start = coordinate(covering.p1)
    covering_end = coordinate(covering.p2)
    overlap_start = max(0.0, min(covering_start, covering_end))
    overlap_end = min(length, max(covering_start, covering_end))
    residuals: list[OpenEdge] = []

    def point_at(offset: float) -> Point:
        return Point(parent.p1.x + offset * unit_x, parent.p1.y + offset * unit_y)

    if overlap_start > tolerance:
        residuals.append(
            OpenEdge(parent.piece_id, parent.edge_id, parent.p1, point_at(overlap_start))
        )
    if length - overlap_end > tolerance:
        residuals.append(
            OpenEdge(parent.piece_id, parent.edge_id, point_at(overlap_end), parent.p2)
        )
    return residuals


def _overlap_segment(first: OpenEdge, second: OpenEdge) -> tuple[Point, Point]:
    """Return the shared collinear interval for connection visualisation."""

    dx = first.p2.x - first.p1.x
    dy = first.p2.y - first.p1.y
    unit_x, unit_y = dx / first.length, dy / first.length
    values = [
        (point.x - first.p1.x) * unit_x + (point.y - first.p1.y) * unit_y
        for point in (second.p1, second.p2)
    ]
    start = max(0.0, min(values))
    end = min(first.length, max(values))
    return (
        Point(first.p1.x + start * unit_x, first.p1.y + start * unit_y),
        Point(first.p1.x + end * unit_x, first.p1.y + end * unit_y),
    )


def score_base_piece(piece: Piece, config: SolverConfig | None = None) -> float:
    """Score area, near-right angles and longest edge for base selection."""

    active_config = config or SolverConfig()
    angles = polygon_corner_angles_deg(piece.polygon)
    right_angle_count = sum(
        abs(angle - 90.0) <= active_config.base_right_angle_tolerance_deg
        for angle in angles
    )
    return (
        active_config.base_area_weight * piece.area
        + active_config.base_right_angle_weight * right_angle_count
        + active_config.base_longest_edge_weight * piece.longest_edge_length
    )


class PuzzleSolver:
    """Assemble up to four polygons into one allowed rectangle."""

    def __init__(
        self,
        config: SolverConfig | None = None,
        debug: bool = False,
    ) -> None:
        self.config = config or SolverConfig()
        self.debug = debug
        self.stats = SearchStats()
        self.visited_states: set[tuple[object, ...]] = set()
        self._pieces_by_id: dict[int, Piece] = {}
        self._total_piece_count = 0
        self._total_piece_area = 0.0
        self._last_validation: FinalValidation | None = None
        self._best_state: SolverState | None = None
        self._best_validation: FinalValidation | None = None

    def solve(self, pieces: Sequence[Piece] | Iterable[Piece]) -> Solution:
        """Search all edge-derived rigid poses using DFS and backtracking."""

        piece_list = list(pieces)
        self.stats = SearchStats()
        self.visited_states.clear()
        self._last_validation = None
        self._best_state = None
        self._best_validation = None

        input_error = self._validate_input(piece_list)
        if input_error is not None:
            return Solution(False, reason=input_error)

        self._pieces_by_id = {piece.id: piece for piece in piece_list}
        self._total_piece_count = len(piece_list)
        self._total_piece_area = sum(piece.area for piece in piece_list)
        base_piece = self._select_base_piece(piece_list)
        min_x, min_y, _, _ = base_piece.bounds
        base_transform = RigidTransform(0.0, (-min_x, -min_y))
        placed_base = PlacedPiece.from_piece(base_piece, base_transform)
        initial_state = SolverState(
            placed_pieces=[placed_base],
            used_piece_ids={base_piece.id},
            open_edges=list(placed_base.edges),
        )
        self._log(
            f"[BASE] piece={base_piece.id} area={base_piece.area:.3f} "
            f"translation=({-min_x:.3f}, {-min_y:.3f})"
        )

        solved_state = self._dfs(initial_state)
        if self.config.find_best_solution and self._best_state is not None:
            solved_state = self._best_state
            self._last_validation = self._best_validation
        if solved_state is None or self._last_validation is None:
            return Solution(False, reason="No valid assembly found")

        validation = self._last_validation
        return Solution(
            success=True,
            placed_pieces=tuple(sorted(solved_state.placed_pieces, key=lambda item: item.piece_id)),
            rectangle_width_mm=validation.long_side_mm,
            rectangle_height_mm=validation.short_side_mm,
            score=validation.score,
            rectangle=validation.rectangle,
            connections=tuple(solved_state.connections),
        )

    def plot_solution(self, solution: Solution, **kwargs):  # type: ignore[no-untyped-def]
        """Plot a successful result; forwards options to visualization."""

        from .visualization import plot_solution

        return plot_solution(solution, **kwargs)

    def plot_board_solution(
        self,
        pieces: Sequence[Piece],
        solution: Solution,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        """Plot Q2-style scattered pieces above and assembly below a divider."""

        from .visualization import plot_board_solution

        return plot_board_solution(pieces, solution, **kwargs)

    def animate_board_solution(
        self,
        pieces: Sequence[Piece],
        solution: Solution,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        """Create a one-piece-at-a-time board assembly animation."""

        from .visualization import animate_board_solution

        return animate_board_solution(pieces, solution, **kwargs)

    def _validate_input(self, pieces: list[Piece]) -> str | None:
        if not pieces:
            return "At least one piece is required"
        if len(pieces) > self.config.max_piece_count:
            return f"At most {self.config.max_piece_count} pieces are supported"
        identifiers = [piece.id for piece in pieces]
        if len(set(identifiers)) != len(identifiers):
            return "Piece IDs must be unique"
        for piece in pieces:
            if any(
                edge.length + self.config.geometry_tolerance_mm
                < self.config.min_edge_length_mm
                for edge in piece.edges
            ):
                return (
                    f"Piece {piece.id} has an edge shorter than "
                    f"{self.config.min_edge_length_mm:g} mm"
                )
        total_area = sum(piece.area for piece in pieces)
        maximum_area = self.config.max_long_side_mm * self.config.max_short_side_mm
        if total_area > maximum_area + self.config.area_tolerance_mm2:
            return "Total piece area exceeds the largest allowed rectangle"
        return None

    def _select_base_piece(self, pieces: list[Piece]) -> Piece:
        has_right_angle = any(
            any(
                abs(angle - 90.0) <= self.config.base_right_angle_tolerance_deg
                for angle in polygon_corner_angles_deg(piece.polygon)
            )
            for piece in pieces
        )
        if not has_right_angle:
            return max(pieces, key=lambda piece: (piece.area, piece.longest_edge_length, -piece.id))
        return max(
            pieces,
            key=lambda piece: (score_base_piece(piece, self.config), -piece.id),
        )

    def _dfs(self, state: SolverState) -> SolverState | None:
        depth = len(state.used_piece_ids) - 1
        self.stats.dfs_calls += 1
        self._log(f"[DFS] depth={depth} used={sorted(state.used_piece_ids)}")

        signature = self._state_signature(state)
        if signature in self.visited_states:
            return None
        self.visited_states.add(signature)

        if len(state.used_piece_ids) == self._total_piece_count:
            validation = check_final_rectangle(state, self.config)
            if validation.valid:
                current_best_score = (
                    self._best_validation.score
                    if self._best_validation is not None
                    and self._best_validation.score is not None
                    else math.inf
                )
                validation_score = (
                    validation.score if validation.score is not None else math.inf
                )
                if self._best_state is None or validation_score < current_best_score:
                    self._best_state = state
                    self._best_validation = validation
                self._log(
                    f"[FINAL] PASS rectangle={validation.long_side_mm:.3f}x"
                    f"{validation.short_side_mm:.3f} mm"
                )
                if self.config.find_best_solution:
                    stop_ratio = self.config.best_solution_stop_area_ratio
                    if (
                        stop_ratio is not None
                        and validation_score
                        <= self._total_piece_area * stop_ratio
                    ):
                        self._last_validation = validation
                        return state
                    return None
                self._last_validation = validation
                return state
            self.stats.final_rejections += 1
            self._log(f"[FINAL] FAIL {validation.reason}")
            return None

        candidates = self._generate_candidates(state)
        for candidate in candidates:
            self.stats.candidate_attempts += 1
            if candidate.mapping == "direct":
                self.stats.direct_mapping_attempts += 1
            else:
                self.stats.reversed_mapping_attempts += 1
            self._log(
                f"[TRY] piece={candidate.piece.id} edge={candidate.edge.edge_id} "
                f"open={candidate.open_edge.piece_id}:{candidate.open_edge.edge_id} "
                f"mapping={candidate.mapping} anchor={candidate.anchor} "
                f"partial={candidate.partial}"
            )
            self._log(
                f"[LENGTH] {candidate.open_edge.length:.3f} vs "
                f"{candidate.edge.length:.3f}"
            )
            self._log(
                f"[POSE] rotation={math.degrees(candidate.transform.rotation_rad):.3f}deg "
                f"translation={candidate.transform.translation}"
            )

            placed = PlacedPiece.from_piece(candidate.piece, candidate.transform)
            owner = state.placed_by_id(candidate.open_edge.piece_id)
            transformed_edge = placed.edge(candidate.edge.edge_id)
            if not check_correct_side(
                owner,
                candidate.open_edge,
                placed,
                transformed_edge,
                self.config.side_tolerance_mm2,
            ):
                self.stats.side_rejections += 1
                self._log("[CHECK] side=FAIL")
                continue
            self._log("[CHECK] side=PASS")

            if candidate.partial:
                vertex_error = _partial_vertex_error(
                    candidate.open_edge,
                    transformed_edge,
                )
                vertex_valid = vertex_error <= self.config.max_vertex_distance_mm
            else:
                vertex_valid, vertex_error = check_vertex_distance(
                    candidate.open_edge,
                    transformed_edge.p1,
                    transformed_edge.p2,
                    candidate.mapping,
                    self.config.max_vertex_distance_mm,
                )
            if not vertex_valid:
                self.stats.vertex_rejections += 1
                self._log(f"[CHECK] vertex_distance=FAIL error={vertex_error:.3f}")
                continue
            self._log(f"[CHECK] vertex_distance=PASS error={vertex_error:.3f}")

            if not check_bbox(state.placed_pieces, placed, self.config):
                self.stats.bbox_rejections += 1
                self._log("[CHECK] bbox=FAIL")
                continue
            self._log("[CHECK] bbox=PASS")

            overlap_valid, overlap_area = check_overlap(
                state.placed_pieces,
                placed,
                self.config.overlap_tolerance_mm2,
            )
            if not overlap_valid:
                self.stats.overlap_rejections += 1
                self._log(f"[CHECK] overlap=FAIL area={overlap_area:.3f}")
                continue
            self._log(f"[CHECK] overlap=PASS area={overlap_area:.3f}")

            child = self._add_piece(state, placed, candidate)
            self.stats.placements += 1
            result = self._dfs(child)
            if result is not None:
                return result
            self.stats.backtracks += 1
            self._log(
                f"[BACKTRACK] piece={candidate.piece.id} edge={candidate.edge.edge_id}"
            )
        return None

    def _generate_candidates(self, state: SolverState) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        unused_pieces = [
            piece
            for piece_id, piece in self._pieces_by_id.items()
            if piece_id not in state.used_piece_ids
        ]
        for open_edge in state.open_edges:
            for piece in unused_pieces:
                for edge in piece.edges:
                    length_matches = check_length_match(
                        open_edge.length,
                        edge.length,
                        self.config.length_tolerance_mm,
                    )
                    residual_length = abs(open_edge.length - edge.length)
                    partial_match = (
                        self.config.allow_partial_edge_matches
                        and not length_matches
                        and residual_length
                        >= self.config.partial_min_residual_mm
                        - self.config.length_tolerance_mm
                    )
                    if not length_matches and not partial_match:
                        self.stats.length_rejections += 1
                        continue
                    pose_options = (
                        (("direct", "start"), ("reversed", "end"))
                        if length_matches
                        else (
                            ("direct", "start"),
                            ("direct", "end"),
                            ("reversed", "start"),
                            ("reversed", "end"),
                        )
                    )
                    seen_poses: set[tuple[float, float, float]] = set()
                    for mapping, anchor in pose_options:
                        transform = _calculate_anchored_pose(
                            open_edge,
                            edge,
                            mapping,
                            anchor,
                        )
                        pose_key = (
                            round(transform.rotation_rad, 9),
                            round(transform.translation[0], 7),
                            round(transform.translation[1], 7),
                        )
                        if pose_key in seen_poses:
                            continue
                        seen_poses.add(pose_key)
                        score = self._candidate_score(
                            state,
                            open_edge,
                            edge,
                            transform,
                            mapping,
                            partial_match,
                        )
                        candidates.append(
                            _Candidate(
                                score,
                                open_edge,
                                piece,
                                edge,
                                mapping,
                                anchor,
                                partial_match,
                                transform,
                            )
                        )
        candidates.sort(
            key=lambda candidate: (
                candidate.score,
                candidate.piece.id,
                candidate.edge.edge_id,
                0 if candidate.mapping == "direct" else 1,
                candidate.anchor,
            )
        )
        return candidates

    def _candidate_score(
        self,
        state: SolverState,
        open_edge: OpenEdge,
        edge: Edge,
        transform: RigidTransform,
        mapping: str,
        partial: bool,
    ) -> float:
        transformed_p1 = transform.apply(edge.p1)
        transformed_p2 = transform.apply(edge.p2)
        transformed_edge = OpenEdge(
            edge.piece_id,
            edge.edge_id,
            transformed_p1,
            transformed_p2,
        )
        if partial:
            vertex_error = _partial_vertex_error(open_edge, transformed_edge)
        else:
            if mapping == "direct":
                targets = (open_edge.p1, open_edge.p2)
            else:
                targets = (open_edge.p2, open_edge.p1)
            vertex_error = max(
                math.dist(transformed_p1.as_tuple(), targets[0].as_tuple()),
                math.dist(transformed_p2.as_tuple(), targets[1].as_tuple()),
            )
        length_error = (
            self.config.length_tolerance_mm
            if partial
            else abs(open_edge.length - edge.length)
        )

        transformed_vertices = [transform.apply(point) for point in edge_owner_vertices(edge, self._pieces_by_id)]
        all_points = [
            point
            for placed in state.placed_pieces
            for point in placed.vertices
        ] + transformed_vertices
        xs = [point.x for point in all_points]
        ys = [point.y for point in all_points]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        short_side, long_side = sorted((width, height))
        shape_error = max(0.0, short_side - self.config.max_short_side_mm) + max(
            0.0, long_side - self.config.max_long_side_mm
        )
        return (
            self.config.weight_length * length_error
            + self.config.weight_vertex * vertex_error
            + self.config.weight_shape * shape_error
        )

    def _add_piece(
        self,
        state: SolverState,
        placed: PlacedPiece,
        candidate: _Candidate,
    ) -> SolverState:
        """Create a child state; the parent remains untouched for backtracking."""

        child = state.copy()
        child.placed_pieces.append(placed)
        child.used_piece_ids.add(placed.piece_id)
        removed = False
        retained_edges: list[OpenEdge] = []
        for edge in child.open_edges:
            if not removed and edge == candidate.open_edge:
                removed = True
                continue
            retained_edges.append(edge)
        child.open_edges = retained_edges

        transformed_edge = placed.edge(candidate.edge.edge_id)
        if candidate.partial:
            split_tolerance = self.config.length_tolerance_mm
            child.open_edges.extend(
                _subtract_collinear_overlap(
                    candidate.open_edge,
                    transformed_edge,
                    split_tolerance,
                )
            )
            child.open_edges.extend(
                _subtract_collinear_overlap(
                    transformed_edge,
                    candidate.open_edge,
                    split_tolerance,
                )
            )
        child.open_edges.extend(
            edge for edge in placed.edges if edge.edge_id != candidate.edge.edge_id
        )
        connection_start, connection_end = _overlap_segment(
            candidate.open_edge,
            transformed_edge,
        )
        child.connections.append(
            Connection(
                candidate.open_edge.piece_id,
                candidate.open_edge.edge_id,
                placed.piece_id,
                candidate.edge.edge_id,
                connection_start,
                connection_end,
            )
        )
        return child

    def _state_signature(self, state: SolverState) -> tuple[object, ...]:
        poses = tuple(
            sorted(
                (
                    placed.piece_id,
                    round(placed.rotation, self.config.signature_rotation_precision),
                    round(placed.x, self.config.signature_position_precision),
                    round(placed.y, self.config.signature_position_precision),
                )
                for placed in state.placed_pieces
            )
        )
        # The same poses can be reached through different connection trees.
        # Open edges affect all future branches, so they are part of the state.
        open_edge_ids = tuple(
            sorted(
                (
                    edge.piece_id,
                    edge.edge_id,
                    round(edge.p1.x, self.config.signature_position_precision),
                    round(edge.p1.y, self.config.signature_position_precision),
                    round(edge.p2.x, self.config.signature_position_precision),
                    round(edge.p2.y, self.config.signature_position_precision),
                )
                for edge in state.open_edges
            )
        )
        return (tuple(sorted(state.used_piece_ids)), poses, open_edge_ids)

    def _log(self, message: str) -> None:
        if self.debug:
            print(message)


def edge_owner_vertices(edge: Edge, pieces_by_id: dict[int, Piece]) -> tuple[Point, ...]:
    """Return source vertices for candidate scoring."""

    return tuple(pieces_by_id[edge.piece_id].vertices)
