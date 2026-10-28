import pytest
from test_support.actions import workflows as act


@pytest.mark.parametrize("field", ["pricing", "limits", "missing_model", "unknown_price", "hosted_shape", "hosted_field"])
def test_unfilled_judge_config_template_is_a_clean_error_without_network(tmp_path, field):
    observed = act.judge_config_rejection(tmp_path, field)
    assert observed["run_exit"] == observed["prepare_exit"] == 0
    assert observed["exit"] == 2
    assert observed["network_calls"] == 0
    assert "rag-eval:" in observed["stderr"]


def test_unknown_query_charge_preserves_known_ingest_cost_in_persisted_report(tmp_path):
    observed = act.partial_embedding_cost(tmp_path)
    summary = next(iter(observed["report"]["summary"].values()))
    assert observed["requests"] == 2
    assert summary["cost_usd"] is None
    assert summary["cost_complete"] is False
    assert summary["observed_cost_usd"] == pytest.approx(.000009)


def test_partial_embedding_failure_does_not_recount_known_charge_on_pipeline_reuse(tmp_path):
    observed = act.partial_embedding_cost(tmp_path, reuse=True)
    first, second = observed["observations"]
    assert observed["requests"] == 2
    assert observed["lifetime"]["cost_usd"] is None
    assert observed["lifetime"]["known_cost_lower_bound_usd"] == pytest.approx(.000009)
    assert first["usage"]["cost_usd"] is None
    assert first["usage"]["known_cost_lower_bound_usd"] == pytest.approx(.000009)
    assert second["usage"]["known_cost_lower_bound_usd"] == 0


def test_store_benchmark_persists_charges_when_embedding_preparation_fails(tmp_path):
    observed = act.runtime_embedding_cli(tmp_path, mode="store_failure")
    assert observed["exit"] == 1
    assert len(observed["requests"]) == 2
    assert observed["report"]["status"] == "failed"
    assert observed["report"]["embedding_usage"]["cost_usd"] is None
    assert observed["report"]["embedding_usage"]["known_cost_lower_bound_usd"] == pytest.approx(.000003)
    assert observed["report"]["embedding_cleanup"]["status"] == "completed"


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_raw_text_cli_runs_real_http_embeddings_without_provided_vectors(tmp_path, backend):
    observed = act.runtime_embedding_cli(tmp_path, backend)
    assert observed["exit"] == 0
    assert observed["metadata"]["dimensions"] == 2
    rows = observed["report"]["rows"]
    assert rows and all(row["status"] == "completed" for row in rows)
    assert all(row["observation"]["result"]["metadata"]["embedding_usage"]["requests"] == 2 for row in rows)
    assert len(observed["requests"]) == 2 * len(rows)
    if backend == "openai":
        assert all(row["observation"]["result"]["usage"]["cost_usd"] == pytest.approx(.000012) for row in rows)
    else:
        assert all(row["observation"]["result"]["usage"]["cost_usd"] is None for row in rows)


@pytest.mark.parametrize("mode,exit_code", [("no_opt_in", 1), ("budget", 2)])
def test_cli_blocks_embedding_dispatch_without_optin_or_sufficient_total_reservation(tmp_path, mode, exit_code):
    observed = act.runtime_embedding_cli(tmp_path, mode=mode)
    assert observed["exit"] == exit_code
    assert observed["requests"] == []


@pytest.mark.parametrize("mode", ["load", "store"])
def test_benchmark_supports_runtime_text_embeddings_and_bounded_pipeline_load(tmp_path, mode):
    observed = act.runtime_embedding_cli(tmp_path, mode=mode)
    assert observed["exit"] == 0
    assert observed["requests"]
    if mode == "load":
        assert observed["report"]["kind"] == "pipeline_load"
        assert observed["report"]["status"] == "completed"
        assert observed["report"]["cost_usd"] > 0
    else:
        assert observed["report"]["embedding_usage"]["requests"] > 0


@pytest.mark.parametrize("kind", ["missing_dimensions", "provided_document", "provided_query", "policy", "fixture"])
def test_runtime_vector_policy_rejects_ambiguous_or_synthetic_inputs(kind):
    assert act.runtime_validation(kind)


def test_custom_prompt_and_source_tool_reach_the_actual_tool_loop():
    observed = act.prompt_tools()
    assert observed["result"]["metadata"]["status"] == "completed"
    assert observed["messages"][0][0]["content"] == "Unit custom source prompt."
    starts = [row for row in observed["result"]["traces"] if row["kind"] == "tool_start"]
    assert [row["data"]["name"] for row in starts] == ["read_source"]
    assert observed["resolved"]["prompt"]["template"] == {"system": "Unit custom source prompt."}
