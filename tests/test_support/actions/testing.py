"""Public behavior actions for the reusable architecture policy."""

from test_support.contracts.observations import observed
from test_support.physical import testing as _driver


@observed
def inspect_case(name):
    return _driver.inspect_case(name)


@observed
def observation(kind):
    return _driver.observation(kind)


@observed
def invalid_policy(value):
    return _driver.invalid_policy(value)


@observed
def staged_policy(mode):
    return _driver.staged_policy(mode)


@observed
def health_evidence(kind):
    return _driver.health_evidence(kind)


@observed
def storage_factory_contract():
    return _driver.storage_factory_contract()
