import pytest
from acsl.framework.pipeline_engine import PipelineEngine, PRESETS


class TestPipelineEngine:
    def test_standard_order(self):
        pe = PipelineEngine("standard")
        order = pe.execution_order
        assert order.index("sensor") < order.index("estimator")
        assert order.index("estimator") < order.index("reference")
        assert order.index("reference") < order.index("controller")

    def test_dnn_order(self):
        pe = PipelineEngine("dnn")
        order = pe.execution_order
        assert "sensor" in order
        assert "controller" in order
        assert "estimator" not in order

    def test_estimation_only(self):
        pe = PipelineEngine("estimation_only")
        assert pe.execution_order == ["sensor", "estimator"]

    def test_custom_dag(self):
        dag = {"a": [], "b": ["a"], "c": ["b"]}
        pe = PipelineEngine("custom", custom_dag=dag)
        assert pe.execution_order == ["a", "b", "c"]

    def test_unknown_preset(self):
        with pytest.raises(ValueError):
            PipelineEngine("nonexistent")

    def test_cycle_detection(self):
        dag = {"a": ["b"], "b": ["a"]}
        with pytest.raises(RuntimeError, match="Cycle"):
            PipelineEngine("custom", custom_dag=dag)
