"""Q1每轮观察并只执行一个碎片的闭环控制器。"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import cv2

from .pieces import target_rectangle_vertices_mm
from .calibration import ArmCoordinateMapper
from .models import ExecutionResult, SceneAnalysis, SingleMovePlan
from .motion import plan_single_move
from .planning_advisory import build_four_piece_advisory
from .runtime_config import Q1RuntimeConfig
from .auditor import audit_scene
from .selector import select_next_piece
from .state_machine import Q1State, Q1StateMachine, StateEvent
from . import config as vision_config
from .vision import cm_to_px, rectify_paper


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class RunRecorder:
    def __init__(self, root: Path, mode: str, config: Q1RuntimeConfig) -> None:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.run_id = run_id
        self.directory = (root / run_id).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.events_path = self.directory / "events.jsonl"
        self.write(
            "run.json",
            {
                "run_id": run_id,
                "mode": mode,
                "created_at": datetime.now().isoformat(),
                **config.report_metadata(),
                "config": config,
            },
        )
        self.latest_path = self.directory.parent / "LATEST_RUN.txt"
        self.latest_path.write_text(str(self.directory) + "\n", encoding="utf-8")
        self.announce()

    def announce(self, *, prefix: str = "Q1_RUN") -> None:
        """Print stable, copyable paths even when the run later fails."""
        print(f"{prefix}_ID={self.run_id}", flush=True)
        print(f"{prefix}_DIR={self.directory}", flush=True)
        print(f"{prefix}_EVENTS={self.events_path}", flush=True)

    def write(self, relative: str, value: Any) -> None:
        path = self.directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_jsonable(value), ensure_ascii=False, indent=2), encoding="utf-8")

    def event(self, event: StateEvent) -> None:
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(_jsonable(event), ensure_ascii=False) + "\n")


class Q1Controller:
    def __init__(self, *, camera, analyzer, robot, magnet, mapper: ArmCoordinateMapper, config: Q1RuntimeConfig) -> None:
        self.camera = camera
        self.analyzer = analyzer
        self.robot = robot
        self.magnet = magnet
        self.mapper = mapper
        self.config = config
        self.machine = Q1StateMachine()
        self.recorder = RunRecorder(config.run_root, config.mode, config)
        self.previous_scene: SceneAnalysis | None = None
        self.previous_action: SingleMovePlan | None = None
        self.executions: list[ExecutionResult] = []

    def _record_physical_pick_verification(self, cycle: int, audit) -> None:
        if self.previous_action is None:
            return
        template_id = self.previous_action.template_id
        if template_id not in audit.placed_ok:
            return
        self.config.physical_pick_verified = True
        for execution in reversed(self.executions):
            if execution.template_id == template_id:
                execution.release_confirmed = True
                execution.details["physical_pick_verified_by_vision"] = True
                execution.details["verification_cycle"] = cycle
                break
        self.recorder.write(
            f"cycle_{cycle:02d}/physical_pick_verification.json",
            {
                "physical_pick_enabled": True,
                "physical_pick_verified": True,
                "magnet_backend": "stm32",
                "template_id": template_id,
                "evidence": "post-move visual audit classified template as PLACED_OK",
                "audit": audit,
            },
        )

    def _transition(
        self,
        state: Q1State,
        cycle: int,
        template_id: str | None = None,
        reason: str = "",
        data: dict | None = None,
    ) -> None:
        event = self.machine.transition(
            state,
            cycle_index=cycle,
            template_id=template_id,
            reason=reason,
            data=data,
        )
        self.recorder.event(event)

    def _save_cycle(self, cycle: int, name: str, value: Any) -> None:
        self.recorder.write(f"cycle_{cycle:02d}/{name}", value)

    def _save_cycle_images(self, cycle: int, snapshot, scene: SceneAnalysis) -> None:
        cycle_dir = self.recorder.directory / f"cycle_{cycle:02d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        raw_path = cycle_dir / "raw.png"
        cv2.imwrite(str(raw_path), snapshot.frame)
        view = snapshot.frame.copy()
        cv2.imwrite(str(cycle_dir / "scene.png"), view)
        overlay = view.copy()
        paper = getattr(self.analyzer, "last_paper", None)
        if paper is not None:
            paper_corners = np.rint(paper.corners_px).astype(np.int32)
            cv2.polylines(
                overlay,
                [paper_corners.reshape(-1, 1, 2)],
                True,
                (255, 255, 0),
                3,
                cv2.LINE_AA,
            )
            divider = float(
                getattr(self.analyzer, "last_divider_y_cm", None)
                or vision_config.DIVIDER_Y_CM
            )
            divider_points = np.rint(
                [
                    cm_to_px((0.0, divider), paper),
                    cm_to_px((vision_config.A4_WIDTH_CM, divider), paper),
                ]
            ).astype(np.int32)
            cv2.line(
                overlay,
                tuple(divider_points[0]),
                tuple(divider_points[1]),
                (255, 0, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                overlay,
                "A4 DETECTED",
                tuple(paper_corners[0] + np.array([8, 22])),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )
            origin = self.config.target_origin_mm
            rect = np.rint(
                [
                    cm_to_px(tuple(point_mm / 10.0), paper)
                    for point_mm in target_rectangle_vertices_mm(origin)
                ]
            ).astype(np.int32)
            cv2.polylines(overlay, [rect.reshape(-1, 1, 2)], True, (0, 200, 255), 2, cv2.LINE_AA)
            cv2.putText(
                overlay,
                f"TARGET 100x60mm {vision_config.TARGET_LAYOUT_MODE.upper()}",
                tuple(rect[0] + np.array([5, -8])),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 200, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imwrite(
                str(cycle_dir / "rectified.png"),
                rectify_paper(snapshot.frame, paper),
            )
            self._save_cycle(
                cycle,
                "paper_frame.json",
                {
                    "corners_px_tl_tr_br_bl": paper.corners_px,
                    "detected_corners_px_tl_tr_br_bl": (
                        getattr(self.analyzer, "last_detected_paper", None).corners_px
                        if getattr(self.analyzer, "last_detected_paper", None)
                        is not None
                        else None
                    ),
                    "paper_frame_locked": (
                        getattr(self.analyzer, "locked_paper", None) is not None
                    ),
                    "paper_corner_drift_px": getattr(
                        self.analyzer, "last_paper_corner_drift_px", None
                    ),
                    "paper_corner_drift_limit_px": (
                        self.config.paper_corner_drift_limit_px
                    ),
                    "landscape_in_image": paper.landscape_in_image,
                    "divider_y_cm": divider,
                    "divider_points_px": divider_points,
                    "source_region": "paper y < divider; image-left when landscape_in_image=true",
                    "target_region": "paper y >= divider; image-right when landscape_in_image=true",
                    "target_rectangle_mm": [100.0, 60.0],
                    "target_rectangle_px": rect,
                    "target_layout_mode": vision_config.TARGET_LAYOUT_MODE,
                },
            )
            for template_id, state in scene.templates.items():
                expected = np.rint(
                    [
                        cm_to_px(tuple(point_mm / 10.0), paper)
                        for point_mm in state.expected_target_vertices_mm
                    ]
                ).astype(np.int32)
                cv2.polylines(
                    overlay,
                    [expected.reshape(-1, 1, 2)],
                    True,
                    (0, 140, 255),
                    1,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    overlay,
                    template_id,
                    tuple(np.rint(np.mean(expected, axis=0)).astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 140, 255),
                    1,
                    cv2.LINE_AA,
                )

        for piece in scene.pieces:
            points = np.rint(piece.vertices_px).astype(np.int32).reshape(-1, 1, 2)
            color = (0, 210, 0) if piece.template_id in scene.placed_templates else (0, 210, 255)
            cv2.polylines(overlay, [points], True, color, 2, cv2.LINE_AA)
            center = tuple(np.rint(np.mean(points.reshape(-1, 2), axis=0)).astype(int))
            cv2.putText(overlay, piece.template_id or "?", center, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        cv2.imwrite(str(cycle_dir / "overlay.png"), overlay)
        scene.image_path = str(raw_path)
        try:
            from .debug_viz import save_debug_overlays

            save_debug_overlays(
                cycle_dir,
                rectified=view,
                scene=scene,
                assignment=getattr(self.analyzer, "last_assignment", None),
                paper=paper,
            )
        except Exception:
            pass
        self._save_cycle(
            cycle,
            "result.json",
            {
                "scene_valid": scene.scene_valid,
                "placed": sorted(scene.placed_templates),
                "remaining": sorted(scene.remaining_templates),
                "assignment_cost": scene.assignment_total_cost,
                "assignment_margin": scene.assignment_margin,
                "warnings": scene.warnings,
            },
        )

    def _capture_analyze(self, cycle: int, *, verify: bool = False) -> tuple[Any, SceneAnalysis]:
        self._transition(Q1State.VERIFY_CAPTURE if verify else Q1State.CAPTURE_SCENE, cycle)
        snapshot = self.camera.capture_snapshot(cycle)
        self._transition(Q1State.VERIFY_SCENE if verify else Q1State.ANALYZE_SCENE, cycle)
        scene = self.analyzer.analyze(snapshot, cycle)
        scene.timings_ms["capture_burst_ms"] = float(
            snapshot.metadata.get("capture_burst_ms", 0.0)
        )
        scene.timings_ms["select_best_frame_ms"] = float(
            snapshot.metadata.get("select_best_frame_ms", 0.0)
        )
        self._save_cycle_images(cycle, snapshot, scene)
        self._save_cycle(cycle, "scene.json", scene)
        self._save_cycle(
            cycle,
            "four_piece_advisory.json",
            build_four_piece_advisory(scene, self.mapper, self.config),
        )
        return snapshot, scene

    def run(self) -> SceneAnalysis:
        cycle = 0
        visual_retries = 0
        self._transition(Q1State.SELF_CHECK, cycle)

        try:
            self.robot.initialize()
            self.magnet.initialize()
            self.camera.open()
            self.magnet.ensure_off()
            while cycle <= self.config.max_cycles:
                cycle_started = time.perf_counter()
                self._transition(Q1State.MOVE_TO_OBSERVE, cycle)
                self.magnet.ensure_off()
                self._transition(Q1State.WAIT_ARM_STABLE, cycle)
                # HOME uses the same send+fresh-feedback wait as pick/release.
                # Stale or unconfirmed feedback is a hard fault: magnet stays off
                # and no later pose is sent.
                try:
                    self.robot.move_to_observe_pose()
                except BaseException as home_exc:
                    self._transition(
                        Q1State.HARDWARE_FAULT,
                        cycle,
                        reason=f"HOME feedback not confirmed: {home_exc}",
                        data={
                            "last_target_pose": getattr(self.robot, "_last_pose", None),
                            "last_actual_pose": getattr(self.robot, "_last_actual", None),
                            "last_pose_error": getattr(self.robot, "_last_error", None),
                            "motion_attempts": getattr(
                                self.robot, "_motion_attempts", []
                            ),
                        },
                    )
                    raise RuntimeError(
                        "HARDWARE_FAULT: NexArm HOME was not confirmed by fresh "
                        "feedback; magnet remains off and no recovery pose was sent; "
                        f"cause={home_exc}"
                    ) from home_exc

                _, scene = self._capture_analyze(cycle, verify=self.previous_scene is not None)

                self._transition(Q1State.AUDIT_SCENE, cycle)
                audit_started = time.perf_counter()
                audit = audit_scene(
                    scene,
                    self.previous_action,
                    self.previous_scene,
                    remaining_move_tolerance_mm=self.config.remaining_move_tolerance_mm,
                )
                scene.timings_ms["audit_ms"] = (time.perf_counter() - audit_started) * 1000.0
                self._save_cycle(cycle, "audit.json", audit)
                self._record_physical_pick_verification(cycle, audit)

                if audit.requires_reanalysis:
                    visual_retries += 1
                    self._transition(Q1State.RECOVERABLE_ERROR, cycle, reason="视觉一一匹配失败，重新抓图")
                    if visual_retries > self.config.max_visual_retries:
                        raise RuntimeError("ANALYSIS_FAILED: 视觉重试次数已用尽")
                    continue
                visual_retries = 0

                if audit.all_complete:
                    scene.timings_ms["total_cycle_ms"] = (time.perf_counter() - cycle_started) * 1000.0
                    self._save_cycle(cycle, "scene.json", scene)
                    self._transition(Q1State.FINAL_VERIFY, cycle)
                    self.recorder.write(
                        "final.json",
                        {
                            "completed": True,
                            **self.config.report_metadata(),
                            "scene": scene,
                            "audit": audit,
                            "executions": self.executions,
                        },
                    )
                    self._transition(Q1State.COMPLETED, cycle)
                    return scene

                if cycle >= self.config.max_cycles:
                    raise RuntimeError(
                        "PLAN_FAILED: maximum execution cycles reached after final visual verification"
                    )

                self._transition(Q1State.UPDATE_PLAN, cycle)
                self._transition(Q1State.SELECT_NEXT_PIECE, cycle)
                selection_started = time.perf_counter()
                template_id, selection = select_next_piece(
                    scene,
                    audit,
                    excluded_templates=set(),
                )
                scene.timings_ms["selection_ms"] = (time.perf_counter() - selection_started) * 1000.0
                self._save_cycle(cycle, "selection.json", selection)

                self._transition(Q1State.PLAN_SINGLE_MOVE, cycle, template_id)
                plan_started = time.perf_counter()
                if selection.get("use_previous_plan") and self.previous_action is not None:
                    # MISSING/释放失败：不得从不存在的源位置重新规划
                    plan = self.previous_action
                    plan.reason_selected = selection["reason"]
                else:
                    plan = plan_single_move(
                        scene,
                        template_id,
                        self.mapper,
                        self.config,
                        reason_selected=selection["reason"],
                    )
                scene.timings_ms["single_plan_ms"] = (time.perf_counter() - plan_started) * 1000.0
                scene.timings_ms["total_cycle_ms"] = (time.perf_counter() - cycle_started) * 1000.0
                self._save_cycle(cycle, "scene.json", scene)
                self._save_cycle(cycle, "single_move_plan.json", plan)
                if not self.config.direct_pick_release_pose_verified:
                    raise RuntimeError(
                        "MOTION_CALIBRATION_REQUIRED: planned direct pick/release poses "
                        "were saved, but no pick motion was sent because "
                        "direct_pick_release_pose_verified=false"
                    )

                if audit.recovery_mode == "RELEASE_RECOVERY_FROM_LAST_PLAN":
                    self._transition(
                        Q1State.RELEASE_RECOVERY,
                        cycle,
                        template_id,
                        "missing after move",
                    )
                    self.magnet.ensure_off()
                    result = self.robot.execute_release_recovery(plan, 1)
                    self.executions.append(result)
                    self._save_cycle(cycle, "execution_result.json", result)
                    if not result.ok:
                        self._transition(
                            Q1State.HARDWARE_FAULT,
                            cycle,
                            template_id,
                            reason=result.reason,
                        )
                        raise RuntimeError(
                            f"HARDWARE_FAULT: release recovery disabled/failed: "
                            f"{result.reason}"
                        )
                    self._transition(Q1State.RETURN_TO_OBSERVE, cycle, template_id)
                    self.previous_scene = scene
                    self.previous_action = plan
                    cycle += 1
                    continue

                # Real hardware phases are recorded inside execute_single_move:
                # pick feedback confirm -> magnet ON confirm -> release feedback
                # confirm -> magnet OFF confirm. Do not invent intermediate states
                # after the atomic call returns.
                self._transition(
                    Q1State.EXECUTE_PICK,
                    cycle,
                    template_id,
                    reason="source confirm, magnet hold, release confirm",
                )
                try:
                    result = self.robot.execute_single_move(plan, self.magnet)
                except BaseException as move_exc:
                    self._transition(
                        Q1State.HARDWARE_FAULT,
                        cycle,
                        template_id,
                        reason=str(move_exc),
                        data={
                            "motion_attempts": getattr(
                                self.robot, "_motion_attempts", []
                            ),
                        },
                    )
                    raise
                self._transition(
                    Q1State.RELEASE_PIECE,
                    cycle,
                    template_id,
                    reason="magnet off confirmed after release feedback",
                    data={"execution": result},
                )
                if not result.ok:
                    recovered = False
                    for attempt in range(1, self.config.max_release_retries + 1):
                        self._transition(Q1State.RELEASE_RECOVERY, cycle, template_id, result.reason)
                        self.magnet.ensure_off()
                        result = self.robot.execute_release_recovery(plan, attempt)
                        if result.ok:
                            recovered = True
                            break
                    if not recovered:
                        raise RuntimeError(f"RELEASE_FAILED: {template_id}: {result.reason}")
                self.executions.append(result)
                self._save_cycle(cycle, "execution_result.json", result)
                self._transition(Q1State.RETURN_TO_OBSERVE, cycle, template_id)
                self.previous_scene = scene
                self.previous_action = plan
                cycle += 1

            raise RuntimeError("PLAN_FAILED: 超过最大闭环轮数")
        except BaseException as exc:
            self.recorder.write(
                "failure.json",
                {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "state": self.machine.state,
                    "last_target_pose": getattr(self.robot, "_last_pose", None),
                    "last_actual_pose": getattr(self.robot, "_last_actual", None),
                    "last_pose_error": getattr(self.robot, "_last_error", None),
                    "motion_attempts": getattr(
                        self.robot, "_motion_attempts", []
                    ),
                    "nexarm_initial_status": getattr(
                        self.robot, "_initial_status", None
                    ),
                    "executions": self.executions,
                    **self.config.report_metadata(),
                },
            )
            print(
                f"Q1_FAILURE_FILE={self.recorder.directory / 'failure.json'}",
                flush=True,
            )
            self.recorder.announce(prefix="Q1_FAILED_RUN")
            emergency_failures = []
            try:
                self.magnet.emergency_off()
            except BaseException as shutdown_exc:
                emergency_failures.append(
                    {
                        "action": "magnet_emergency_off",
                        "error_type": type(shutdown_exc).__name__,
                        "error": str(shutdown_exc),
                    }
                )
            try:
                self.robot.emergency_stop()
            except BaseException as shutdown_exc:
                emergency_failures.append(
                    {
                        "action": "robot_emergency_stop",
                        "error_type": type(shutdown_exc).__name__,
                        "error": str(shutdown_exc),
                    }
                )
            if emergency_failures:
                self.recorder.write(
                    "emergency_shutdown_failures.json",
                    {"failures": emergency_failures},
                )
            raise
        finally:
            shutdown_actions = (
                ("magnet_emergency_off", self.magnet.emergency_off),
                ("robot_close", self.robot.close),
                ("camera_close", self.camera.close),
                ("magnet_close", self.magnet.close),
            )
            shutdown_failures = []
            for action_name, action in shutdown_actions:
                try:
                    action()
                except BaseException as shutdown_exc:
                    shutdown_failures.append(
                        {
                            "action": action_name,
                            "error_type": type(shutdown_exc).__name__,
                            "error": str(shutdown_exc),
                        }
                    )
            if shutdown_failures:
                self.recorder.write(
                    "shutdown_failures.json",
                    {"failures": shutdown_failures},
                )
            self.recorder.announce(prefix="Q1_LAST_RUN")
