from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from acsl.types.context import StepContext, Result
from acsl.types.contract import IOContract


@runtime_checkable
class Tool(Protocol):
    name: str
    def contract(self) -> IOContract: ...
    def step(self, context: StepContext) -> Optional[Result]: ...


class ToolSlot:
    def __init__(self, category: str):
        self.category = category
        self._tools: Dict[str, Tool] = {}
        self._active: Optional[str] = None

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        if self._active is None:
            self._active = tool.name

    def activate(self, name: str) -> None:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not registered in category '{self.category}'. Available: {list(self._tools.keys())}")
        self._active = name

    @property
    def active_tool(self) -> Optional[Tool]:
        if self._active is None:
            return None
        return self._tools.get(self._active)

    @property
    def active_name(self) -> Optional[str]:
        return self._active

    @property
    def available_tools(self) -> List[str]:
        return list(self._tools.keys())

    def step(self, context: StepContext) -> Optional[Result]:
        tool = self.active_tool
        if tool is None:
            return None
        return tool.step(context)

    def contract(self) -> IOContract:
        tool = self.active_tool
        if tool is None:
            return {"step": {"inputs": {}, "outputs": {}}}
        return tool.contract()


class ToolCategory:
    def __init__(self, name: str, mode: str = "cascade"):
        self.name = name
        self.mode = mode  # "cascade" or "parallel"
        self._slots: Dict[str, ToolSlot] = {}
        self._cascade_order: List[str] = []

    def add_tool(self, tool: Tool) -> None:
        if tool.name not in self._slots:
            slot = ToolSlot(self.name)
            self._slots[tool.name] = slot
            self._cascade_order.append(tool.name)
        self._slots[tool.name].register(tool)

    def set_cascade(self, order: List[str]) -> None:
        for name in order:
            if name not in self._slots:
                raise ValueError(f"Tool '{name}' not found in category '{self.name}'")
        self._cascade_order = order

    def activate_tools(self, names: List[str]) -> None:
        self._cascade_order = []
        for name in names:
            if name not in self._slots:
                raise ValueError(f"Tool '{name}' not found in category '{self.name}'")
            self._cascade_order.append(name)

    def execute(self, context: StepContext) -> Optional[Result]:
        if self.mode == "cascade":
            return self._execute_cascade(context)
        else:
            return self._execute_parallel(context)

    def _execute_cascade(self, context: StepContext) -> Optional[Result]:
        last_result = None
        for slot_name in self._cascade_order:
            slot = self._slots.get(slot_name)
            if slot is None:
                continue
            result = slot.step(context)
            if result is not None:
                last_result = result
                context.update_results(f"{self.name}.{slot_name}", result)
        return last_result

    def _execute_parallel(self, context: StepContext) -> Optional[Result]:
        results = []
        for slot_name in self._cascade_order:
            slot = self._slots.get(slot_name)
            if slot is None:
                continue
            result = slot.step(context)
            if result is not None:
                results.append(result)
                context.update_results(f"{self.name}.{slot_name}", result)
        return results[-1] if results else None

    @property
    def tool_names(self) -> List[str]:
        return list(self._slots.keys())

    @property
    def active_tools(self) -> List[str]:
        return list(self._cascade_order)

    def __repr__(self) -> str:
        return f"ToolCategory({self.name}, mode={self.mode}, tools={self._cascade_order})"
