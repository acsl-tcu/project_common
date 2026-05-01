from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING
import numpy as np

from acsl.types.safety import SafetyConfig, SafetyAlert

if TYPE_CHECKING:
    from acsl.types.context import StepContext


class SafetyMonitor:
    def __init__(self, config: SafetyConfig):
        config.validate()
        self._config = config
        self._last_input: Optional[np.ndarray] = None
        self._last_comm_time: float = 0.0
        self._last_estimator_time: float = 0.0
        self._alerts: List[SafetyAlert] = []

    def saturate(self, control_input: np.ndarray) -> np.ndarray:
        saturated = control_input.copy()
        if len(saturated) >= 1:
            saturated[0] = np.clip(saturated[0], 0.0, self._config.thrust_max)
        for i in range(min(3, len(saturated) - 1)):
            saturated[i + 1] = np.clip(
                saturated[i + 1],
                -self._config.torque_max[i],
                self._config.torque_max[i],
            )
        if self._last_input is not None and len(saturated) == len(self._last_input):
            delta = saturated - self._last_input
            delta = np.clip(delta, -self._config.input_rate_limit, self._config.input_rate_limit)
            saturated = self._last_input + delta
        self._last_input = saturated.copy()
        return saturated

    def check(self, context: "StepContext") -> List[SafetyAlert]:
        alerts: List[SafetyAlert] = []
        now = context.time.now

        if self._last_comm_time > 0:
            if (now - self._last_comm_time) * 1000 > self._config.comm_timeout_ms:
                alerts.append(SafetyAlert("comm_timeout", "critical", "Communication timeout", now))

        if self._last_estimator_time > 0:
            if (now - self._last_estimator_time) * 1000 > self._config.estimator_timeout_ms:
                alerts.append(SafetyAlert("estimator_stale", "critical", "Estimator data stale", now))

        self._alerts.extend(alerts)
        return alerts

    def update_comm_time(self, t: float) -> None:
        self._last_comm_time = t

    def update_estimator_time(self, t: float) -> None:
        self._last_estimator_time = t

    def has_critical(self, alerts: List[SafetyAlert]) -> bool:
        return any(a.severity == "critical" for a in alerts)

    @property
    def config(self) -> SafetyConfig:
        return self._config

    def __repr__(self) -> str:
        return f"SafetyMonitor(thrust_max={self._config.thrust_max})"
