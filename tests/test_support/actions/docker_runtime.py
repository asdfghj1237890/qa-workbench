"""Inspect actual image identity and persisted archive writes as detached data."""

from test_support.contracts.observations import observed
from test_support.physical import docker_runtime as _driver


@observed
def validation_enabled():
    return _driver.validation_enabled()


@observed
def process_identity():
    return _driver.process_identity()


@observed
def write_mounted_archive():
    return _driver.write_mounted_archive()
