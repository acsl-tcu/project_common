from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from acsl.framework.tool_category import ToolCategory, Tool
from acsl.framework.blackboard import AgentState
from acsl.types.context import StepContext, Result
from acsl.types.parameter import AgentParameter


@dataclass
class AgentConfig:
    agent_id: int = 0
    dt: float = 0.025
    parameter: Optional[AgentParameter] = None


class Agent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self._categories: Dict[str, ToolCategory] = {}
        self._state_snapshot: Optional[AgentState] = None

    @property
    def agent_id(self) -> int:
        return self.config.agent_id

    def add_category(self, category: ToolCategory) -> None:
        self._categories[category.name] = category

    def get_category(self, name: str) -> Optional[ToolCategory]:
        return self._categories.get(name)

    def apply_allocation(self, allocation: Any) -> None:
        if allocation is None:
            return
        alloc_dict = allocation.as_dict() if hasattr(allocation, "as_dict") else {}
        for cat_name, tool_names in alloc_dict.items():
            category = self._categories.get(cat_name)
            if category and tool_names:
                try:
                    category.activate_tools(tool_names)
                except ValueError:
                    pass

    def get_state_snapshot(self) -> AgentState:
        state = AgentState(agent_id=self.config.agent_id)
        est = self._categories.get("estimator")
        if est:
            # Will be populated during pipeline execution
            pass
        return self._state_snapshot or state

    def update_state_snapshot(self, context: StepContext) -> AgentState:
        state = AgentState(agent_id=self.config.agent_id, phase=context.phase)
        est_result = context.results.get("estimator")
        if est_result:
            state.estimate = est_result.state
        ref_result = context.results.get("reference")
        if ref_result:
            state.reference = ref_result.state
        ctrl_result = context.results.get("controller")
        if ctrl_result:
            state.controller_output = ctrl_result.input
        self._state_snapshot = state
        return state

    @property
    def categories(self) -> Dict[str, ToolCategory]:
        return dict(self._categories)

    def __repr__(self) -> str:
        cats = list(self._categories.keys())
        return f"Agent(id={self.config.agent_id}, categories={cats})"
