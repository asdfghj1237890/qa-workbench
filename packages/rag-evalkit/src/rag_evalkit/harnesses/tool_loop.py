"""A provider-independent, bounded synchronous client-tool loop."""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, replace
from typing import Any

from ..contracts import ContractError, UnsupportedCapability
from ..runtime import (
    Generation,
    HarnessResult,
    Message,
    ModelAdapter,
    RequestLedger,
    RunLimits,
    RuntimeFailure,
    ToolCall,
    ToolSpec,
    TraceEvent,
    Usage,
    bounded_call,
    safe_evidence,
    tool_result_text,
    validate_arguments,
    with_request_ledger,
)


class ToolLoopHarness:
    def __init__(self, model: ModelAdapter):
        self.model = model

    def describe(self) -> dict[str, Any]:
        return {"harness": type(self).__name__, "harness_version": 1, "model": self.model.describe(),
                "settings": {"tool_dispatch": "sequential", "unknown_tool": "fail_closed",
                             "tool_error": "fail_closed", "schema": "portable_json_subset",
                             "cancellation": "bounded_wait_and_no_further_dispatch",
                             "inflight_callback": "may_continue; requires_cooperative_tool_handler"}}

    def run(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = (),
            handlers: Mapping[str, Callable[[Mapping[str, Any]], Any]] | None = None,
            limits: RunLimits | None = None, cancel: threading.Event | None = None) -> HarnessResult:
        limits = limits or RunLimits()
        handlers = dict(handlers or {})
        specifications = {tool.name: tool for tool in tools}
        if len(specifications) != len(tools):
            raise ContractError("tool names must be unique")
        if set(handlers) - set(specifications):
            raise ContractError("handlers require declared tool specifications")
        history = list(copy.deepcopy(tuple(messages)))
        if not history or not all(isinstance(message, Message) for message in history):
            raise ContractError("harness requires messages")
        if tools:
            self.model.capabilities.require("tools")
        deadline = time.monotonic() + limits.timeout_seconds
        traces = [TraceEvent("run_start", {"description": self.describe(), "limits": asdict(limits)})]
        usage = Usage(0, 0, 0.0)
        requests = turns = 0
        reserved_requests = 0
        request_ledger = RequestLedger()
        model_dispatches = [0]
        adapter_reported_requests = True
        model_inflight = False
        seen_call_ids: set[str] = set()
        answer, status = "", "incomplete"
        model_description = self.model.describe()
        live = model_description.get("evidence_kind") == "live_http"
        expected_requests = 2 if model_description.get("token_count") == "provider_endpoint" else 1
        contains_credentials = getattr(self.model, "contains_credentials", lambda value: False)
        sanitize = getattr(self.model, "sanitize_evidence", lambda value: copy.deepcopy(value))
        try:
            if contains_credentials([asdict(message) for message in history]):
                raise RuntimeFailure("credential_input")
            while turns < limits.max_turns:
                if cancel is not None and cancel.is_set():
                    raise RuntimeFailure("cancelled")
                if requests + expected_requests > limits.max_requests:
                    raise RuntimeFailure("request_limit")
                remaining_budget = None
                if limits.max_budget_usd is not None:
                    if usage.cost_usd is None:
                        raise RuntimeFailure("usage_unknown")
                    remaining_budget = limits.max_budget_usd - usage.cost_usd
                    if remaining_budget <= 0:
                        raise RuntimeFailure("budget_limit")
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    raise RuntimeFailure("timeout")
                call_limits = replace(limits, timeout_seconds=remaining_time,
                                      max_requests=limits.max_requests - requests,
                                      max_budget_usd=remaining_budget)
                turns += 1
                requests += expected_requests
                reserved_requests += expected_requests
                traces.append(TraceEvent("model_start", {"turn": turns, "requests_reserved": expected_requests}))
                model_inflight = True

                def invoke_model(history_snapshot=tuple(history), call_limits=call_limits):
                    model_dispatches[0] += 1
                    return with_request_ledger(
                        lambda: self.model.generate(history_snapshot, tools=tools, limits=call_limits, cancel=cancel),
                        request_ledger,
                    )

                try:
                    generation = bounded_call(invoke_model, deadline=deadline, cancel=cancel)
                except RuntimeFailure as exc:
                    actual_requests = exc.raw.get("api_requests")
                    if isinstance(actual_requests, int) and not isinstance(actual_requests, bool):
                        requests += actual_requests - expected_requests
                    raise
                if not isinstance(generation, Generation):
                    raise RuntimeFailure("invalid_generation")
                model_inflight = False
                if "api_requests" not in generation.usage.details:
                    adapter_reported_requests = False
                observed_requests = generation.usage.details.get("api_requests", expected_requests)
                if isinstance(observed_requests, bool) or not isinstance(observed_requests, int) or observed_requests < 1:
                    raise RuntimeFailure("invalid_request_accounting")
                requests += observed_requests - expected_requests
                usage = usage.plus(generation.usage)
                traces.extend(generation.traces)
                traces.append(TraceEvent("model_end", {"turn": turns, "finish_reason": generation.finish_reason,
                                                        "usage": asdict(generation.usage), "raw": generation.raw,
                                                        "resolved_model": generation.model,
                                                        "resolved_model_observed": bool(generation.model),
                                                        "requested_model": model_description.get("model", ""),
                                                        "provider": generation.provider}))
                if requests > limits.max_requests:
                    raise RuntimeFailure("request_limit")
                if generation.usage.details.get("hosted_limits_exceeded"):
                    raise RuntimeFailure("hosted_tool_limit_exceeded")
                if live and (usage.input_tokens is None or usage.output_tokens is None or usage.cost_usd is None):
                    raise RuntimeFailure("usage_unknown")
                if limits.max_budget_usd is not None:
                    if usage.cost_usd is None:
                        raise RuntimeFailure("usage_unknown")
                    if usage.cost_usd > limits.max_budget_usd:
                        raise RuntimeFailure("budget_exceeded")
                if generation.usage.input_tokens is not None and generation.usage.input_tokens > limits.max_input_tokens:
                    raise RuntimeFailure("input_token_limit_exceeded")
                if generation.usage.output_tokens is not None and generation.usage.output_tokens > limits.max_output_tokens:
                    raise RuntimeFailure("output_token_limit_exceeded")
                history.append(Message("assistant", generation.text, generation.tool_calls,
                                       provider_state=generation.provider_state))
                if generation.finish_reason != "tool_calls":
                    if generation.tool_calls:
                        raise RuntimeFailure("inconsistent_generation_tool_calls")
                    answer, status = generation.text, generation.finish_reason
                    break
                if not generation.tool_calls:
                    raise RuntimeFailure("empty_tool_calls")
                ids = [call.id for call in generation.tool_calls]
                if len(ids) != len(set(ids)) or seen_call_ids.intersection(ids):
                    raise RuntimeFailure("duplicate_tool_call_id")
                seen_call_ids.update(ids)
                # Do not dispatch side effects when no continuation request can run.
                if turns >= limits.max_turns or requests + expected_requests > limits.max_requests:
                    raise RuntimeFailure("turn_limit" if turns >= limits.max_turns else "request_limit")
                estimate_cost = getattr(self.model, "estimate_cost", None)
                if limits.max_budget_usd is not None and callable(estimate_cost):
                    reservation = estimate_cost(limits)
                    if reservation is None:
                        raise RuntimeFailure("usage_unknown")
                    if reservation > limits.max_budget_usd - usage.cost_usd:
                        raise RuntimeFailure("budget_limit")
                # Validate the complete batch before the first side effect.
                for call in generation.tool_calls:
                    if time.monotonic() >= deadline:
                        raise RuntimeFailure("timeout", raw={"operation_may_continue": False})
                    if cancel is not None and cancel.is_set():
                        raise RuntimeFailure("cancelled", raw={"operation_may_continue": False})
                    if call.name not in specifications or call.name not in handlers:
                        raise RuntimeFailure("unsupported_tool")
                    validate_arguments(call.arguments, specifications[call.name].input_schema)
                for call in generation.tool_calls:
                    traces.append(TraceEvent("tool_requested", {"id": call.id, "name": call.name, "arguments": call.arguments}))

                    def invoke_tool(call=call):
                        arguments = copy.deepcopy(dict(call.arguments))
                        if time.monotonic() >= deadline:
                            raise RuntimeFailure("timeout", raw={"operation_may_continue": False})
                        if cancel is not None and cancel.is_set():
                            raise RuntimeFailure("cancelled", raw={"operation_may_continue": False})
                        traces.append(TraceEvent("tool_start", {"id": call.id, "name": call.name}))
                        return handlers[call.name](arguments)

                    try:
                        result = bounded_call(invoke_tool, deadline=deadline, cancel=cancel)
                        if contains_credentials(result):
                            raise RuntimeFailure("tool_credential_echo")
                        content = tool_result_text(result)
                    except RuntimeFailure:
                        raise
                    except Exception as exc:
                        raise RuntimeFailure("tool_error", raw={"name": call.name, "error_type": type(exc).__name__}) from None
                    history.append(Message("tool", content, tool_call_id=call.id))
                    traces.append(TraceEvent("tool_result", {"id": call.id, "name": call.name, "result": safe_evidence(result)}))
            else:
                status = "turn_limit"
        except RuntimeFailure as exc:
            status = exc.code
            for event in exc.raw.get("stream_traces", ()):
                if isinstance(event, Mapping) and isinstance(event.get("kind"), str):
                    traces.append(TraceEvent(event["kind"], event.get("data", {})))
            traces.append(TraceEvent("runtime_error", {"code": exc.code, **exc.raw}))
            if requests and model_inflight:
                # A provider may have consumed tokens before losing the response.
                # Do not report a fabricated zero cost for unobserved requests.
                usage = Usage(None, None, None, {"incomplete_observation": True,
                                                "observed_prior_usage": asdict(usage),
                                                "partial_request_usage": exc.raw.get("partial_usage", {})})
        except UnsupportedCapability as exc:
            status = "unsupported"
            traces.append(TraceEvent("runtime_error", {"code": status, "error_type": type(exc).__name__}))
            if model_inflight:
                usage = Usage(None, None, None, {"incomplete_observation": True})
        except ContractError as exc:
            status = "contract_error"
            traces.append(TraceEvent("runtime_error", {"code": status, "error_type": type(exc).__name__}))
            if model_inflight:
                usage = Usage(None, None, None, {"incomplete_observation": True})
        except Exception as exc:
            status = "error"
            traces.append(TraceEvent("runtime_error", {"code": status, "error_type": type(exc).__name__}))
            if model_inflight:
                usage = Usage(None, None, None, {"incomplete_observation": True})
        if contains_credentials(status):
            status = "runtime_credential_echo"
        observed_requests = request_ledger.close()
        transport_observed = model_description.get("request_accounting") == "transport_observed"
        if transport_observed:
            requests = observed_requests["started"]
        elif not adapter_reported_requests or model_inflight:
            requests = model_dispatches[0]
        accounting = {"reserved": reserved_requests,
                      "observed_http_requests": observed_requests["started"] if transport_observed else None,
                      "completed_http_requests": observed_requests["completed"] if transport_observed else None,
                      "in_flight_http_requests": observed_requests["in_flight"] if transport_observed else None,
                      "observations_complete": transport_observed and not observed_requests["in_flight"],
                      "model_dispatches": model_dispatches[0],
                      "unit": "http_requests" if transport_observed else "adapter_reported_requests" if adapter_reported_requests and not model_inflight else "logical_model_calls"}
        traces.append(TraceEvent("run_end", {"status": status, "requests": requests, "turns": turns, "usage": asdict(usage),
                                            "request_accounting": accounting}))
        metadata = {"harness": self.describe(), "limits": asdict(limits),
                    "evidence_kind": model_description.get("evidence_kind", "unknown"),
                    "synthetic": model_description.get("synthetic", False),
                    "request_accounting": accounting,
                    "usage_complete": usage.input_tokens is not None and usage.output_tokens is not None and usage.cost_usd is not None}
        # Evidence is a typed clone. It is never reused as this run's mutable
        # protocol state; known credentials cannot escape through initial history
        # or a tool result even when a callback unexpectedly returns them.
        public_history = tuple(
            Message(message.role, sanitize(message.content),
                    tuple(ToolCall(sanitize(call.id), sanitize(call.name), sanitize(call.arguments)) for call in message.tool_calls),
                    tool_call_id=sanitize(message.tool_call_id), provider_items=tuple(sanitize(message.provider_items)),
                    provider_state=sanitize(message.provider_state))
            for message in history
        )
        public_traces = tuple(TraceEvent(event.kind, sanitize(event.data), event.timestamp) for event in traces)
        public_usage = Usage(usage.input_tokens, usage.output_tokens, usage.cost_usd, sanitize(usage.details))
        return HarnessResult(sanitize(answer), public_history, public_traces, public_usage, status, requests, turns, sanitize(metadata))
