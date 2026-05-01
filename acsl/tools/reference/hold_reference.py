from __future__ import annotations
from typing import Optional
import numpy as np
from acsl.types.context import StepContext, Result
from acsl.types.state import State3D
from acsl.tools.base import tool_contract


@tool_contract(
    inputs={"estimate": {"dtype": "State3D", "optional": True, "path": "estimator.estimate"}},
    outputs={"reference": {"dtype": "State3D", "path": "reference.state"}},
)
class HoldReference:
    name = "hold"

    def __init__(self, position: Optional[np.ndarray] = None):
        self._hold_position = position

    def step(self, context: StepContext) -> Optional[Result]:
        if self._hold_position is None:
            est = context.get_upstream("estimator")
            if est and est.state is not None:
                self._hold_position = est.state.p.copy()
            else:
                self._hold_position = np.zeros(3)

        ref = State3D(p=self._hold_position.copy())
        return Result(state=ref, timestamp=context.time.now)
