"""Finite JSON reports reject nonstandard constants at the read boundary."""

import pytest
from test_support.actions import serialization as act


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_constants_retain_the_contract_error(tmp_path, constant):
    result = act.read_constant(tmp_path, constant)
    assert result["error_type"] == "ContractError"
    assert result["message"] == "nonfinite JSON: " + constant


def test_finite_json_still_round_trips_utf8_text(tmp_path):
    assert act.read_constant(tmp_path, "42") == {"value": 42, "text": "繁體中文"}
