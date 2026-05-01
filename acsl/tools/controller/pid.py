from __future__ import annotations
from typing import Optional
import numpy as np
from acsl.types.context import StepContext, Result
from acsl.types.state import State3D
from acsl.types.parameter import AgentParameter
from acsl.tools.base import tool_contract


@tool_contract(
    inputs={
        "estimate": {"dtype": "State3D", "path": "estimator.estimate"},
        "reference": {"dtype": "State3D", "path": "reference.state"},
    },
    outputs={
        "cmd_input": {"dtype": "ndarray", "path": "controller.input"},
    },
)
class PIDController:
    name = "pid"

    def __init__(self, kp: float = 5.0, kd: float = 2.0, ki: float = 0.0):
        self._kp = kp
        self._kd = kd
        self._ki = ki
        self._integral = np.zeros(3)

    def step(self, context: StepContext) -> Optional[Result]:
        est = context.get_upstream("estimator")
        ref = context.get_upstream("reference")
        if est is None or ref is None:
            return None
        if est.state is None or ref.state is None:
            return None

        state: State3D = est.state
        ref_state: State3D = ref.state

        e = ref_state.p - state.p
        de = ref_state.v - state.v
        self._integral += e * context.time.dt

        param = context.parameter
        mass = param.mass if param else 1.0
        g = param.gravity if param else 9.81

        accel_cmd = self._kp * e + self._kd * de + self._ki * self._integral
        thrust = mass * (accel_cmd[2] + g)
        torque = mass * accel_cmd[:2]

        u = np.array([thrust, torque[0], torque[1], 0.0])

        return Result(
            input=u,
            metadata={"error_norm": float(np.linalg.norm(e))},
            timestamp=context.time.now,
        )
