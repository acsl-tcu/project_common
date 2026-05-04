"""ToolTestBench のテスト（rosbag 不要、from_messages で検証）"""
import numpy as np
import pytest
from acsl.testing import ToolTestBench
from acsl.types.context import StepContext, Result


class DummyController:
    name = "pid"
    def __init__(self, kp=1.0):
        self._kp = kp
    def step(self, context):
        est = context.get_upstream("estimator")
        ref = context.get_upstream("reference")
        if est is None or ref is None:
            return None
        e = ref.state - est.state
        u = self._kp * e
        return Result(input=u, metadata={"error": float(np.linalg.norm(e))})


class TestToolTestBench:
    def test_from_messages(self):
        msgs = [
            (0.0, "estimator", Result(state=np.array([0.0, 0.0, 0.0]))),
            (0.0, "reference", Result(state=np.array([1.0, 0.5, 0.0]))),
            (0.1, "estimator", Result(state=np.array([0.1, 0.05, 0.0]))),
            (0.1, "reference", Result(state=np.array([1.0, 0.5, 0.0]))),
            (0.2, "estimator", Result(state=np.array([0.2, 0.1, 0.0]))),
            (0.2, "reference", Result(state=np.array([1.0, 0.5, 0.0]))),
        ]
        bench = ToolTestBench.from_messages(msgs)
        bench.set_tool(DummyController(kp=2.0), category="controller")
        bench.set_dt(0.05)
        results = bench.run()

        assert len(results) > 0
        valid = [r for r in results if r.result is not None]
        assert len(valid) > 0
        assert valid[0].result.input is not None

    def test_get_timeseries(self):
        msgs = [
            (0.0, "estimator", Result(state=np.array([0.0, 0.0, 0.0]))),
            (0.0, "reference", Result(state=np.array([1.0, 0.0, 0.0]))),
            (0.1, "estimator", Result(state=np.array([0.5, 0.0, 0.0]))),
            (0.1, "reference", Result(state=np.array([1.0, 0.0, 0.0]))),
        ]
        bench = ToolTestBench.from_messages(msgs)
        bench.set_tool(DummyController(kp=1.0))
        bench.set_dt(0.05)
        bench.run()

        times, inputs = bench.get_timeseries("input")
        assert len(times) > 0
        assert inputs.shape[1] == 3  # [x, y, yaw] error

    def test_summary(self):
        msgs = [
            (0.0, "estimator", Result(state=np.array([0.0, 0.0]))),
            (0.0, "reference", Result(state=np.array([1.0, 1.0]))),
        ]
        bench = ToolTestBench.from_messages(msgs)
        bench.set_tool(DummyController())
        bench.set_dt(0.02)
        bench.run()
        s = bench.summary()
        assert s["steps"] > 0
        assert s["valid"] > 0

    def test_cascade(self):
        class ScaleTool:
            name = "scale"
            def step(self, context):
                prev = context.get_cascade_input()
                if prev and prev.input is not None:
                    return Result(input=prev.input * 0.5)
                est = context.get_upstream("estimator")
                if est:
                    return Result(input=est.state)
                return None

        msgs = [
            (0.0, "estimator", Result(state=np.array([2.0, 4.0]))),
        ]
        bench = ToolTestBench.from_messages(msgs)
        bench.set_cascade([ScaleTool()])
        bench.set_tool(ScaleTool(), category="controller")
        bench.set_dt(0.02)
        results = bench.run()
        valid = [r for r in results if r.result is not None]
        assert len(valid) > 0
        np.testing.assert_allclose(valid[0].result.input, [1.0, 2.0])

    def test_none_upstream(self):
        bench = ToolTestBench.from_messages([])
        bench.set_tool(DummyController())
        bench.set_dt(0.02)
        results = bench.run()
        assert len(results) == 0
