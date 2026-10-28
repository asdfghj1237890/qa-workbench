"""Exact, deterministic in-memory oracle (no ANN claims)."""
from __future__ import annotations

import copy
from collections.abc import Sequence

from ..contracts import (
    Capabilities,
    Document,
    SearchHit,
    SearchSpec,
    UnsupportedCapability,
)
from ._common import (
    FEATURES,
    StoreLifecycle,
    description,
    dimensions_checked,
    documents_checked,
    ids_checked,
    matches,
    similarity,
    spec_checked,
)


class MemoryStore(StoreLifecycle):
    capabilities = Capabilities(FEATURES)

    def __init__(self, dimensions: int):
        self.dimensions = dimensions_checked(dimensions)
        self._documents: dict[str, Document] = {}
        self._closed = False

    def describe(self) -> dict:
        return description("memory", self.dimensions, algorithm="exact", precision="python_float64")

    def upsert(self, documents: Sequence[Document]) -> None:
        self._check_open()
        for document in documents_checked(documents, self.dimensions):
            self._documents[document.id] = document

    def search(self, spec: SearchSpec) -> list[SearchHit]:
        self._check_open()
        spec_checked(spec, self.dimensions)
        if not spec.exact:
            raise UnsupportedCapability("memory implements exact search only")
        scored = [(similarity(spec.vector, document.vector, spec.metric), document) for document in self._documents.values() if matches(document.metadata, spec.filters)]
        scored.sort(key=lambda item: (-item[0], item[1].id))
        kind = {"cosine": "cosine_similarity", "l2": "negative_l2_distance", "inner_product": "inner_product"}[spec.metric]
        return [SearchHit(copy.deepcopy(document), score, score, kind, rank) for rank, (score, document) in enumerate(scored[:spec.top_k], 1)]

    def delete(self, ids: Sequence[str]) -> None:
        self._check_open()
        for document_id in ids_checked(ids):
            self._documents.pop(document_id, None)

    def close(self) -> None:
        self._documents.clear()
        self._closed = True
