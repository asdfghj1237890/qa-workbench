"""Shared value validation, never backend I/O."""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from ..contracts import ContractError, Document, SearchSpec

FEATURES = frozenset({"metric:cosine", "metric:l2", "metric:inner_product", "exact", "filter:eq", "upsert", "delete"})


class StoreError(RuntimeError):
    """Sanitized backend failure; connection strings and payloads are omitted."""


def dimensions_checked(dimensions: int) -> int:
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise ContractError("dimensions must be a positive integer")
    return dimensions


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise ContractError("resource identifier must contain lowercase letters, numbers or underscores")
    return value


def json_value(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ContractError("metadata must contain JSON values with finite numbers") from error


def documents_checked(documents: Sequence[Document], dimensions: int) -> list[Document]:
    result = []
    for document in documents:
        if not isinstance(document, Document) or len(document.vector) != dimensions:
            raise ContractError("document vector dimensions do not match the store")
        if not any(document.vector):
            raise ContractError("document vectors must be nonzero for the shared cosine-capable corpus")
        vector_storage_checked(document.vector, require_nonzero=True)
        if any(not isinstance(key, str) for key in document.metadata):
            raise ContractError("metadata keys must be strings")
        metadata = json.loads(json_value(dict(document.metadata)))
        result.append(Document(document.id, document.text, document.vector, metadata))
    return result


def spec_checked(spec: SearchSpec, dimensions: int) -> None:
    if not isinstance(spec, SearchSpec) or len(spec.vector) != dimensions:
        raise ContractError("query vector dimensions do not match the store")
    vector_storage_checked(spec.vector, require_nonzero=spec.metric == "cosine")


def vector_storage_checked(vector: Sequence[float], *, require_nonzero: bool) -> None:
    try:
        stored = [struct.unpack("f", struct.pack("f", value))[0] for value in vector]
    except (OverflowError, struct.error):
        raise ContractError("vectors must be representable as finite float32 values") from None
    if any(not math.isfinite(value) for value in stored) or (require_nonzero and not any(stored)):
        raise ContractError("vectors must remain finite and nonzero at float32 storage precision")


def ids_checked(ids: Sequence[str]) -> list[str]:
    if isinstance(ids, str) or any(not isinstance(value, str) or not value for value in ids):
        raise ContractError("ids must be a sequence of nonempty strings")
    return list(ids)


def token(key: str, value: Any) -> str:
    # JSON numbers compare numerically, but booleans never equal numbers.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return hashlib.sha256(json_value([key, value]).encode()).hexdigest()


def filter_tokens(metadata: Mapping[str, Any]) -> list[str]:
    return [token(key, value) for key, value in metadata.items() if value is None or isinstance(value, (str, int, float, bool))]


def matches(metadata: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    return all(key in metadata and token(key, metadata[key]) == token(key, value) for key, value in filters.items())


def similarity(left: Sequence[float], right: Sequence[float], metric: str) -> float:
    if metric == "l2":
        return -math.dist(left, right)
    dot = math.fsum(a * b for a, b in zip(left, right, strict=True))
    if metric == "inner_product":
        return dot
    return max(-1.0, min(1.0, dot / (math.hypot(*left) * math.hypot(*right))))


def description(backend: str, dimensions: int, **settings: Any) -> dict[str, Any]:
    config = {"backend": backend, "dimensions": dimensions, "score_direction": "higher_is_better", "zero_documents": "rejected", **settings}
    return {**config, "settings_fingerprint": hashlib.sha256(json_value(config).encode()).hexdigest()}


class StoreLifecycle:
    _closed = False

    def _check_open(self) -> None:
        if self._closed:
            raise StoreError("store is closed")

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
