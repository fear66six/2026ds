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

from . import config
from .pieces import target_rectangle_vertices_mm
from .calibration import ArmCoordinateMapper
from .models import ExecutionResult, SceneAnalysis, SingleMovePlan
from .motion import plan_single_move
from .runtime_config import Q1RuntimeConfig
from .selector import select_next_piece
from .state_machine import Q1State, Q1StateMachine, StateEvent


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
        self.directory = root / run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.events_path = self.directory / "events.jsonl"
        self.write(
            "run.json",
            {
                "run_id": run_id,
                "mode": mode,
                "created_at": datetime.now().isoformat(),
                "config": config,
            },
        )

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

    def _transition(self, state: Q1State, cycle: int, template_id: str | None = None, reason: str = "") -> None:
        event = self.machine.transition(state, cycle_index=cycle, template_id=template_id, reason=reason)
        self.recorder.event(event)

    def _save_cycle(self, cycle: int, name: str, value: Any) -> None:
        self.recorder.write(f"cycle_{cycle:02d}/{name}", value)

    def _save_cycle_images(self, cycle: int, snapshot, scene: SceneAnalysis) -> None:
        cycle_dir = self.recorder.directory / f"cycle_{cycle:02d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        raw_path = cycle_dir / "raw.png"
        cv2.imwrite(str(raw_path), snapshot.frame)
        if getattr(self.analyzer, "paper_calibration", None) is not None:
            view = self.analyzer.paper_calibration.rectify(snapshot.frame)
        else:
            view = snapshot.frame.copy()
        cv2.imwrite(str(cycle_dir / "rectified.png"), view)
        overlay = view.copy()
        px_per_mm = None
        if scene.pieces:
            piece = scene.pieces[0]
            verts_mm = np.asarray(piece.vertices_mm, dtype=np.float64)
            verts_px = np.asarray(piece.vertices_px, dtype=np.float64).reshape(-1, 2)
            span_mm = float(np.max(np.ptp(verts_mm, axis=0)))
            span_px = float(np.max(np.ptp(verts_px, axis=0)))
            if span_mm > 1e-3 and span_px > 1e-3:
                px_per_mm = span_px / span_mm
        if px_per_mm is None and getattr(self.analyzer, "paper_calibration", None) is not None:
            output_w, _ = self.analyzer.paper_calibration.output_size
            px_per_mm = output_w / (config.A4_WIDTH_CM * 10.0)

        if px_per_mm is not None:
            origin = self.config.target_origin_mm
            rect = np.rint(target_rectangle_vertices_mm(origin) * px_per_mm).astype(np.int32)
            cv2.polylines(overlay, [rect.reshape(-1, 1, 2)], True, (0, 200, 255), 2, cv2.LINE_AA)
            for template_id, state in scene.templates.items():
                expected = np.rint(state.expected_target_vertices_mm * px_per_mm).astype(np.int32)
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

    def run(self) -> SceneAnalysis:
        cycle = 0
        visual_retries = 0
        self._transition(Q1State.SELF_CHECK, cycle)
        self.robot.initialize()
        self.magnet.initialize()
        self.camera.open()
        self.magnet.ensure_off()

        try:
            while cycle < self.config.max_cycles:
                cycle_started = time.perf_counter()
                self._transition(Q1State.MOVE_TO_OBSERVE, cycle)
                self.magnet.ensure_off()
                self.robot.move_to_observe_pose()
                self._transition(Q1State.WAIT_ARM_STABLE, cycle)
                if not self.robot.wait_until_idle(max(2.0, self.config.settle_time_ms / 1000.0 + 1.0)):
                    raise RuntimeError("HARDWARE_FAULT: 机械臂未在超时内稳定")

                capture_state = Q1State.CAPTURE_SCENE if self.previous_scene is None else Q1State.VERIFY_CAPTURE
                analyze_state = Q1State.ANALYZE_SCENE if self.previous_scene is None else Q1State.VERIFY_SCENE
                self._transition(capture_state, cycle)
                snapshot = self.camera.capture_snapshot(cycle)
                self._transition(analyze_state, cycle)
                scene = self.analyzer.analyze(snapshot, cycle)
                scene.timings_ms["capture_burst_ms"] = float(snapshot.metadata.get("capture_burst_ms", 0.0))
                scene.timings_ms["select_best_frame_ms"] = float(snapshot.metadata.get("select_best_frame_ms", 0.0))
                self._save_cycle_images(cycle, snapshot, scene)
                self._save_cycle(cycle, "scene.json", scene)

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
                    self.recorder.write("final.json", {"completed": True, "scene": scene, "audit": audit})
                    self._transition(Q1State.COMPLETED, cycle)
                    return scene

                self._transition(Q1State.UPDATE_PLAN, cycle)
                self._transition(Q1State.SELECT_NEXT_PIECE, cycle)
                selection_started = time.perf_counter()
                template_id, selection = select_next_piece(scene, audit)
                scene.timings_ms["selection_ms"] = (time.perf_counter() - selection_started) * 1000.0
                self._save_cycle(cycle, "selection.json", selection)

                self._transition(Q1State.PLAN_SINGLE_MOVE, cycle, template_id)
                plan_started = time.perf_counter()
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

                self._transition(Q1State.EXECUTE_PICK, cycle, template_id)
                self._transition(Q1State.VERIFY_PICK, cycle, template_id)
                self._transition(Q1State.EXECUTE_TRANSFER, cycle, template_id)
                self._transition(Q1State.EXECUTE_PLACE, cycle, template_id)
                self._transition(Q1State.RELEASE_PIECE, cycle, template_id)
                result = self.robot.execute_single_move(plan, self.magnet)
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
        except BaseException:
            self.magnet.emergency_off()
            self.robot.emergency_stop()
            raise
        finally:
            self.magnet.emergency_off()
            self.robot.close()
            self.camera.close()
            self.magnet.close()
