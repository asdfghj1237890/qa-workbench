"""Adapter resolution errors remain distinct from adapter initialization failures."""

import pytest
from test_support.actions import cli as act


@pytest.mark.parametrize("case", [
    "no_separator", "empty", "empty_module", "empty_factory", "missing_module",
    "missing_parent", "missing_child", "missing_attribute", "noncallable",
])
def test_unresolvable_adapter_names_are_usage_errors(case):
    result = act.load_adapter(case)
    assert result["error_type"] == "SystemExit"
    assert result["exit_code"] == 2
    assert "adapter must name an installed module:factory" in result["stderr"]


@pytest.mark.parametrize("case,error_type,message", [
    ("factory_value", "ValueError", "bad adapter setting"),
    ("factory_import", "ImportError", "factory SDK unavailable"),
    ("factory_attribute", "AttributeError", "factory setting missing"),
    ("dependency_missing", "ModuleNotFoundError", "qa_review_missing_dependency"),
    ("dependency_import", "ImportError", "dependency initialization failed"),
    ("module_value", "ValueError", "module setting invalid"),
    ("module_attribute", "AttributeError", "module setting missing"),
])
def test_adapter_import_and_factory_failures_preserve_their_cause(case, error_type, message):
    result = act.load_adapter(case)
    assert result["error_type"] == error_type
    assert message in result["message"]
    assert "adapter must name" not in result["stderr"]


def test_resolved_factory_still_starts_the_authenticated_workbench():
    result = act.load_adapter("valid")
    assert result["error_type"] is None
    assert result["server_calls"] == 1
    assert result["factory_calls"] == 1
