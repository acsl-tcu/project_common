import pytest
from acsl.types.contract import merge_contracts, diff_contracts, validate_pipeline_contracts


class TestDiffContracts:
    def test_compatible(self):
        producer = {"step": {"inputs": {}, "outputs": {"estimate": {"dtype": "State3D"}}}}
        consumer = {"step": {"inputs": {"estimate": {"dtype": "State3D"}}, "outputs": {}}}
        missing, mismatched = diff_contracts(producer, consumer)
        assert missing == []
        assert mismatched == []

    def test_missing(self):
        producer = {"step": {"inputs": {}, "outputs": {}}}
        consumer = {"step": {"inputs": {"estimate": {"dtype": "State3D"}}, "outputs": {}}}
        missing, _ = diff_contracts(producer, consumer)
        assert "estimate" in missing

    def test_optional_not_missing(self):
        producer = {"step": {"inputs": {}, "outputs": {}}}
        consumer = {"step": {"inputs": {"estimate": {"dtype": "State3D", "optional": True}}, "outputs": {}}}
        missing, _ = diff_contracts(producer, consumer)
        assert missing == []

    def test_dtype_mismatch(self):
        producer = {"step": {"inputs": {}, "outputs": {"x": {"dtype": "float"}}}}
        consumer = {"step": {"inputs": {"x": {"dtype": "int"}}, "outputs": {}}}
        _, mismatched = diff_contracts(producer, consumer)
        assert "x" in mismatched


class TestMergeContracts:
    def test_merge(self):
        c1 = {"step": {"inputs": {}, "outputs": {"a": {"dtype": "int"}}}}
        c2 = {"step": {"inputs": {}, "outputs": {"b": {"dtype": "float"}}}}
        merged = merge_contracts([c1, c2])
        assert "a" in merged["step"]["outputs"]
        assert "b" in merged["step"]["outputs"]
