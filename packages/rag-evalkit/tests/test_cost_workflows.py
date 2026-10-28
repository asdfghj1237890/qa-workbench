"""Known offline embedding charges survive workflow failure boundaries."""

import pytest
from test_support.actions import cost_workflows as actions


def test_store_construction_failure_closes_the_already_created_embedding_adapter():
    observed = actions.fail_store_construction()
    assert observed["failure"]["code"] == "fixture_store_constructor_failure"
    assert observed["state"] == {"embedding_closes": 1, "store_closes": 0, "store_attempts": 1}


def test_experiment_retrieval_failure_preserves_ingest_and_query_charges(tmp_path):
    observed = actions.record_failed_experiment(tmp_path)
    report = observed["report"]
    assert report["complete"] is True
    assert report["rows"][0]["status"] == "failed"
    assert report["rows"][0]["observation"]["adapter_usage"]["cost_usd"] == pytest.approx(0.2)
    assert report["summary"]["vector"]["cost_usd"] == pytest.approx(0.2)
    assert report["summary"]["vector"]["observed_cost_usd"] == pytest.approx(0.2)
    assert observed["state"]["embedding_closes"] == observed["state"]["store_closes"] == 1


def test_reusing_pipeline_after_retrieval_failure_only_charges_each_increment_once():
    observed = actions.reuse_failed_pipeline()
    usage = [failure["adapter_usage"] for failure in observed["failures"]]
    assert [failure["code"] for failure in observed["failures"]] == ["fixture_search_failure"] * 2
    assert [row["requests"] for row in usage] == [2, 1]
    assert [row["cost_usd"] for row in usage] == pytest.approx([0.2, 0.1])
    assert sum(row["known_cost_lower_bound_usd"] for row in usage) == pytest.approx(0.3)


def test_benchmark_counts_charged_factory_failures_in_warmup_and_measured_rows():
    observed = actions.benchmark_failed_requests()
    report = observed["report"]
    assert report["status"] == "failed"
    assert len(report["rows"]) == 2
    assert [row["warmup"] for row in report["rows"]] == [True, False]
    assert [row["usage"]["cost_usd"] for row in report["rows"]] == pytest.approx([0.25, 0.25])
    assert report["cost_usd"] == pytest.approx(0.5)
    assert report["known_cost_lower_bound_usd"] == pytest.approx(0.5)
    assert observed["state"]["embedding_closes"] == observed["state"]["store_closes"] == 2


def test_generation_exception_keeps_known_embedding_cost_without_inventing_model_cost():
    observed = actions.reuse_failed_pipeline("generation_exception")
    usage = [failure["adapter_usage"] for failure in observed["failures"]]
    assert len(usage) == 2
    assert [row["cost_usd"] for row in usage] == [None, None]
    assert [row["model_outcome_unknown"] for row in usage] == [True, True]
    assert [row["known_cost_lower_bound_usd"] for row in usage] == pytest.approx([0.2, 0.1])


def test_experiment_unknown_model_usage_keeps_known_embedding_cost_lower_bound(tmp_path):
    report = actions.record_failed_experiment(tmp_path, "model_unknown")["report"]
    assert report["rows"][0]["status"] == "failed"
    assert report["rows"][0]["observation"]["result"]["usage"]["cost_usd"] is None
    assert report["summary"]["vector"]["cost_usd"] is None
    assert report["summary"]["vector"]["cost_complete"] is False
    assert report["summary"]["vector"]["observed_cost_usd"] == pytest.approx(0.2)


def test_benchmark_unknown_model_usage_keeps_warmup_and_measured_embedding_lower_bounds():
    report = actions.benchmark_failed_requests("model_unknown")["report"]
    assert report["status"] == "failed"
    assert report["cost_usd"] is None
    assert report["unknown_cost_requests"] == 2
    assert report["known_cost_lower_bound_usd"] == pytest.approx(0.4)


@pytest.mark.parametrize(("failure", "lower_bound"), [("tool_model_unknown", 0.25), ("tool_model_partial_unknown", 0.28)])
def test_later_unknown_tool_loop_request_keeps_prior_model_and_embedding_charges(tmp_path, failure, lower_bound):
    observed = actions.record_failed_experiment(tmp_path, failure)
    result = observed["report"]["rows"][0]["observation"]["result"]
    assert observed["state"]["model_calls"] == 2
    assert observed["state"]["tool_result_received"] is True
    assert sum(event["kind"] == "tool_result" for event in result["traces"]) == 1
    assert result["usage"]["cost_usd"] is None
    assert result["usage"]["details"]["embedding"]["cost_usd"] == pytest.approx(0.2)
    assert result["usage"]["details"]["model"]["details"]["observed_prior_usage"]["cost_usd"] == pytest.approx(0.05)
    assert observed["report"]["summary"]["vector"]["cost_usd"] is None
    assert observed["report"]["summary"]["vector"]["observed_cost_usd"] == pytest.approx(lower_bound)


def test_unsupported_search_preserves_known_embedding_charges_in_the_experiment(tmp_path):
    report = actions.record_failed_experiment(tmp_path, "unsupported_search")["report"]
    row = report["rows"][0]
    assert row["status"] == "unsupported"
    assert row["observation"]["error"]["type"] == "UnsupportedCapability"
    assert row["observation"]["adapter_usage"]["cost_usd"] == pytest.approx(0.2)
    assert row["observation"]["cleanup"]["status"] == "completed"
    assert report["summary"]["vector"]["observed_cost_usd"] == pytest.approx(0.2)


@pytest.mark.parametrize("failure", ["ingest_cleanup", "ingest_embedder_cleanup"])
def test_initialization_cleanup_failure_does_not_replace_the_original_error_or_usage(failure):
    observed = actions.fail_initialization_and_cleanup(failure)
    error = observed["failure"]
    assert error["type"] == "RuntimeFailure"
    assert error["code"] == "fixture_ingest_failure"
    assert error["adapter_usage"]["cost_usd"] == pytest.approx(0.1)
    assert error["adapter_cleanup"]["status"] == "failed"
    assert error["adapter_cleanup"]["attempted"] is True
    assert error["adapter_cleanup"]["error"]["type"] == "RuntimeError"
    assert "fixture-cleanup-sensitive" not in str(observed)
    assert observed["state"]["embedding_closes"] == observed["state"]["store_closes"] == 1


@pytest.mark.parametrize(("failure", "original_type"), [("ingest_cleanup", "RuntimeFailure"), ("unsupported_ingest_cleanup", "UnsupportedCapability")])
def test_experiment_records_failed_initialization_cleanup_and_keeps_original_costs(tmp_path, failure, original_type):
    observed = actions.record_failed_experiment(tmp_path, failure)
    row = observed["report"]["rows"][0]
    assert row["status"] == "failed"
    assert row["observation"]["error"]["type"] == original_type
    assert row["observation"]["adapter_usage"]["cost_usd"] == pytest.approx(0.1)
    assert row["observation"]["cleanup"]["status"] == "failed"
    assert row["observation"]["cleanup"]["attempted"] is True
    assert row["observation"]["cleanup"]["error"]["type"] == "RuntimeError"
    assert observed["report"]["summary"]["vector"]["observed_cost_usd"] == pytest.approx(0.1)
    assert "fixture-cleanup-sensitive" not in str(observed)


def test_benchmark_retains_charged_factory_failure_and_failed_cleanup_evidence():
    observed = actions.benchmark_failed_requests("ingest_cleanup")
    report = observed["report"]
    assert report["status"] == "failed"
    assert [row["error"]["type"] for row in report["rows"]] == ["RuntimeFailure", "RuntimeFailure"]
    assert [row["cleanup"] for row in report["rows"]] == ["failed", "failed"]
    assert all(row["cleanup_attempted"] is True for row in report["rows"])
    assert all(row["cleanup_error"]["type"] == "RuntimeError" for row in report["rows"])
    assert report["known_cost_lower_bound_usd"] == pytest.approx(0.5)
    assert "fixture-cleanup-sensitive" not in str(observed)
