from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class SafetyConfig:
    thrust_max: float = 0.0
    torque_max: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    comm_timeout_ms: int = 500
    estimator_timeout_ms: int = 200
    input_rate_limit: float = 10.0
    failsafe_action: str = "pixhawk_land"

    def validate(self) -> None:
        if self.thrust_max <= 0:
            raise ValueError("thrust_max must be configured (no default for safety)")
        if all(t <= 0 for t in self.torque_max):
            raise ValueError("torque_max must be configured (no default for safety)")


@dataclass
class SafetyAlert:
    alert_type: str = ""
    severity: str = "warning"
    message: str = ""
    timestamp: float = 0.0
