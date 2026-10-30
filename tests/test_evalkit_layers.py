"""Portable-suite imports follow the same direction through absolute and relative names."""

import pytest
from test_support.actions import evalkit_layers as act


@pytest.mark.parametrize("case,diagnostic", [
    ("script_from_physical", "script bypasses actions"),
    ("script_relative_physical", "script bypasses actions"),
    ("nested_script_relative_physical", "script bypasses actions"),
    ("script_from_mock", "script bypasses actions"),
    ("script_from_core", "script bypasses actions"),
    ("script_app", "script bypasses actions"),
    ("physical_from_actions", "physical reverses dependency"),
    ("physical_relative_actions", "physical reverses dependency"),
    ("physical_from_script", "physical reverses dependency"),
    ("action_unobserved", "public action requires @observed"),
    ("core_app", "portable core depends on application"),
])
def test_checker_rejects_full_import_targets_and_unchecked_actions(case, diagnostic):
    findings = act.inspect_case(case)
    assert any(diagnostic in finding for finding in findings)


@pytest.mark.parametrize("module", [
    "rag_evalkit", "app", "subprocess", "urllib", "sqlite3", "pathlib", "os",
    "socket", "http.client", "shutil", "tempfile", "test_support.physicality",
])
def test_actions_allow_only_observation_and_physical_imports(module):
    assert any("action performs physical work" in finding for finding in act.inspect_action_import(module))


@pytest.mark.parametrize("case", [
    "script_prefix_neighbors", "physical_prefix_neighbors", "core_prefix_neighbors",
    "action_absolute", "action_relative", "action_from_support",
])
def test_module_boundaries_preserve_unrelated_names_and_valid_action_imports(case):
    assert act.inspect_case(case) == []
