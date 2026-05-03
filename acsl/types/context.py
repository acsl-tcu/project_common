from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import numpy as np


@dataclass
class Time:
    now: float = 0.0
    dt: float = 0.025
    step_count: int = 0
    wall_time: float = 0.0


@dataclass
class StepContext:
    time: Time = field(default_factory=Time)
    phase: str = "idle"
    agent_index: int = 0
    results: Dict[str, "Result"] = field(default_factory=dict)
    agent_states: Dict[int, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    parameter: Optional[Any] = None
    _cascade_input: Optional["Result"] = field(default=None, repr=False)

    def get_upstream(self, category: str) -> Optional["Result"]:
        return self.results.get(category)

    def get_cascade_input(self) -> Optional["Result"]:
        """cascade 内で前段 Tool の出力を取得する。"""
        return self._cascade_input

    def get_agent_state(self, agent_id: int) -> Optional[Any]:
        return self.agent_states.get(agent_id)

    def update_results(self, category: str, result: "Result") -> None:
        self.results[category] = result


@dataclass
class Result:
    state: Optional[Any] = None
    output: Optional[Any] = None
    input: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
