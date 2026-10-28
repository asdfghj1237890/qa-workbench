"""Keep adapter/client objects out of behavioral test scripts."""

import copy
import dataclasses
import functools


def _check(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            _check(getattr(value, field.name))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _check(key)
            _check(item)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _check(item)
        return
    raise TypeError("observation contains live object: " + type(value).__name__)


def observed(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        result = function(*args, **kwargs)
        _check(result)
        return copy.deepcopy(result)
    return wrapped
