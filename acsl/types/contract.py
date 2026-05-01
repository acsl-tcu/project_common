from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypedDict


class IOField(TypedDict, total=False):
    shape: Tuple[int, ...]
    dtype: str
    dtype_class: Optional[type]
    optional: bool
    desc: str
    path: str
    source: str  # "system" / "blackboard" / "config"
    merge_strategy: str  # "replace" / "append" / "sum"


class IOConstructor(TypedDict, total=False):
    inputs: Dict[str, IOField]


class IOStep(TypedDict, total=False):
    inputs: Dict[str, IOField]
    outputs: Dict[str, IOField]


class ComposeSpec(TypedDict, total=False):
    mode: str  # "cascade" / "parallel"
    merge_outputs: Dict[str, str]


class IOContract(TypedDict, total=False):
    constructor: IOConstructor
    step: IOStep
    compose: ComposeSpec
    inputs: Dict[str, IOField]
    outputs: Dict[str, IOField]


def _normalize_contract(contract: IOContract) -> IOContract:
    constructor = contract.get("constructor", {}) or {}
    step = contract.get("step", {}) or {}
    if "step" not in contract and ("inputs" in contract or "outputs" in contract):
        step = {
            "inputs": contract.get("inputs", {}) or {},
            "outputs": contract.get("outputs", {}) or {},
        }
    return {
        "constructor": {"inputs": constructor.get("inputs", {}) or {}},
        "step": {
            "inputs": step.get("inputs", {}) or {},
            "outputs": step.get("outputs", {}) or {},
        },
    }


def merge_contracts(contracts: Iterable[IOContract]) -> IOContract:
    merged_ctor: Dict[str, IOField] = {}
    merged_in: Dict[str, IOField] = {}
    merged_out: Dict[str, IOField] = {}
    for c in contracts:
        n = _normalize_contract(c)
        merged_ctor.update(n["constructor"].get("inputs", {}))
        merged_in.update(n["step"].get("inputs", {}))
        merged_out.update(n["step"].get("outputs", {}))
    return {
        "constructor": {"inputs": merged_ctor},
        "step": {"inputs": merged_in, "outputs": merged_out},
    }


def diff_contracts(
    producer: IOContract, consumer: IOContract
) -> Tuple[List[str], List[str]]:
    missing: List[str] = []
    mismatched: List[str] = []
    p_norm = _normalize_contract(producer)
    c_norm = _normalize_contract(consumer)
    p_out = p_norm.get("step", {}).get("outputs", {})
    c_in = c_norm.get("step", {}).get("inputs", {})
    for name, spec in c_in.items():
        if spec.get("source") == "system":
            continue
        if name not in p_out:
            if not spec.get("optional", False):
                missing.append(name)
            continue
        prod_spec = p_out[name]
        if spec.get("dtype") and prod_spec.get("dtype") and spec["dtype"] != prod_spec["dtype"]:
            mismatched.append(name)
        elif spec.get("shape") and prod_spec.get("shape") and spec["shape"] != prod_spec["shape"]:
            mismatched.append(name)
    return missing, mismatched


def step_outputs(contract: IOContract) -> Dict[str, IOField]:
    return _normalize_contract(contract).get("step", {}).get("outputs", {})


def validate_pipeline_contracts(tools_in_order: list) -> Dict[str, Dict[str, list]]:
    report: Dict[str, Dict[str, list]] = {}
    if not tools_in_order:
        return report
    agg: IOContract = {"constructor": {"inputs": {}}, "step": {"inputs": {}, "outputs": {}}}
    for tool in tools_in_order:
        c = tool.contract() if hasattr(tool, "contract") else _normalize_contract({})
        missing, mismatched = diff_contracts(agg, c)
        name = getattr(tool, "name", tool.__class__.__name__)
        key = f"upstream->{name}"
        report[key] = {"missing": missing, "mismatched": mismatched}
        agg = merge_contracts([agg, {"step": {"inputs": {}, "outputs": step_outputs(c)}}])
    return report
