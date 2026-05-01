from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import time as time_mod

if TYPE_CHECKING:
    from acsl.framework.agent import Agent
    from acsl.types.context import StepContext, Result


PRESETS = {
    "standard": {
        "sensor": [],
        "estimator": ["sensor"],
        "reference": ["estimator"],
        "controller": ["estimator", "reference"],
        "input_transform": ["controller"],
        "plant": ["input_transform"],
    },
    "dnn": {
        "sensor": [],
        "controller": ["sensor"],
        "input_transform": ["controller"],
        "plant": ["input_transform"],
    },
    "estimation_only": {
        "sensor": [],
        "estimator": ["sensor"],
    },
    "mpc_hybrid": {
        "sensor": [],
        "estimator": ["sensor"],
        "reference": ["estimator"],
        "controller": ["estimator", "reference"],
        "input_transform": ["controller"],
        "plant": ["input_transform"],
    },
}


class PipelineEngine:
    def __init__(self, preset: str = "standard", custom_dag: Optional[Dict[str, List[str]]] = None):
        self._preset = preset
        if preset == "custom" and custom_dag:
            self._dag = custom_dag
        elif preset in PRESETS:
            self._dag = PRESETS[preset]
        else:
            raise ValueError(f"Unknown preset '{preset}'. Available: {list(PRESETS.keys()) + ['custom']}")
        self._execution_order = self._topological_sort()
        self._timings: Dict[str, float] = {}

    @property
    def preset(self) -> str:
        return self._preset

    @property
    def execution_order(self) -> List[str]:
        return list(self._execution_order)

    @property
    def timings(self) -> Dict[str, float]:
        return dict(self._timings)

    def execute_step(self, agent: "Agent", context: "StepContext") -> None:
        self._timings.clear()
        for category_name in self._execution_order:
            category = agent.get_category(category_name)
            if category is None:
                continue
            t0 = time_mod.perf_counter()
            result = category.execute(context)
            elapsed = time_mod.perf_counter() - t0
            self._timings[category_name] = elapsed
            if result is not None:
                context.update_results(category_name, result)

    def _topological_sort(self) -> List[str]:
        visited: set = set()
        order: List[str] = []
        temp: set = set()

        def visit(name: str) -> None:
            if name in temp:
                raise RuntimeError(f"Cycle detected involving '{name}'")
            if name in visited:
                return
            temp.add(name)
            for dep in self._dag.get(name, []):
                visit(dep)
            temp.remove(name)
            visited.add(name)
            order.append(name)

        for n in self._dag:
            visit(n)
        return order

    def __repr__(self) -> str:
        return f"PipelineEngine(preset={self._preset}, order={self._execution_order})"
