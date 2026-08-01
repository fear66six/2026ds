"""Q3 top-level workflow using the completed Q1 hardware executors."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from q1.calibration import ArmCoordinateMapper
from q1.models import ExecutionResult, PieceMove
from q1.state_machine import Q1State, Q1StateMachine, StateEvent
from q1.workflow import jsonable

from .models import CardScene
from .runtime_config import Q3RuntimeConfig
from .workflow import capture_and_plan


class RunRecorder:
    def __init__(self, root: Path, mode: str, config: Q3RuntimeConfig) -> None:
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.directory = (root / self.run_id).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.events_path = self.directory / "events.jsonl"
        self.write(
            "run.json",
            {
                "run_id": self.run_id,
                "mode": mode,
                "created_at": datetime.now().isoformat(),
                **config.report_metadata(),
                "config": config,
            },
        )
        self.latest_path = self.directory.parent / "LATEST_RUN.txt"
        self.latest_path.write_text(str(self.directory) + "\n", encoding="utf-8")
        self.announce()

    def announce(self, *, prefix: str = "Q3_RUN") -> None:
        print(f"{prefix}_ID={self.run_id}", flush=True)
        print(f"{prefix}_DIR={self.directory}", flush=True)
        print(f"{prefix}_EVENTS={self.events_path}", flush=True)

    def write(self, relative: str, value: Any) -> None:
        path = self.directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(jsonable(value), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def event(self, event: StateEvent) -> None:
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(jsonable(event), ensure_ascii=False) + "\n")


class Q3Controller:
    def __init__(
        self,
        *,
        camera,
        analyzer,
        robot,
        magnet,
        mapper: ArmCoordinateMapper,
        config: Q3RuntimeConfig,
    ) -> None:
        self.camera = camera
        self.analyzer = analyzer
        self.robot = robot
        self.magnet = magnet
        self.mapper = mapper
        self.config = config
        self.machine = Q1StateMachine()
        self.recorder = RunRecorder(config.run_root, config.mode, config)
        self.move_queue: list[PieceMove] = []
        self.executions: list[ExecutionResult] = []

    def _transition(
        self,
        state: Q1State,
        move_index: int = 0,
        template_id: str | None = None,
        reason: str = "",
        data: dict | None = None,
    ) -> None:
        self.recorder.event(
            self.machine.transition(
                state,
                cycle_index=move_index,
                template_id=template_id,
                reason=reason,
                data=data,
            )
        )

    def _initialize_devices(self) -> None:
        self._transition(Q1State.INITIALIZE_ROBOT)
        self._transition(Q1State.MOVE_TO_OBSERVE)
        self.robot.initialize()
        self._transition(Q1State.INITIALIZE_CAMERA)
        self.camera.open()
        self._transition(Q1State.INITIALIZE_MAGNET)
        self.magnet.initialize()
        self.magnet.ensure_off()

    def _capture_and_plan(self) -> CardScene:
        states = {
            "capture": Q1State.CAPTURE_SCENE,
            "analyze": Q1State.ANALYZE_SCENE,
            "plan": Q1State.BUILD_MOVE_QUEUE,
        }

        def change_phase(phase: str) -> None:
            self._transition(states[phase])

        scene, self.move_queue = capture_and_plan(
            camera=self.camera,
            analyzer=self.analyzer,
            mapper=self.mapper,
            config=self.config,
            output_dir=self.recorder.directory,
            phase_changed=change_phase,
        )
        return scene

    def _execute_move_queue(self) -> None:
        for move_index, move in enumerate(self.move_queue):
            self._transition(
                Q1State.EXECUTE_MOVE,
                move_index,
                move.template_id,
                reason="card pick -> lift -> rotate -> transit -> place",
            )
            self.magnet.ensure_off()
            result = self.robot.execute_single_move(move, self.magnet)
            self.executions.append(result)
            self.recorder.write(
                f"moves/{move_index + 1:02d}_{move.template_id}.json",
                {"move": move, "execution": result},
            )
            if not result.ok:
                raise RuntimeError(
                    f"MOVE_FAILED: piece={move.template_id}, reason={result.reason}"
                )

    def run(self) -> CardScene:
        started = time.perf_counter()
        failed = False
        try:
            if not self.config.direct_pick_release_pose_verified:
                raise RuntimeError("DIRECT_PICK_RELEASE_POSE_UNVERIFIED")
            self._initialize_devices()
            scene = self._capture_and_plan()
            self._execute_move_queue()
            if self.move_queue:
                self._transition(
                    Q1State.MOVE_TO_OBSERVE,
                    len(self.move_queue),
                    reason="return HOME after final card fragment",
                )
                self.robot.move_to_observe_pose()

            self.robot.notify_completion()
            self._transition(Q1State.COMPLETED, len(self.move_queue))
            self.recorder.write(
                "final.json",
                {
                    "completed": True,
                    "completion_basis": "card move queue exhausted",
                    "post_move_visual_verification": False,
                    "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                    "scene": scene,
                    "piece_moves": self.move_queue,
                    "executions": self.executions,
                    **self.config.report_metadata(),
                },
            )
            return scene
        except BaseException as exc:
            failed = True
            self._transition(Q1State.FAILED, reason=str(exc))
            self.recorder.write(
                "failure.json",
                {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "state": self.machine.state,
                    "last_target_pose": getattr(self.robot, "_last_pose", None),
                    "motion_attempts": getattr(self.robot, "_motion_attempts", []),
                    "piece_moves": self.move_queue,
                    "executions": self.executions,
                    **self.config.report_metadata(),
                },
            )
            self.recorder.announce(prefix="Q3_FAILED_RUN")
            raise
        finally:
            shutdown_actions = [("magnet_emergency_off", self.magnet.emergency_off)]
            if failed:
                shutdown_actions.append(("robot_emergency_stop", self.robot.emergency_stop))
            else:
                shutdown_actions.append(("robot_close", self.robot.close))
            shutdown_actions.extend(
                [("camera_close", self.camera.close), ("magnet_close", self.magnet.close)]
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
            self.recorder.announce(prefix="Q3_LAST_RUN")
