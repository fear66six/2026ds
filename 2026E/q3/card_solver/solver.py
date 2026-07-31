"""Joint geometric and playing-card-pattern DFS with backtracking."""

from __future__ import annotations

from dataclasses import dataclass, replace
import itertools
import math
from typing import Iterable, Sequence

from .config import PatternConfig, SolverConfig
from .geometry import Point, RigidTransform, normalize_angle, polygon_angles_deg
from .models import (
    Edge,
    OpenEdge,
    Piece,
    PieceObservation,
    PlacedPiece,
    SeamScore,
    Solution,
    SolverState,
)
from .pattern_matching import PatternMatcher
from .validation import (
    FinalValidation,
    check_bbox,
    check_correct_side,
    check_final_assembly,
    is_uniform_rectangular_grid,
    is_uniform_rectangular_strips,
    check_length_match,
    check_overlap,
)


@dataclass
class SearchStats:
    dfs_calls: int = 0
    candidate_attempts: int = 0
    placements: int = 0
    backtracks: int = 0
    length_rejections: int = 0
    side_rejections: int = 0
    vertex_rejections: int = 0
    bbox_rejections: int = 0
    overlap_rejections: int = 0
    pattern_rejections: int = 0
    final_rejections: int = 0
    grid_candidate_attempts: int = 0
    grid_valid_candidates: int = 0
    strip_candidate_attempts: int = 0
    strip_valid_candidates: int = 0
    composite_edge_merges: int = 0
    expanded_searches: int = 0
    expanded_candidates: int = 0


@dataclass(frozen=True)
class _Candidate:
    score: float
    open_edge: OpenEdge
    piece: Piece
    edge: Edge
    mapping: str
    anchor: str
    partial: bool
    approximate: bool
    transform: RigidTransform
    seam: SeamScore


def calculate_pose(
    open_edge: OpenEdge,
    candidate_edge: Edge,
    mapping: str,
    anchor: str = "start",
) -> RigidTransform:
    """Align an edge using either endpoint correspondence, without scaling."""

    if mapping not in {"direct", "reversed"}:
        raise ValueError("mapping must be direct or reversed")
    if anchor not in {"start", "end", "center"}:
        raise ValueError("anchor must be start, end or center")
    same_direction = mapping == "direct"
    target_angle = open_edge.angle if same_direction else open_edge.angle + math.pi
    rotation = normalize_angle(target_angle - candidate_edge.angle)
    if anchor == "center":
        target = Point(
            0.5 * (open_edge.p1.x + open_edge.p2.x),
            0.5 * (open_edge.p1.y + open_edge.p2.y),
        )
        candidate_anchor = Point(
            0.5 * (candidate_edge.p1.x + candidate_edge.p2.x),
            0.5 * (candidate_edge.p1.y + candidate_edge.p2.y),
        )
    elif anchor == "start":
        target = open_edge.p1
        candidate_anchor = candidate_edge.p1 if same_direction else candidate_edge.p2
    else:
        target = open_edge.p2
        candidate_anchor = candidate_edge.p2 if same_direction else candidate_edge.p1
    rotated = RigidTransform(rotation).apply(candidate_anchor)
    return RigidTransform(rotation, (target.x - rotated.x, target.y - rotated.y))


def _point_segment_distance(point: Point, segment: OpenEdge) -> float:
    dx = segment.p2.x - segment.p1.x
    dy = segment.p2.y - segment.p1.y
    denominator = dx * dx + dy * dy
    if denominator <= 1e-12:
        return math.dist(point.as_tuple(), segment.p1.as_tuple())
    fraction = (
        (point.x - segment.p1.x) * dx + (point.y - segment.p1.y) * dy
    ) / denominator
    fraction = min(1.0, max(0.0, fraction))
    closest = Point(segment.p1.x + fraction * dx, segment.p1.y + fraction * dy)
    return math.dist(point.as_tuple(), closest.as_tuple())


def _partial_vertex_error(first: OpenEdge, second: OpenEdge) -> float:
    shorter, longer = (first, second) if first.length <= second.length else (second, first)
    return max(
        _point_segment_distance(shorter.p1, longer),
        _point_segment_distance(shorter.p2, longer),
    )


def _overlap_segment(first: OpenEdge, second: OpenEdge) -> tuple[Point, Point]:
    dx = (first.p2.x - first.p1.x) / first.length
    dy = (first.p2.y - first.p1.y) / first.length
    values = [
        (point.x - first.p1.x) * dx + (point.y - first.p1.y) * dy
        for point in (second.p1, second.p2)
    ]
    start = max(0.0, min(values))
    end = min(first.length, max(values))
    return (
        Point(first.p1.x + start * dx, first.p1.y + start * dy),
        Point(first.p1.x + end * dx, first.p1.y + end * dy),
    )


def _subtract_overlap(
    parent: OpenEdge,
    covering: OpenEdge,
    tolerance: float,
) -> list[OpenEdge]:
    dx = (parent.p2.x - parent.p1.x) / parent.length
    dy = (parent.p2.y - parent.p1.y) / parent.length
    values = [
        (point.x - parent.p1.x) * dx + (point.y - parent.p1.y) * dy
        for point in (covering.p1, covering.p2)
    ]
    overlap_start = max(0.0, min(values))
    overlap_end = min(parent.length, max(values))

    def point_at(offset: float) -> Point:
        return Point(parent.p1.x + offset * dx, parent.p1.y + offset * dy)

    output: list[OpenEdge] = []
    if overlap_start > tolerance:
        output.append(OpenEdge(parent.piece_id, parent.edge_id, parent.p1, point_at(overlap_start)))
    if parent.length - overlap_end > tolerance:
        output.append(OpenEdge(parent.piece_id, parent.edge_id, point_at(overlap_end), parent.p2))
    return output


def _undirected_angle_error_deg(first: OpenEdge, second: OpenEdge) -> float:
    """Return the smaller angle between segments, ignoring direction."""

    difference = abs(math.degrees(first.angle - second.angle)) % 180.0
    return min(difference, 180.0 - difference)


def _try_merge_open_edges(
    first: OpenEdge,
    second: OpenEdge,
    angle_tolerance_deg: float,
    distance_tolerance_mm: float,
) -> OpenEdge | None:
    """Join adjacent collinear boundary segments into one search edge."""

    if _undirected_angle_error_deg(first, second) > angle_tolerance_deg:
        return None

    unit_x = (first.p2.x - first.p1.x) / first.length
    unit_y = (first.p2.y - first.p1.y) / first.length

    def projected_coordinates(point: Point) -> tuple[float, float]:
        offset_x = point.x - first.p1.x
        offset_y = point.y - first.p1.y
        along = offset_x * unit_x + offset_y * unit_y
        perpendicular = abs(offset_x * unit_y - offset_y * unit_x)
        return along, perpendicular

    second_start, start_distance = projected_coordinates(second.p1)
    second_end, end_distance = projected_coordinates(second.p2)
    if max(start_distance, end_distance) > distance_tolerance_mm:
        return None

    second_min, second_max = sorted((second_start, second_end))
    interval_gap = max(0.0, second_min) - min(first.length, second_max)
    if interval_gap > distance_tolerance_mm:
        return None
    overlap_length = min(first.length, second_max) - max(0.0, second_min)
    # Positive-length overlap may be two sides of an unresolved internal seam,
    # not consecutive portions of the assembled exterior boundary.
    if overlap_length > distance_tolerance_mm:
        return None

    combined_min = min(0.0, second_min)
    combined_max = max(first.length, second_max)
    if combined_max - combined_min <= max(first.length, second.length) + 1e-7:
        return None
    return OpenEdge(
        first.piece_id,
        first.edge_id,
        Point(
            first.p1.x + combined_min * unit_x,
            first.p1.y + combined_min * unit_y,
        ),
        Point(
            first.p1.x + combined_max * unit_x,
            first.p1.y + combined_max * unit_y,
        ),
    )


def _merge_collinear_open_edges(
    edges: Sequence[OpenEdge],
    angle_tolerance_deg: float,
    distance_tolerance_mm: float,
) -> tuple[list[OpenEdge], int]:
    """Repeatedly merge adjacent collinear open segments, including chains."""

    merged_edges = list(edges)
    merge_count = 0
    while True:
        replacement: tuple[int, int, OpenEdge] | None = None
        for first_index, first in enumerate(merged_edges):
            for second_index in range(first_index + 1, len(merged_edges)):
                combined = _try_merge_open_edges(
                    first,
                    merged_edges[second_index],
                    angle_tolerance_deg,
                    distance_tolerance_mm,
                )
                if combined is not None:
                    replacement = (first_index, second_index, combined)
                    break
            if replacement is not None:
                break
        if replacement is None:
            return merged_edges, merge_count

        first_index, second_index, combined = replacement
        merged_edges = [
            edge
            for index, edge in enumerate(merged_edges)
            if index not in (first_index, second_index)
        ]
        merged_edges.append(combined)
        merge_count += 1


class CardPuzzleSolver:
    """Solve at most four textured polygons with DFS and geometric pruning."""

    def __init__(
        self,
        config: SolverConfig | None = None,
        pattern_config: PatternConfig | None = None,
        debug: bool = False,
    ) -> None:
        self.config = config or SolverConfig()
        self.pattern_config = pattern_config or PatternConfig()
        self.debug = debug
        self.stats = SearchStats()
        self._pieces: dict[int, Piece] = {}
        self._observations: dict[int, PieceObservation] = {}
        self._matcher = PatternMatcher({}, self.pattern_config)
        self._visited: set[tuple[object, ...]] = set()
        self._best_state: SolverState | None = None
        self._best_validation: FinalValidation | None = None
        self._optimal_found = False
        self._expanded_length_search = False
        self._stage_dfs_calls = 0

    def solve(
        self,
        items: Sequence[PieceObservation | Piece]
        | Iterable[PieceObservation | Piece],
    ) -> Solution:
        values = list(items)
        if len(values) > self.config.max_piece_count:
            return Solution(
                False,
                reason=f"At most {self.config.max_piece_count} pieces are supported",
            )
        # Two agreeing corner indices can propose an opposite-suit distractor
        # set.  Try that high-confidence hypothesis first for speed, but retain
        # the all-fragment hypothesis as a fallback so colour is never the only
        # authority for rejecting a multicolour face-card fragment.
        hypotheses: list[
            tuple[list[PieceObservation | Piece], tuple[int, ...]]
        ] = []
        selected_values, ignored_piece_ids = self._select_card_fragments(values)
        if ignored_piece_ids and len(selected_values) < len(values):
            hypotheses.append((selected_values, ignored_piece_ids))
        hypotheses.append((values, ()))

        last_failure = Solution(False, reason="No valid geometry and pattern assembly found")
        for hypothesis_values, hypothesis_ignored_ids in hypotheses:
            result = self._solve_exact(hypothesis_values, hypothesis_ignored_ids)
            if result.success:
                return result
            last_failure = result
        return last_failure

    def _solve_exact(
        self,
        values: list[PieceObservation | Piece],
        ignored_piece_ids: tuple[int, ...],
    ) -> Solution:
        """Solve one fixed fragment-membership hypothesis."""

        pieces = [item.piece if isinstance(item, PieceObservation) else item for item in values]
        observations = {
            item.piece.id: item for item in values if isinstance(item, PieceObservation)
        }
        error = self._validate_input(pieces, bool(observations))
        if error:
            return Solution(False, ignored_piece_ids=ignored_piece_ids, reason=error)
        self.stats = SearchStats()
        self._visited.clear()
        self._best_state = None
        self._best_validation = None
        self._optimal_found = False
        self._expanded_length_search = False
        self._stage_dfs_calls = 0
        self._pieces = {piece.id: piece for piece in pieces}
        self._observations = observations
        self._matcher = PatternMatcher(observations, self.pattern_config)

        strip_applicable = is_uniform_rectangular_strips(pieces, self.config)
        grid_applicable = is_uniform_rectangular_grid(pieces, self.config)
        if strip_applicable:
            if self._search_rectangular_strips(pieces):
                self._log("[STRIPS] selected globally validated strip assembly")
            else:
                self._log("[STRIPS] no globally valid strip assembly")
        elif grid_applicable:
            if self._search_rectangular_grid(pieces):
                self._log("[GRID] selected globally validated 2x2 card assembly")
            else:
                self._log("[GRID] no globally valid 2x2 card assembly")
        else:
            base = self._select_base(pieces)
            min_x, min_y, _, _ = base.bounds
            placed = PlacedPiece.from_piece(base, RigidTransform(0.0, (-min_x, -min_y)))
            initial = SolverState([placed], {base.id}, list(placed.edges))
            self._log(f"[BASE] piece={base.id} area={base.area:.2f}")
            if ignored_piece_ids:
                self._log(f"[FILTER] ignored distractors={list(ignored_piece_ids)}")
            self._dfs(initial, len(pieces))
            if (
                self._best_state is None
                and self.config.enable_expanded_length_search
            ):
                # Preserve the established fast search for all normal inputs.
                # Only an otherwise-unsolved puzzle pays for candidates in the
                # former 4..18 mm length-error dead zone.
                self.stats.expanded_searches += 1
                self._expanded_length_search = True
                self._stage_dfs_calls = 0
                self._visited.clear()
                self._optimal_found = False
                self._log("[SEARCH] retry with expanded length candidates")
                self._dfs(initial, len(pieces))
        if self._best_state is None or self._best_validation is None:
            return Solution(
                False,
                ignored_piece_ids=ignored_piece_ids,
                reason="No valid geometry and pattern assembly found",
            )
        validation = self._best_validation
        return Solution(
            success=True,
            placed_pieces=tuple(
                sorted(self._best_state.placed_pieces, key=lambda value: value.piece_id)
            ),
            rectangle_width_mm=validation.long_side_mm,
            rectangle_height_mm=validation.short_side_mm,
            geometry_score=validation.geometry_score,
            pattern_score=validation.pattern_score,
            pattern_confidence=validation.pattern_confidence,
            corner_layout_score=validation.corner_layout_score,
            corner_layout_confidence=validation.corner_layout_confidence,
            symmetry_score=validation.symmetry_score,
            symmetry_confidence=validation.symmetry_confidence,
            rectangle=validation.rectangle,
            seams=validation.seams,
            ignored_piece_ids=ignored_piece_ids,
        )

    def _select_card_fragments(
        self,
        values: list[PieceObservation | Piece],
    ) -> tuple[list[PieceObservation | Piece], tuple[int, ...]]:
        """Remove a strongly opposite-suit distractor when indices identify a card.

        Standard playing cards are monochromatic: diamonds/hearts are red and
        clubs/spades are black.  Two detected corner indices establish the
        target colour.  Ink-free fragments remain eligible because a valid cut
        can pass through an unprinted white region.
        """

        if not self.config.allow_distractor_pieces or not values:
            return values, ()
        if not all(isinstance(item, PieceObservation) for item in values):
            return values, ()
        observations = [item for item in values if isinstance(item, PieceObservation)]
        marker_observations = [item for item in observations if item.corner_markers]
        if sum(len(item.corner_markers) for item in marker_observations) < 2:
            return values, ()
        marker_red = sum(item.red_ink_area_mm2 for item in marker_observations)
        marker_black = sum(item.black_ink_area_mm2 for item in marker_observations)
        ratio = self.pattern_config.suit_dominance_ratio
        minimum = self.pattern_config.suit_min_ink_area_mm2
        if marker_red >= minimum and marker_red >= ratio * max(marker_black, 1e-9):
            target = "red"
        elif marker_black >= minimum and marker_black >= ratio * max(marker_red, 1e-9):
            target = "black"
        else:
            return values, ()

        selected: list[PieceObservation | Piece] = []
        ignored: list[int] = []
        for item in observations:
            target_area = (
                item.red_ink_area_mm2 if target == "red" else item.black_ink_area_mm2
            )
            opposite_area = (
                item.black_ink_area_mm2 if target == "red" else item.red_ink_area_mm2
            )
            clearly_opposite = (
                opposite_area >= minimum
                and opposite_area >= ratio * max(target_area, 1e-9)
            )
            if clearly_opposite:
                ignored.append(item.piece.id)
            else:
                selected.append(item)
        if len(selected) < 2 or sum(
            len(item.corner_markers)
            for item in selected
            if isinstance(item, PieceObservation)
        ) < 2:
            return values, ()
        return selected, tuple(sorted(ignored))

    def _validate_input(self, pieces: list[Piece], image_mode: bool) -> str | None:
        if not pieces:
            return "At least one piece is required"
        if len(pieces) > self.config.max_piece_count:
            return f"At most {self.config.max_piece_count} pieces are supported"
        if len({piece.id for piece in pieces}) != len(pieces):
            return "Piece IDs must be unique"
        minimum = self.config.image_min_edge_mm if image_mode else self.config.min_physical_edge_mm
        for piece in pieces:
            if min(edge.length for edge in piece.edges) + 1e-7 < minimum:
                return f"Piece {piece.id} has an edge shorter than {minimum:g} mm"
        total_area = sum(piece.area for piece in pieces)
        maximum_area = self.config.max_long_side_mm * self.config.max_short_side_mm
        if total_area > maximum_area + self.config.max_final_gap_area_mm2:
            return "Total piece area exceeds the largest target rectangle"
        return None

    def _select_base(self, pieces: list[Piece]) -> Piece:
        def score(piece: Piece) -> tuple[float, int]:
            right_angles = sum(
                abs(angle - 90.0) <= self.config.base_right_angle_tolerance_deg
                for angle in polygon_angles_deg(piece.polygon)
            )
            return (piece.area + 50.0 * right_angles + piece.longest_edge_length, -piece.id)

        return max(pieces, key=score)

    def _search_rectangular_grid(self, pieces: list[Piece]) -> bool:
        """Evaluate the common four-quarter-card layout without scaling.

        Four rectangular card quarters have many indistinguishable equal
        edges, which makes a connection-tree DFS sensitive to pixel endpoint
        error.  For this specific, detectable geometry there are only
        ``4! * 2**4 = 384`` rigid candidates: every slot permutation and the
        two 180-degree orientations of each piece.  Geometry, seam texture,
        corner-index chirality and symmetry are still fully revalidated.
        """

        if not is_uniform_rectangular_grid(pieces, self.config):
            return False

        orientations: dict[int, tuple[float, float]] = {}
        for piece in pieces:
            rectangle = piece.polygon.minimum_rotated_rectangle
            corners = list(rectangle.exterior.coords)[:-1]
            rectangle_edges = []
            for index in range(4):
                first = corners[index]
                second = corners[(index + 1) % 4]
                dx, dy = second[0] - first[0], second[1] - first[1]
                rectangle_edges.append((math.hypot(dx, dy), math.atan2(dy, dx)))
            short_edge_angle = min(rectangle_edges, key=lambda value: value[0])[1]
            base_rotation = normalize_angle(-short_edge_angle)
            orientations[piece.id] = (
                base_rotation,
                normalize_angle(base_rotation + math.pi),
            )

        slots = ("top-left", "top-right", "bottom-left", "bottom-right")
        found = False
        for permutation in itertools.permutations(pieces):
            rotation_sets = (orientations[piece.id] for piece in permutation)
            for rotations in itertools.product(*rotation_sets):
                self.stats.grid_candidate_attempts += 1
                placed_pieces: list[PlacedPiece] = []
                for slot, piece, rotation in zip(slots, permutation, rotations):
                    rotated = PlacedPiece.from_piece(piece, RigidTransform(rotation))
                    min_x, min_y, max_x, max_y = rotated.polygon.bounds
                    translation_x = (
                        -max_x if slot in ("top-left", "bottom-left") else -min_x
                    )
                    translation_y = (
                        -max_y if slot in ("top-left", "top-right") else -min_y
                    )
                    placed_pieces.append(
                        PlacedPiece.from_piece(
                            piece,
                            RigidTransform(
                                rotation,
                                (translation_x, translation_y),
                            ),
                        )
                    )
                state = SolverState(
                    placed_pieces,
                    {piece.piece_id for piece in placed_pieces},
                    [],
                )
                validation = check_final_assembly(
                    state,
                    self.config,
                    self._matcher,
                    self.pattern_config,
                )
                if not validation.valid:
                    continue
                self.stats.grid_valid_candidates += 1
                found = True
                if (
                    self._best_validation is None
                    or self._validation_objective(validation)
                    < self._validation_objective(self._best_validation)
                ):
                    self._best_state = state
                    self._best_validation = validation
        return found

    def _search_rectangular_strips(self, pieces: list[Piece]) -> bool:
        """Exhaustively arrange two to four elongated rectangular strips.

        A strip puzzle has only ``n! * 2**n`` physical candidates: strip
        order and the two non-reflected 180-degree orientations.  Stacking
        bounding rectangles avoids connection-tree sensitivity to one-pixel
        endpoint errors while preserving each piece's exact rigid geometry.
        """

        if not is_uniform_rectangular_strips(pieces, self.config):
            return False

        orientations: dict[int, tuple[float, float]] = {}
        for piece in pieces:
            rectangle = piece.polygon.minimum_rotated_rectangle
            corners = list(rectangle.exterior.coords)[:-1]
            rectangle_edges = []
            for index in range(4):
                first = corners[index]
                second = corners[(index + 1) % 4]
                dx, dy = second[0] - first[0], second[1] - first[1]
                rectangle_edges.append((math.hypot(dx, dy), math.atan2(dy, dx)))
            long_edge_angle = max(rectangle_edges, key=lambda value: value[0])[1]
            base_rotation = normalize_angle(-long_edge_angle)
            orientations[piece.id] = (
                base_rotation,
                normalize_angle(base_rotation + math.pi),
            )

        found = False
        for permutation in itertools.permutations(pieces):
            rotation_sets = (orientations[piece.id] for piece in permutation)
            for rotations in itertools.product(*rotation_sets):
                self.stats.strip_candidate_attempts += 1
                placed_pieces: list[PlacedPiece] = []
                cursor_y = 0.0
                for piece, rotation in zip(permutation, rotations):
                    rotated = PlacedPiece.from_piece(piece, RigidTransform(rotation))
                    min_x, min_y, max_x, max_y = rotated.polygon.bounds
                    translation_x = -0.5 * (min_x + max_x)
                    translation_y = cursor_y - min_y
                    placed_pieces.append(
                        PlacedPiece.from_piece(
                            piece,
                            RigidTransform(rotation, (translation_x, translation_y)),
                        )
                    )
                    cursor_y += max_y - min_y
                state = SolverState(
                    placed_pieces,
                    {piece.piece_id for piece in placed_pieces},
                    [],
                )
                validation = check_final_assembly(
                    state,
                    self.config,
                    self._matcher,
                    self.pattern_config,
                )
                if not validation.valid:
                    continue
                self.stats.strip_valid_candidates += 1
                found = True
                self._log(
                    "[STRIPS] valid order="
                    f"{[piece.id for piece in permutation]} "
                    f"pattern={validation.pattern_score:.3f} "
                    f"corners={validation.corner_layout_score:.3f} "
                    f"symmetry={validation.symmetry_score:.3f}"
                )
                if (
                    self._best_validation is None
                    or self._validation_objective(validation)
                    < self._validation_objective(self._best_validation)
                ):
                    self._best_state = state
                    self._best_validation = validation
        return found

    def _dfs(self, state: SolverState, total_count: int) -> None:
        self.stats.dfs_calls += 1
        self._stage_dfs_calls += 1
        if self._stage_dfs_calls > self.config.max_search_nodes:
            return
        self._log(f"[DFS] depth={len(state.used_piece_ids)-1} used={sorted(state.used_piece_ids)}")
        signature = self._signature(state)
        if signature in self._visited:
            return
        self._visited.add(signature)
        if len(state.used_piece_ids) == total_count:
            validation = check_final_assembly(
                state, self.config, self._matcher, self.pattern_config
            )
            if not validation.valid:
                self.stats.final_rejections += 1
                self._log(f"[FINAL] FAIL {validation.reason}")
                return
            objective = self._validation_objective(validation)
            best_objective = (
                self._validation_objective(self._best_validation)
                if self._best_validation is not None
                else math.inf
            )
            if objective < best_objective:
                self._best_state = state
                self._best_validation = validation
                self._log(
                    f"[FINAL] PASS {validation.long_side_mm:.2f}x"
                    f"{validation.short_side_mm:.2f} pattern={validation.pattern_score:.3f} "
                    f"corners={validation.corner_layout_score:.3f} "
                    f"symmetry={validation.symmetry_score:.3f}"
                )
                geometry_good = (
                    (validation.geometry_score or 0.0)
                    <= self.config.best_solution_stop_gap_ratio
                )
                if not self._observations:
                    self._optimal_found = geometry_good
                else:
                    corner_good = (
                        validation.corner_layout_confidence <= 0.0
                        or validation.corner_layout_score
                        <= self.config.best_solution_stop_corner_error
                    )
                    symmetry_good = (
                        validation.symmetry_confidence <= 0.0
                        or validation.symmetry_score
                        <= self.config.best_solution_stop_symmetry_error
                    )
                    self._optimal_found = (
                        geometry_good
                        and corner_good
                        and symmetry_good
                        and validation.pattern_confidence
                        >= self.config.best_solution_stop_pattern_confidence
                        and validation.pattern_score
                        <= self.config.best_solution_stop_pattern_error
                    )
            return

        for candidate in self._generate_candidates(state):
            self.stats.candidate_attempts += 1
            self._log(
                f"[TRY] piece={candidate.piece.id} edge={candidate.edge.edge_id} "
                f"open={candidate.open_edge.piece_id}:{candidate.open_edge.edge_id} "
                f"mapping={candidate.mapping} partial={candidate.partial} "
                f"approximate={candidate.approximate}"
            )
            placed = PlacedPiece.from_piece(candidate.piece, candidate.transform)
            owner = state.placed_by_id(candidate.open_edge.piece_id)
            placed = self._resolve_raster_slivers(state, placed, owner, candidate.open_edge)
            transformed_edge = placed.edge(candidate.edge.edge_id)
            if not check_correct_side(owner, candidate.open_edge, placed, 1e-7):
                self.stats.side_rejections += 1
                self._log("[CHECK] side=FAIL")
                continue
            vertex_error = _partial_vertex_error(candidate.open_edge, transformed_edge)
            if vertex_error > self.config.max_vertex_distance_mm:
                self.stats.vertex_rejections += 1
                self._log(f"[CHECK] vertex=FAIL error={vertex_error:.2f}")
                continue
            if not check_bbox(state.placed_pieces, placed, self.config):
                self.stats.bbox_rejections += 1
                self._log("[CHECK] bbox=FAIL")
                continue
            overlap_ok, overlap_area = check_overlap(
                state.placed_pieces,
                placed,
                self.config,
                allow_sliver=False,
            )
            if not overlap_ok:
                self.stats.overlap_rejections += 1
                self._log(f"[CHECK] overlap=FAIL area={overlap_area:.2f}")
                continue
            seam_start, seam_end = _overlap_segment(
                candidate.open_edge, transformed_edge
            )
            active_seam = self._score_connection_seam(
                owner,
                candidate.open_edge,
                placed,
                candidate.edge.edge_id,
                seam_start,
                seam_end,
            )
            candidate = replace(
                candidate,
                transform=placed.transform,
                seam=active_seam,
            )
            if self._matcher.rejects(candidate.seam):
                self.stats.pattern_rejections += 1
                self._log(
                    f"[CHECK] pattern=FAIL error={candidate.seam.error:.3f} "
                    f"confidence={candidate.seam.confidence:.3f}"
                )
                continue
            self._log(
                f"[CHECK] PASS pattern={candidate.seam.error:.3f}/"
                f"{candidate.seam.confidence:.3f}"
            )
            child = self._add_piece(state, placed, candidate)
            self.stats.placements += 1
            before = self._best_state
            self._dfs(child, total_count)
            if self._optimal_found:
                return
            if not self.config.find_best_solution and self._best_state is not None:
                return
            self.stats.backtracks += 1
            if before is self._best_state:
                self._log(f"[BACKTRACK] piece={candidate.piece.id}")

    def _resolve_raster_slivers(
        self,
        state: SolverState,
        placed: PlacedPiece,
        owner: PlacedPiece,
        open_edge: OpenEdge,
    ) -> PlacedPiece:
        """Slide along the joined edge to remove a narrow second-edge overlap.

        Independent contour fits can make a four-piece loop fail to close by a
        few pixels. The initial candidate may therefore contain an allowed
        narrow sliver. Moving only along the already joined edge preserves that
        contact while removing overlap with another neighbour; no scaling or
        reflection is introduced.
        """

        others = [
            item for item in state.placed_pieces if item.piece_id != owner.piece_id
        ]
        if not others:
            return placed

        def overlap_area(value: PlacedPiece) -> float:
            return sum(value.polygon.intersection(item.polygon).area for item in others)

        current_area = overlap_area(placed)
        target_area = min(1.0, self.config.overlap_tolerance_mm2)
        if current_area <= target_area:
            return placed
        tangent_x = (open_edge.p2.x - open_edge.p1.x) / open_edge.length
        tangent_y = (open_edge.p2.y - open_edge.p1.y) / open_edge.length
        step = 0.25
        maximum_steps = max(
            1, int(math.ceil(self.config.max_overlap_sliver_width_mm / step)) + 4
        )
        current = placed
        for _ in range(maximum_steps):
            options: list[tuple[float, PlacedPiece]] = []
            for direction in (-1.0, 1.0):
                transform = RigidTransform(
                    current.rotation,
                    (
                        current.x + direction * step * tangent_x,
                        current.y + direction * step * tangent_y,
                    ),
                )
                trial = PlacedPiece.from_piece(current.source_piece, transform)
                options.append((overlap_area(trial), trial))
            best_area, best = min(options, key=lambda item: item[0])
            if best_area >= current_area - 1e-6:
                break
            current, current_area = best, best_area
            if current_area <= target_area:
                break
        return current

    def _generate_candidates(self, state: SolverState) -> list[_Candidate]:
        output: list[_Candidate] = []
        unused = [piece for piece in self._pieces.values() if piece.id not in state.used_piece_ids]
        for open_edge in state.open_edges:
            owner = state.placed_by_id(open_edge.piece_id)
            for piece in unused:
                for edge in piece.edges:
                    difference = abs(open_edge.length - edge.length)
                    exact = check_length_match(
                        open_edge.length,
                        edge.length,
                        self.config.length_tolerance_mm,
                    )
                    approximate = (
                        self._expanded_length_search
                        and not exact
                        and difference
                        <= self.config.approximate_full_match_tolerance_mm
                    )
                    strict_partial = (
                        self.config.allow_partial_edge_matches
                        and not exact
                        and min(open_edge.length, edge.length) >= self.config.min_connection_length_mm
                        and difference >= self.config.partial_min_residual_mm
                    )
                    expanded_partial = (
                        self.config.allow_partial_edge_matches
                        and self._expanded_length_search
                        and not exact
                        and not approximate
                        and min(open_edge.length, edge.length)
                        >= self.config.min_connection_length_mm
                        and difference < self.config.partial_min_residual_mm
                    )
                    partial = strict_partial or expanded_partial
                    if not exact and not approximate and not partial:
                        self.stats.length_rejections += 1
                        continue
                    # Raster endpoints carry independent error.  Even when
                    # lengths are within tolerance, anchoring the shorter
                    # observed edge at the other end can be the only pose that
                    # closes a four-piece loop.  Exact equal edges collapse to
                    # duplicate poses and are removed by ``seen`` below.
                    options = (
                        (("direct", "center"), ("reversed", "center"))
                        if approximate
                        else (
                            ("direct", "start"),
                            ("direct", "end"),
                            ("reversed", "start"),
                            ("reversed", "end"),
                        )
                    )
                    seen: set[tuple[float, float, float]] = set()
                    for mapping, anchor in options:
                        transform = calculate_pose(open_edge, edge, mapping, anchor)
                        key = (
                            round(transform.rotation_rad, 8),
                            round(transform.translation[0], 6),
                            round(transform.translation[1], 6),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        placed = PlacedPiece.from_piece(piece, transform)
                        transformed_edge = placed.edge(edge.edge_id)
                        # Pattern comparison is more expensive than these
                        # geometric hard checks. Reject impossible poses before
                        # sampling texture profiles; DFS repeats the checks
                        # after optional sliver correction for safety.
                        if not check_correct_side(
                            owner, open_edge, placed, 1e-7
                        ):
                            continue
                        if (
                            _partial_vertex_error(open_edge, transformed_edge)
                            > self.config.max_vertex_distance_mm
                        ):
                            continue
                        if not check_bbox(state.placed_pieces, placed, self.config):
                            continue
                        preliminary_overlap, _ = check_overlap(
                            state.placed_pieces,
                            placed,
                            self.config,
                            allow_sliver=True,
                        )
                        if not preliminary_overlap:
                            continue
                        seam_start, seam_end = _overlap_segment(open_edge, transformed_edge)
                        if math.dist(seam_start.as_tuple(), seam_end.as_tuple()) < self.config.min_connection_length_mm:
                            continue
                        seam = self._score_connection_seam(
                            owner,
                            open_edge,
                            placed,
                            edge.edge_id,
                            seam_start,
                            seam_end,
                        )
                        output.append(
                            _Candidate(
                                self._candidate_score(
                                    state,
                                    open_edge,
                                    edge,
                                    placed,
                                    transformed_edge,
                                    partial,
                                    approximate,
                                    seam,
                                ),
                                open_edge,
                                piece,
                                edge,
                                mapping,
                                anchor,
                                partial,
                                approximate,
                                transform,
                                seam,
                            )
                        )
                        if approximate or expanded_partial:
                            self.stats.expanded_candidates += 1
        output.sort(
            key=lambda item: (
                item.score,
                item.piece.id,
                item.edge.edge_id,
                item.mapping,
                item.anchor,
            )
        )
        return output

    def _score_connection_seam(
        self,
        owner: PlacedPiece,
        open_edge: OpenEdge,
        placed: PlacedPiece,
        placed_edge_id: int,
        seam_start: Point,
        seam_end: Point,
    ) -> SeamScore:
        """Score a real source edge, deferring composite seams to final checks.

        A composite search edge can span boundaries from multiple placed
        pieces, so no single source texture profile represents its full
        length. Intermediate rejection would therefore be unsafe. The final
        validator discovers and scores every actual pairwise seam after all
        polygons are placed.
        """

        source_edge = owner.edge(open_edge.edge_id)
        if (
            open_edge.length
            > source_edge.length
            + self.config.open_edge_merge_distance_tolerance_mm
        ):
            return SeamScore(
                owner.piece_id,
                open_edge.edge_id,
                placed.piece_id,
                placed_edge_id,
                seam_start,
                seam_end,
                0.0,
                0.0,
            )
        return self._matcher.score(
            owner,
            open_edge.edge_id,
            placed,
            placed_edge_id,
            seam_start,
            seam_end,
        )

    def _candidate_score(
        self,
        state: SolverState,
        open_edge: OpenEdge,
        edge: Edge,
        placed: PlacedPiece,
        transformed_edge: OpenEdge,
        partial: bool,
        approximate: bool,
        seam: SeamScore,
    ) -> float:
        vertex_error = _partial_vertex_error(open_edge, transformed_edge)
        raw_length_error = abs(open_edge.length - edge.length)
        if approximate:
            length_error = raw_length_error
        elif partial and raw_length_error >= self.config.partial_min_residual_mm:
            length_error = self.config.length_tolerance_mm
        else:
            length_error = raw_length_error
        points = [point for item in state.placed_pieces for point in item.vertices] + list(placed.vertices)
        width = max(point.x for point in points) - min(point.x for point in points)
        height = max(point.y for point in points) - min(point.y for point in points)
        short_side, long_side = sorted((width, height))
        shape_error = max(0.0, short_side - self.config.max_short_side_mm) + max(
            0.0, long_side - self.config.max_long_side_mm
        )
        return (
            self.config.weight_length * length_error
            + self.config.weight_vertex * vertex_error
            + self.config.weight_shape * shape_error
            + self.config.weight_pattern
            * seam.confidence
            * (seam.error - self.config.pattern_confidence_reward)
        )

    def _add_piece(
        self,
        state: SolverState,
        placed: PlacedPiece,
        candidate: _Candidate,
    ) -> SolverState:
        child = state.copy()
        child.placed_pieces.append(placed)
        child.used_piece_ids.add(placed.piece_id)
        removed = False
        retained: list[OpenEdge] = []
        for edge in child.open_edges:
            if not removed and edge == candidate.open_edge:
                removed = True
            else:
                retained.append(edge)
        child.open_edges = retained
        transformed_edge = placed.edge(candidate.edge.edge_id)
        if candidate.partial:
            tolerance = self.config.length_tolerance_mm
            child.open_edges.extend(_subtract_overlap(candidate.open_edge, transformed_edge, tolerance))
            child.open_edges.extend(_subtract_overlap(transformed_edge, candidate.open_edge, tolerance))
        child.open_edges.extend(
            edge for edge in placed.edges if edge.edge_id != candidate.edge.edge_id
        )
        if self.config.merge_collinear_open_edges:
            child.open_edges, merge_count = _merge_collinear_open_edges(
                child.open_edges,
                self.config.open_edge_merge_angle_tolerance_deg,
                self.config.open_edge_merge_distance_tolerance_mm,
            )
            self.stats.composite_edge_merges += merge_count
            if merge_count:
                self._log(
                    f"[OPEN_EDGE] composite_merges={merge_count} "
                    f"remaining={len(child.open_edges)}"
                )
        child.seams.append(candidate.seam)
        return child

    def _validation_objective(self, validation: FinalValidation) -> float:
        confidence = validation.pattern_confidence
        if not validation.strict_global_pattern:
            return (
                self.config.irregular_geometry_weight
                * float(validation.geometry_score or 0.0)
                + self.config.irregular_pattern_weight
                * validation.pattern_score
                * confidence
            )
        pattern_cost = validation.pattern_score * confidence + (
            self.config.pattern_uncertainty_penalty * (1.0 - confidence)
        )
        return float(validation.geometry_score or 0.0) + (
            self.config.weight_pattern * pattern_cost
        ) + (
            self.config.weight_corner_layout
            * validation.corner_layout_confidence
            * validation.corner_layout_score
        ) + (
            self.config.weight_symmetry
            * validation.symmetry_confidence
            * validation.symmetry_score
        )

    def _signature(self, state: SolverState) -> tuple[object, ...]:
        poses = tuple(
            sorted(
                (
                    item.piece_id,
                    round(item.rotation, self.config.signature_rotation_precision),
                    round(item.x, self.config.signature_position_precision),
                    round(item.y, self.config.signature_position_precision),
                )
                for item in state.placed_pieces
            )
        )
        edges = tuple(
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
        return (tuple(sorted(state.used_piece_ids)), poses, edges)

    def _log(self, message: str) -> None:
        if self.debug:
            print(message)
