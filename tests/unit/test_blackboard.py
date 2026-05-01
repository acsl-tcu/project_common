import pytest
from acsl.framework.blackboard import Blackboard, AgentState


class TestBlackboard:
    def test_write_not_readable_before_swap(self):
        bb = Blackboard()
        bb.write(0, AgentState(agent_id=0, phase="armed"))
        assert bb.read(0) is None

    def test_readable_after_swap(self):
        bb = Blackboard()
        bb.write(0, AgentState(agent_id=0, phase="armed"))
        bb.swap()
        state = bb.read(0)
        assert state is not None
        assert state.phase == "armed"

    def test_double_buffer_isolation(self):
        bb = Blackboard()
        bb.write(0, AgentState(agent_id=0, phase="step1"))
        bb.swap()
        bb.write(0, AgentState(agent_id=0, phase="step2"))
        state = bb.read(0)
        assert state.phase == "step1"

    def test_read_all(self):
        bb = Blackboard()
        bb.write(0, AgentState(agent_id=0))
        bb.write(1, AgentState(agent_id=1))
        bb.swap()
        all_states = bb.read_all()
        assert len(all_states) == 2

    def test_deep_copy(self):
        bb = Blackboard()
        state = AgentState(agent_id=0, custom={"data": [1, 2, 3]})
        bb.write(0, state)
        bb.swap()
        read_state = bb.read(0)
        read_state.custom["data"].append(4)
        read_again = bb.read(0)
        assert len(read_again.custom["data"]) == 3
