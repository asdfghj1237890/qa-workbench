"""Elasticsearch HTTP adapter using an exclusively owned ephemeral index.

Protocols: https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-script-score-query
and https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector
The original vector is stored separately for audit and normalized scores. No
existing index is adopted, and cleanup checks its random ownership marker.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from ..contracts import (
    Capabilities,
    ContractError,
    Document,
    SearchHit,
    SearchSpec,
    UnsupportedCapability,
)
from ._common import (
    FEATURES,
    StoreError,
    StoreLifecycle,
    description,
    dimensions_checked,
    documents_checked,
    filter_tokens,
    identifier,
    ids_checked,
    json_value,
    similarity,
    spec_checked,
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ElasticsearchStore(StoreLifecycle):
    def __init__(self, endpoint: str, dimensions: int, *, index_name: str | None = None,
                 api_key: str | None = None, username: str | None = None, password: str | None = None,
                 timeout: float = 10, ann_metric: str | None = None, num_candidates: int = 100,
                 hnsw_m: int = 16, hnsw_ef_construction: int = 100):
        self.dimensions = dimensions_checked(dimensions)
        parts = urlsplit(endpoint)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
            raise ContractError("endpoint requires an HTTP(S) URL without credentials, query or fragment")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ContractError("timeout must be positive and finite")
        if ann_metric not in {None, "cosine", "l2", "inner_product"}:
            raise UnsupportedCapability("unsupported ANN metric")
        for label, value, minimum in (("num_candidates", num_candidates, 1), ("hnsw_m", hnsw_m, 2), ("hnsw_ef_construction", hnsw_ef_construction, 1)):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ContractError(label + " is invalid")
        if num_candidates > 10000:
            raise ContractError("Elasticsearch num_candidates must not exceed 10000")
        self._endpoint, self._timeout = endpoint.rstrip("/"), timeout
        self._target_sha = hashlib.sha256(json_value({"scheme": parts.scheme, "host": parts.hostname, "port": parts.port, "path": parts.path.rstrip("/"), "auth_user": username, "auth_mode": "api_key" if api_key else "basic" if username is not None else "anonymous"}).encode()).hexdigest()
        self._owner = uuid4().hex
        self.index_name = identifier(index_name or "rag_evalkit_" + uuid4().hex)
        if not self.index_name.startswith("rag_evalkit_"):
            raise ContractError("ephemeral index names must start with rag_evalkit_")
        self._headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key and (username or password):
            raise ContractError("choose API key or basic authentication")
        if api_key:
            self._headers["Authorization"] = "ApiKey " + api_key
        elif username is not None:
            self._headers["Authorization"] = "Basic " + base64.b64encode((username + ":" + (password or "")).encode()).decode()
        self._ann_metric, self._num_candidates = ann_metric, num_candidates
        self._hnsw_m, self._hnsw_ef_construction = hnsw_m, hnsw_ef_construction
        self.capabilities = Capabilities(FEATURES | ({"ann"} if ann_metric else set()))
        self._closed = False
        info = self._request("GET", "", root=True)
        self._server_version = info.get("version", {}).get("number")
        if not isinstance(self._server_version, str) or not self._server_version:
            raise StoreError("Elasticsearch server version could not be observed")
        vector_mapping: dict[str, Any] = {"type": "dense_vector", "dims": dimensions, "index": bool(ann_metric)}
        if ann_metric:
            vector_mapping.update(similarity={"cosine": "cosine", "l2": "l2_norm", "inner_product": "max_inner_product"}[ann_metric],
                                  index_options={"type": "hnsw", "m": hnsw_m, "ef_construction": hnsw_ef_construction})
        body = {"settings": {"number_of_shards": 1, "number_of_replicas": 0}, "mappings": {
            "_meta": {"rag_evalkit_owner": self._owner}, "dynamic": "strict", "properties": {
                "document_id": {"type": "keyword"}, "text": {"type": "text", "index": False},
                "metadata": {"type": "object", "enabled": False}, "filter_tokens": {"type": "keyword"},
                "original_vector": {"type": "double", "index": False, "doc_values": False}, "vector": vector_mapping}}}
        try:
            result = self._request("PUT", "", body)
            if not result.get("acknowledged"):
                raise StoreError("Elasticsearch index creation was not acknowledged")
        except Exception as error:
            # A lost acknowledgement may still have created our index. Its marker
            # lets cleanup distinguish that case from a pre-existing resource.
            try:
                self.close()
            except Exception:
                error.add_note("owned-index cleanup could not be confirmed")
            raise

    def _request(self, method: str, suffix: str, body: Any = None, *, missing_ok: bool = False, root: bool = False) -> dict:
        data = None if body is None else json_value(body).encode("utf-8")
        request = Request(self._endpoint + ("/" if root else "/" + self.index_name + suffix), data=data, headers=self._headers, method=method)
        try:
            with build_opener(_NoRedirect()).open(request, timeout=self._timeout) as response:
                result = json.loads(response.read())
                if not isinstance(result, dict):
                    raise StoreError("Elasticsearch returned a non-object response")
                return result
        except HTTPError as error:
            if missing_ok and error.code == 404:
                return {}
            raise StoreError("Elasticsearch " + method + " failed with HTTP " + str(error.code)) from None
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            raise StoreError("Elasticsearch request failed or returned invalid JSON") from None

    def describe(self) -> dict:
        return description("elasticsearch", self.dimensions, algorithm="hnsw" if self._ann_metric else "exact",
                           target_sha=self._target_sha,
                           server_version=self._server_version,
                           ann_metric=self._ann_metric, num_candidates=self._num_candidates if self._ann_metric else None,
                           hnsw_m=self._hnsw_m if self._ann_metric else None,
                           hnsw_ef_construction=self._hnsw_ef_construction if self._ann_metric else None,
                           precision="float32_index_float64_source", timeout_seconds=self._timeout)

    def upsert(self, documents: Sequence[Document]) -> None:
        self._check_open()
        documents = documents_checked(documents, self.dimensions)
        for document in documents:
            self._request("PUT", "/_doc/" + quote(document.id, safe="") + "?refresh=wait_for", {
                "document_id": document.id, "text": document.text, "vector": document.vector,
                "original_vector": document.vector, "metadata": document.metadata,
                "filter_tokens": filter_tokens(document.metadata)})

    def search(self, spec: SearchSpec) -> list[SearchHit]:
        self._check_open()
        spec_checked(spec, self.dimensions)
        filters = [{"term": {"filter_tokens": value}} for value in filter_tokens(spec.filters)]
        query = {"bool": {"filter": filters}} if filters else {"match_all": {}}
        body: dict[str, Any] = {"size": spec.top_k, "_source": ["document_id", "text", "original_vector", "metadata"],
                                "sort": [{"_score": "desc"}, {"document_id": "asc"}]}
        if spec.exact:
            source = {"cosine": "cosineSimilarity(params.vector, 'vector') + 1.0",
                      "l2": "1.0 / (1.0 + l2norm(params.vector, 'vector'))",
                      "inner_product": "double d = dotProduct(params.vector, 'vector'); return d >= 0 ? d + 1.0 : 1.0 / (1.0 - d);"}[spec.metric]
            body["query"] = {"script_score": {"query": query, "script": {"source": source, "params": {"vector": spec.vector}}}}
        else:
            if self._ann_metric != spec.metric:
                raise UnsupportedCapability("ANN requires an index configured for the requested metric")
            if spec.top_k > self._num_candidates:
                raise ContractError("ANN top_k must not exceed configured num_candidates")
            body["knn"] = {"field": "vector", "query_vector": spec.vector, "k": spec.top_k,
                           "num_candidates": self._num_candidates, "filter": query}
        result = self._request("POST", "/_search", body)
        if result.get("timed_out") or result.get("_shards", {}).get("failed", 0):
            raise StoreError("Elasticsearch search was partial or timed out")
        hits = result.get("hits", {}).get("hits")
        if not isinstance(hits, list) or len(hits) > spec.top_k:
            raise StoreError("Elasticsearch returned invalid search evidence")
        observations = []
        seen = set()
        for hit in hits:
            try:
                source = hit["_source"]
                document = Document(source["document_id"], source["text"], tuple(source["original_vector"]), source["metadata"])
                documents_checked([document], self.dimensions)
                if document.id in seen:
                    raise ValueError()
                seen.add(document.id)
                raw_score = float(hit["_score"])
                score = similarity(spec.vector, document.vector, spec.metric)
                if not math.isfinite(raw_score) or not math.isfinite(score):
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                raise StoreError("Elasticsearch returned invalid search evidence") from None
            observations.append((score, document, raw_score))
        observations.sort(key=lambda item: (-item[0], item[1].id))
        return [SearchHit(document, score, raw, "elasticsearch_" + ("script_score" if spec.exact else "knn_score") + ":" + spec.metric, rank)
                for rank, (score, document, raw) in enumerate(observations, 1)]

    def delete(self, ids: Sequence[str]) -> None:
        self._check_open()
        for document_id in ids_checked(ids):
            self._request("DELETE", "/_doc/" + quote(document_id, safe="") + "?refresh=wait_for", missing_ok=True)

    def close(self) -> None:
        if self._closed:
            return
        mapping = self._request("GET", "/_mapping", missing_ok=True)
        if mapping:
            owner = mapping.get(self.index_name, {}).get("mappings", {}).get("_meta", {}).get("rag_evalkit_owner")
            if owner != self._owner:
                raise StoreError("refusing to delete an index with a different ownership marker")
            result = self._request("DELETE", "")
            if not result.get("acknowledged"):
                raise StoreError("owned index deletion was not acknowledged")
        self._closed = True
