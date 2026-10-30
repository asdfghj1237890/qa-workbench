"""Inspect portable test architecture in isolated package trees."""

from test_support.contracts.observations import observed
from test_support.physical import evalkit_layers as _driver


@observed
def inspect_case(case):
    return _driver.inspect_case(case)


@observed
def inspect_action_import(module):
    return _driver.inspect_action_import(module)
