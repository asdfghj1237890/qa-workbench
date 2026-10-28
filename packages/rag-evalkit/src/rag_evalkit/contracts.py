"""Backend-independent search contracts; scores always increase with relevance.

Equality filters are an AND of scalar metadata values. A backend must reject an
unsupported metric or feature rather than silently approximating its semantics.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class UnsupportedCapability(ValueError):
    """The requested behavior cannot be supplied by this adapter."""


class ContractError(ValueError):
    """Invalid input or an invalid adapter observation."""


@dataclass(frozen=True)
class Capabilities:
    features: frozenset[str] = frozenset()

    def require(self, *features: str) -> None:
        missing = set(features) - self.features
        if missing:
            raise UnsupportedCapability("unsupported capabilities: " + ", ".join(sorted(missing)))


def checked_vector(values: Sequence[float]) -> tuple[float, ...]:
    if not values or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ContractError("vector must contain finite numbers and be nonempty")
    return tuple(float(v) for v in values)


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    vector: tuple[float, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or not isinstance(self.text, str):
            raise ContractError("document requires a nonempty string id and text")
        object.__setattr__(self, "vector", checked_vector(self.vector))
        if not isinstance(self.metadata, Mapping):
            raise ContractError("metadata must be a mapping")


@dataclass(frozen=True)
class SearchSpec:
    vector: tuple[float, ...]
    top_k: int = 10
    filters: Mapping[str, Any] = field(default_factory=dict)
    metric: str = "cosine"
    exact: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", checked_vector(self.vector))
        if isinstance(self.top_k, bool) or not isinstance(self.top_k, int) or self.top_k < 1:
            raise ContractError("top_k must be a positive integer")
        if self.metric not in {"cosine", "l2", "inner_product"}:
            raise UnsupportedCapability("unsupported metric: " + str(self.metric))
        if self.metric == "cosine" and not any(self.vector):
            raise ContractError("cosine query must have a nonzero norm")
        if not isinstance(self.exact, bool) or not isinstance(self.filters, Mapping):
            raise ContractError("exact must be boolean and filters must be a mapping")
        for key, value in self.filters.items():
            if not isinstance(key, str) or not key or not (value is None or isinstance(value, (str, int, float, bool))):
                raise UnsupportedCapability("filters support scalar equality only")
            if isinstance(value, float) and not math.isfinite(value):
                raise ContractError("filter numbers must be finite")


@dataclass(frozen=True)
class SearchHit:
    document: Document
    score: float
    raw_score: float
    score_kind: str
    rank: int


@runtime_checkable
class VectorStore(Protocol):
    capabilities: Capabilities

    def describe(self) -> dict[str, Any]: ...
    def upsert(self, documents: Sequence[Document]) -> None: ...
    def search(self, spec: SearchSpec) -> list[SearchHit]: ...
    def delete(self, ids: Sequence[str]) -> None: ...
    def close(self) -> None: ...
