"""Observe standalone adapter loading through the public CLI."""

from test_support.contracts.observations import observed
from test_support.physical import cli as _driver


@observed
def load_adapter(case):
    return _driver.load_adapter(case)
