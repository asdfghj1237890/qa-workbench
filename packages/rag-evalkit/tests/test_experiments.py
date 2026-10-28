import pytest
from test_support.actions import experiments as act


def test_both_rag_pipelines_finish_with_auditable_source_evidence(tmp_path):
    observed = act.run_example(tmp_path)
    report = observed["report"]
    assert report["complete"]
    assert len(report["rows"]) == 4
    assert {row["status"] for row in report["rows"]} == {"completed"}
    assert all(row["observation"]["grade"]["checks"]["citation_membership"] for row in report["rows"])
    assert all(summary["cost_usd"] == 0 for summary in report["summary"].values())
    assert all(summary["semantic_verdict"] == "not_evaluated" for summary in report["summary"].values())


def test_resume_keeps_completed_observations_and_only_executes_pending_trials(tmp_path):
    first = act.run_example(tmp_path, stop_after=1)
    assert not first["report"]["complete"]
    completed = next(row for row in first["report"]["rows"] if row["status"] == "completed")
    after = act.resume(first["directory"])
    assert after["complete"]
    assert after["rows"][completed["ordinal"]] == completed


def test_interrupted_running_trial_is_recovered_under_exclusive_lease(tmp_path):
    observed = act.interrupted_trial(tmp_path)
    assert observed["before"][0]["status"] == "running"
    assert observed["after"]["complete"]
    assert {row["status"] for row in observed["after"]["rows"]} == {"completed"}


def test_same_run_rejects_two_simultaneous_executors(tmp_path):
    assert "active executor" in act.concurrent_executor(tmp_path)


def test_declared_rag_axis_produces_case_clustered_paired_comparison(tmp_path):
    run = act.run_example(tmp_path)
    compared = act.compare_run(run["directory"], ["rag"])
    assert compared["error"] is None
    assert compared["result"]["paired_trials"] == 2
    assert compared["result"]["unit"] == "case"
    assert compared["result"]["mean_delta"] == 0


@pytest.mark.parametrize("factor", ["model", "harness"])
def test_changing_an_undeclared_factor_prevents_comparison(tmp_path, factor):
    result = act.changed_condition(tmp_path, factor=factor, declared=["rag"])
    assert result["error"] == "incomparable configured factor: " + factor


@pytest.mark.parametrize("factor", ["model", "harness"])
def test_explicit_model_and_harness_axes_allow_real_candidate_changes(tmp_path, factor):
    result = act.changed_condition(tmp_path, factor=factor, declared=["rag", factor])
    assert result["error"] is None
    assert result["result"]["paired_trials"] == 2


@pytest.mark.parametrize("kind", ["leak", "secrets", "unknown_field", "unknown_gold", "budget", "unknown_cost"])
def test_invalid_inputs_or_unbounded_live_runs_are_rejected(kind):
    assert act.invalid_input(kind)


@pytest.mark.parametrize("kind", ["observation", "missing"])
def test_saved_evidence_detects_tampering_and_missing_trials(tmp_path, kind):
    assert act.journal_corruption(tmp_path, kind)


def test_installed_cli_runs_from_an_independent_project_directory(tmp_path):
    result = act.cli_outside_repo(tmp_path)
    assert result["code"] == 0, result["stderr"]
    assert len(result["runs"]) == 1
    assert result["runs"][0]["counts"] == {"completed": 4}


def test_metrics_and_cluster_sampling_do_not_treat_repeats_as_independent_cases():
    result = act.metric_observations()
    assert result["recall"] == 1
    assert result["ndcg"] == 1
    assert result["empty"] is None
    assert result["clustered"]["mean_delta"] == 0
    assert result["clustered"]["cases"] == 2


def test_vector_benchmark_records_measured_latency_recall_and_limits():
    result = act.benchmark()
    assert result["ann_recall_at_k"] == 1
    assert result["throughput_qps"] > 0
    assert result["latency_ms"]["p99"] >= result["latency_ms"]["p50"] >= 0
    assert result["measurement_limits"]["server_resource_usage"] == "not_measured"
    assert result["cleanup"]["status"] == "completed"


def test_randomized_paired_schedule_is_reproducible():
    result = act.repeat_schedule()
    assert result["first"] == result["second"]
    assert len(result["first"]) == 4


def test_unsupported_adapter_is_retained_as_unsupported_and_never_passed(tmp_path):
    result = act.explicit_unsupported(tmp_path)
    assert result["complete"]
    assert result["summary"]["vector"]["statuses"] == {"unsupported": 2}
    assert result["summary"]["vector"]["structural_passes"] == 0


@pytest.mark.parametrize("factor", ["top_k", "prompt", "tools", "embedding"])
def test_plugin_effective_defaults_are_fingerprinted_in_their_own_factor(tmp_path, factor):
    result = act.hidden_effective_factor(tmp_path, factor)
    expected = "rag" if factor == "top_k" else factor
    assert {row["status"] for row in result["report"]["rows"]} == {"completed"}
    assert result["error"] == "incomparable resolved factor: " + expected
