import numpy as np
import pytest
from acsl.types.context import StepContext, Time
from acsl.types.parameter import AgentParameter
from acsl.framework.agent import Agent, AgentConfig
from acsl.framework.pipeline_engine import PipelineEngine
from acsl.framework.tool_category import ToolCategory
from acsl.framework.phase_manager import PhaseManager, PhaseTransition, PhaseAllocation, PhaseConfig
from acsl.framework.orchestrator import Orchestrator
from acsl.framework.blackboard import Blackboard
from acsl.tools.sensor.direct_sensor import DirectSensor
from acsl.tools.estimator.direct_estimator import DirectEstimator
from acsl.tools.reference.hold_reference import HoldReference
from acsl.tools.reference.takeoff_reference import TakeoffReference
from acsl.tools.reference.time_varying_reference import TimeVaryingReference
from acsl.tools.controller.pid import PIDController
from acsl.tools.plant.model_quat13 import ModelQuat13


def _build_agent_with_refs() -> Agent:
    param = AgentParameter(mass=1.0)
    agent = Agent(AgentConfig(agent_id=0, dt=0.025, parameter=param))

    sensor_cat = ToolCategory("sensor")
    sensor_cat.add_tool(DirectSensor())

    estimator_cat = ToolCategory("estimator")
    estimator_cat.add_tool(DirectEstimator())

    ref_cat = ToolCategory("reference")
    ref_cat.add_tool(HoldReference())
    ref_cat.add_tool(TakeoffReference(target_altitude=1.0))
    ref_cat.add_tool(TimeVaryingReference(radius=1.0, period=10.0))

    ctrl_cat = ToolCategory("controller")
    ctrl_cat.add_tool(PIDController(kp=3.0, kd=1.5))

    plant_cat = ToolCategory("plant")
    plant_cat.add_tool(ModelQuat13())

    for cat in [sensor_cat, estimator_cat, ref_cat, ctrl_cat, plant_cat]:
        agent.add_category(cat)

    return agent


class TestPhaseTransitions:
    def test_idle_to_takeoff_allocation(self):
        agent = _build_agent_with_refs()
        pm = PhaseManager()
        pm.add_phase("idle", PhaseConfig(allocation=PhaseAllocation(reference=["hold"])))
        pm.add_phase("takeoff", PhaseConfig(allocation=PhaseAllocation(reference=["takeoff"])))

        step_count = [0]

        def takeoff_guard(ctx):
            step_count[0] += 1
            return step_count[0] > 3

        pm.add_transition(PhaseTransition("idle", "takeoff", guard=takeoff_guard))
        pm.set_initial("idle")

        agent.apply_allocation(pm.current_allocation())

        orch = Orchestrator(
            agents=[agent],
            pipeline_engine=PipelineEngine("standard"),
            phase_manager=pm,
            dt=0.025,
        )

        for _ in range(5):
            orch.step()

        assert pm.current_phase == "takeoff"
        assert len(pm.history) >= 1
