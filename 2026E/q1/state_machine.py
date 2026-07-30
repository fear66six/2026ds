"""与 Q1 主程序设计流程一致的精简状态日志。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Q1State(str, Enum):
    INIT = "INIT"
    INITIALIZE_CAMERA = "INITIALIZE_CAMERA"
    INITIALIZE_ROBOT = "INITIALIZE_ROBOT"
    INITIALIZE_MAGNET = "INITIALIZE_MAGNET"
    MOVE_TO_OBSERVE = "MOVE_TO_OBSERVE"
    CAPTURE_SCENE = "CAPTURE_SCENE"
    ANALYZE_SCENE = "ANALYZE_SCENE"
    BUILD_MOVE_QUEUE = "BUILD_MOVE_QUEUE"
    EXECUTE_MOVE = "EXECUTE_MOVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class StateEvent:
    timestamp: str
    state_from: str
    state_to: str
    cycle_index: int
    template_id: str | None
    reason: str
    data: dict[str, Any]


class Q1StateMachine:
    def __init__(self) -> None:
        self.state = Q1State.INIT
        self.events: list[StateEvent] = []

    def transition(
        self,
        target: Q1State,
        *,
        cycle_index: int = 0,
        template_id: str | None = None,
        reason: str = "",
        data: dict[str, Any] | None = None,
    ) -> StateEvent:
        event = StateEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            state_from=self.state.value,
            state_to=target.value,
            cycle_index=cycle_index,
            template_id=template_id,
            reason=reason,
            data=data or {},
        )
        self.events.append(event)
        self.state = target
        return event
