from __future__ import annotations
from typing import Optional
import numpy as np
from acsl.types.context import StepContext, Result
from acsl.tools.base import tool_contract


@tool_contract(
    inputs={"cmd_input": {"dtype": "ndarray", "path": "controller.input"}},
    outputs={"throttle_input": {"dtype": "ndarray", "path": "input_transform.output"}},
)
class Thrust2Throttle:
    name = "thrust2throttle"

    def __init__(self, hover_thrust: float = 0.5):
        self._hover_thrust = hover_thrust

    def step(self, context: StepContext) -> Optional[Result]:
        ctrl = context.get_upstream("controller")
        if ctrl is None or ctrl.input is None:
            return None

        u = ctrl.input.copy()
        param = context.parameter
        mass = param.mass if param else 1.0
        g = param.gravity if param else 9.81
        hover_force = mass * g
        if hover_force > 0:
            u[0] = (u[0] / hover_force) * self._hover_thrust
        u[0] = np.clip(u[0], 0.0, 1.0)

        return Result(input=u, timestamp=context.time.now)
