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
class LandingReference:
    name = "landing"

    def __init__(self, descent_rate: float = 0.3):
        self._descent_rate = descent_rate
        self._start_alt: Optional[float] = None
        self._start_time: Optional[float] = None

    def step(self, context: StepContext) -> Optional[Result]:
        if self._start_time is None:
            self._start_time = context.time.now
            est = context.get_upstream("estimator")
            if est and est.state is not None:
                self._start_alt = est.state.p[2]
            else:
                self._start_alt = 1.0

        elapsed = context.time.now - self._start_time
        alt = max(self._start_alt - self._descent_rate * elapsed, 0.0)

        ref = State3D(p=np.array([0.0, 0.0, alt]))
        return Result(state=ref, timestamp=context.time.now)
