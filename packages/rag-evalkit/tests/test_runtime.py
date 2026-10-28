"""Behavioral scripts: assertions stay here; all wiring lives in physical."""

import pytest
from test_support.actions import runtime


def test_replay_is_explicitly_synthetic_and_does_not_invent_token_usage():
    observed = runtime.replay_answer()
    assert observed["result"].answer == "Synthetic answer"
    assert observed["result"].status == "completed"
    assert observed["result"].metadata["synthetic"] is True
    assert observed["description"]["evidence_kind"] == "synthetic_replay"
    assert observed["result"].usage.input_tokens is None
    assert observed["result"].usage.output_tokens is None
    assert observed["result"].usage.cost_usd == 0


def test_replay_can_exercise_the_same_tool_loop_without_a_provider():
    observed = runtime.replay_answer(tools=True)
    assert observed["result"].status == "completed"
    assert observed["result"].requests == 2
    assert [event.kind for event in observed["result"].traces].count("tool_result") == 1


def test_cancellation_before_start_prevents_any_model_dispatch():
    observed = runtime.replay_answer(cancel_before=True)
    assert observed["result"].status == "cancelled"
    assert observed["result"].requests == 0


def test_unknown_cost_is_not_converted_to_zero_or_accepted_under_budget():
    result = runtime.unknown_cost_run()
    assert result.status == "usage_unknown"
    assert result.usage.cost_usd is None
    assert result.usage.input_tokens is None


def test_usage_aggregation_preserves_unknown_values():
    observed = runtime.summed_usage()
    assert observed["unknown"].input_tokens is None
    assert observed["unknown"].output_tokens == 7
    assert observed["unknown"].cost_usd is None
    assert observed["known"].input_tokens == 6
    assert observed["known"].output_tokens == 8
    assert observed["known"].cost_usd == pytest.approx(0.3)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(("guard", "status", "requests"), [
    ("opt_in", "live_opt_in_required", 0),
    ("pricing", "live_pricing_and_budget_required", 0),
    ("budget", "budget_limit", 0),
    ("input_limit", "input_token_limit", 1),
    ("requests", "request_limit", 2),
    ("turns", "turn_limit", 2),
    ("http_error", "provider_http_error", 2),
    ("live_missing_usage", "usage_unknown", 2),
])
def test_guards_fail_closed_before_tool_side_effects(provider, guard, status, requests):
    observed = runtime.guarded_run(provider, guard)
    assert observed["result"].status == status
    assert observed["dispatched"] == []
    assert len(observed["requests"]) == requests
    assert observed["result"].requests == requests


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(("failure", "status"), [
    ("unknown_tool", "unsupported_tool"),
    ("bad_arguments", "contract_error"),
    ("malformed_tool", "provider_invalid_response"),
    ("tool_error", "tool_error"),
])
def test_invalid_or_failed_tools_do_not_trigger_a_second_model_request(provider, failure, status):
    observed = runtime.failed_tool_run(provider, failure)
    expected = "provider_invalid_tool_call" if provider == "openai" and failure == "malformed_tool" else status
    assert observed["result"].status == expected
    assert len(observed["requests"]) == 2
    assert len(observed["dispatched"]) == (1 if failure == "tool_error" else 0)
    assert "fixture-only-sensitive" not in str(observed["result"].traces)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(("failure", "status"), [("timeout", "timeout"), ("cancel", "cancelled")])
def test_inflight_tool_timeout_and_cancel_are_bounded_and_disclosed(provider, failure, status):
    observed = runtime.failed_tool_run(provider, failure)
    assert observed["result"].status == status
    assert observed["handler_started_at_return"] is True
    assert observed["handler_completed_at_return"] is False
    assert len(observed["requests"]) == 2
    errors = [event.data for event in observed["result"].traces if event.kind == "runtime_error"]
    assert errors[-1]["operation_may_continue"] is True


@pytest.mark.parametrize("case", ["stream", "schema", "single_turn_tools", "unknown_setting"])
def test_unsupported_features_are_explicitly_rejected(case):
    observed = runtime.rejected_configuration(case)
    assert observed["error_type"] == "UnsupportedCapability"


@pytest.mark.parametrize("case", ["endpoint_credentials", "endpoint_query", "fixture_without_transport", "nan_price", "nan_timeout", "negative_usage"])
def test_invalid_or_credential_bearing_configuration_is_rejected(case):
    observed = runtime.rejected_configuration(case)
    assert observed["error_type"] == "ContractError"


def test_invalid_batch_is_rejected_before_any_valid_tool_side_effect():
    observed = runtime.mixed_tool_batch()
    assert observed["result"].status == "unsupported_tool"
    assert observed["dispatched"] == []


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_tool_side_effects_wait_for_budget_for_the_continuation(provider):
    observed = runtime.insufficient_continuation_budget(provider)
    assert observed["result"].status == "budget_limit"
    assert len(observed["requests"]) == 2
    assert observed["dispatched"] == []


def test_requested_tool_is_not_recorded_as_started_when_dispatch_times_out():
    observed = runtime.expired_tool_dispatch()
    assert observed["result"].status == "timeout"
    assert observed["dispatched"] == []
    events = [event.kind for event in observed["result"].traces]
    assert events.count("tool_requested") == 1
    assert events.count("tool_start") == 0
    assert events.count("tool_result") == 0


def test_uninstrumented_custom_model_reports_logical_calls_without_claiming_http_observation():
    result = runtime.custom_request_accounting()
    assert result.status == "completed"
    assert result.requests == 1
    accounting = result.metadata["request_accounting"]
    assert accounting["unit"] == "logical_model_calls"
    assert accounting["observed_http_requests"] is None
    assert accounting["observations_complete"] is False


def test_slow_count_timeout_retains_observed_requests_separately_from_reserved_slots():
    for observed in runtime.slow_count_runs(25):
        result = observed["result"]
        assert result.status == "timeout"
        assert result.requests == observed["actual_requests_at_return"]
        assert observed["actual_requests_after_cleanup"] == observed["actual_requests_at_return"]
        accounting = result.metadata["request_accounting"]
        assert accounting["reserved"] == 2
        assert accounting["observed_http_requests"] == result.requests
        assert accounting["unit"] == "http_requests"
        if result.requests:
            assert accounting["in_flight_http_requests"] == 1
            assert accounting["observations_complete"] is False


def test_boolean_enum_does_not_accept_a_numerically_equal_json_number():
    observed = runtime.enum_type_mismatch()
    assert observed["error_type"] == "ContractError"


@pytest.mark.parametrize("role", ["system", "user", "tool"])
def test_provider_state_is_only_valid_on_assistant_messages(role):
    observed = runtime.message_state_validation(role)
    assert observed["error_type"] == "ContractError"
