import pytest
from test_support.actions import quality as act


def test_bound_independent_declared_review_can_finish_the_quality_gate():
    result = act.review_scenario("pass")["result"]
    assert result["status"] == "passed"
    assert result["semantic_acceptance"] == "accepted_by_declared_review"
    assert result["judge_agreement"] == 1
    assert "self-attested" in result["identity_verification"]


@pytest.mark.parametrize("kind,reason", [("pending", "human_annotations"), ("dev", "holdout_only"), ("corpus", "real_corpus_declared"), ("dataset_fixture", "real_corpus_declared"), ("provenance_fixture", "real_corpus_declared"), ("replay", "live_model_declared"), ("missing_review", "independent_review"), ("sample_floor", "insufficient_independent_cases"), ("missing_calibration", "judge_calibration"), ("positive_only", "incomplete_judge_calibration"), ("class_floor", "incomplete_judge_calibration"), ("holdout_calibration", "incomplete_judge_calibration"), ("synthetic_calibration", "incomplete_judge_calibration")])
def test_missing_real_quality_evidence_remains_pending(kind, reason):
    result = act.review_scenario(kind)["result"]
    assert result["status"] == "pending"
    assert reason in result["pending"]
    assert result["independent_cases"] == 2


@pytest.mark.parametrize("kind", ["tamper", "rehash_tamper", "stale_annotations", "missing_sample", "duplicate_sample", "synthetic_labels", "same_reviewer", "audit_mismatch", "synthetic_audit", "audit_calibration_mismatch", "calibration_tamper", "calibration_status_tamper", "calibration_input_tamper", "judge_identity", "judge_limits", "observed_model_change", "unknown_observed_model", "mixed_observed_model", "failed_judge", "judge_errors", "case_leak", "family_leak"])
def test_tampering_partial_labels_and_nonindependent_review_are_rejected(kind):
    observed = act.review_scenario(kind)
    assert observed["result"] is None
    assert observed["error"]


@pytest.mark.parametrize("kind", ["bad_quality", "disagreement", "low_sensitivity", "low_specificity"])
def test_low_quality_or_uncalibrated_judge_fails_the_gate(kind):
    assert act.review_scenario(kind)["result"]["status"] == "failed"


def test_initial_review_bundle_withholds_variant_identity_and_model_scores():
    bundle = act.review_scenario("pass")["bundle"]
    assert all(set(row) == {"sample_id", "query", "answer", "evidence"} for row in bundle["samples"])
    assert all(set(item) == {"document_id", "chunk_id", "source_id", "text", "rank"} for row in bundle["samples"] for item in row["evidence"])


def test_model_judge_produces_rubric_ratings_with_its_fixture_provenance():
    result = act.model_judge("valid")
    assert result["status"] == "completed"
    assert result["synthetic"] is True
    assert len(result["ratings"]) == 4
    assert result["cost_usd"] == 0


def test_invalid_model_decisions_preserve_failed_evidence():
    result = act.model_judge("invalid")
    assert result["status"] == "failed"
    assert len(result["errors"]) == 4
    assert result["ratings"] == []
    assert result["cost_usd"] == 0
    assert result["known_cost_lower_bound_usd"] == 0


def test_live_judge_stops_after_actual_overrun_and_retains_the_exceeded_charge():
    observed = act.live_judge_stub("overrun")
    result = observed["result"]
    assert observed["generation_dispatches"] == result["attempted_samples"] == 1
    assert result["status"] == "failed"
    assert result["cost_usd"] == result["known_cost_lower_bound_usd"] == pytest.approx(.002)
    assert len(result["errors"]) == 1


def test_live_judge_unknown_charges_stop_dispatch_and_keep_partial_usage():
    observed = act.live_judge_stub("unknown_cost")
    result = observed["result"]
    assert observed["generation_dispatches"] == 1
    assert result["status"] == "failed"
    assert result["cost_usd"] is None
    assert result["unknown_cost_requests"] == 1
    assert result["usage"][0]["details"]["partial_request_usage"]["input_tokens"] == 10


def test_live_judge_preserves_actual_model_identity_and_exact_execution_configuration():
    result = act.live_judge_stub("identity")["result"]
    assert result["status"] == "completed"
    assert result["reviewer"]["descriptor"]["model"] == "configured-alias"
    assert result["observed_models"] == ["actual-judge-a"]
    assert all(row["complete"] and row["models"] == ["actual-judge-a"] for row in result["model_observations"])
    assert result["reviewer"]["execution"]["limits"]["max_input_tokens"] == 1000


@pytest.mark.parametrize("kind", ["unknown_model", "model_change"])
def test_live_judge_missing_or_changed_actual_model_identity_cannot_complete(kind):
    result = act.live_judge_stub(kind)["result"]
    assert result["status"] == "failed"
    assert result["errors"]


@pytest.mark.parametrize("location", ["dataset", "provenance", "model"])
@pytest.mark.parametrize("value", [1, "true", "synthetic_fixture", [], {}])
def test_synthetic_marker_requires_a_boolean_in_every_declared_location(location, value):
    observed = act.synthetic_marker(location, value)
    assert observed["bundle"] is None
    assert "synthetic markers must be boolean" in observed["error"]


def test_development_calibration_requires_positive_and_negative_independent_cases():
    result = act.calibration_scenario("positive_only")
    assert result["status"] == "pending"
    assert result["independent_cases"] == 2
    assert all(row["positive_cases"] == 2 and row["negative_cases"] == 0 for row in result["criteria"].values())


def test_repeated_trials_never_inflate_calibration_class_support():
    result = act.calibration_scenario("repeated_cases")
    assert result["status"] == "passed"
    assert result["independent_cases"] == 2
    assert all(row["positive_cases"] == row["negative_cases"] == 1 for row in result["criteria"].values())
    assert all(row["sensitivity"] == row["specificity"] == row["balanced_accuracy"] == 1 for row in result["criteria"].values())


def test_all_good_quality_holdout_uses_a_separate_positive_negative_development_calibration():
    observed = act.review_scenario("pass")
    assert observed["result"]["status"] == "passed"
    assert observed["calibration"]["status"] == "passed"
    assert observed["result"]["human_pass_rates"] == {"a": 1, "b": 1}
    assert observed["result"]["thresholds"]["min_calibration_class"] == 1
    assert observed["calibration"]["policy"]["min_samples"] == 2


def test_calibration_gives_equal_weight_to_cases_despite_unequal_trial_counts():
    result = act.calibration_scenario("case_weights")
    assert result["status"] == "failed"
    assert result["independent_cases"] == 4
    assert all(row["sensitivity"] == .5 and row["specificity"] == 1 and row["balanced_accuracy"] == .75 for row in result["criteria"].values())


@pytest.mark.parametrize("kind,status", [("default_policy", "passed"), ("default_insufficient", "pending")])
def test_default_calibration_policy_requires_twenty_cases_and_five_per_human_class(kind, status):
    result = act.calibration_scenario(kind)
    assert result["status"] == status
    assert result["policy"]["min_samples"] == 20
    assert result["policy"]["min_class"] == 5
    assert result["policy"]["min_accuracy"] == .8


def test_cli_recomputes_original_dev_calibration_and_scores_separate_holdout(tmp_path):
    observed = act.cli_calibration(tmp_path)
    assert observed["exits"] == [0, 0, 0, 0, 0]
    assert observed["incomplete_template_exit"] == 2
    assert observed["template"]["reviewer"]["id"] == ""
    assert observed["template"]["decision"] == observed["template"]["rationale"] == observed["template"]["reviewed_at"] == ""
    assert observed["calibration"]["status"] == "passed"
    assert observed["score"]["status"] == "passed"
    assert observed["score"]["calibration"]["policy"]["min_class"] == 1


@pytest.mark.parametrize("kind", ["bundle", "key", "human", "judge", "audit", "audit_reviewer", "calibration", "calibration_bundle"])
def test_malformed_quality_artifacts_return_contract_exit_without_traceback(tmp_path, kind):
    observed = act.cli_calibration(tmp_path, malformed=kind)
    assert observed["exits"][-1] == 2
    assert observed["score"] is None


def test_pipeline_load_measures_real_pipeline_and_all_warmup_costs():
    observed = act.benchmark_scenario("success")
    result = observed["result"]
    assert result["status"] == "completed"
    assert result["attempts"] == result["completed"] == 3
    assert len(result["rows"]) == observed["cleanup_calls"] == 4
    assert sum(row["warmup"] for row in result["rows"]) == 1
    assert result["latency_ms"]["p95"] > 0
    assert result["cost_usd"] == 0
    assert result["semantic_acceptance"] == "not_evaluated"


def test_failed_load_attempts_are_counted_and_resources_are_cleaned():
    observed = act.benchmark_scenario("failure")
    result = observed["result"]
    assert result["status"] == "failed"
    assert result["completed"] == 0
    assert result["failed"] == 3
    assert observed["cleanup_calls"] == 4
    assert result["cost_usd"] is None
    assert result["unknown_cost_requests"] == 4
    assert all(row["error"]["message"] == "pipeline benchmark request failed" for row in result["rows"])


def test_cli_exports_separate_blind_and_private_artifacts_and_pending_gate(tmp_path):
    observed = act.cli_review(tmp_path)
    assert observed["prepare_exit"] == 0
    assert observed["score_exit"] == 2
    assert observed["score"]["status"] == "pending"
    assert observed["private_is_separate"]
