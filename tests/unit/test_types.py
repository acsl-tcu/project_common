import numpy as np
import pytest
from acsl.types.state import State3D, State2D
from acsl.types.context import Time, StepContext, Result
from acsl.types.parameter import AgentParameter


class TestState3D:
    def test_default(self):
        s = State3D()
        np.testing.assert_array_equal(s.p, np.zeros(3))
        np.testing.assert_array_equal(s.q, [1, 0, 0, 0])

    def test_euler_identity(self):
        s = State3D()
        euler = s.euler
        np.testing.assert_allclose(euler, [0, 0, 0], atol=1e-10)

    def test_xd_shape(self):
        s = State3D(p=np.array([1, 2, 3]), v=np.array([4, 5, 6]))
        xd = s.xd
        assert xd.shape == (20,)
        np.testing.assert_array_equal(xd[0:3], [1, 2, 3])
        np.testing.assert_array_equal(xd[4:7], [4, 5, 6])

    def test_copy(self):
        s = State3D(p=np.array([1, 2, 3]))
        s2 = s.copy()
        s2.p[0] = 99
        assert s.p[0] == 1

    def test_rotation_matrix_identity(self):
        s = State3D()
        R = s.rotation_matrix
        np.testing.assert_allclose(R, np.eye(3), atol=1e-10)


class TestState2D:
    def test_default(self):
        s = State2D()
        assert s.x == 0.0
        assert s.yaw == 0.0


class TestTime:
    def test_default(self):
        t = Time()
        assert t.now == 0.0
        assert t.dt == 0.025

    def test_custom(self):
        t = Time(now=1.5, dt=0.01, step_count=150)
        assert t.now == 1.5
        assert t.step_count == 150


class TestStepContext:
    def test_get_upstream_empty(self):
        ctx = StepContext()
        assert ctx.get_upstream("sensor") is None

    def test_update_and_get(self):
        ctx = StepContext()
        r = Result(state="test")
        ctx.update_results("sensor", r)
        assert ctx.get_upstream("sensor").state == "test"

    def test_get_agent_state(self):
        ctx = StepContext(agent_states={0: "state0"})
        assert ctx.get_agent_state(0) == "state0"
        assert ctx.get_agent_state(1) is None


class TestAgentParameter:
    def test_default(self):
        p = AgentParameter()
        assert p.mass == 1.0
        assert p.gravity == 9.81

    def test_to_vector(self):
        p = AgentParameter(mass=2.0)
        v = p.to_vector()
        assert v[0] == 2.0
        assert len(v) > 3
