from __future__ import annotations
from typing import Optional
import numpy as np
from acsl.types.context import StepContext, Result
from acsl.types.state import State3D
from acsl.types.parameter import AgentParameter
from acsl.tools.base import tool_contract


@tool_contract(
    inputs={"cmd_input": {"dtype": "ndarray", "optional": True}},
    outputs={"plant_state": {"dtype": "State3D", "path": "plant.state"}},
)
class ModelQuat13:
    name = "model_quat13"

    def __init__(self, initial_state: Optional[State3D] = None):
        self._state = initial_state or State3D()

    @property
    def state(self) -> State3D:
        return self._state

    def step(self, context: StepContext) -> Optional[Result]:
        ctrl = context.get_upstream("controller")
        it = context.get_upstream("input_transform")

        if it is not None and it.input is not None:
            u = it.input
        elif ctrl is not None and ctrl.input is not None:
            u = ctrl.input
        else:
            u = np.array([0.0, 0.0, 0.0, 0.0])

        param = context.parameter or AgentParameter()
        dt = context.time.dt

        self._state = self._rk4_step(self._state, u, param, dt)

        return Result(state=self._state.copy(), timestamp=context.time.now)

    def _rk4_step(self, state: State3D, u: np.ndarray, param: AgentParameter, dt: float) -> State3D:
        def deriv(s: State3D) -> tuple:
            R = s.rotation_matrix
            e3 = np.array([0.0, 0.0, 1.0])

            thrust = u[0] if len(u) > 0 else 0.0
            torque = u[1:4] if len(u) >= 4 else np.zeros(3)

            dp = s.v
            dv = (thrust / param.mass) * R @ e3 - param.gravity * e3

            w = s.w
            omega_quat = np.array([0.0, w[0], w[1], w[2]])
            dq = 0.5 * self._quat_mult(s.q, omega_quat)

            J = param.inertia
            J_diag = np.diag(J) if J.ndim == 2 else J[:3]
            dw = np.zeros(3)
            for i in range(3):
                if J_diag[i] != 0:
                    dw[i] = torque[i] / J_diag[i]

            return dp, dv, dq, dw

        dp1, dv1, dq1, dw1 = deriv(state)

        s2 = State3D(
            p=state.p + 0.5*dt*dp1,
            v=state.v + 0.5*dt*dv1,
            q=self._normalize_quat(state.q + 0.5*dt*dq1),
            w=state.w + 0.5*dt*dw1,
        )
        dp2, dv2, dq2, dw2 = deriv(s2)

        s3 = State3D(
            p=state.p + 0.5*dt*dp2,
            v=state.v + 0.5*dt*dv2,
            q=self._normalize_quat(state.q + 0.5*dt*dq2),
            w=state.w + 0.5*dt*dw2,
        )
        dp3, dv3, dq3, dw3 = deriv(s3)

        s4 = State3D(
            p=state.p + dt*dp3,
            v=state.v + dt*dv3,
            q=self._normalize_quat(state.q + dt*dq3),
            w=state.w + dt*dw3,
        )
        dp4, dv4, dq4, dw4 = deriv(s4)

        new_state = State3D(
            p=state.p + (dt/6)*(dp1 + 2*dp2 + 2*dp3 + dp4),
            v=state.v + (dt/6)*(dv1 + 2*dv2 + 2*dv3 + dv4),
            q=self._normalize_quat(state.q + (dt/6)*(dq1 + 2*dq2 + 2*dq3 + dq4)),
            w=state.w + (dt/6)*(dw1 + 2*dw2 + 2*dw3 + dw4),
        )
        return new_state

    @staticmethod
    def _quat_mult(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        return np.array([
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2,
        ])

    @staticmethod
    def _normalize_quat(q: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(q)
        return q / n if n > 1e-10 else np.array([1.0, 0.0, 0.0, 0.0])
