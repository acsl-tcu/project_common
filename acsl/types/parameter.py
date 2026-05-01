from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class AgentParameter:
    mass: float = 1.0
    gravity: float = 9.81
    arm_length: float = 0.17
    inertia: np.ndarray = field(default_factory=lambda: np.diag([0.01, 0.01, 0.02]))

    def to_vector(self) -> np.ndarray:
        return np.array([self.mass, *self.inertia.flatten(), self.arm_length, self.gravity])
