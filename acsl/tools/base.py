from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Protocol, Type, runtime_checkable
from acsl.types.context import StepContext, Result
from acsl.types.contract import IOContract


@runtime_checkable
class Tool(Protocol):
    name: str
    def contract(self) -> IOContract: ...
    def step(self, context: StepContext) -> Optional[Result]: ...


@runtime_checkable
class InitializableTool(Tool, Protocol):
    def initialize(self, context: StepContext) -> None: ...
    def is_ready(self) -> bool: ...


def tool_contract(
    inputs: Optional[Dict[str, Dict[str, Any]]] = None,
    outputs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Callable:
    def decorator(cls: type) -> type:
        auto_inputs = {}
        for name, spec in (inputs or {}).items():
            field = {
                "path": spec.get("path", ""),
                "optional": spec.get("optional", False),
                "desc": spec.get("desc", ""),
            }
            if "dtype" in spec:
                field["dtype"] = spec["dtype"]
            auto_inputs[name] = field

        auto_outputs = {}
        for name, spec in (outputs or {}).items():
            field = {
                "path": spec.get("path", ""),
                "optional": spec.get("optional", False),
                "desc": spec.get("desc", ""),
            }
            if "dtype" in spec:
                field["dtype"] = spec["dtype"]
            auto_outputs[name] = field

        _contract: IOContract = {
            "constructor": {"inputs": {}},
            "step": {"inputs": auto_inputs, "outputs": auto_outputs},
        }

        original_contract = getattr(cls, "contract", None)
        if original_contract is None or not callable(original_contract):
            def contract_method(self) -> IOContract:
                return _contract
            cls.contract = contract_method

        return cls
    return decorator
