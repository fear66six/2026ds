"""Q1 单步闭环状态机与可追溯状态日志。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Q1State(str, Enum):
    INIT = "INIT"
    SELF_CHECK = "SELF_CHECK"
    MOVE_TO_OBSERVE = "MOVE_TO_OBSERVE"
    WAIT_ARM_STABLE = "WAIT_ARM_STABLE"
    CAPTURE_SCENE = "CAPTURE_SCENE"
    ANALYZE_SCENE = "ANALYZE_SCENE"
    AUDIT_SCENE = "AUDIT_SCENE"
    SELECT_NEXT_PIECE = "SELECT_NEXT_PIECE"
    PLAN_SINGLE_MOVE = "PLAN_SINGLE_MOVE"
    EXECUTE_PICK = "EXECUTE_PICK"
    VERIFY_PICK = "VERIFY_PICK"
    EXECUTE_TRANSFER = "EXECUTE_TRANSFER"
    EXECUTE_PLACE = "EXECUTE_PLACE"
    RELEASE_PIECE = "RELEASE_PIECE"
    RELEASE_RECOVERY = "RELEASE_RECOVERY"
    RETURN_TO_OBSERVE = "RETURN_TO_OBSERVE"
    VERIFY_CAPTURE = "VERIFY_CAPTURE"
    VERIFY_SCENE = "VERIFY_SCENE"
    UPDATE_PLAN = "UPDATE_PLAN"
    FINAL_VERIFY = "FINAL_VERIFY"
    COMPLETED = "COMPLETED"
    RECOVERABLE_ERROR = "RECOVERABLE_ERROR"
    HARDWARE_FAULT = "HARDWARE_FAULT"


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

