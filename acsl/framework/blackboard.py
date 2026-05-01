from __future__ import annotations
import copy
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set


@dataclass
class AgentState:
    agent_id: int = 0
    estimate: Optional[Any] = None
    reference: Optional[Any] = None
    controller_output: Optional[Any] = None
    phase: str = "idle"
    custom: Dict[str, Any] = field(default_factory=dict)


class Blackboard:
    def __init__(self, num_agents: int = 0):
        self._read_buffer: Dict[int, AgentState] = {}
        self._write_buffer: Dict[int, AgentState] = {}
        self._lock = threading.Lock()

    def write(self, agent_id: int, state: AgentState) -> None:
        with self._lock:
            self._write_buffer[agent_id] = copy.deepcopy(state)

    def read(self, agent_id: int) -> Optional[AgentState]:
        with self._lock:
            state = self._read_buffer.get(agent_id)
            return copy.deepcopy(state) if state else None

    def read_all(self) -> Dict[int, AgentState]:
        with self._lock:
            return {k: copy.deepcopy(v) for k, v in self._read_buffer.items()}

    def swap(self) -> None:
        with self._lock:
            self._read_buffer = dict(self._write_buffer)

    def agent_ids(self) -> Set[int]:
        with self._lock:
            return set(self._read_buffer.keys()) | set(self._write_buffer.keys())

    def __repr__(self) -> str:
        return f"Blackboard(agents={self.agent_ids()})"
