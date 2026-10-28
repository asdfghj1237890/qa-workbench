"""Real HTTP transport evidence; actual model services require explicit opt-in."""

import pytest
from test_support.actions import embeddings


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_arbitrary_unicode_text_is_sent_through_real_http_and_results_match_input_order(backend):
    observed = embeddings.embed_texts(backend)
    assert observed["error"] is None
    assert observed["result"]["vectors"][0] == (3, 4)
    assert observed["result"]["vectors"][1][0] == observed["first_float32"]
    assert observed["result"]["usage"]["input_tokens"] == 9
    assert observed["result"]["usage"]["cost_usd"] == pytest.approx(0.000009)
    assert observed["usage"]["requests"] == 1
    assert observed["requests"][0]["credential_received"] is True
    assert observed["physical"] == "loopback_http_protocol_fixture"
    input_field = "input" if backend == "openai" else "inputs"
    assert observed["requests"][0]["body"][input_field] == [
        "A newly supplied English passage.", "任意的新文字，可直接批次嵌入。", "A third unseen passage."]
    assert "e4bbbbe6848f" in observed["requests"][0]["wire_utf8_hex"]


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_batch_size_bounds_dispatch_without_changing_result_count(backend):
    observed = embeddings.embed_texts(backend, batch_size=2)
    assert observed["error"] is None
    assert len(observed["result"]["vectors"]) == 3
    assert observed["result"]["usage"]["details"]["api_requests"] == 2
    assert observed["usage"]["requests"] == 2
    input_field = "input" if backend == "openai" else "inputs"
    assert [request["body"][input_field] for request in observed["requests"]] == [
        ["A newly supplied English passage.", "任意的新文字，可直接批次嵌入。"], ["A third unseen passage."]]


@pytest.mark.parametrize("backend", ["openai", "tei"])
@pytest.mark.parametrize("inherited", [False, True])
@pytest.mark.parametrize("scenario,code", [("timeout", "timeout"), ("cancel", "cancelled")])
def test_no_first_request_can_escape_after_body_construction_outlives_call(backend, inherited, scenario, code):
    observed = embeddings.delayed_body_dispatch(backend, inherited=inherited, scenario=scenario)
    assert observed["body_entered"] is True
    assert observed["error"] == code
    assert observed["requests_at_return"] == observed["requests_after_return"] == 0
    assert observed["error_raw"]["api_requests"] == 0
    assert observed["usage"]["requests"] == 0
    assert observed["parent_before_reuse"]["started"] == 0
    assert observed["parent_after_reuse"]["started"] == observed["parent_after_reuse"]["completed"] == 1


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_call_timeout_cannot_relax_configured_lifetime_timeout(backend):
    observed = embeddings.timeout_override(backend)
    assert observed["error"] == "timeout"
    assert observed["elapsed"] < 0.3
    assert observed["requests"] <= 1


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_successful_child_ledger_forwards_observed_requests_without_closing_parent(backend):
    observed = embeddings.delayed_body_dispatch(backend, inherited=True, scenario="success")
    assert observed["error"] is None
    assert observed["requests_at_return"] == observed["requests_after_return"] == 1
    assert observed["parent_before_reuse"]["started"] == observed["parent_before_reuse"]["completed"] == 1
    assert observed["parent_after_reuse"]["started"] == observed["parent_after_reuse"]["completed"] == 2


@pytest.mark.parametrize("scenario", ["input_tokens", "large_input"])
def test_metered_input_that_can_exceed_remaining_token_cap_is_rejected_before_http(scenario):
    observed = embeddings.embed_texts("openai", scenario)
    assert observed["error"] == "embedding_input_token_bound_exceeded"
    assert observed["requests"] == []
    assert observed["usage"]["requests"] == 0


def test_unknown_compatible_provider_requires_explicit_token_upper_bound_contract():
    observed = embeddings.embed_texts("openai", "no_token_bound")
    assert observed["error"] == "embedding_token_bound_required"
    assert observed["requests"] == []


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_explicit_normalization_returns_unit_float32_vectors(backend):
    observed = embeddings.embed_texts(backend, normalize=True)
    assert observed["result"]["vectors"][0] == pytest.approx((0.6, 0.8))
    assert observed["description"]["normalization"] == "client_l2_after_float32"
    assert observed["description"]["model_version"] == "declared-model-v1"
    assert len(observed["description"]["target_sha256"]) == 64


def test_tei_sends_explicit_truncation_normalization_and_prompt_policy():
    observed = embeddings.embed_texts("tei")
    body = observed["requests"][0]["body"]
    assert body["truncate"] is False
    assert body["normalize"] is False
    assert body["prompt_name"] == "query"


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_single_and_many_embedding_interfaces_share_the_same_real_adapter(backend):
    observed = embeddings.embed_texts(backend, "single_and_many")
    assert observed["error"] is None
    assert observed["result"]["single"] == observed["result"]["many"][0]
    assert len(observed["result"]["many"]) == 2
    assert observed["usage"]["input_tokens"] == 9


@pytest.mark.parametrize("backend", ["openai", "tei"])
@pytest.mark.parametrize("scenario", ["empty_batch", "blank_text", "nontext", "string_batch"])
def test_invalid_text_batches_are_rejected_before_dispatch(backend, scenario):
    observed = embeddings.embed_texts(backend, scenario)
    assert observed["error"] is not None
    assert observed["requests"] == []


def test_a_resolved_model_change_cannot_silently_mix_embedding_spaces():
    observed = embeddings.embed_texts("openai", "model_change", batch_size=1)
    assert observed["error"] == "embedding_resolved_model_changed"
    assert observed["usage"]["input_tokens"] == 6
    assert len(observed["requests"]) == 2


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_failure_after_a_successful_chunk_preserves_observed_tokens_and_unknown_failed_cost(backend):
    observed = embeddings.embed_texts(backend, "partial_http_error", batch_size=1)
    assert observed["error"] == "embedding_http_error"
    assert len(observed["requests"]) == 2
    assert observed["error_raw"]["completed_inputs"] == 1
    assert observed["usage"]["input_tokens"] is None
    assert observed["usage"]["details"]["observed_input_tokens"] == 3
    assert observed["usage"]["cost_usd"] is None


@pytest.mark.parametrize("scenario,code", [
    ("count", "embedding_result_count_mismatch"), ("dimensions", "embedding_dimensions_mismatch"),
    ("zero", "embedding_invalid_float32"), ("nan", "embedding_invalid_vector"),
    ("infinity", "embedding_invalid_vector"), ("bool", "embedding_invalid_vector"),
    ("overflow", "embedding_invalid_float32"), ("underflow", "embedding_invalid_float32"),
    ("usage_negative", "embedding_invalid_usage"), ("invalid_json", "embedding_transport_error"),
])
@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_invalid_service_observations_fail_closed(backend, scenario, code):
    observed = embeddings.embed_texts(backend, scenario)
    assert observed["error"] == code
    assert observed["result"] is None
    assert observed["usage"]["requests"] == 1


@pytest.mark.parametrize("scenario", ["duplicate_index", "invalid_index", "missing_index"])
def test_openai_rejects_ambiguous_or_missing_input_indices(scenario):
    observed = embeddings.embed_texts("openai", scenario)
    assert observed["error"] == "embedding_invalid_index"


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_unpriced_self_hosted_embeddings_keep_unknown_cost(backend):
    observed = embeddings.embed_texts(backend, "usage_unknown", unpriced=True)
    assert observed["error"] is None
    assert observed["result"]["usage"]["input_tokens"] is None
    assert observed["result"]["usage"]["cost_usd"] is None
    assert observed["usage"]["cost_usd"] is None
    assert observed["usage"]["unknown_cost"] is True


def test_metered_service_without_usage_retains_unknown_cost_and_fails_budget_accounting():
    observed = embeddings.embed_texts("openai", "usage_unknown")
    assert observed["error"] == "embedding_usage_unknown"
    assert observed["usage"]["cost_usd"] is None


@pytest.mark.parametrize("backend", ["openai", "tei"])
@pytest.mark.parametrize("scenario,code", [("request_limit", "request_limit"), ("input_bytes", "embedding_input_bytes_limit"),
    ("budget", "budget_limit"), ("cancel_before", "cancelled"), ("close", "embedding_closed")])
def test_admission_guards_prevent_any_http_request(backend, scenario, code):
    observed = embeddings.embed_texts(backend, scenario)
    assert observed["error"] == code
    assert observed["requests"] == []
    assert observed["usage"]["requests"] == 0


def test_metered_embedding_requires_explicit_opt_in():
    observed = embeddings.embed_texts("openai", "no_opt_in")
    assert observed["error"] == "live_embedding_opt_in_required"
    assert observed["requests"] == []


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_observed_token_overrun_is_preserved_as_a_failure(backend):
    observed = embeddings.embed_texts(backend, "provider_token_overrun")
    assert observed["error"] == "embedding_input_token_limit_exceeded"
    assert observed["usage"]["input_tokens"] == 3
    assert observed["usage"]["cost_usd"] == pytest.approx(0.000003)


@pytest.mark.parametrize("backend", ["openai", "tei"])
@pytest.mark.parametrize("scenario,code", [("timeout", "timeout"), ("cancel_in_flight", "cancelled")])
def test_timeout_and_cancellation_bound_wait_and_preserve_uncertain_in_flight_work(backend, scenario, code):
    observed = embeddings.embed_texts(backend, scenario, batch_size=1)
    assert observed["error"] == code
    assert observed["elapsed"] < 0.3
    assert len(observed["requests"]) <= 1
    assert observed["error_raw"]["api_requests"] in {0, 1}
    assert observed["error_raw"]["api_requests"] >= len(observed["requests"])
    if scenario == "cancel_in_flight":
        assert len(observed["requests"]) == 1
    if observed["error_raw"]["api_requests"]:
        assert observed["usage"]["cost_usd"] is None
        assert observed["error_raw"]["operation_may_continue"] is True
        assert observed["error_raw"]["usage_observation_complete"] is False
    else:
        assert observed["usage"]["requests"] == 0
        assert observed["usage"]["cost_usd"] == 0


@pytest.mark.parametrize("backend", ["openai", "tei"])
@pytest.mark.parametrize("scenario", ["redirect", "http_error"])
def test_errors_do_not_leak_credentials_or_follow_authenticated_redirects(backend, scenario):
    observed = embeddings.embed_texts(backend, scenario)
    assert observed["error"] == "embedding_http_error"
    assert observed["redirect_hits"] == []
    assert observed["usage"]["unknown_cost"] is True
    assert "fixture-only-sensitive" not in str(observed)


def test_credential_echo_in_resolved_model_fails_closed():
    observed = embeddings.embed_texts("openai", "model_echo")
    assert observed["error"] == "embedding_credential_echo"
    assert "fixture-only-sensitive" not in str(observed)


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_request_limits_apply_across_ingest_and_query_calls(backend):
    observed = embeddings.embed_texts(backend, "lifetime_requests")
    assert observed["error"] == "request_limit"
    assert len(observed["requests"]) == 1
    assert observed["usage"]["requests"] == 1
    assert observed["usage"]["input_tokens"] == 3


@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_token_limits_apply_across_multiple_calls_and_retain_overrun(backend):
    observed = embeddings.embed_texts(backend, "lifetime_tokens")
    assert observed["error"] == "embedding_input_token_limit_exceeded"
    assert observed["usage"]["requests"] == 2
    assert observed["usage"]["input_tokens"] == 6


@pytest.mark.parametrize("case", ["http_remote", "endpoint_credentials", "endpoint_query", "endpoint_fragment",
    "endpoint_whitespace", "endpoint_port", "model_version", "timeout", "normalize", "batch_size", "header_injection"])
def test_invalid_or_unsafe_configuration_is_rejected_without_network(case):
    assert embeddings.rejected_configuration(case) is not None


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["openai", "tei"])
def test_explicit_actual_service_returns_distinct_vectors_with_recorded_provenance(backend):
    if not embeddings.live_service_available(backend):
        pytest.skip("requires EVALKIT_LIVE_EMBEDDINGS=1 and explicit endpoint/model/version/dimensions and paid budget where applicable")
    observed = embeddings.embed_live_texts(backend)
    vectors = observed["result"]["vectors"]
    assert len(vectors) == 2
    assert vectors[0] != vectors[1]
    assert len(vectors[0]) == observed["description"]["dimensions"]
    assert sum(value * value for value in vectors[0]) == pytest.approx(1, abs=1e-5)
    assert observed["usage"]["requests"] == 1
