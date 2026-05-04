import pytest
from acsl.framework.config_loader import ConfigLoader, register_guard


class TestConfigLoaderBuildAgent:
    def test_build_agent_minimal(self):
        loader = ConfigLoader()
        loader.load_dict({
            "robot": {"dt": 0.01},
            "agent": {
                "sensor": {
                    "tools": {
                        "direct": {"class": "acsl.tools.sensor.direct_sensor.DirectSensor"},
                    },
                    "cascade": ["direct"],
                },
            },
        })
        agent, dt = loader.build_agent()
        assert dt == 0.01
        assert agent.get_category("sensor") is not None
        assert "direct" in agent.get_category("sensor").tool_names

    def test_build_agent_missing_class(self):
        loader = ConfigLoader()
        loader.load_dict({
            "robot": {},
            "agent": {
                "sensor": {
                    "tools": {
                        "bad": {"class": "nonexistent.module.Foo"},
                    },
                },
            },
        })
        agent, dt = loader.build_agent()
        assert agent.get_category("sensor") is not None
        assert len(agent.get_category("sensor").tool_names) == 0


class TestConfigLoaderBuildPhaseManager:
    def test_build_phases(self):
        loader = ConfigLoader()
        loader.load_dict({
            "phases": {
                "idle": {
                    "transitions": [
                        {"to": "run", "guard": {"type": "always"}},
                    ],
                },
                "run": {},
            },
        })
        pm = loader.build_phase_manager()
        assert pm is not None
        assert pm.current_phase == "idle"
        assert "run" in pm.phases

    def test_build_phases_with_allocation(self):
        loader = ConfigLoader()
        loader.load_dict({
            "phases": {
                "takeoff": {
                    "allocation": {
                        "reference": ["takeoff_ref"],
                    },
                    "transitions": [],
                },
            },
        })
        pm = loader.build_phase_manager()
        alloc = pm.current_allocation()
        assert alloc is not None
        assert alloc.reference == ["takeoff_ref"]

    def test_custom_guard(self):
        register_guard("test_guard", lambda ctx: True)
        loader = ConfigLoader()
        loader.load_dict({
            "phases": {
                "a": {
                    "transitions": [
                        {"to": "b", "guard": {"type": "test_guard"}},
                    ],
                },
                "b": {},
            },
        })
        pm = loader.build_phase_manager()
        from acsl.types.context import StepContext
        result = pm.evaluate(StepContext())
        assert result == "b"


class TestConfigLoaderBuildAll:
    def test_build_all(self):
        loader = ConfigLoader()
        loader.load_dict({
            "meta": {"pipeline": "standard"},
            "robot": {"dt": 0.025},
            "agent": {
                "sensor": {
                    "tools": {
                        "direct": {"class": "acsl.tools.sensor.direct_sensor.DirectSensor"},
                    },
                    "cascade": ["direct"],
                },
            },
            "phases": {
                "run": {},
            },
        })
        orch, agent, pm = loader.build_all()
        assert orch is not None
        assert len(orch.agents) == 1
        assert pm.current_phase == "run"
