import pytest
import numpy as np
from acsl.framework.tool_category import ToolCategory
from acsl.types.context import StepContext, Result, Time


class DummyTool:
    def __init__(self, name: str, output_value: float = 1.0):
        self.name = name
        self._val = output_value

    def contract(self):
        return {"step": {"inputs": {}, "outputs": {self.name: {"dtype": "float"}}}}

    def step(self, context: StepContext):
        return Result(state=self._val, timestamp=context.time.now)


class TestToolCategory:
    def test_add_and_execute(self):
        cat = ToolCategory("sensor")
        cat.add_tool(DummyTool("s1", 10.0))
        ctx = StepContext(time=Time(now=0.1))
        result = cat.execute(ctx)
        assert result is not None
        assert result.state == 10.0

    def test_cascade_order(self):
        cat = ToolCategory("estimator", mode="cascade")
        cat.add_tool(DummyTool("ekf", 1.0))
        cat.add_tool(DummyTool("lpf", 2.0))
        cat.set_cascade(["ekf", "lpf"])
        ctx = StepContext(time=Time(now=0.1))
        result = cat.execute(ctx)
        assert result.state == 2.0

    def test_activate_tools(self):
        cat = ToolCategory("reference")
        cat.add_tool(DummyTool("hold", 0.0))
        cat.add_tool(DummyTool("circle", 5.0))
        cat.activate_tools(["circle"])
        ctx = StepContext(time=Time(now=0.1))
        result = cat.execute(ctx)
        assert result.state == 5.0

    def test_activate_unknown_raises(self):
        cat = ToolCategory("sensor")
        with pytest.raises(ValueError):
            cat.activate_tools(["nonexistent"])

    def test_cascade_input_passing(self):
        """cascade 内で前段の出力を get_cascade_input() で取得できる"""
        class AddTool:
            def __init__(self, name, add_value):
                self.name = name
                self._add = add_value
            def contract(self):
                return {"step": {"inputs": {}, "outputs": {}}}
            def step(self, context):
                prev = context.get_cascade_input()
                base = prev.input[0] if prev and prev.input is not None else 0.0
                return Result(input=np.array([base + self._add]))

        cat = ToolCategory("controller", mode="cascade")
        cat.add_tool(AddTool("nominal", 1.0))    # 0 + 1 = 1
        cat.add_tool(AddTool("avoid", 0.5))       # 1 + 0.5 = 1.5
        cat.add_tool(AddTool("saturate", 0.1))    # 1.5 + 0.1 = 1.6
        cat.set_cascade(["nominal", "avoid", "saturate"])
        ctx = StepContext(time=Time(now=0.1))
        result = cat.execute(ctx)
        assert result.input is not None
        np.testing.assert_allclose(result.input[0], 1.6)
        # cascade 終了後は _cascade_input がクリアされる
        assert ctx.get_cascade_input() is None
        # 各段の結果が results に保存されている
        assert ctx.get_upstream("controller.nominal").input[0] == 1.0
        assert ctx.get_upstream("controller.avoid").input[0] == 1.5

    def test_parallel_mode(self):
        cat = ToolCategory("sensor", mode="parallel")
        cat.add_tool(DummyTool("cam", 1.0))
        cat.add_tool(DummyTool("lidar", 2.0))
        ctx = StepContext(time=Time(now=0.1))
        result = cat.execute(ctx)
        assert result is not None
