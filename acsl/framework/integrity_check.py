from __future__ import annotations
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from acsl.types.contract import diff_contracts, merge_contracts, step_outputs, _normalize_contract, IOContract

if TYPE_CHECKING:
    from acsl.framework.agent import Agent
    from acsl.framework.pipeline_engine import PipelineEngine


class IntegrityChecker:
    def __init__(self):
        self._report: Dict[str, Dict[str, list]] = {}

    def check_agent(self, agent: "Agent", pipeline: "PipelineEngine") -> Dict[str, Dict[str, list]]:
        self._report = {}
        agg: IOContract = {"constructor": {"inputs": {}}, "step": {"inputs": {}, "outputs": {}}}

        for category_name in pipeline.execution_order:
            category = agent.get_category(category_name)
            if category is None:
                continue

            for tool_name in category.active_tools:
                slot = category._slots.get(tool_name)
                if slot is None or slot.active_tool is None:
                    continue
                tool = slot.active_tool
                contract = tool.contract()
                missing, mismatched = diff_contracts(agg, contract)
                key = f"upstream->{category_name}.{tool_name}"
                self._report[key] = {"missing": missing, "mismatched": mismatched}
                agg = merge_contracts([agg, {"step": {"inputs": {}, "outputs": step_outputs(contract)}}])

        return self._report

    def is_valid(self) -> bool:
        return all(
            not v["missing"] and not v["mismatched"]
            for v in self._report.values()
        )

    @property
    def report(self) -> Dict[str, Dict[str, list]]:
        return dict(self._report)

    def format_report(self) -> str:
        lines = []
        for key, result in self._report.items():
            status = "OK" if not result["missing"] and not result["mismatched"] else "FAIL"
            lines.append(f"  [{status}] {key}: missing={result['missing']}, mismatched={result['mismatched']}")
        return "\n".join(lines)
