from __future__ import annotations
from typing import Optional
from acsl.types.context import StepContext, Result
from acsl.types.contract import IOContract
from acsl.tools.base import tool_contract


@tool_contract(
    inputs={"pose_twist": {"dtype": "State3D", "path": "sensor.pose_twist"}},
    outputs={"estimate": {"dtype": "State3D", "path": "estimator.estimate"}},
)
class DirectEstimator:
    name = "direct"

    def step(self, context: StepContext) -> Optional[Result]:
        sensor_result = context.get_upstream("sensor")
        if sensor_result is None:
            return None
        return Result(state=sensor_result.state, timestamp=context.time.now)
