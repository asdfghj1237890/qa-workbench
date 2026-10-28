"""Protocol-fixture compatibility tests; these do not claim live model quality."""

import pytest
from test_support.actions import runtime


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_provider_fixture_normalizes_answer_usage_and_resolved_identity(provider):
    observed = runtime.provider_answer(provider)
    result = observed["result"]
    assert result.status == "completed"
    assert result.answer == "Supported [source:doc-1]"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.usage.cost_usd == pytest.approx(0.00002)
    assert result.requests == 2
    assert result.metadata["synthetic"] is True
    assert result.metadata["evidence_kind"] == "protocol_fixture"
    ends = [event for event in result.traces if event.kind == "model_end"]
    assert ends[0].data["resolved_model"] == "fixture-model-resolved"
    assert observed["requests"][0]["body"]["model"] == "fixture-model"
    assert observed["requests"][1]["body"]["stream"] is False


def test_responses_protocol_preserves_function_ids_and_reasoning_continuation():
    observed = runtime.tool_journey("openai")
    assert observed["result"].status == "completed"
    assert observed["result"].requests == 4
    assert observed["result"].usage.cost_usd == pytest.approx(0.00004)
    assert observed["dispatched"] == [{"query": "evidence"}]
    first_body = observed["requests"][1]["body"]
    assert first_body["tools"][0]["type"] == "function"
    assert first_body["reasoning"] == {"effort": "low"}
    assert first_body["store"] is False
    assert first_body["include"] == ["reasoning.encrypted_content"]
    continuation = observed["requests"][3]["body"]["input"]
    calls = [item for item in continuation if item.get("type") == "function_call"]
    results = [item for item in continuation if item.get("type") == "function_call_output"]
    assert calls[0]["call_id"] == results[0]["call_id"] == "call_fixture"
    assert '"source_id":"doc-1"' in results[0]["output"]
    assert any(item.get("encrypted_content") == "fixture-encrypted" for item in continuation)
    assert observed["description"]["settings"] == {"reasoning_effort": "low"}


def test_messages_protocol_uses_tool_use_result_blocks_with_linked_ids():
    observed = runtime.tool_journey("anthropic")
    assert observed["result"].status == "completed"
    assert observed["dispatched"] == [{"query": "evidence"}]
    assert observed["requests"][1]["body"]["tools"][0]["input_schema"]["type"] == "object"
    continuation = observed["requests"][3]["body"]["messages"]
    assert [item["role"] for item in continuation] == ["user", "assistant", "user"]
    assert continuation[1]["content"][0]["type"] == "tool_use"
    assert continuation[2]["content"][0]["type"] == "tool_result"
    assert continuation[1]["content"][0]["id"] == continuation[2]["content"][0]["tool_use_id"] == "call_fixture"
    assert observed["requests"][1]["headers"]["anthropic-version"] == "2023-06-01"
    assert observed["description"]["token_count_accuracy"].startswith("provider_estimate")


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize(("variant", "status"), [("length", "length"), ("refusal", "refusal"), ("incomplete", "incomplete"), ("unknown_block", "unsupported")])
def test_noncompletion_is_not_reported_as_success(provider, variant, status):
    observed = runtime.provider_answer(provider, variant)
    assert observed["result"].status == status
    if status == "refusal":
        assert observed["result"].answer in {"", "Cannot comply"}
    if status == "unsupported":
        assert observed["result"].answer == ""


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("variant", ["missing_usage", "unknown_cache_price"])
def test_missing_metering_or_cache_pricing_keeps_cost_unknown(provider, variant):
    observed = runtime.provider_answer(provider, variant)
    assert observed["result"].status == "usage_unknown"
    assert observed["result"].usage.cost_usd is None


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_credentials_are_redacted_from_raw_response_trace_and_description(provider):
    observed = runtime.provider_answer(provider, "secret")
    assert "fixture-only-sensitive" not in str(observed)
    headers = observed["requests"][0]["headers"]
    key = "Authorization" if provider == "openai" else "x-api-key"
    assert headers[key] == "[REDACTED]"


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_input_count_is_a_separate_observed_request_before_generation(provider):
    observed = runtime.provider_answer(provider)
    assert len(observed["requests"]) == 2
    count_body = observed["requests"][0]["body"]
    assert "max_output_tokens" not in count_body
    assert "max_tokens" not in count_body
    ends = [event for event in observed["result"].traces if event.kind == "model_end"]
    assert ends[0].data["usage"]["details"]["input_tokens_counted"] == 10
    assert ends[0].data["usage"]["details"]["api_requests"] == 2


@pytest.mark.parametrize(("provider", "input_tokens", "cost"), [("openai", 10, 0.00001775), ("anthropic", 13, 0.00002075)])
def test_cache_accounting_respects_each_providers_input_token_semantics(provider, input_tokens, cost):
    result = runtime.cached_usage(provider)
    assert result.status == "completed"
    assert result.usage.input_tokens == input_tokens
    assert result.usage.cost_usd == pytest.approx(cost)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_provider_usage_over_output_cap_is_retained_as_a_failure(provider):
    observed = runtime.provider_answer(provider, "output_over_limit")
    assert observed["result"].status == "output_token_limit_exceeded"
    assert observed["result"].usage.output_tokens == 65


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_invalid_provider_usage_does_not_report_zero_cost(provider):
    observed = runtime.provider_answer(provider, "negative_usage")
    assert observed["result"].status == "provider_invalid_usage"
    assert observed["result"].usage.cost_usd is None


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("location", ["text", "tool", "model", "key"])
def test_known_provider_credential_echo_fails_closed_before_answer_or_tool_history(provider, location):
    observed = runtime.credential_echo(provider, location)
    result = observed["result"]
    assert result.status == "provider_credential_echo"
    assert result.answer == ""
    assert result.usage.cost_usd is None
    assert len(result.messages) == 2
    assert "fixture-only-sensitive" not in observed["serialized_result"]
    assert all(event.kind != "tool_start" for event in result.traces)


def test_evidence_redacts_credential_mapping_keys_without_overwriting_a_colliding_field():
    observed = runtime.safe_mapping_keys()
    assert "fixture-only-sensitive" not in str(observed)
    assert "sk-catalog-code-123456" not in str(observed)
    assert observed["[REDACTED_FIELD_0]"] == "preserved"
    assert len(observed) == 3


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_keylike_legitimate_arguments_reach_handler_and_continuation_unchanged(provider):
    observed = runtime.keylike_tool_journey(provider)
    assert observed["result"].status == "completed"
    assert observed["dispatched"] == [{"query": "sk-catalog-code-123456"}]
    body = observed["requests"][3]["body"]
    if provider == "openai":
        calls = [item for item in body["input"] if item.get("type") == "function_call"]
        assert "sk-catalog-code-123456" in calls[0]["arguments"]
    else:
        assert body["messages"][1]["content"][0]["input"] == {"query": "sk-catalog-code-123456"}
    assert sum(event.kind == "tool_start" for event in observed["result"].traces) == 1


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_returned_opaque_state_can_continue_on_the_owning_model_instance(provider):
    observed = runtime.state_continuation(provider)
    assert observed["error"] is None
    assert observed["followup"].finish_reason == "completed"
    state = observed["generation"].provider_state
    assert isinstance(state, str) and len(state) == 32
    assert observed["generation_record"]["provider_state"] == state
    assert "_provider_states" not in observed["generation_record"]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("mode", ["cross_instance", "cross_provider", "expired", "cleared", "external_items"])
def test_unknown_expired_or_external_protocol_state_never_silently_falls_back(provider, mode):
    observed = runtime.state_continuation(provider, mode)
    assert observed["error"]["code"] == ("external_provider_items_unsupported" if mode == "external_items" else "unknown_provider_state")
    assert len(observed["requests"]) == observed["requests_before"]
    assert observed["other_requests"] == []


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("entry", ["input_text", "input_tool_key", "tool_value", "tool_key"])
def test_initial_history_and_tool_results_cannot_leak_the_known_provider_key(provider, entry):
    observed = runtime.credential_entry(provider, entry)
    assert observed["result"].status == ("credential_input" if entry.startswith("input_") else "tool_credential_echo")
    assert observed["result"].answer == ""
    assert "fixture-only-sensitive" not in observed["serialized_result"]
    assert len(observed["requests"]) == (0 if entry.startswith("input_") else 2)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_credential_bearing_callback_error_code_is_normalized_before_public_result(provider):
    observed = runtime.credential_entry(provider, "tool_error")
    assert observed["result"].status == "runtime_credential_echo"
    assert "fixture-only-sensitive" not in observed["serialized_result"]
    assert len(observed["requests"]) == 2


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_legitimate_keylike_tool_result_survives_returned_history_continuation(provider):
    observed = runtime.credential_entry(provider, "tool_legitimate")
    assert observed["result"].status == "completed"
    assert observed["resumed"].status == "completed"
    messages = observed["result"].messages
    tool_results = [message for message in messages if message.role == "tool"]
    assert "sk-catalog-code-123456" in tool_results[0].content
    body = observed["requests"][5]["body"]
    if provider == "openai":
        outputs = [item for item in body["input"] if item.get("type") == "function_call_output"]
        assert "sk-catalog-code-123456" in outputs[0]["output"]
    else:
        assert "sk-catalog-code-123456" in body["messages"][2]["content"][0]["content"]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_plain_assistant_output_preserves_provider_annotations_and_phase_in_followup(provider):
    observed = runtime.plain_continuation(provider)
    assert observed["first"].status == observed["second"].status == "completed"
    assert observed["first"].messages[-1].provider_state
    body = observed["requests"][3]["body"]
    if provider == "openai":
        assistant = [item for item in body["input"] if item.get("role") == "assistant"][0]
        assert assistant["id"] == "message-phase-fixture"
        assert assistant["phase"] == "final_answer"
        assert assistant["content"][0]["annotations"][0]["title"] == "fixture source"
    else:
        assert body["messages"][1]["content"][0]["citations"][0]["document_title"] == "fixture source"
