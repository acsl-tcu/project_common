from __future__ import annotations
from typing import Optional
import numpy as np
from acsl.types.context import StepContext, Result
from acsl.types.state import State3D
from acsl.tools.base import tool_contract


@tool_contract(
    inputs={"estimate": {"dtype": "State3D", "optional": True}},
    outputs={"reference": {"dtype": "State3D"}},
)
class TakeoffReference:
    name = "takeoff"

    def __init__(self, target_altitude: float = 1.0, rate: float = 0.5):
        self._target = target_altitude
        self._rate = rate
        self._start_time: Optional[float] = None

    def step(self, context: StepContext) -> Optional[Result]:
        if self._start_time is None:
            self._start_time = context.time.now

        elapsed = context.time.now - self._start_time
        alt = min(self._rate * elapsed, self._target)

        ref = State3D(p=np.array([0.0, 0.0, alt]))
        return Result(state=ref, timestamp=context.time.now)
