"""Real server conformance: explicit opt-in, unique owned resources, finally cleanup."""
import pytest
from test_support.actions.stores import StoreSession, live_store_available


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["es_live", "postgres_live"])
@pytest.mark.parametrize("metric,expected,scores", [
    ("cosine", ["a", "b", "c"], [1, 0, -1]),
    ("l2", ["a", "b", "c"], [0, -(2 ** 0.5), -2]),
    ("inner_product", ["a", "b", "c"], [1, 0, -1]),
])
def test_real_server_shared_conformance(backend, metric, expected, scores):
    if not live_store_available(backend):
        pytest.skip("requires EVALKIT_INTEGRATION=1 and this backend's configured URL/DSN")
    with StoreSession(backend) as store:
        store.upsert([
            {"id": "a", "text": "first source", "vector": [1, 0, 0], "metadata": {"tenant": "one", "nullable": None, "flag": True}},
            {"id": "b", "vector": [0, 1, 0], "metadata": {"tenant": "one", "flag": 1}},
            {"id": "c", "vector": [-1, 0, 0], "metadata": {"tenant": "two"}},
        ])
        hits = store.search([1, 0, 0], metric=metric, top_k=3)
        assert [hit["document"]["id"] for hit in hits] == expected
        assert [hit["score"] for hit in hits] == pytest.approx(scores, abs=1e-5)
        assert [hit["document"]["id"] for hit in store.search([1, 0, 0], filters={"tenant": "one"})] == ["a", "b"]
        assert [hit["document"]["id"] for hit in store.search([1, 0, 0], filters={"nullable": None})] == ["a"]
        assert [hit["document"]["id"] for hit in store.search([1, 0, 0], filters={"flag": 1.0})] == ["b"]
        assert store.search([1, 0, 0], filters={"missing": None}) == []
        store.upsert([{"id": "a", "text": "updated source", "vector": [0, 0, 1]}])
        assert next(hit for hit in store.search([1, 0, 0]) if hit["document"]["id"] == "a")["document"]["text"] == "updated source"
        store.delete(["a", "c", "missing"])
        assert [hit["document"]["id"] for hit in store.search([1, 0, 0])] == ["b"]
        with pytest.raises(ValueError):
            store.upsert([{"id": "zero", "vector": [0, 0, 0]}])


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["es_live", "postgres_live"])
@pytest.mark.parametrize("metric", ["cosine", "l2", "inner_product"])
def test_real_server_ann_matches_exact_on_small_fixture(backend, metric):
    if not live_store_available(backend):
        pytest.skip("requires EVALKIT_INTEGRATION=1 and this backend's configured URL/DSN")
    with StoreSession(backend, ann_metric=metric) as store:
        store.upsert([
            {"id": "a", "vector": [1, 0, 0]}, {"id": "b", "vector": [0, 1, 0]},
            {"id": "c", "vector": [-1, 0, 0]}, {"id": "d", "vector": [0.8, 0.2, 0]},
        ])
        exact = store.search([1, 0, 0], metric=metric, top_k=2)
        ann = store.search([1, 0, 0], metric=metric, top_k=2, exact=False)
        assert [hit["document"]["id"] for hit in ann] == [hit["document"]["id"] for hit in exact]
        assert [hit["score"] for hit in ann] == pytest.approx([hit["score"] for hit in exact], abs=1e-5)
        assert store.describe()["ann_metric"] == metric
