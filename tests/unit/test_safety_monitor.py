import pytest
import numpy as np
from acsl.framework.safety_monitor import SafetyMonitor
from acsl.types.safety import SafetyConfig
from acsl.types.context import StepContext, Time


class TestSafetyMonitor:
    def test_config_validation_fails(self):
        with pytest.raises(ValueError):
            SafetyMonitor(SafetyConfig())

    def test_thrust_saturation(self):
        sm = SafetyMonitor(SafetyConfig(thrust_max=15.0, torque_max=(1.0, 1.0, 0.5)))
        u = np.array([20.0, 0.0, 0.0, 0.0])
        sat = sm.saturate(u)
        assert sat[0] <= 15.0

    def test_torque_saturation(self):
        sm = SafetyMonitor(SafetyConfig(thrust_max=15.0, torque_max=(1.0, 1.0, 0.5)))
        u = np.array([10.0, 5.0, -5.0, 3.0])
        sat = sm.saturate(u)
        assert sat[1] <= 1.0
        assert sat[2] >= -1.0
        assert sat[3] <= 0.5

    def test_rate_limiting(self):
        sm = SafetyMonitor(SafetyConfig(thrust_max=20.0, torque_max=(5.0, 5.0, 5.0), input_rate_limit=1.0))
        u1 = np.array([10.0, 0.0, 0.0, 0.0])
        sm.saturate(u1)
        u2 = np.array([20.0, 0.0, 0.0, 0.0])
        sat = sm.saturate(u2)
        assert sat[0] <= 11.0

    def test_watchdog_no_alert_initially(self):
        sm = SafetyMonitor(SafetyConfig(thrust_max=15.0, torque_max=(1.0, 1.0, 0.5)))
        ctx = StepContext(time=Time(now=0.1))
        alerts = sm.check(ctx)
        assert len(alerts) == 0
