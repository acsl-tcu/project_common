from __future__ import annotations
from typing import Optional
import numpy as np
from acsl.types.context import StepContext, Result
from acsl.types.state import State3D
from acsl.tools.base import tool_contract


@tool_contract(
    inputs={},
    outputs={"reference": {"dtype": "State3D"}},
)
class TimeVaryingReference:
    name = "time_varying"

    def __init__(self, trajectory: str = "circle", radius: float = 1.0, period: float = 10.0, altitude: float = 1.0):
        self._trajectory = trajectory
        self._radius = radius
        self._omega = 2 * np.pi / period
        self._altitude = altitude

    def step(self, context: StepContext) -> Optional[Result]:
        t = context.time.now
        if self._trajectory == "circle":
            x = self._radius * np.cos(self._omega * t)
            y = self._radius * np.sin(self._omega * t)
            z = self._altitude
            vx = -self._radius * self._omega * np.sin(self._omega * t)
            vy = self._radius * self._omega * np.cos(self._omega * t)
            yaw = np.arctan2(vy, vx)
            ref = State3D(
                p=np.array([x, y, z]),
                v=np.array([vx, vy, 0.0]),
                q=np.array([np.cos(yaw/2), 0.0, 0.0, np.sin(yaw/2)]),
            )
        else:
            ref = State3D(p=np.array([0.0, 0.0, self._altitude]))

        return Result(state=ref, timestamp=context.time.now)
