import numpy as np
import pytest
from acsl.types.context import StepContext, Time
from acsl.types.parameter import AgentParameter
from acsl.types.state import State3D
from acsl.framework.agent import Agent, AgentConfig
from acsl.framework.pipeline_engine import PipelineEngine
from acsl.framework.tool_category import ToolCategory
from acsl.framework.orchestrator import Orchestrator
from acsl.framework.phase_manager import PhaseManager
from acsl.framework.blackboard import Blackboard
from acsl.tools.sensor.direct_sensor import DirectSensor
from acsl.tools.estimator.direct_estimator import DirectEstimator
from acsl.tools.reference.time_varying_reference import TimeVaryingReference
from acsl.tools.controller.pid import PIDController
from acsl.tools.plant.model_quat13 import ModelQuat13


def _build_agent() -> Agent:
    param = AgentParameter(mass=1.0)
    agent = Agent(AgentConfig(agent_id=0, dt=0.025, parameter=param))

    sensor_cat = ToolCategory("sensor")
    sensor_cat.add_tool(DirectSensor())

    estimator_cat = ToolCategory("estimator")
    estimator_cat.add_tool(DirectEstimator())

    reference_cat = ToolCategory("reference")
    reference_cat.add_tool(TimeVaryingReference(radius=1.0, period=10.0))

    controller_cat = ToolCategory("controller")
    controller_cat.add_tool(PIDController(kp=3.0, kd=1.5))

    plant_cat = ToolCategory("plant")
    plant_cat.add_tool(ModelQuat13())

    for cat in [sensor_cat, estimator_cat, reference_cat, controller_cat, plant_cat]:
        agent.add_category(cat)

    return agent


class TestStandardPipeline:
    def test_single_step(self):
        agent = _build_agent()
        pe = PipelineEngine("standard")
        ctx = StepContext(
            time=Time(now=0.025, dt=0.025, step_count=1),
            phase="flight",
            parameter=agent.config.parameter,
        )
        pe.execute_step(agent, ctx)
        assert "controller" in ctx.results
        assert ctx.results["controller"].input is not None

    def test_multi_step_position_changes(self):
        agent = _build_agent()
        pe = PipelineEngine("standard")
        for i in range(10):
            ctx = StepContext(
                time=Time(now=(i+1)*0.025, dt=0.025, step_count=i+1),
                phase="flight",
                parameter=agent.config.parameter,
            )
            pe.execute_step(agent, ctx)

        plant_result = ctx.results.get("plant")
        assert plant_result is not None
        state = plant_result.state
        assert isinstance(state, State3D)
        assert not np.allclose(state.p, np.zeros(3))

    def test_orchestrator_run(self):
        agent = _build_agent()
        pm = PhaseManager()
        pm.add_phase("flight")
        pm.set_initial("flight")

        orch = Orchestrator(
            agents=[agent],
            pipeline_engine=PipelineEngine("standard"),
            phase_manager=pm,
            dt=0.025,
        )
        history = orch.run(steps=20)
        assert len(history) == 20
