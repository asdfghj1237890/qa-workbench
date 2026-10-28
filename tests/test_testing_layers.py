"""Project-independent enforcement of the script/action/physical contract."""

import pytest
from test_support.actions import testing
from test_support.contracts.testing import POLICY_CASES


@pytest.mark.parametrize("case,diagnostic", POLICY_CASES)
def test_configured_project_rejects_each_boundary_violation(case, diagnostic):
    result = testing.inspect_case(case)
    assert any(diagnostic in finding for finding in result["findings"])
    assert all(finding.startswith(result["path"] + ":") for finding in result["findings"])


@pytest.mark.parametrize("case", ["valid_script", "lifecycle_action", "contract_observation_binding"])
def test_valid_public_contracts_and_declared_fixture_bridge_remain_usable(case):
    assert testing.inspect_case(case)["findings"] == []


@pytest.mark.parametrize("value", [
    {"test_root": "../outside"},
    {"test_root": "/outside"},
    {"support_package": "invalid.package"},
    {"lifecycle_actions": ["application.driver"]},
    {"lifecycle_actions": "quality_support.actions.lifecycle.isolated_orders"},
    {"skip": ["test_orders.py"]},
    {"observation_modules": ["application"]},
])
def test_policy_rejects_unclassified_or_escape_configuration(value):
    assert testing.invalid_policy(value)


def test_staged_configuration_and_script_ignore_clean_working_tree_overlays():
    result = testing.staged_policy("overlay")
    assert result["code"] == 1
    assert "forbidden dependency application" in result["output"]
    assert "no scripts found" not in result["output"]


def test_missing_indexed_configuration_cannot_fall_back_to_local_copy():
    result = testing.staged_policy("missing_config")
    assert result["code"] != 0


@pytest.mark.parametrize("mode", ["clean", "nested"])
def test_valid_staged_tree_accepts_custom_paths_and_support_namespace(mode):
    result = testing.staged_policy(mode)
    assert result["code"] == 0, result["output"]
    assert "index" in result["output"]
