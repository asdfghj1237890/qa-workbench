"""Model capability behavior; socket/protocol details live behind actions."""

import pytest
from test_support.actions import model_extensions as actions


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("actual_mode", ["changed", "missing", "null"])
def test_provider_reported_model_identity_survives_parse_finalize_and_harness(provider, streaming, actual_mode):
    observed = actions.observe_model_identity(provider, actual_mode, streaming=streaming)
    expected = actions.OBSERVED_MODEL if actual_mode == "changed" else ""
    assert observed["error"] is None
    assert observed["parsed"].model == expected
    assert observed["generation"].model == expected
    assert observed["description"]["model"] == actions.REQUESTED_MODEL
    end = next(event for event in observed["result"].traces if event.kind == "model_end")
    assert end.data["resolved_model"] == expected
    assert end.data["resolved_model_observed"] is bool(expected)
    assert end.data["requested_model"] == actions.REQUESTED_MODEL


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(("actual_mode", "status"), [("bad_type", "provider_invalid_model_identity"), ("credential", "provider_credential_echo")])
def test_invalid_or_secret_provider_model_identity_fails_without_fabricating_an_alias(provider, streaming, actual_mode, status):
    observed = actions.observe_model_identity(provider, actual_mode, streaming=streaming)
    assert observed["error"].code == status
    assert observed["result"].status == status
    assert not any(event.kind == "model_end" for event in observed["result"].traces)
    assert actions.EXPECTED_CREDENTIAL not in str(observed["result"])


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("actual_mode", ["changed", "missing"])
def test_experiments_persist_actual_identity_and_leave_absent_identity_unknown(tmp_path, provider, streaming, actual_mode):
    row = actions.persist_observed_model_identity(tmp_path, provider, actual_mode, streaming=streaming)
    expected = [actions.OBSERVED_MODEL] if actual_mode == "changed" else []
    assert row["status"] == "completed"
    assert row["observation"]["resolved_factors"]["model"]["observed_models"] == expected
    assert row["observation"]["resolved_factors"]["model"]["model"] == actions.REQUESTED_MODEL
    ends = [event for event in row["observation"]["result"]["traces"] if event["kind"] == "model_end"]
    assert [event["data"]["resolved_model"] for event in ends] == (expected or [""])


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_streaming_reads_real_http_progress_before_the_terminal_is_sent(provider):
    observed = actions.read_progressively_over_http(provider)
    assert observed["progressive"] is True
    assert "".join(event.data["text"] for event in observed["events"] if event.kind == "text_delta") == "Hello 世界"
    assert observed["events"][-1].generation.usage.output_tokens == 5
    assert len(observed["requests"]) == 2


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_streaming_normalizes_text_terminal_usage_and_accounting(provider):
    observed = actions.stream_answer(provider)
    assert observed["result"].status == "completed"
    assert observed["result"].answer == "Hello 世界"
    assert observed["result"].usage.input_tokens == 10
    assert observed["result"].usage.output_tokens == 5
    assert observed["result"].requests == 2
    assert sum(event.kind == "text_delta" for event in observed["result"].traces) == 2
    assert observed["closed"] == [True]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_tool_argument_fragments_are_exposed_before_a_complete_typed_call(provider):
    observed = actions.stream_answer(provider, "tool", iterator=True)
    assert len([event for event in observed["events"] if event.kind == "tool_call_delta"]) == 2
    assert observed["result"].finish_reason == "tool_calls"
    assert observed["result"].tool_calls[0].arguments == {"query": "evidence"}


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(("failure", "status"), [("truncated", "provider_truncated_stream"), ("error", "provider_stream_error"),
                                                  ("cancel", "cancelled"), ("timeout", "timeout"), ("bytes", "stream_byte_limit"),
                                                  ("events", "stream_event_limit"), ("malformed", "provider_invalid_stream_json")])
def test_stream_failures_retain_requests_and_unknown_total_cost(provider, failure, status):
    observed = actions.stream_answer(provider, failure)
    assert observed["result"].status == status
    assert observed["result"].requests == 2
    assert observed["result"].usage.cost_usd is None
    assert observed["result"].usage.details["incomplete_observation"] is True


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_terminal_without_billable_usage_does_not_invent_counts(provider):
    observed = actions.stream_answer(provider, "missing_usage")
    assert observed["result"].usage.input_tokens is None
    assert observed["result"].usage.output_tokens is None
    assert observed["result"].usage.cost_usd is None


def test_anthropic_truncation_keeps_observed_input_usage_as_partial_evidence():
    observed = actions.stream_answer("anthropic", "truncated")
    assert observed["result"].usage.details["partial_request_usage"]["input_tokens"] == 10


def test_stream_credential_echo_is_redacted_from_all_public_events():
    observed = actions.stream_answer("openai", "credential")
    assert observed["result"].status == "provider_credential_echo"
    assert "fixture-key-sensitive" not in str(observed["result"])


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("channel", ["text", "tool"])
@pytest.mark.parametrize("fragment_size", [1, 2, 5, 12, 20])
def test_fragmented_credentials_never_reconstruct_from_public_deltas(provider, channel, fragment_size):
    observed = actions.consume_fragmented_credential(provider, channel, fragment_size)
    assert observed["failure"].code == "provider_credential_echo"
    assert observed["failure"].raw["api_requests"] == 2
    assert actions.EXPECTED_CREDENTIAL not in observed["public_text"]
    assert actions.EXPECTED_CREDENTIAL not in str(observed["public_events"])
    assert actions.EXPECTED_CREDENTIAL not in str(observed["failure"].raw)
    assert observed["final"] is None
    assert "Safe " in observed["public_text"]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("fragment_size", [1, 5, 12])
def test_json_escaped_credentials_are_protected_across_tool_argument_fragments(provider, fragment_size):
    observed = actions.consume_fragmented_credential(provider, "tool", fragment_size, escaped=True)
    assert observed["failure"].code == "provider_credential_echo"
    assert actions.EXPECTED_CREDENTIAL not in observed["decoded_public"]
    assert observed["final"] is None
    assert "Safe " in observed["decoded_public"]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("channel", ["text", "tool"])
def test_nonsecret_suffixes_are_flushed_after_a_valid_terminal(provider, channel):
    observed = actions.consume_fragmented_credential(provider, channel, 1, partial_prefix=True)
    assert observed["failure"] is None
    assert observed["public_text"] == observed["expected_text"]
    assert observed["final"].finish_reason == ("tool_calls" if channel == "tool" else "completed")


@pytest.mark.parametrize(("provider", "mode", "status"), [
    ("openai", "inconsistent", "provider_inconsistent_stream_terminal"),
    ("openai", "tool_inconsistent", "provider_inconsistent_stream_terminal"),
    ("anthropic", "inconsistent", "provider_invalid_stream_terminal"),
    ("anthropic", "tool_inconsistent", "provider_invalid_tool_call"),
])
def test_terminal_and_tool_delta_contradictions_do_not_become_success(provider, mode, status):
    observed = actions.stream_answer(provider, mode)
    assert observed["result"].status == status
    assert observed["result"].requests == 2
    assert observed["result"].usage.cost_usd is None


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("mode", ["url", "base64"])
def test_portable_text_and_image_blocks_reach_count_and_generation(provider, mode):
    observed = actions.describe_image(provider, mode)
    assert observed["result"].status == "completed"
    assert observed["result"].messages[0].content[0].text == "Describe"
    assert "image_input" in observed["description"]["capabilities"]
    assert len(observed["requests"]) == 2
    assert "aW1hZ2U=" not in str(observed["result"].traces)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_image_capability_must_be_explicitly_declared_for_the_configured_model(provider):
    observed = actions.describe_image(provider, "disabled")
    assert observed["result"].status == "unsupported"
    assert observed["requests"] == []


@pytest.mark.parametrize("mode", ["audio", "bad_base64", "credential_url", "hosted_anthropic", "assistant_image"])
def test_unsupported_modalities_and_invalid_image_inputs_fail_explicitly(mode):
    assert actions.reject_invalid_content(mode) in {"ContractError", "UnsupportedCapability"}


@pytest.mark.parametrize("mode", ["normal", "streaming"])
def test_hosted_search_retains_results_citations_and_charges_without_client_dispatch(mode):
    observed = actions.research_with_hosted_tools(mode)
    assert observed["result"].status == "completed"
    assert observed["dispatched"] == []
    assert observed["result"].usage.cost_usd == pytest.approx(0.03002)
    assert observed["reservation"] >= 0.06
    assert sum(event.kind == "hosted_tool_call" for event in observed["result"].traces) == 2
    assert sum(event.kind == "citation" for event in observed["result"].traces) == 2
    assert "Source evidence" in str(observed["result"].traces)


@pytest.mark.parametrize(("mode", "status"), [("budget", "budget_limit"), ("live_unknown", "hosted_tool_pricing_required")])
def test_unfunded_or_unknown_live_hosted_charges_fail_before_http_dispatch(mode, status):
    observed = actions.research_with_hosted_tools(mode)
    assert observed["result"].status == status
    assert observed["requests"] == []


def test_fixture_hosted_tools_with_unknown_rates_keep_cost_unknown():
    observed = actions.research_with_hosted_tools("unknown")
    assert observed["result"].usage.cost_usd is None
    assert observed["result"].usage.details["summed_requests"] is True


def test_hosted_call_limit_failure_keeps_observed_billable_usage():
    observed = actions.research_with_hosted_tools("limit")
    assert observed["result"].status == "hosted_tool_limit_exceeded"
    assert observed["result"].usage.input_tokens == 10
    assert observed["result"].usage.cost_usd == pytest.approx(0.03002)
    assert observed["dispatched"] == []


def test_later_stream_failure_keeps_prior_metered_totals_as_partial_evidence():
    observed = actions.fail_after_a_metered_turn()
    assert observed["result"].status == "provider_truncated_stream"
    assert observed["result"].requests == 4
    assert observed["result"].usage.cost_usd is None
    assert observed["result"].usage.details["observed_prior_usage"]["input_tokens"] == 10
    assert observed["result"].usage.details["observed_prior_usage"]["output_tokens"] == 5
    assert observed["result"].usage.details["observed_prior_usage"]["cost_usd"] == pytest.approx(0.00002)
    assert len(observed["dispatched"]) == 1


def test_opaque_reasoning_is_private_even_after_a_stream_terminal():
    observed = actions.retain_private_reasoning()
    assert "opaque-secret-blob" not in str(observed["public"])
    assert "opaque-secret-blob" in str(observed["private"])
