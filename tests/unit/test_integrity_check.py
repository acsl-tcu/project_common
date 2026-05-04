import pytest
from acsl.framework.integrity_check import IntegrityChecker
from acsl.framework.agent import Agent, AgentConfig
from acsl.framework.pipeline_engine import PipelineEngine
from acsl.framework.tool_category import ToolCategory
from acsl.types.context import StepContext, Result


class ToolWithContract:
    name = "with_contract"
    def contract(self):
        return {"step": {"inputs": {}, "outputs": {"data": {"dtype": "float"}}}}
    def step(self, context):
        return Result(state=1.0)


class ToolWithoutContract:
    name = "no_contract"
    def step(self, context):
        return Result(state=2.0)


class TestIntegrityChecker:
    def test_strict_mode_fails_without_contract(self):
        agent = Agent(AgentConfig(agent_id=0))
        cat = ToolCategory("sensor")
        cat.add_tool(ToolWithoutContract())
        agent.add_category(cat)

        checker = IntegrityChecker(strict=True)
        checker.check_agent(agent, PipelineEngine("estimation_only"))
        assert not checker.is_valid()
        assert "contract() not defined" in str(checker.report)

    def test_poc_mode_skips_without_contract(self):
        agent = Agent(AgentConfig(agent_id=0))
        cat = ToolCategory("sensor")
        cat.add_tool(ToolWithoutContract())
        agent.add_category(cat)

        checker = IntegrityChecker(strict=False)
        checker.check_agent(agent, PipelineEngine("estimation_only"))
        assert checker.is_valid()
        assert len(checker.warnings) == 1

    def test_with_contract_passes(self):
        agent = Agent(AgentConfig(agent_id=0))
        cat = ToolCategory("sensor")
        cat.add_tool(ToolWithContract())
        agent.add_category(cat)

        checker = IntegrityChecker(strict=True)
        checker.check_agent(agent, PipelineEngine("estimation_only"))
        assert checker.is_valid()
