"""Inspect static build-input admission through detached observations."""
from test_support.contracts.observations import observed
from test_support.physical import docker_context as _driver


@observed
def inspect_docker_context():
    return _driver.docker_context_policy()
