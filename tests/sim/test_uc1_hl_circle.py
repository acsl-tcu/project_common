import numpy as np
import pytest
from acsl.types.parameter import AgentParameter
from acsl.types.state import State3D
from acsl.framework.agent import Agent, AgentConfig
from acsl.framework.pipeline_engine import PipelineEngine
from acsl.framework.tool_category import ToolCategory
from acsl.framework.orchestrator import Orchestrator
from acsl.framework.phase_manager import PhaseManager, PhaseConfig, PhaseAllocation
from acsl.tools.sensor.direct_sensor import DirectSensor
from acsl.tools.estimator.direct_estimator import DirectEstimator
from acsl.tools.reference.takeoff_reference import TakeoffReference
from acsl.tools.reference.time_varying_reference import TimeVaryingReference
from acsl.tools.controller.pid import PIDController
from acsl.tools.plant.model_quat13 import ModelQuat13


class TestUC1CircleTracking:
    def test_drone_reaches_altitude(self):
        param = AgentParameter(mass=1.0)
        agent = Agent(AgentConfig(agent_id=0, dt=0.01, parameter=param))

        for name, tool in [
            ("sensor", DirectSensor()),
            ("estimator", DirectEstimator()),
            ("reference", TakeoffReference(target_altitude=1.0, rate=0.5)),
            ("controller", PIDController(kp=8.0, kd=4.0)),
            ("plant", ModelQuat13()),
        ]:
            cat = ToolCategory(name)
            cat.add_tool(tool)
            agent.add_category(cat)

        pm = PhaseManager()
        pm.add_phase("takeoff")
        pm.set_initial("takeoff")

        orch = Orchestrator(
            agents=[agent],
            pipeline_engine=PipelineEngine("standard"),
            phase_manager=pm,
            dt=0.01,
        )
        orch.run(steps=300)

        plant_cat = agent.get_category("plant")
        tool = plant_cat._slots["model_quat13"].active_tool
        final_z = tool.state.p[2]
        assert final_z > 0.3, f"Drone should gain altitude, got z={final_z}"
