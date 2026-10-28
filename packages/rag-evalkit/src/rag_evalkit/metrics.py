"""Pure ranking and uncertainty functions, with no provider dependencies."""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Collection, Mapping, Sequence

from .contracts import ContractError


def _relevance(gold):
    values = dict(gold) if isinstance(gold, Mapping) else {key: 1.0 for key in gold}
    if any(not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0 for key, value in values.items()):
        raise ContractError("relevance must map document IDs to finite nonnegative numbers")
    return values


def _ranked(ids, k):
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ContractError("k must be positive")
    values = list(ids)
    if len(values) != len(set(values)):
        raise ContractError("ranked IDs must be unique")
    return values[:k]


def recall_at_k(retrieved_ids: Sequence[str], gold: Collection[str] | Mapping[str, float], k: int) -> float | None:
    ranked = _ranked(retrieved_ids, k)
    relevant = {key for key, value in _relevance(gold).items() if value > 0}
    return len(set(ranked) & relevant) / len(relevant) if relevant else None


def ndcg_at_k(retrieved_ids: Sequence[str], relevance: Collection[str] | Mapping[str, float], k: int) -> float | None:
    ranked, values = _ranked(retrieved_ids, k), _relevance(relevance)
    ideal = sorted(values.values(), reverse=True)[:k]
    try:
        idcg = sum((2.0 ** value - 1) / math.log2(i + 2) for i, value in enumerate(ideal))
        dcg = sum((2.0 ** values.get(key, 0.0) - 1) / math.log2(i + 2) for i, key in enumerate(ranked))
    except OverflowError as exc:
        raise ContractError("relevance grade is too large") from exc
    return dcg / idcg if idcg else None


def wilson(passed: int, total: int) -> list[float] | None:
    if not isinstance(passed, int) or not isinstance(total, int) or not 0 <= passed <= total:
        raise ContractError("invalid success counts")
    if not total:
        return None
    z = 1.959963984540054
    proportion, denominator = passed / total, 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def percentile(values: Sequence[float], q: float) -> float | None:
    if not 0 <= q <= 1 or any(not math.isfinite(v) for v in values):
        raise ContractError("invalid percentile input")
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def paired_bootstrap(case_deltas: Mapping[str, Sequence[float]], *, seed: int = 0, samples: int = 2000) -> dict:
    """Resample case clusters, keeping repeated trials within a case together."""
    if samples < 100 or not case_deltas or any(not values or any(not math.isfinite(v) for v in values) for values in case_deltas.values()):
        raise ContractError("bootstrap requires finite paired case observations and >=100 samples")
    means = [statistics.mean(case_deltas[key]) for key in sorted(case_deltas)]
    generator = random.Random(seed)
    draws = [statistics.mean(generator.choices(means, k=len(means))) for _ in range(samples)]
    return {"mean_delta": statistics.mean(means), "ci95": [percentile(draws, .025), percentile(draws, .975)], "unit": "case", "cases": len(means), "samples": samples, "seed": seed}
