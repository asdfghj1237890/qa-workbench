"""Actual runtime wiring; protocol fixtures are synthetic, never live LLM proof.

Contract: Responses function_call/function_call_output and usage are anchored to
https://developers.openai.com/api/docs/guides/function-calling and token-counting.
Messages tool_use/tool_result are anchored to
https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls.
All HTTP is intercepted by the injected transport, with no socket or API key.
"""

import copy
import json
import threading
import time
from dataclasses import asdict
from unittest.mock import patch

from rag_evalkit.contracts import Capabilities
from rag_evalkit.harnesses import SingleTurnHarness, ToolLoopHarness
from rag_evalkit.models import (
    AnthropicMessagesModel,
    HTTPResponse,
    OpenAIResponsesModel,
    Pricing,
    ReplayModel,
)
from rag_evalkit.runtime import (
    Generation,
    Message,
    RunLimits,
    RuntimeFailure,
    ToolCall,
    ToolSpec,
    Usage,
    safe_evidence,
)

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}},
           "required": ["query"], "additionalProperties": False}


def _tool():
    return ToolSpec("lookup", "Find supporting source text", _SCHEMA)


def _response(provider, variant="completed"):
    if provider == "openai":
        response = {"id": "resp_fixture", "model": "fixture-model-resolved", "status": "completed",
                    "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Supported [source:doc-1]"}]}],
                    "usage": {"input_tokens": 10, "output_tokens": 5, "input_tokens_details": {"cached_tokens": 0}}}
        if variant in {"tool", "malformed_tool", "bad_arguments", "unknown_tool", "credential_tool", "legitimate_keylike_tool"}:
            query = 3 if variant == "bad_arguments" else "fixture-only-sensitive" if variant == "credential_tool" else "sk-catalog-code-123456" if variant == "legitimate_keylike_tool" else "evidence"
            arguments = "{" if variant == "malformed_tool" else json.dumps({"query": query})
            response["output"] = [{"type": "reasoning", "id": "rs_fixture", "summary": [], "encrypted_content": "fixture-encrypted"},
                                  {"type": "function_call", "id": "fc_fixture", "call_id": "call_fixture", "name": "unknown" if variant == "unknown_tool" else "lookup", "arguments": arguments}]
        elif variant == "length":
            response.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        elif variant == "refusal":
            response["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot comply"}]
        elif variant == "incomplete":
            response["status"] = "in_progress"
        elif variant == "unknown_block":
            response["output"] = [{"type": "web_search_call"}]
    else:
        response = {"id": "msg_fixture", "type": "message", "model": "fixture-model-resolved", "role": "assistant",
                    "content": [{"type": "text", "text": "Supported [source:doc-1]"}], "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5}}
        if variant in {"tool", "malformed_tool", "bad_arguments", "unknown_tool", "credential_tool", "legitimate_keylike_tool"}:
            query = 3 if variant == "bad_arguments" else "fixture-only-sensitive" if variant == "credential_tool" else "sk-catalog-code-123456" if variant == "legitimate_keylike_tool" else "evidence"
            arguments = [] if variant == "malformed_tool" else {"query": query}
            response.update(content=[{"type": "tool_use", "id": "call_fixture", "name": "unknown" if variant == "unknown_tool" else "lookup", "input": arguments}], stop_reason="tool_use")
        elif variant in {"length", "refusal", "incomplete"}:
            response["stop_reason"] = {"length": "max_tokens", "refusal": "refusal", "incomplete": "pause_turn"}[variant]
            if variant == "refusal":
                response["content"] = [{"type": "text", "text": "Cannot comply"}]
        elif variant == "unknown_block":
            response["content"] = [{"type": "server_tool_use"}]
    if variant == "missing_usage":
        response.pop("usage")
    if variant == "unknown_cache_price":
        if provider == "openai":
            response["usage"]["input_tokens_details"]["cached_tokens"] = 3
        else:
            response["usage"]["cache_read_input_tokens"] = 3
    if variant == "negative_usage":
        response["usage"]["input_tokens"] = -1
    if variant == "output_over_limit":
        response["usage"]["output_tokens"] = 65
    if variant == "secret":
        response["debug"] = {"api_key": "fixture-only-sensitive", "echo": "fixture-only-sensitive"}
    if variant == "credential_text":
        if provider == "openai":
            response["output"][0]["content"][0]["text"] = "echo fixture-only-sensitive"
        else:
            response["content"][0]["text"] = "echo fixture-only-sensitive"
    if variant == "credential_model":
        response["model"] = "fixture-only-sensitive"
    if variant == "credential_key":
        response["debug"] = {"fixture-only-sensitive": "echoed-as-property", "[REDACTED_FIELD_0]": "preserved collision field"}
    if variant == "phase":
        if provider == "openai":
            response["output"][0].update(id="message-phase-fixture", phase="final_answer")
            response["output"][0]["content"][0]["annotations"] = [{"type": "url_citation", "url": "https://example.invalid/source", "title": "fixture source", "start_index": 0, "end_index": 9}]
        else:
            response["content"][0]["citations"] = [{"type": "char_location", "cited_text": "Supported", "document_index": 0, "document_title": "fixture source", "start_char_index": 0, "end_char_index": 9}]
    return response


class ProtocolTransport:
    def __init__(self, provider, variants=("completed",), *, token_count=10, status=200):
        self.provider, self.variants = provider, list(variants)
        self.token_count, self.status = token_count, status
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": safe_evidence(headers), "body": copy.deepcopy(body), "timeout": timeout})
        if url.endswith("/input_tokens") or url.endswith("/count_tokens"):
            return HTTPResponse(200, {"input_tokens": self.token_count})
        return HTTPResponse(self.status, _response(self.provider, self.variants.pop(0)))


def _model(provider, transport, *, live=False, pricing=True, settings=None):
    kind = OpenAIResponsesModel if provider == "openai" else AnthropicMessagesModel
    return kind("fixture-model", api_key="fixture-only-sensitive", transport=transport,
                evidence_kind="live_http" if live else "protocol_fixture", settings=settings,
                pricing=Pricing(1, 2) if pricing else None)


def observe_provider(provider, variant="completed", *, live=False):
    transport = ProtocolTransport(provider, (variant,))
    model = _model(provider, transport, live=live)
    limits = RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1, live_opt_in=live)
    result = SingleTurnHarness(model).run([Message("system", "Use sources"), Message("user", "Question")], limits=limits)
    return {"result": result, "requests": transport.calls, "description": model.describe()}


def observe_tool_journey(provider):
    transport = ProtocolTransport(provider, ("tool", "completed"))
    model = _model(provider, transport, settings={"reasoning_effort": "low"} if provider == "openai" else {})
    dispatched = []

    def lookup(arguments):
        dispatched.append(copy.deepcopy(arguments))
        return {"source_id": "doc-1", "text": "Supporting evidence"}

    result = ToolLoopHarness(model).run([Message("user", "Find evidence")], tools=[_tool()], handlers={"lookup": lookup},
                                       limits=RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1))
    return {"result": result, "requests": transport.calls, "dispatched": dispatched, "description": model.describe()}


def observe_guard(provider, guard):
    transport = ProtocolTransport(provider, ("tool", "completed"), token_count=2000 if guard == "input_limit" else 10)
    live = guard in {"opt_in", "pricing", "budget", "live_missing_usage"}
    if guard == "live_missing_usage":
        transport.variants = ["missing_usage"]
    model = _model(provider, transport, live=live, pricing=guard != "pricing")
    settings = {"max_input_tokens": 1000, "max_output_tokens": 64,
                "live_opt_in": guard != "opt_in", "max_budget_usd": 0.00001 if guard == "budget" else 0.1}
    if guard == "pricing":
        settings["max_budget_usd"] = None
    if guard == "requests":
        settings["max_requests"] = 2
    if guard == "turns":
        settings["max_turns"] = 1
    if guard == "http_error":
        transport.status = 429
    dispatched = []
    result = ToolLoopHarness(model).run([Message("user", "Find evidence")], tools=[_tool()],
                                       handlers={"lookup": lambda args: dispatched.append(args)}, limits=RunLimits(**settings))
    return {"result": result, "requests": transport.calls, "dispatched": dispatched}


def observe_tool_failure(provider, failure):
    transport = ProtocolTransport(provider, (failure if failure in {"unknown_tool", "bad_arguments", "malformed_tool"} else "tool", "completed"))
    dispatched = []
    cancel = threading.Event()
    handler_started = threading.Event()
    handler_completed = threading.Event()
    release_handler = threading.Event()

    def lookup(arguments):
        dispatched.append(arguments)
        handler_started.set()
        try:
            if failure == "tool_error":
                raise ValueError("fixture-only-sensitive")
            if failure == "cancel":
                cancel.set()
            if failure in {"timeout", "cancel"}:
                release_handler.wait(5)
            return {"source_id": "doc-1"}
        finally:
            handler_completed.set()

    start = time.monotonic()
    result = ToolLoopHarness(_model(provider, transport)).run([Message("user", "Find evidence")], tools=[_tool()],
        handlers={"lookup": lookup}, cancel=cancel,
        limits=RunLimits(timeout_seconds=0.5 if failure == "timeout" else 2, max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1))
    observed = {"result": result, "requests": transport.calls, "dispatched": dispatched, "elapsed": time.monotonic() - start,
                "handler_started_at_return": handler_started.is_set(), "handler_completed_at_return": handler_completed.is_set()}
    release_handler.set()
    if handler_started.is_set():
        handler_completed.wait(1)
    return observed


def observe_replay(*, tools=False, cancel_before=False):
    generations = [Generation("", (ToolCall("replay-call", "lookup", {"query": "evidence"}),), "tool_calls"), "Synthetic answer"] if tools else ["Synthetic answer"]
    model = ReplayModel(generations)
    cancel = threading.Event()
    if cancel_before:
        cancel.set()
    result = ToolLoopHarness(model).run([Message("user", "Question")], cancel=cancel,
        tools=[_tool()] if tools else [], handlers={"lookup": lambda args: "source:doc-1"} if tools else {})
    return {"result": result, "description": model.describe()}


def observe_unknown_cost():
    class UnmeteredModel:
        capabilities = Capabilities(frozenset({"text"}))

        def describe(self):
            return {"model": "unmetered", "evidence_kind": "external_adapter", "synthetic": False}

        def generate(self, messages, **kwargs):
            return Generation("Answer", usage=Usage())

    return ToolLoopHarness(UnmeteredModel()).run([Message("user", "Question")], limits=RunLimits(max_budget_usd=1))


def observe_configuration_failure(case):
    try:
        if case == "stream":
            OpenAIResponsesModel("fixture", settings={"stream": True})
        elif case == "endpoint_credentials":
            OpenAIResponsesModel("fixture", endpoint="https://credential:secret@example.test/v1")
        elif case == "endpoint_query":
            OpenAIResponsesModel("fixture", endpoint="https://example.test/v1?api_key=secret")
        elif case == "schema":
            ToolSpec("lookup", "Unsupported schema", {"type": "object", "oneOf": []})
        elif case == "single_turn_tools":
            SingleTurnHarness(ReplayModel(["answer"])).run([Message("user", "q")], tools=[_tool()])
        elif case == "unknown_setting":
            AnthropicMessagesModel("fixture", settings={"reasoning_effort": "low"})
        elif case == "fixture_without_transport":
            OpenAIResponsesModel("fixture", evidence_kind="protocol_fixture")
        elif case == "nan_price":
            Pricing(float("nan"), 1)
        elif case == "nan_timeout":
            RunLimits(timeout_seconds=float("nan"))
        elif case == "negative_usage":
            Usage(-1, 2)
    except Exception as exc:
        return {"error_type": type(exc).__name__, "message": str(exc)}
    return {"error_type": None}


def observe_usage_sum():
    return {"unknown": Usage(None, 3, None).plus(Usage(2, 4, 0.1)),
            "known": Usage(2, 3, 0.2).plus(Usage(4, 5, 0.1))}


def observe_cached_usage(provider):
    transport = ProtocolTransport(provider, ("unknown_cache_price",))
    kind = OpenAIResponsesModel if provider == "openai" else AnthropicMessagesModel
    model = kind("fixture", transport=transport, evidence_kind="protocol_fixture", pricing=Pricing(1, 2, 0.25, 3))
    return SingleTurnHarness(model).run([Message("user", "Question")],
        limits=RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1))


def observe_tool_batch():
    model = ReplayModel([Generation("", (ToolCall("valid", "lookup", {"query": "evidence"}),
                                           ToolCall("invalid", "unknown", {})), "tool_calls"), "answer"])
    dispatched = []
    result = ToolLoopHarness(model).run([Message("user", "Question")], tools=[_tool()],
        handlers={"lookup": lambda args: dispatched.append(args)})
    return {"result": result, "dispatched": dispatched}


def observe_insufficient_continuation_budget(provider):
    transport = ProtocolTransport(provider, ("tool", "completed"))
    dispatched = []
    result = ToolLoopHarness(_model(provider, transport)).run([Message("user", "Question")], tools=[_tool()],
        handlers={"lookup": lambda args: dispatched.append(args)},
        limits=RunLimits(max_input_tokens=10, max_output_tokens=5, max_budget_usd=0.00003))
    return {"result": result, "requests": transport.calls, "dispatched": dispatched}


def observe_credential_echo(provider, location):
    observed = observe_provider(provider, "credential_" + location)
    observed["serialized_result"] = json.dumps(asdict(observed["result"]), ensure_ascii=False)
    return observed


def observe_safe_mapping_keys():
    return safe_evidence({"fixture-only-sensitive": "value", "[REDACTED_FIELD_0]": "preserved",
                          "sk-catalog-code-123456": "pattern key"}, ("fixture-only-sensitive",))


def observe_state_continuation(provider, mode="same"):
    variants = ("legitimate_keylike_tool", "legitimate_keylike_tool", "completed") if mode == "expired" else ("legitimate_keylike_tool", "completed")
    transport = ProtocolTransport(provider, variants)
    kind = OpenAIResponsesModel if provider == "openai" else AnthropicMessagesModel
    model = kind("fixture-model", api_key="fixture-only-sensitive", transport=transport,
                 evidence_kind="protocol_fixture", pricing=Pricing(1, 2), max_provider_states=1 if mode == "expired" else 128)
    limits = RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1)
    initial = [Message("user", "Question")]
    generation = model.generate(initial, tools=[_tool()], limits=limits)
    history = initial + [Message("assistant", generation.text, generation.tool_calls, provider_state=generation.provider_state),
                         Message("tool", "Supporting evidence", tool_call_id="call_fixture")]
    target = model
    other_transport = None
    if mode in {"cross_instance", "cross_provider"}:
        target_kind = kind if mode == "cross_instance" else AnthropicMessagesModel if provider == "openai" else OpenAIResponsesModel
        other_transport = ProtocolTransport(provider, ("completed",))
        target = target_kind("fixture-model", api_key="fixture-only-sensitive", transport=other_transport,
                             evidence_kind="protocol_fixture", pricing=Pricing(1, 2))
    if mode == "expired":
        model.generate(initial, tools=[_tool()], limits=limits)
    if mode == "cleared":
        model.clear_provider_states()
    if mode == "external_items":
        history[1] = Message("assistant", generation.text, generation.tool_calls,
                             provider_items=tuple(generation.raw["response"]["output" if provider == "openai" else "content"]))
    before = len(transport.calls)
    error = None
    followup = None
    try:
        followup = target.generate(history, tools=[_tool()], limits=limits)
    except RuntimeFailure as exc:
        error = {"code": exc.code, "raw": exc.raw}
    return {"generation": generation, "generation_record": asdict(generation), "followup": followup,
            "requests": transport.calls, "requests_before": before, "other_requests": other_transport.calls if other_transport else [],
            "error": error, "description": model.describe()}


def observe_keylike_tool_journey(provider):
    transport = ProtocolTransport(provider, ("legitimate_keylike_tool", "completed"))
    dispatched = []
    result = ToolLoopHarness(_model(provider, transport)).run([Message("user", "Question")], tools=[_tool()],
        handlers={"lookup": lambda args: dispatched.append(copy.deepcopy(args))},
        limits=RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1))
    return {"result": result, "requests": transport.calls, "dispatched": dispatched}


def observe_slow_count(repetitions=20):
    snapshots = []
    for _ in range(repetitions):
        calls = []
        started, release, finished = threading.Event(), threading.Event(), threading.Event()

        def transport(url, headers, body, timeout, calls=calls, started=started, release=release, finished=finished):
            calls.append(url)
            started.set()
            # Contract: runtime.RequestLedger must report an HTTP request that
            # is held in flight when the bounded caller returns. Release only
            # after capturing that snapshot; scheduler speed is irrelevant.
            try:
                release.wait()
                return HTTPResponse(200, {"input_tokens": 1})
            finally:
                finished.set()

        model = OpenAIResponsesModel("fixture-model", transport=transport, evidence_kind="protocol_fixture", pricing=Pricing(1, 1))
        result = SingleTurnHarness(model).run([Message("user", "Question")], limits=RunLimits(timeout_seconds=0.01, max_budget_usd=0.1))
        snapshots.append({"result": result, "actual_requests_at_return": len(calls), "calls": calls})
        release.set()
        if started.is_set():
            if not finished.wait(2):
                raise AssertionError("held count callback did not finish after release")
    return [{"result": item["result"], "actual_requests_at_return": item["actual_requests_at_return"],
             "actual_requests_after_cleanup": len(item["calls"])} for item in snapshots]


def observe_expired_tool_dispatch():
    import rag_evalkit.harnesses.tool_loop as harness_module

    actual_bounded_call = harness_module.bounded_call
    invocations = []
    dispatched = []

    def before_dispatch(callback, *, deadline, cancel=None):
        invocations.append("bounded")
        if len(invocations) == 2:
            raise RuntimeFailure("timeout", raw={"operation_may_continue": False})
        return actual_bounded_call(callback, deadline=deadline, cancel=cancel)

    model = ReplayModel([Generation("", (ToolCall("call", "lookup", {"query": "evidence"}),), "tool_calls"), "answer"])
    with patch.object(harness_module, "bounded_call", before_dispatch):
        result = ToolLoopHarness(model).run([Message("user", "Question")], tools=[_tool()],
            handlers={"lookup": lambda args: dispatched.append(args)})
    return {"result": result, "dispatched": dispatched}


def observe_custom_request_accounting():
    class ConstantModel:
        capabilities = Capabilities(frozenset({"text"}))

        def describe(self):
            return {"model": "constant", "evidence_kind": "synthetic_fixture", "synthetic": True}

        def generate(self, messages, **kwargs):
            return Generation("answer", usage=Usage(1, 1, 0))

    return SingleTurnHarness(ConstantModel()).run([Message("user", "Question")])


def observe_enum_type_mismatch():
    from rag_evalkit.runtime import validate_arguments

    schema = {"type": "object", "properties": {"flag": {"type": "boolean", "enum": [1]}}, "required": ["flag"]}
    tool = ToolSpec("lookup", "Type-sensitive enum", schema)
    try:
        validate_arguments({"flag": True}, tool.input_schema)
    except Exception as exc:
        return {"error_type": type(exc).__name__}
    return {"error_type": None}


def observe_message_state_validation(role):
    try:
        Message(role, "Question", tool_call_id="call" if role == "tool" else None, provider_state="opaque")
    except Exception as exc:
        return {"error_type": type(exc).__name__}
    return {"error_type": None}


def observe_credential_entry(provider, entry):
    variants = ("tool", "completed", "completed") if entry.startswith("tool_") else ("completed",)
    transport = ProtocolTransport(provider, variants)
    model = _model(provider, transport)
    initial = [Message("user", "Question")]
    if entry == "input_text":
        initial = [Message("user", "Question fixture-only-sensitive")]
    if entry == "input_tool_key":
        initial.append(Message("assistant", "", (ToolCall("call", "lookup", {"fixture-only-sensitive": "value"}),)))
    output = {"text": "fixture-only-sensitive"} if entry == "tool_value" else {"fixture-only-sensitive": "value"} if entry == "tool_key" else {"text": "sk-catalog-code-123456"}

    def lookup(args):
        if entry == "tool_error":
            raise RuntimeFailure("fixture-only-sensitive")
        return copy.deepcopy(output)

    result = ToolLoopHarness(model).run(initial, tools=[_tool()], handlers={"lookup": lookup},
        limits=RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1))
    resumed = None
    if entry == "tool_legitimate":
        resumed = SingleTurnHarness(model).run([*result.messages, Message("user", "Follow-up")],
            limits=RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1))
    return {"result": result, "serialized_result": json.dumps(asdict(result), ensure_ascii=False),
            "requests": transport.calls, "resumed": resumed}


def observe_plain_continuation(provider):
    transport = ProtocolTransport(provider, ("phase", "completed"))
    model = _model(provider, transport)
    first = SingleTurnHarness(model).run([Message("user", "Question")],
        limits=RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1))
    second = SingleTurnHarness(model).run([*first.messages, Message("user", "Follow-up")],
        limits=RunLimits(max_input_tokens=1000, max_output_tokens=64, max_budget_usd=0.1))
    return {"first": first, "second": second, "requests": transport.calls}
