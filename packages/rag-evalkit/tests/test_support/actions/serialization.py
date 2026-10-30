"""Observe finite JSON reads as detached data."""

from test_support.observed import observed
from test_support.physical import serialization as _driver


@observed
def read_constant(directory, constant):
    return _driver.read_constant(directory, constant)
