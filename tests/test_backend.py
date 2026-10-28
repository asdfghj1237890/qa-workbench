"""Portable workbench scenarios, asserted through public business actions."""
from test_support.actions import backend as act


def test_reading_tasks_and_history_never_executes_an_adapter():
    result = act.inspect_workbench()
    assert result["executions"] == 0
    assert result["tasks"] == ["check", "paid-check"]
    assert result["history"] == []


def test_another_system_uses_the_same_lifecycle_and_owner_bound_evidence():
    result = act.run_and_review()
    assert result["status"] == "completed"
    assert result["structural_status"] == "passed"
    assert result["initial_semantic_status"] == "pending_review"
    assert result["wrong_owner_status"] == 404
    assert result["wrong_hash_status"] == 409
    assert result["missing_row_status"] == 422
    assert result["reviewed_semantic_status"] == "reviewed"
    assert result["quality_passed"] is False
    assert result["hash_matches"] is True


def test_paid_consent_budget_and_options_are_checked_before_dispatch():
    result = act.check_admission()
    assert result["denied_codes"] == [422, 422, 422, 422, 422]
    assert result["executions_before_acceptance"] == 0
    assert result["executions_after_acceptance"] == 1
    assert result["accepted_budget"] == 0.1


def test_restart_recovers_sanitized_logs_without_rerunning_work():
    result = act.restart_workbench()
    assert result["executions"] == 1
    assert result["restored_status"] == "completed"
    assert result["report_hash_unchanged"] is True
    assert result["logs_unchanged"] is True
    assert result["credential_exposed"] is False
    assert result["redaction_present"] is True


def test_abandoned_checkpoint_is_interrupted_and_never_resumed():
    result = act.recover_abandoned_run()
    assert result["status"] == "interrupted"
    assert result["error"] == "execution_interrupted"
    assert result["quality_passed"] is False
    assert result["executions"] == 0


def test_cancel_and_timeout_stop_following_adapter_work():
    result = act.stop_execution()
    assert result["cancel_status"] == "cancelled"
    assert result["timeout_status"] == "timed_out"
    assert result["later_side_effects"] == 0


def test_import_keeps_historical_identity_and_cannot_establish_current_quality():
    result = act.import_evidence()
    assert result["source_sha_preserved"] is True
    assert result["historical_import"] is True
    assert result["quality_passed"] is False
    assert result["semantic_status"] == "pending_review"
    assert result["duplicate_status"] == 409
    assert result["tampered_status"] == 422


def test_corrupt_archive_is_unavailable_instead_of_returning_empty_history():
    result = act.corrupt_archive()
    assert result["status"] == 503


def test_http_host_requires_authentication_and_reads_do_not_start_jobs():
    result = act.exercise_http()
    assert result["unauthenticated_status"] == 401
    assert result["capabilities_status"] == 200
    assert result["executions_after_reads"] == 0
    assert result["start_status"] == 202
    assert result["completed"] is True
    assert result["other_owner_status"] == 404
    assert result["cache_control"] == "no-store"
    assert result["invalid_input_status"] == 422
    assert result["secret_echoed"] is False
    assert result["oversized_body_status"] == 413


def test_saved_quality_flags_require_a_matching_review_when_recovered():
    result = act.recover_forged_quality()
    assert result["quality_passed"] is False
    assert result["semantic_status"] == "pending_review"


def test_adapter_contract_rejects_invalid_source_identity_and_remote_schema_refs():
    result = act.reject_invalid_contract()
    assert result["bad_source_rejected"] is True
    assert result["remote_reference_rejected"] is True
    assert result["executions"] == 0


def test_project_specific_report_rows_require_exact_case_hashes():
    result = act.review_other_report_shape()
    assert result["original_report_preserved"] is True
    assert result["rows_key"] == "samples"
    assert result["missing_rows_status"] == 422
    assert result["reviewed_status"] == "reviewed"
    assert result["quality_passed"] is False


def test_copied_backend_runs_outside_the_news_system_checkout():
    result = act.run_independently()
    assert result["exit_code"] == 0, result["stderr"]
    assert result["project_id"] == "example-system"
    assert result["status"] == "completed"


def test_second_system_template_executes_its_real_layered_business_tests():
    result = act.run_second_system()
    assert result["project_id"] == "cart-example"
    assert result["status"] == "completed"
    assert result["structural_status"] == "passed"
    assert result["quality_passed"] is False
    assert result["counts"] == {"tests": 2, "passed": 2, "failed": 0, "error": 0, "skipped": 0}
    assert [case.rsplit("::", 1)[-1] for case in result["case_ids"]] == [
        "test_cart_total_includes_every_item", "test_cart_rejects_a_negative_price"]
    assert result["semantic_acceptance"] == "not_evaluated"
    assert "2 passed" in result["logs"]


def test_second_system_cancel_and_timeout_terminate_owned_test_processes():
    result = act.stop_second_system()
    assert result["business_process_started"] is True
    assert result["cancel_status"] == "cancelled"
    assert result["business_process_alive"] is False
    assert result["timeout_status"] == "timed_out"
    assert result["timeout_quality_passed"] is False


def test_cli_authentication_rejects_malformed_unicode_without_a_server_error():
    result = act.check_cli_authentication()
    assert result["valid_status"] == 200
    assert result["malformed_status"] == 401
    assert result["malformed_body"] == {"detail": "authentication_required"}


def test_failed_review_write_preserves_pending_evidence_and_allows_retry():
    result = act.retry_failed_review_write()
    assert result["failed_write_status"] == 503
    assert result["semantic_status_after_failure"] == "pending_review"
    assert result["review_after_failure"] is None
    assert result["report_hash_preserved"] is True
    assert result["semantic_status_after_retry"] == "reviewed"
    assert result["quality_passed"] is False
