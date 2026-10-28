"""Backend-independent behavior assertions over exact oracle and protocol fixtures."""
import math

import pytest
from test_support.actions.stores import (
    StoreSession,
    observe_construction_failure,
    observe_existing_index_collision,
)

BACKENDS = ["memory", "es_protocol", "postgres_protocol"]
DOCUMENTS = [
    {"id": "a", "text": "alpha source", "vector": [1, 0, 0], "metadata": {"group": "en", "flag": True, "nullable": None}},
    {"id": "b", "vector": [0, 1, 0], "metadata": {"group": "en", "flag": 1}},
    {"id": "c", "vector": [-1, 0, 0], "metadata": {"group": "zh", "flag": False}},
    {"id": "d", "vector": [2, 0, 0], "metadata": {"group": "en", "nullable": "null"}},
]


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("metric,ids,scores", [
    ("cosine", ["a", "d", "b", "c"], [1, 1, 0, -1]),
    ("l2", ["a", "d", "b", "c"], [0, -1, -math.sqrt(2), -2]),
    ("inner_product", ["d", "a", "b", "c"], [2, 1, 0, -1]),
])
def test_shared_exact_ranking_and_score_contract(backend, metric, ids, scores):
    with StoreSession(backend) as store:
        store.upsert(DOCUMENTS)
        hits = store.search([1, 0, 0], metric=metric, top_k=4)
        assert [hit["document"]["id"] for hit in hits] == ids
        assert [hit["score"] for hit in hits] == pytest.approx(scores)
        assert [hit["rank"] for hit in hits] == [1, 2, 3, 4]
        assert all(math.isfinite(hit["raw_score"]) and hit["score_kind"] for hit in hits)
        assert hits[ids.index("a")]["document"]["text"] == "alpha source"
        if backend == "postgres_protocol":
            assert hits[-1]["raw_score"] == pytest.approx(1 - scores[-1] if metric == "cosine" else -scores[-1])
        if backend == "es_protocol":
            assert hits[0]["raw_score"] >= 0
            assert hits[0]["score_kind"].startswith("elasticsearch_script_score:")


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("filters,expected", [
    ({"group": "en"}, ["a", "d", "b"]),
    ({"group": "en", "flag": True}, ["a"]),
    ({"flag": 1.0}, ["b"]),
    ({"nullable": None}, ["a"]),
    ({"nullable": "null"}, ["d"]),
    ({"missing": None}, []),
])
def test_shared_scalar_filter_semantics(backend, filters, expected):
    with StoreSession(backend) as store:
        store.upsert(DOCUMENTS)
        hits = store.search([1, 0, 0], filters=filters)
        assert [hit["document"]["id"] for hit in hits] == expected


@pytest.mark.parametrize("backend", BACKENDS)
def test_upsert_delete_visibility_and_detached_values(backend):
    with StoreSession(backend) as store:
        documents = [{"id": "a/id ?漢字", "vector": [1, 0, 0], "metadata": {"nested": {"source": "original"}}}]
        store.upsert(documents)
        documents[0]["metadata"]["nested"]["source"] = "mutated"
        first = store.search([1, 0, 0])
        assert first[0]["document"]["metadata"]["nested"]["source"] == "original"
        first[0]["document"]["metadata"]["nested"]["source"] = "leaked"
        assert store.search([1, 0, 0])[0]["document"]["metadata"]["nested"]["source"] == "original"
        store.upsert([{"id": "a/id ?漢字", "text": "replaced", "vector": [0, 1, 0]}])
        updated = store.search([1, 0, 0])
        assert len(updated) == 1
        assert updated[0]["document"]["text"] == "replaced"
        assert updated[0]["score"] == pytest.approx(0)
        store.delete(["a/id ?漢字", "does-not-exist"])
        assert store.search([1, 0, 0]) == []


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("documents", [
    [{"id": "valid", "vector": [1, 0, 0]}, {"id": "invalid", "vector": [1, 0]}],
    [{"id": "zero", "vector": [0, 0, 0]}],
    [{"id": "nan", "vector": [float("nan"), 0, 0]}],
    [{"id": "boolean", "vector": [True, 0, 0]}],
    [{"id": "float32_overflow", "vector": [1e100, 0, 0]}],
    [{"id": "float32_underflow", "vector": [1e-100, 0, 0]}],
    [{"id": "metadata", "vector": [1, 0, 0], "metadata": {"invalid": float("inf")}}],
])
def test_invalid_document_batch_is_rejected_before_mutation(backend, documents):
    with StoreSession(backend) as store:
        with pytest.raises(ValueError):
            store.upsert(documents)
        assert store.search([1, 0, 0]) == []


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("vector,settings", [
    ([1, 0], {}), ([0, 0, 0], {}), ([1, 0, 0], {"top_k": 0}),
    ([1, 0, 0], {"filters": {"group": ["en"]}}), ([1, 0, 0], {"metric": "unknown"}),
])
def test_invalid_queries_are_explicit(backend, vector, settings):
    with StoreSession(backend) as store:
        with pytest.raises(ValueError):
            store.search(vector, **settings)


@pytest.mark.parametrize("backend", BACKENDS)
def test_exact_only_cannot_silently_claim_ann(backend):
    with StoreSession(backend) as store:
        with pytest.raises(ValueError, match="exact search only|ANN requires"):
            store.search([1, 0, 0], exact=False)


@pytest.mark.parametrize("backend", BACKENDS)
def test_describe_is_stable_and_excludes_connection_secrets(backend):
    with StoreSession(backend) as first, StoreSession(backend) as second:
        description = first.describe()
        if backend == "es_protocol":
            assert description["target_sha"] != second.describe()["target_sha"]
        else:
            assert description == second.describe()
        assert len(description["settings_fingerprint"]) == 64
        assert description["score_direction"] == "higher_is_better"
        assert all(value not in str(description) for value in ["private", "synthetic-test-key", "postgres://", "http://", "rag_evalkit_"])
        assert description["algorithm"] == "exact"


def test_postgres_target_uses_effective_connection_info_including_libpq_defaults():
    from test_support.actions.stores import observe_resolved_postgres_targets
    result = observe_resolved_postgres_targets()
    assert result["left"]["target_sha"] != result["right"]["target_sha"]
    assert "different-effective-libpq-host" not in str(result)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_database_redirect_is_rejected_before_forwarding_any_credentials(status):
    from test_support.actions.stores import observe_database_redirect
    result = observe_database_redirect(status)
    assert result["error_type"] == "StoreError"
    assert result["target_requests"] == 0
    assert result["source_authorization"] == "ApiKey synthetic-redirect-test"
    assert "synthetic-redirect-test" not in result["error"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_closed_store_rejects_use(backend):
    with StoreSession(backend) as store:
        store.close()
        store.close()
        with pytest.raises(RuntimeError, match="closed"):
            store.search([1, 0, 0])


@pytest.mark.parametrize("backend", ["es_protocol", "postgres_protocol"])
def test_owned_resources_are_cleaned_and_foreign_ownership_is_preserved(backend):
    with StoreSession(backend) as store:
        owner = store.owner()
        store.tamper_owner("foreign-owner")
        with pytest.raises(RuntimeError, match="ownership"):
            store.close()
        assert store.capture()["resources_remaining"] == 1
        store.tamper_owner(owner)
        store.close()
        assert store.capture()["resources_remaining"] == 0
        if backend == "postgres_protocol":
            assert store.capture()["connection_closed"] is True


@pytest.mark.parametrize("backend", ["es_protocol", "postgres_protocol"])
@pytest.mark.parametrize("metric", ["cosine", "l2", "inner_product"])
def test_configured_ann_uses_the_backend_protocol_and_records_settings(backend, metric):
    with StoreSession(backend, ann_metric=metric) as store:
        store.upsert(DOCUMENTS)
        hits = store.search([1, 0, 0], metric=metric, exact=False, top_k=2)
        assert len(hits) == 2
        assert hits[0]["document"]["id"] == ("d" if metric == "inner_product" else "a")
        description = store.describe()
        assert description["algorithm"] == "hnsw"
        assert description["ann_metric"] == metric
        assert description["hnsw_m"] == 16
        captured = store.capture()
        if backend == "es_protocol":
            assert captured["evidence"] == "synthetic_http_protocol"
            assert any("knn" in (request["body"] or {}) for request in captured["requests"])
        else:
            assert captured["evidence"] == "synthetic_dbapi_protocol"
            assert any(request["sql"].startswith("EXPLAIN (FORMAT JSON)") for request in captured["requests"])


def test_pg_ann_planner_fallback_is_unsupported():
    with StoreSession("postgres_protocol", ann_metric="cosine") as store:
        store.fault("fallback")
        with pytest.raises(ValueError, match="planner did not select"):
            store.search([1, 0, 0], exact=False)


@pytest.mark.parametrize("fault", ["partial", "timeout"])
def test_es_partial_search_is_never_a_pass(fault):
    with StoreSession("es_protocol") as store:
        store.fault(fault)
        with pytest.raises(RuntimeError, match="partial or timed out"):
            store.search([1, 0, 0])


def test_pg_filters_and_document_ids_use_bound_values():
    with StoreSession("postgres_protocol") as store:
        store.upsert([{"id": "'; DROP TABLE outside; --", "vector": [1, 0, 0], "metadata": {"x') OR true --": "quoted'value"}}])
        hits = store.search([1, 0, 0], filters={"x') OR true --": "quoted'value"})
        assert len(hits) == 1
        requests = store.capture()["requests"]
        assert all("DROP TABLE outside" not in request["sql"] and "quoted'value" not in request["sql"] for request in requests)
        assert any("enable_indexscan = off" in request["sql"] for request in requests)


@pytest.mark.parametrize("backend", ["es_protocol", "postgres_protocol"])
def test_constructor_failure_leaves_no_owned_resource(backend):
    observation = observe_construction_failure(backend)
    assert observation["error_type"] == "StoreError"
    assert observation["resources_remaining"] == 0
    assert "private" not in observation["error"]
    if backend == "postgres_protocol":
        assert observation["connection_closed"] is True


def test_existing_index_is_not_adopted_or_deleted():
    observation = observe_existing_index_collision()
    assert observation["error_type"] == "StoreError"
    assert observation["resources_remaining"] == 1
    assert observation["delete_requests"] == []


def test_es_malformed_search_does_not_become_an_empty_success():
    with StoreSession("es_protocol") as store:
        store.fault("malformed")
        with pytest.raises(RuntimeError, match="invalid search evidence"):
            store.search([1, 0, 0])
