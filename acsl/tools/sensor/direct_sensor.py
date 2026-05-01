from __future__ import annotations
from typing import Any, Dict, Optional
import numpy as np
from acsl.types.context import StepContext, Result
from acsl.types.contract import IOContract
from acsl.types.state import State3D
from acsl.tools.base import tool_contract


@tool_contract(
    inputs={"plant_state": {"dtype": "State3D", "optional": True, "path": "plant.state"}},
    outputs={"pose_twist": {"dtype": "State3D", "path": "sensor.pose_twist"}},
)
class DirectSensor:
    name = "direct"

    def __init__(self, noise_std: float = 0.0):
        self._noise_std = noise_std

    def step(self, context: StepContext) -> Optional[Result]:
        plant_result = context.get_upstream("plant")
        if plant_result and plant_result.state is not None:
            state = plant_result.state.copy() if hasattr(plant_result.state, 'copy') else plant_result.state
        else:
            state = State3D()

        if self._noise_std > 0:
            state.p = state.p + np.random.normal(0, self._noise_std, 3)

        return Result(state=state, timestamp=context.time.now)
