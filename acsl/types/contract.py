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
    """ツール列の contract 整合性を検証 (名前マッチ)。"""
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


def validate_category_contracts(
    categories: Dict[str, list],
    execution_order: List[str],
) -> Dict[str, Dict[str, list]]:
    """カテゴリ別パイプラインの contract 整合性を検証。

    input の path フィールド ("category.field") から参照先カテゴリを特定し、
    そのカテゴリの output と照合する。path がなければ直前カテゴリの output で照合。

    Args:
        categories: {category_name: [tool, ...]} 各カテゴリのアクティブツール列
        execution_order: カテゴリの実行順序

    Returns:
        {tool_name: {"missing": [...], "mismatched": [...]}}
    """
    report: Dict[str, Dict[str, list]] = {}

    # カテゴリ別の累積 output を構築
    category_outputs: Dict[str, Dict[str, IOField]] = {}

    for cat_name in execution_order:
        tools = categories.get(cat_name, [])
        cat_outputs: Dict[str, IOField] = {}

        for tool in tools:
            c = tool.contract() if hasattr(tool, "contract") else _normalize_contract({})
            c_norm = _normalize_contract(c)
            c_in = c_norm.get("step", {}).get("inputs", {})
            c_out = c_norm.get("step", {}).get("outputs", {})
            tool_name = getattr(tool, "name", tool.__class__.__name__)

            missing: List[str] = []
            mismatched: List[str] = []

            for input_name, spec in c_in.items():
                if spec.get("source") == "system":
                    continue

                path = spec.get("path", "")
                if "." in path:
                    # path = "category.field" → 指定カテゴリの output から探す
                    ref_cat, ref_field = path.split(".", 1)
                    ref_outputs = category_outputs.get(ref_cat, {})
                    if ref_field not in ref_outputs:
                        if not spec.get("optional", False):
                            missing.append(f"{ref_cat}.{ref_field}")
                    else:
                        prod_spec = ref_outputs[ref_field]
                        if (spec.get("dtype") and prod_spec.get("dtype")
                                and spec["dtype"] != prod_spec["dtype"]):
                            mismatched.append(f"{ref_cat}.{ref_field}")
                else:
                    # path なし → 同カテゴリ内 cascade の直前 output から探す
                    if input_name not in cat_outputs:
                        # 直前カテゴリの output からも探す
                        found = False
                        for prev_cat in execution_order:
                            if prev_cat == cat_name:
                                break
                            if input_name in category_outputs.get(prev_cat, {}):
                                found = True
                                prod_spec = category_outputs[prev_cat][input_name]
                                if (spec.get("dtype") and prod_spec.get("dtype")
                                        and spec["dtype"] != prod_spec["dtype"]):
                                    mismatched.append(input_name)
                                break
                        if not found and not spec.get("optional", False):
                            missing.append(input_name)
                    else:
                        prod_spec = cat_outputs[input_name]
                        if (spec.get("dtype") and prod_spec.get("dtype")
                                and spec["dtype"] != prod_spec["dtype"]):
                            mismatched.append(input_name)

            if missing or mismatched:
                report[tool_name] = {"missing": missing, "mismatched": mismatched}

            cat_outputs.update(c_out)

        category_outputs[cat_name] = cat_outputs

    return report
