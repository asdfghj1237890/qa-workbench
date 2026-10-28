"""Behavioral contracts exercised by installed, offline external SDKs."""

import pytest
from test_support.actions import integrations as actions


def test_importing_bridges_does_not_import_optional_frameworks():
    seen = actions.framework_dependency_isolation()
    assert seen["returncode"] == 0, seen["stderr"]
    assert seen["imported_frameworks"] == ""


@pytest.mark.parametrize("framework", ["langchain", "llamaindex"])
def test_real_rag_engines_preserve_exact_source_text_and_parent_lineage(framework):
    seen = actions.framework_answer(framework)
    result = seen["result"]
    assert result["metadata"]["status"] == "completed", result["traces"]
    assert result["answer"]
    assert result["evidence"][0]["document_id"] == "document-9"
    assert result["evidence"][0]["chunk_id"] == "chunk-9"
    assert result["evidence"][0]["source_id"] == "source-9"
    assert result["evidence"][0]["text"] == "The reference material says the observatory opens at nine."
    assert result["evidence"][0]["raw_score"] is None
    assert result["usage"]["cost_usd"] is None
    assert seen["leaked_secret"] is False
    assert result["metadata"]["latency_seconds"] >= 0


def test_langchain_model_callback_preserves_reported_usage_without_inventing_cost():
    seen = actions.framework_answer("langchain", "usage")
    assert seen["result"]["usage"]["input_tokens"] == 7
    assert seen["result"]["usage"]["output_tokens"] == 3
    assert seen["result"]["usage"]["cost_usd"] is None


def test_llamaindex_preserves_actual_node_scores():
    seen = actions.framework_answer("llamaindex", "score")
    assert seen["result"]["evidence"][0]["score"] == 0.75


@pytest.mark.parametrize("framework", ["langchain", "llamaindex"])
@pytest.mark.parametrize("scenario,status", [("error", "error"), ("timeout", "timeout"), ("cancel", "cancelled"),
    ("cancel_inflight", "cancelled"), ("budget", "budget_unsupported")])
def test_rag_failures_never_become_completed_answers(framework, scenario, status):
    seen = actions.framework_answer(framework, scenario)
    assert seen["result"]["metadata"]["status"] == status
    assert seen["result"]["answer"] == ""
    assert seen["leaked_secret"] is False


def test_actual_sdk_agent_and_runner_produce_accounted_normalized_messages():
    seen = actions.sdk_agent_run()
    result = seen["result"]
    assert result["status"] == "completed", result["traces"]
    assert result["answer"] == "The observatory opens at nine. [source:source-9]"
    assert result["messages"][-1]["role"] == "assistant"
    assert result["usage"]["input_tokens"] == 7
    assert result["usage"]["output_tokens"] == 3
    assert result["usage"]["cost_usd"] is None
    assert seen["dispatch_count"] == 1
    assert seen["leaked_state"] is False


@pytest.mark.parametrize("scenario", ["tool", "portable_tool"])
def test_sdk_dispatches_native_and_portable_tools_before_final_answer(scenario):
    seen = actions.sdk_agent_run(scenario)
    result = seen["result"]
    assert result["status"] == "completed", result["traces"]
    assert seen["tool_inputs"] == ["observatory"]
    assert seen["dispatch_count"] == 2
    assert result["usage"]["input_tokens"] == 14
    assert any(message["role"] == "tool" for message in result["messages"])
    assert any(event["kind"] == "tool_start" for event in result["traces"])


@pytest.mark.parametrize("scenario,status,dispatches", [("cancel", "cancelled", 0), ("budget", "budget_unsupported", 0),
    ("live_guard", "live_opt_in_required", 0), ("timeout", "timeout", 1), ("error", "error", 1),
    ("cancel_inflight", "cancelled", 1),
    ("refusal", "refusal", 1), ("unsupported_hosted", "unsupported_sdk_item", 1),
    ("portable_tool_error", "tool_error", 1),
    ("empty_output", "incomplete", 1),
    ("unknown_tool", "error", 1), ("tool_error", "error", 1), ("request_limit", "request_limit", 1),
    ("turn_limit", "turn_limit", 1)])
def test_sdk_guards_and_errors_stop_further_dispatch(scenario, status, dispatches):
    seen = actions.sdk_agent_run(scenario)
    assert seen["result"]["status"] == status, seen["result"]["traces"]
    assert seen["dispatch_count"] == dispatches
    assert seen["result"]["answer"] == ""
    assert seen["leaked_secret"] is False


@pytest.mark.parametrize("scenario", ["unknown_usage", "transport_unknown_usage"])
def test_sdk_unknown_usage_remains_unknown(scenario):
    seen = actions.sdk_agent_run(scenario)
    assert seen["result"]["status"] == "completed"
    assert seen["result"]["usage"]["input_tokens"] is None
    assert seen["result"]["usage"]["output_tokens"] is None
    assert seen["result"]["usage"]["cost_usd"] is None


def test_sdk_credentials_and_opaque_provider_state_do_not_escape_evidence():
    seen = actions.sdk_agent_run("secret")
    assert seen["result"]["status"] == "completed"
    assert seen["leaked_secret"] is False
    assert seen["leaked_state"] is False


def test_sdk_runner_can_orchestrate_the_portable_provider_adapter_under_a_real_cost_cap():
    seen = actions.sdk_agent_run("bridge_budget")
    result = seen["result"]
    assert result["status"] == "completed", result["traces"]
    assert seen["tool_inputs"] == ["observatory"]
    assert seen["dispatch_count"] == 0
    assert seen["transport_calls"] == ["input_tokens", "responses", "input_tokens", "responses"]
    assert result["usage"]["input_tokens"] == 14
    assert result["usage"]["cost_usd"] == 0.02
    assert result["metadata"]["request_accounting"]["portable_model_requests"] == 4
    assert result["metadata"]["usage_complete"] is True
    assert seen["leaked_secret"] is False


def test_sdk_portable_bridge_reserves_the_second_turn_against_remaining_budget():
    seen = actions.sdk_agent_run("bridge_budget_exhausted")
    assert seen["result"]["status"] == "budget_limit", seen["result"]["traces"]
    assert seen["transport_calls"] == ["input_tokens", "responses"]
    assert seen["tool_inputs"] == []
    assert seen["result"]["answer"] == ""
    assert not any(event["kind"] == "tool_start" for event in seen["result"]["traces"])


def test_sdk_bridge_retains_the_originating_models_private_reasoning_continuation():
    seen = actions.sdk_agent_run("bridge_reasoning")
    assert seen["result"]["status"] == "completed", seen["result"]["traces"]
    assert seen["continuation_types"] == ["message", "reasoning", "function_call", "function_call_output"]
    assert seen["tool_inputs"] == ["observatory"]
    assert seen["leaked_state"] is False


@pytest.mark.parametrize("scenario,status", [("bridge_request_exhausted", "request_limit"), ("bridge_turn_exhausted", "turn_limit")])
def test_sdk_bridge_checks_continuation_request_and_turn_capacity_before_tool_effects(scenario, status):
    seen = actions.sdk_agent_run(scenario)
    assert seen["result"]["status"] == status, seen["result"]["traces"]
    assert seen["transport_calls"] == ["input_tokens", "responses"]
    assert seen["tool_inputs"] == []
    assert not any(event["kind"] == "tool_start" for event in seen["result"]["traces"])


def test_sdk_explicitly_reported_zero_tokens_survive_normalization():
    seen = actions.sdk_agent_run("reported_zero_usage")
    assert seen["result"]["status"] == "completed"
    assert seen["result"]["usage"]["input_tokens"] == 0
    assert seen["result"]["usage"]["output_tokens"] == 0


@pytest.mark.parametrize("scenario,status", [("empty", "incomplete"), ("refusal", "refusal")])
def test_langchain_empty_or_refused_messages_are_not_completed_answers(scenario, status):
    seen = actions.framework_answer("langchain", scenario)
    assert seen["result"]["metadata"]["status"] == status
    assert seen["result"]["answer"] == ""


@pytest.mark.parametrize("framework", ["langchain", "llamaindex"])
@pytest.mark.parametrize("factor", ["prompt", "tools"])
def test_example_framework_factories_reject_factors_they_cannot_apply(framework, factor):
    seen = actions.example_rejects_unsupported_factor(framework, factor)
    assert seen["error"] == "UnsupportedCapability"
    assert "fixed prompt" in seen["message"]
