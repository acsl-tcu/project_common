from __future__ import annotations
from dataclasses import field
from typing import Any, Dict, List, Optional
import time as time_mod

from acsl.framework.agent import Agent
from acsl.framework.pipeline_engine import PipelineEngine
from acsl.framework.phase_manager import PhaseManager
from acsl.framework.blackboard import Blackboard
from acsl.framework.safety_monitor import SafetyMonitor
from acsl.types.context import StepContext, Time, Result
from acsl.types.safety import SafetyConfig, SafetyAlert


class Orchestrator:
    def __init__(
        self,
        agents: Optional[List[Agent]] = None,
        pipeline_engine: Optional[PipelineEngine] = None,
        phase_manager: Optional[PhaseManager] = None,
        blackboard: Optional[Blackboard] = None,
        safety_monitor: Optional[SafetyMonitor] = None,
        dt: float = 0.025,
    ):
        self.agents: List[Agent] = agents or []
        self.pipeline_engine = pipeline_engine or PipelineEngine("standard")
        self.phase_manager = phase_manager or PhaseManager()
        self.blackboard = blackboard or Blackboard()
        self.safety_monitor = safety_monitor
        self._dt = dt
        self._time = 0.0
        self._step_count = 0
        self._log: List[Dict[str, Any]] = []

    def add_agent(self, agent: Agent) -> None:
        self.agents.append(agent)

    def step(self) -> StepContext:
        self._time += self._dt
        self._step_count += 1
        wall_time = time_mod.time()

        time = Time(now=self._time, dt=self._dt, step_count=self._step_count, wall_time=wall_time)
        context = StepContext(time=time, phase=self.phase_manager.current_phase)
        context.agent_states = {k: v for k, v in self.blackboard.read_all().items()}

        # 1. Phase evaluation
        new_phase = self.phase_manager.evaluate(context)
        if new_phase:
            allocation = self.phase_manager.transition(new_phase, context)
            context.phase = new_phase
            for agent in self.agents:
                agent.apply_allocation(allocation)

        # 2. Execute all agents
        for i, agent in enumerate(self.agents):
            agent_ctx = StepContext(
                time=time,
                phase=context.phase,
                agent_index=i,
                agent_states=context.agent_states,
                parameter=agent.config.parameter,
            )
            self.pipeline_engine.execute_step(agent, agent_ctx)
            state = agent.update_state_snapshot(agent_ctx)
            self.blackboard.write(i, state)

        # 3. Safety check
        if self.safety_monitor:
            alerts = self.safety_monitor.check(context)
            if self.safety_monitor.has_critical(alerts):
                self.phase_manager.force_transition("emergency", context)

        # 4. Blackboard swap
        self.blackboard.swap()

        return context

    def run(self, steps: int) -> List[StepContext]:
        history = []
        for _ in range(steps):
            ctx = self.step()
            history.append(ctx)
        return history

    @property
    def time(self) -> float:
        return self._time

    @property
    def step_count(self) -> int:
        return self._step_count

    def __repr__(self) -> str:
        return f"Orchestrator(agents={len(self.agents)}, phase={self.phase_manager.current_phase})"
