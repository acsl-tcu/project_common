from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from acsl.types.context import StepContext


@dataclass
class PhaseAllocation:
    sensor: List[str] = field(default_factory=list)
    estimator: List[str] = field(default_factory=list)
    reference: List[str] = field(default_factory=list)
    controller: List[str] = field(default_factory=list)
    input_transform: List[str] = field(default_factory=list)
    plant: List[str] = field(default_factory=list)
    operator: List[str] = field(default_factory=list)

    def get(self, category: str) -> List[str]:
        return getattr(self, category, [])

    def as_dict(self) -> Dict[str, List[str]]:
        return {
            k: v for k, v in {
                "sensor": self.sensor,
                "estimator": self.estimator,
                "reference": self.reference,
                "controller": self.controller,
                "input_transform": self.input_transform,
                "plant": self.plant,
                "operator": self.operator,
            }.items() if v
        }


@dataclass
class PhaseTransition:
    from_phase: str
    to_phase: str
    guard: Callable[[StepContext], bool]
    priority: int = 0
    description: str = ""


@dataclass
class PhaseConfig:
    allocation: Optional[PhaseAllocation] = None
    on_enter: Optional[Callable[[StepContext], None]] = None
    on_exit: Optional[Callable[[StepContext], None]] = None


class PhaseManager:
    def __init__(self):
        self._current_phase: str = "idle"
        self._transitions: List[PhaseTransition] = []
        self._phase_configs: Dict[str, PhaseConfig] = {}
        self._history: List[Tuple[float, str, str, str]] = []

    @property
    def current_phase(self) -> str:
        return self._current_phase

    def add_phase(self, name: str, config: Optional[PhaseConfig] = None) -> None:
        self._phase_configs[name] = config or PhaseConfig()

    def add_transition(self, transition: PhaseTransition) -> None:
        self._transitions.append(transition)

    def set_initial(self, phase: str) -> None:
        self._current_phase = phase

    def evaluate(self, context: StepContext) -> Optional[str]:
        candidates = [t for t in self._transitions if t.from_phase == self._current_phase]
        candidates.sort(key=lambda t: t.priority, reverse=True)
        for t in candidates:
            try:
                if t.guard(context):
                    return t.to_phase
            except Exception:
                continue
        return None

    def transition(self, new_phase: str, context: StepContext) -> Optional[PhaseAllocation]:
        old_config = self._phase_configs.get(self._current_phase)
        if old_config and old_config.on_exit:
            old_config.on_exit(context)

        old_phase = self._current_phase
        self._current_phase = new_phase
        self._history.append((context.time.now, old_phase, new_phase, "guard"))

        new_config = self._phase_configs.get(new_phase)
        if new_config and new_config.on_enter:
            new_config.on_enter(context)

        return new_config.allocation if new_config else None

    def force_transition(self, new_phase: str, context: StepContext) -> Optional[PhaseAllocation]:
        old_phase = self._current_phase
        self._current_phase = new_phase
        self._history.append((context.time.now, old_phase, new_phase, "forced"))
        new_config = self._phase_configs.get(new_phase)
        return new_config.allocation if new_config else None

    def current_allocation(self) -> Optional[PhaseAllocation]:
        config = self._phase_configs.get(self._current_phase)
        return config.allocation if config else None

    @property
    def history(self) -> List[Tuple[float, str, str, str]]:
        return list(self._history)

    @property
    def phases(self) -> List[str]:
        return list(self._phase_configs.keys())

    def __repr__(self) -> str:
        return f"PhaseManager(current={self._current_phase}, phases={self.phases})"
