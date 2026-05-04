"""Contract integrity checker.

PoC モード (strict=False): contract() のない Tool はスキップ。警告のみ。
統合モード (strict=True): contract() のない Tool はエラー。
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from acsl.types.contract import diff_contracts, merge_contracts, step_outputs, IOContract

if TYPE_CHECKING:
    from acsl.framework.agent import Agent
    from acsl.framework.pipeline_engine import PipelineEngine

logger = logging.getLogger(__name__)


class IntegrityChecker:
    def __init__(self, strict: bool = True):
        """
        Args:
            strict: True なら contract() のない Tool をエラーにする（統合モード）。
                    False なら警告のみでスキップ（PoC モード）。
        """
        self._strict = strict
        self._report: Dict[str, Dict[str, list]] = {}
        self._warnings: List[str] = []

    def check_agent(self, agent: "Agent", pipeline: "PipelineEngine") -> Dict[str, Dict[str, list]]:
        self._report = {}
        self._warnings = []
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

                has_contract = hasattr(tool, 'contract') and callable(tool.contract)

                if not has_contract:
                    key = f"upstream->{category_name}.{tool_name}"
                    if self._strict:
                        self._report[key] = {
                            "missing": ["contract() not defined"],
                            "mismatched": [],
                        }
                        logger.error(
                            f"Tool '{tool_name}' in '{category_name}' has no contract(). "
                            f"Required for integration. Use /generate-contract to create one.")
                    else:
                        self._warnings.append(
                            f"Tool '{tool_name}' in '{category_name}' has no contract() — "
                            f"skipping validation (PoC mode)")
                        logger.warning(self._warnings[-1])
                    continue

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

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    def format_report(self) -> str:
        lines = []
        for w in self._warnings:
            lines.append(f"  [WARN] {w}")
        for key, result in self._report.items():
            status = "OK" if not result["missing"] and not result["mismatched"] else "FAIL"
            lines.append(f"  [{status}] {key}: missing={result['missing']}, mismatched={result['mismatched']}")
        return "\n".join(lines)
