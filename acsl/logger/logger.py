from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import copy


@dataclass
class LogSnapshot:
    t: float = 0.0
    phase: str = "idle"
    agents: List[Dict[str, Any]] = field(default_factory=list)


class StorageHandler:
    def __init__(self, config: Optional[Dict] = None):
        self._buffer: List[LogSnapshot] = []

    def record(self, snapshot: LogSnapshot) -> None:
        self._buffer.append(copy.deepcopy(snapshot))

    @property
    def data(self) -> List[LogSnapshot]:
        return self._buffer

    def clear(self) -> None:
        self._buffer.clear()


class Logger:
    def __init__(self, config: Optional[Dict] = None):
        self._handlers: List[Any] = []
        config = config or {}
        if "storage" in config.get("handlers", ["storage"]):
            self._storage = StorageHandler(config)
            self._handlers.append(self._storage)
        else:
            self._storage = StorageHandler(config)
            self._handlers.append(self._storage)

    def log_step(self, t: float, phase: str, agent_data: Optional[List[Dict]] = None) -> None:
        snapshot = LogSnapshot(t=t, phase=phase, agents=agent_data or [])
        for handler in self._handlers:
            handler.record(snapshot)

    @property
    def storage(self) -> StorageHandler:
        return self._storage

    @property
    def history(self) -> List[LogSnapshot]:
        return self._storage.data
