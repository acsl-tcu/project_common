import pytest
from acsl.framework.phase_manager import PhaseManager, PhaseTransition, PhaseAllocation, PhaseConfig
from acsl.types.context import StepContext, Time


def _make_ctx(t: float = 0.0, phase: str = "idle") -> StepContext:
    return StepContext(time=Time(now=t), phase=phase)


class TestPhaseManager:
    def test_initial_phase(self):
        pm = PhaseManager()
        assert pm.current_phase == "idle"

    def test_add_transition_and_evaluate(self):
        pm = PhaseManager()
        pm.add_phase("idle")
        pm.add_phase("armed")
        pm.add_transition(PhaseTransition(
            from_phase="idle", to_phase="armed",
            guard=lambda ctx: True,
        ))
        ctx = _make_ctx()
        result = pm.evaluate(ctx)
        assert result == "armed"

    def test_guard_prevents_transition(self):
        pm = PhaseManager()
        pm.add_phase("idle")
        pm.add_phase("armed")
        pm.add_transition(PhaseTransition(
            from_phase="idle", to_phase="armed",
            guard=lambda ctx: False,
        ))
        ctx = _make_ctx()
        assert pm.evaluate(ctx) is None

    def test_transition_records_history(self):
        pm = PhaseManager()
        pm.add_phase("idle")
        pm.add_phase("armed")
        ctx = _make_ctx(t=1.0)
        pm.transition("armed", ctx)
        assert pm.current_phase == "armed"
        assert len(pm.history) == 1
        assert pm.history[0][2] == "armed"

    def test_force_transition(self):
        pm = PhaseManager()
        pm.add_phase("idle")
        pm.add_phase("emergency")
        ctx = _make_ctx()
        pm.force_transition("emergency", ctx)
        assert pm.current_phase == "emergency"

    def test_allocation(self):
        alloc = PhaseAllocation(sensor=["motive"], estimator=["ekf"])
        pm = PhaseManager()
        pm.add_phase("flight", PhaseConfig(allocation=alloc))
        pm.set_initial("flight")
        a = pm.current_allocation()
        assert a.sensor == ["motive"]

    def test_priority(self):
        pm = PhaseManager()
        pm.add_phase("idle")
        pm.add_phase("a")
        pm.add_phase("b")
        pm.add_transition(PhaseTransition("idle", "a", guard=lambda ctx: True, priority=1))
        pm.add_transition(PhaseTransition("idle", "b", guard=lambda ctx: True, priority=10))
        ctx = _make_ctx()
        assert pm.evaluate(ctx) == "b"
