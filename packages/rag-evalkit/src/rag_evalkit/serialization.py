"""Canonical, finite JSON and content fingerprints."""

import dataclasses
import hashlib
import json
import math
from collections.abc import Mapping

from .contracts import ContractError


def plain(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ContractError("JSON object keys must be strings")
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(plain(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ContractError("not a finite JSON value: " + type(value).__name__)


def canonical(value):
    return json.dumps(plain(value), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def usage_cost_lower_bound(usage):
    """Retain observed charges even if another request's charge is unknown."""
    if not isinstance(usage, Mapping):
        return 0.0
    cost = usage.get("cost_usd")
    if cost is None:
        details = usage.get("details", {})
        cost = usage.get("known_cost_lower_bound_usd", details.get("known_cost_lower_bound_usd"))
        if cost is None:
            cost = usage_cost_lower_bound(details.get("observed_prior_usage")) + usage_cost_lower_bound(details.get("partial_request_usage"))
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
        raise ContractError("invalid observed cost lower bound")
    return float(cost)


def _reject_nonfinite(value):
    raise ContractError("nonfinite JSON: " + value)


def read_json(path):
    def duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError("duplicate JSON key: " + key)
            result[key] = value
        return result
    with open(path, encoding="utf-8") as source:
        result = json.load(source, object_pairs_hook=duplicate, parse_constant=_reject_nonfinite)
    plain(result)
    return result
