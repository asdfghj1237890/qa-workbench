"""Small injectable HTTP boundary. No retries, redirects, or credential logging."""

from __future__ import annotations

import contextvars
import copy
import json
import math
import queue
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..contracts import Capabilities, ContractError, UnsupportedCapability
from ..runtime import (
    Generation,
    HostedToolSpec,
    ImageBlock,
    Message,
    RequestLedger,
    RunLimits,
    RuntimeFailure,
    StreamEvent,
    TextBlock,
    ToolSpec,
    TraceEvent,
    Usage,
    active_request_ledger,
    bounded_call,
    observed_http_request,
    safe_evidence,
    with_request_ledger,
)
from .streaming import CredentialSafeEmitter, StreamAccumulator, sse_events


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    body: Mapping[str, Any]


class HTTPTransport(Protocol):
    def __call__(self, url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float) -> HTTPResponse: ...


@dataclass(frozen=True)
class HTTPStreamResponse:
    status: int
    chunks: Iterable[bytes]
    close: Callable[[], None] = lambda: None


class HTTPStreamTransport(Protocol):
    def __call__(self, url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float) -> HTTPStreamResponse: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any) -> None:
        return None


def urllib_transport(url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float) -> HTTPResponse:
    request = Request(url, data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                      headers=dict(headers), method="POST")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            payload = response.read(4 * 1024 * 1024 + 1)
            if len(payload) > 4 * 1024 * 1024:
                raise RuntimeFailure("provider_response_too_large")
            parsed = json.loads(payload)
            if not isinstance(parsed, dict):
                raise RuntimeFailure("provider_invalid_json_object")
            return HTTPResponse(response.status, parsed)
    except HTTPError as exc:
        # Provider error text may echo credentials or prompts; retain status only.
        return HTTPResponse(exc.code, {"error": {"type": "http_error"}})
    except (URLError, OSError, ValueError) as exc:
        raise RuntimeFailure("provider_transport_error", raw={"error_type": type(exc).__name__}) from None


def urllib_stream_transport(url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float) -> HTTPStreamResponse:
    """Return immediately after headers, yielding bounded lines as they arrive."""
    request = Request(url, data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                      headers=dict(headers, Accept="text/event-stream"), method="POST")
    try:
        response = build_opener(_NoRedirect()).open(request, timeout=timeout)
    except HTTPError as exc:
        exc.close()
        return HTTPStreamResponse(exc.code, ())
    except (URLError, OSError, ValueError) as exc:
        raise RuntimeFailure("provider_transport_error", raw={"error_type": type(exc).__name__}) from None
    if response.headers.get_content_type() != "text/event-stream":
        response.close()
        raise RuntimeFailure("provider_invalid_stream_content_type")

    def chunks():
        while True:
            line = response.readline(65536)
            if not line:
                break
            yield line

    return HTTPStreamResponse(response.status, chunks(), response.close)


@dataclass(frozen=True)
class Pricing:
    """Caller-supplied USD rates per million tokens; no assumed current prices."""
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float | None = None
    cache_write_input_per_million: float | None = None

    def __post_init__(self) -> None:
        if self.input_per_million is None or self.output_per_million is None:
            raise ContractError("input and output prices must both be supplied")
        for value in asdict(self).values():
            if value is None:
                continue
            try:
                valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
            except OverflowError:
                valid = False
            if not valid:
                raise ContractError("prices must be finite and nonnegative")

    def upper_cost(self, limits: RunLimits) -> float:
        input_rate = max(value for key, value in asdict(self).items() if "input" in key and value is not None)
        return (limits.max_input_tokens * input_rate + limits.max_output_tokens * self.output_per_million) / 1_000_000

    def usage(self, input_tokens: int | None, output_tokens: int | None, *, cached: int = 0,
              cache_write: int = 0, cached_in_input: bool = True, details: Mapping[str, Any] | None = None) -> Usage:
        cost = None
        if input_tokens is not None and output_tokens is not None:
            if (not cached or self.cached_input_per_million is not None) and (not cache_write or self.cache_write_input_per_million is not None):
                ordinary = input_tokens - (cached + cache_write if cached_in_input else 0)
                if ordinary < 0:
                    raise RuntimeFailure("provider_invalid_usage")
                cost = (ordinary * self.input_per_million + output_tokens * self.output_per_million
                        + cached * (self.cached_input_per_million or 0)
                        + cache_write * (self.cache_write_input_per_million or 0)) / 1_000_000
        return Usage(input_tokens if cached_in_input or input_tokens is None else input_tokens + cached + cache_write,
                     output_tokens, cost, dict(details or {}))


class HTTPModel:
    provider = ""
    path = ""
    count_path = ""
    default_endpoint = ""
    allowed_settings: frozenset[str] = frozenset()
    capabilities = Capabilities(frozenset({"text", "tools", "usage", "token_count"}))

    def __init__(self, model: str, *, api_key: str = "", endpoint: str | None = None,
                 settings: Mapping[str, Any] | None = None, pricing: Pricing | None = None,
                 transport: HTTPTransport | None = None, evidence_kind: str = "live_http",
                 max_provider_states: int = 128, max_provider_state_bytes: int = 16 * 1024 * 1024,
                 streaming: bool = False, image_input: bool = False,
                 hosted_tools: Sequence[HostedToolSpec] = (), stream_transport: HTTPStreamTransport | None = None):
        if not isinstance(model, str) or not model:
            raise ContractError("model must be a nonempty explicit identifier")
        endpoint = (endpoint or self.default_endpoint).rstrip("/")
        url = urlsplit(endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ContractError("provider endpoint must be HTTPS without credentials, query or fragment")
        if evidence_kind not in {"live_http", "protocol_fixture"}:
            raise ContractError("evidence_kind must be live_http or protocol_fixture")
        if evidence_kind == "protocol_fixture" and transport is None:
            raise ContractError("protocol_fixture requires an injected transport")
        self.model = model
        self._api_key = api_key
        self.endpoint = endpoint
        self.settings = copy.deepcopy(dict(settings or {}))
        unsupported = set(self.settings) - self.allowed_settings
        if unsupported:
            raise UnsupportedCapability("unsupported model settings: " + ", ".join(sorted(unsupported)))
        json.dumps(self.settings, allow_nan=False)
        self.pricing = pricing
        self._transport = transport or urllib_transport
        if not isinstance(streaming, bool) or not isinstance(image_input, bool):
            raise ContractError("streaming and image_input must be boolean")
        if not all(isinstance(tool, HostedToolSpec) for tool in hosted_tools):
            raise ContractError("hosted_tools requires HostedToolSpec values")
        if hosted_tools and self.provider != "openai":
            raise UnsupportedCapability("hosted tools require OpenAI Responses")
        if len({tool.type for tool in hosted_tools}) != len(hosted_tools):
            raise ContractError("hosted tool types must be unique")
        self.streaming, self.image_input = streaming, image_input
        self.hosted_tools = tuple(hosted_tools)
        self._stream_transport = stream_transport or urllib_stream_transport
        if evidence_kind == "protocol_fixture" and (streaming or stream_transport is not None) and stream_transport is None:
            raise ContractError("streaming protocol_fixture requires an injected stream_transport")
        features = set(type(self).capabilities.features) | {"streaming"}
        if image_input:
            features.add("image_input")
        if self.provider == "openai":
            features.update({"hosted_web_search", "hosted_file_search"})
        self.capabilities = Capabilities(frozenset(features))
        self.evidence_kind = evidence_kind
        for value in (max_provider_states, max_provider_state_bytes):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractError("provider state retention bounds must be positive integers")
        self._max_provider_states = max_provider_states
        self._max_provider_state_bytes = max_provider_state_bytes
        self._provider_states: OrderedDict[str, tuple[list[dict[str, Any]], int]] = OrderedDict()
        self._provider_state_bytes = 0
        self._provider_state_lock = threading.Lock()

    def describe(self) -> dict[str, Any]:
        return {"adapter": type(self).__name__, "adapter_version": 2, "provider": self.provider, "model": safe_evidence(self.model, (self._api_key,)),
                "endpoint": safe_evidence(self.endpoint, (self._api_key,)), "settings": safe_evidence(self.settings, (self._api_key,)),
                "pricing": asdict(self.pricing) if self.pricing else None,
                "evidence_kind": self.evidence_kind, "synthetic": self.evidence_kind != "live_http",
                "capabilities": sorted(self.capabilities.features), "stream": self.streaming,
                "image_input": self.image_input, "model_capability_policy": "caller_declares_image_support; provider_validates_model",
                "hosted_tools": safe_evidence([asdict(tool) for tool in self.hosted_tools], (self._api_key,)),
                "stream_transport": "incremental_sse", "supported_modalities": ["text", "image"] if self.image_input else ["text"],
                "token_count": "provider_endpoint", "retries": 0, "store": False,
                "request_accounting": "transport_observed",
                "provider_state_retention": {"max_states": self._max_provider_states, "max_bytes": self._max_provider_state_bytes,
                                             "eviction": "oldest_first; expired_handle_fails_closed"},
                "budget_policy": "reserve_configured_input_cap_and_output_cap_before_generation",
                "budget_limit": "client_admission_guard; provider metering may differ from count endpoint"}

    def estimate_cost(self, limits: RunLimits) -> float | None:
        """Conservative admission reservation, distinct from observed billable cost."""
        if not self.pricing or any(tool.price_per_call_usd is None for tool in self.hosted_tools):
            return None
        # The API bounds the combined hosted calls, not each tool separately.
        # Reserve all allowed calls at the highest supplied service rate.
        hosted = sum(tool.max_calls for tool in self.hosted_tools) * max((tool.price_per_call_usd for tool in self.hosted_tools), default=0)
        return self.pricing.upper_cost(limits) + hosted

    def _remember_state(self, items: Sequence[Mapping[str, Any]]) -> str:
        """Raw protocol state stays instance-private; only an opaque ID leaves."""
        state = copy.deepcopy([dict(item) for item in items])
        size = len(json.dumps(state, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if size > self._max_provider_state_bytes:
            raise RuntimeFailure("provider_state_capacity")
        identifier = uuid.uuid4().hex
        with self._provider_state_lock:
            while self._provider_states and (len(self._provider_states) >= self._max_provider_states or self._provider_state_bytes + size > self._max_provider_state_bytes):
                _, (_, expired_size) = self._provider_states.popitem(last=False)
                self._provider_state_bytes -= expired_size
            self._provider_states[identifier] = (state, size)
            self._provider_state_bytes += size
        return identifier

    def _resolve_state(self, identifier: str) -> list[dict[str, Any]]:
        with self._provider_state_lock:
            stored = self._provider_states.get(identifier)
            if stored is None:
                raise RuntimeFailure("unknown_provider_state")
            return copy.deepcopy(stored[0])

    def clear_provider_states(self) -> None:
        """Explicit lifecycle boundary; previously returned handles then expire."""
        with self._provider_state_lock:
            self._provider_states.clear()
            self._provider_state_bytes = 0

    def _response_state(self, response: Mapping[str, Any], generation: Generation) -> str | None:
        return None

    def _credential_echo(self, value: Any) -> bool:
        if not self._api_key:
            return False
        if isinstance(value, str):
            return self._api_key in value
        if isinstance(value, Mapping):
            return any(self._credential_echo(key) or self._credential_echo(item) for key, item in value.items())
        if isinstance(value, (tuple, list)):
            return any(self._credential_echo(item) for item in value)
        return False

    def contains_credentials(self, value: Any) -> bool:
        """Check the configured credential without exposing its value."""
        return self._credential_echo(value)

    def sanitize_evidence(self, value: Any) -> Any:
        """Redact the known credential, preserving legitimate normalized values.

        Raw/trace evidence separately uses heuristic credential-field/pattern
        filtering. Normalized message content may contain legitimate `sk-` IDs;
        those must remain suitable for a later protocol continuation.
        """
        if isinstance(value, TextBlock):
            return TextBlock(self.sanitize_evidence(value.text))
        if isinstance(value, ImageBlock):
            return replace(value, url=self.sanitize_evidence(value.url), base64_data=self.sanitize_evidence(value.base64_data))
        if isinstance(value, (list, tuple)):
            return [self.sanitize_evidence(item) for item in value]
        return safe_evidence(value, (self._api_key,), redact_patterns=False, redact_fields=False)

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _body(self, messages: Sequence[Message], tools: Sequence[ToolSpec], limits: RunLimits) -> dict[str, Any]:
        raise NotImplementedError

    def _count_body(self, body: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _parse(self, response: Mapping[str, Any], details: dict[str, Any]) -> Generation:
        raise NotImplementedError

    def _observed_model(self, response: Mapping[str, Any]) -> str:
        """Return only provider-reported identity; requested aliases are separate."""
        value = response.get("model")
        if value is None or value == "":
            return ""
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise RuntimeFailure("provider_invalid_model_identity")
        if self._credential_echo(value):
            raise RuntimeFailure("provider_credential_echo")
        return value

    def _request(self, path: str, body: Mapping[str, Any], timeout: float) -> HTTPResponse:
        try:
            with observed_http_request():
                response = self._transport(self.endpoint + path, self._headers(), body, timeout)
        except RuntimeFailure as exc:
            if self._credential_echo(exc.code) or self._credential_echo(exc.raw):
                raise RuntimeFailure("provider_credential_echo", raw=safe_evidence(exc.raw, (self._api_key,))) from None
            raise
        except Exception as exc:
            raise RuntimeFailure("provider_transport_error", raw={"error_type": type(exc).__name__}) from None
        if not isinstance(response, HTTPResponse) or not isinstance(response.body, Mapping):
            raise RuntimeFailure("provider_invalid_transport_response")
        if not 200 <= response.status < 300:
            raise RuntimeFailure("provider_http_error", raw={"status": response.status, "path": path})
        return response

    def generate(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = (),
                 limits: RunLimits | None = None, cancel: threading.Event | None = None) -> Generation:
        return self._execute(messages, tools=tools, limits=limits or RunLimits(), cancel=cancel, force_stream=self.streaming)

    def stream(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = (),
               limits: RunLimits | None = None, cancel: threading.Event | None = None):
        """Yield normalized events while the HTTP response is still arriving.

        Closing the iterator prevents subsequent dispatch. An in-flight socket
        read can continue until its configured timeout; this is disclosed.
        """
        events: queue.Queue[Any] = queue.Queue()
        stopped = threading.Event()

        class CombinedCancel:
            def is_set(self):
                return stopped.is_set() or (cancel is not None and cancel.is_set())

        context = contextvars.copy_context()

        def run():
            try:
                result = self._execute(messages, tools=tools, limits=limits or RunLimits(), cancel=CombinedCancel(),
                                       force_stream=True, emit=events.put)
                events.put(StreamEvent("generation", {"finish_reason": result.finish_reason}, result))
            except Exception as exc:
                events.put(exc)
            finally:
                events.put(None)

        worker = threading.Thread(target=lambda: context.run(run), daemon=True)
        worker.start()
        try:
            while True:
                event = events.get()
                if event is None:
                    return
                if isinstance(event, Exception):
                    raise event
                yield event
        finally:
            stopped.set()

    def _execute(self, messages, *, tools, limits, cancel, force_stream, emit=None):
        limits = limits or RunLimits()
        inherited_ledger = active_request_ledger()
        ledger = inherited_ledger or RequestLedger()
        started_before = ledger.snapshot()["started"]
        observation: dict[str, Any] = {}
        try:
            return bounded_call(lambda: with_request_ledger(lambda: self._generate(messages, tools=tools, limits=limits, cancel=cancel,
                                                                                  force_stream=force_stream, emit=emit, observation=observation), ledger),
                                deadline=time.monotonic() + limits.timeout_seconds, cancel=cancel)
        except RuntimeFailure as exc:
            snapshot = ledger.snapshot()
            raise RuntimeFailure(exc.code, raw={**observation, **exc.raw, "api_requests": snapshot["started"] - started_before,
                                                "in_flight_http_requests": snapshot["in_flight"],
                                                "request_observation_complete": snapshot["in_flight"] == 0}) from None
        except UnsupportedCapability:
            raise RuntimeFailure("unsupported", raw={"api_requests": ledger.snapshot()["started"] - started_before}) from None
        finally:
            if inherited_ledger is None:
                ledger.close()

    def _generate(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec],
                  limits: RunLimits | None, cancel: threading.Event | None, force_stream: bool = False,
                  emit=None, observation=None) -> Generation:
        limits = limits or RunLimits()
        deadline = time.monotonic() + limits.timeout_seconds
        if cancel is not None and cancel.is_set():
            raise RuntimeFailure("cancelled")
        if self.evidence_kind == "live_http":
            if not limits.live_opt_in:
                raise RuntimeFailure("live_opt_in_required")
            if not self._api_key:
                raise RuntimeFailure("provider_api_key_required")
            if self.pricing is None or limits.max_budget_usd is None:
                raise RuntimeFailure("live_pricing_and_budget_required")
            if any(tool.price_per_call_usd is None for tool in self.hosted_tools):
                raise RuntimeFailure("hosted_tool_pricing_required")
        if limits.max_requests < 2:
            raise RuntimeFailure("request_limit")
        reserve = self.estimate_cost(limits)
        if limits.max_budget_usd is not None and (reserve is None or reserve > limits.max_budget_usd):
            raise RuntimeFailure("budget_limit")
        if not all(isinstance(message, Message) for message in messages):
            raise ContractError("model requires Message values")
        if any(isinstance(block, ImageBlock) for message in messages if not isinstance(message.content, str) for block in message.content):
            self.capabilities.require("image_input")
        body = self._body(tuple(messages), tuple(tools), limits)
        body["stream"] = force_stream
        if force_stream and self.evidence_kind == "protocol_fixture" and self._stream_transport is urllib_stream_transport:
            raise RuntimeFailure("fixture_stream_transport_required")
        if self._credential_echo(body):
            raise RuntimeFailure("credential_input")
        count = self._request(self.count_path, self._count_body(body), limits.timeout_seconds)
        if self._credential_echo(count.body):
            raise RuntimeFailure("provider_credential_echo", raw={"token_count": safe_evidence(count.body, (self._api_key,))})
        counted = count.body.get("input_tokens")
        if isinstance(counted, bool) or not isinstance(counted, int) or counted < 0:
            raise RuntimeFailure("provider_invalid_token_count", raw={"api_requests": 1})
        if counted > limits.max_input_tokens:
            raise RuntimeFailure("input_token_limit", raw={"api_requests": 1, "input_tokens_counted": counted})
        if cancel is not None and cancel.is_set():
            raise RuntimeFailure("cancelled", raw={"api_requests": 1})
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeFailure("timeout", raw={"api_requests": 1})
        if observation is not None:
            observation.update(input_tokens_counted=counted, reserved_cost_usd=reserve, evidence_kind=self.evidence_kind)
        stream_traces: list[TraceEvent] = []
        if force_stream:
            response = self._request_stream(body, remaining, limits, cancel, stream_traces, emit, observation)
        else:
            response = self._request(self.path, body, remaining)
        if self._credential_echo(response.body):
            raise RuntimeFailure("provider_credential_echo", raw={"response": safe_evidence(response.body, (self._api_key,)),
                                                                  "token_count": safe_evidence(count.body, (self._api_key,))})
        details = {"api_requests": 2, "input_tokens_counted": counted, "reserved_cost_usd": reserve,
                   "evidence_kind": self.evidence_kind}
        try:
            generation = self._parse(response.body, details)
        except UnsupportedCapability:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, RuntimeFailure):
                raise
            raise RuntimeFailure("provider_invalid_response", raw={"api_requests": 2, "error_type": type(exc).__name__}) from None
        if self._credential_echo({"text": generation.text, "model": generation.model,
                                  "tool_calls": [asdict(call) for call in generation.tool_calls]}):
            raise RuntimeFailure("provider_credential_echo", raw={"response": safe_evidence(response.body, (self._api_key,))})
        raw = {"request": safe_evidence(body, (self._api_key,)),
               "response": safe_evidence(response.body, (self._api_key,)),
               "token_count": safe_evidence(count.body, (self._api_key,)),
               "evidence_kind": self.evidence_kind,
               "continuation_items": safe_evidence(generation.raw.get("continuation_items", ()), (self._api_key,))}
        provider_state = self._response_state(response.body, generation)
        return Generation(generation.text, generation.tool_calls, generation.finish_reason, generation.usage,
                          raw, self.provider, generation.model, provider_state,
                          generation.hosted_calls, generation.citations, tuple(stream_traces) + generation.traces)

    def _request_stream(self, body, timeout, limits, cancel, traces, emit, observation):
        deadline = time.monotonic() + timeout

        def check():
            if cancel is not None and cancel.is_set():
                raise RuntimeFailure("cancelled", raw={"operation_may_continue": False})
            if time.monotonic() >= deadline:
                raise RuntimeFailure("timeout", raw={"operation_may_continue": False})

        def progress(event):
            if self._credential_echo(event.data):
                raise RuntimeFailure("provider_credential_echo")
            traces.append(TraceEvent(event.kind, event.data))
            if emit:
                emit(event)

        guarded_progress = CredentialSafeEmitter(self._api_key, progress)
        accumulator = StreamAccumulator(self.provider, guarded_progress)
        response = None
        try:
            with observed_http_request():
                response = self._stream_transport(self.endpoint + self.path, self._headers(), body, timeout)
                if not isinstance(response, HTTPStreamResponse):
                    raise RuntimeFailure("provider_invalid_transport_response")
                if not 200 <= response.status < 300:
                    raise RuntimeFailure("provider_http_error", raw={"status": response.status, "path": self.path})
                for event in sse_events(response.chunks, limits, check):
                    if self._credential_echo(event):
                        raise RuntimeFailure("provider_credential_echo")
                    accumulator.feed(event)
                    if observation is not None:
                        observation.update(accumulator.failure_evidence())
                        observation["stream_traces"] = [{"kind": trace.kind, "data": trace.data} for trace in traces]
                    if accumulator.stopped:
                        break
                final_response = accumulator.finish()
                guarded_progress.finish()
                return HTTPResponse(response.status, final_response)
        except RuntimeFailure as exc:
            evidence = {**accumulator.failure_evidence(), **exc.raw,
                        "stream_traces": [{"kind": trace.kind, "data": trace.data} for trace in traces]}
            raise RuntimeFailure(exc.code, raw=safe_evidence(evidence, (self._api_key,))) from None
        except Exception as exc:
            raise RuntimeFailure("provider_transport_error", raw={**accumulator.failure_evidence(), "error_type": type(exc).__name__}) from None
        finally:
            if response is not None:
                response.close()

    def _usage(self, body: Mapping[str, Any], details: Mapping[str, Any], *, anthropic: bool = False) -> Usage:
        usage = body.get("usage") or {}
        if not isinstance(usage, Mapping):
            raise RuntimeFailure("provider_invalid_usage")
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
        input_details = usage.get("input_tokens_details") or {}
        cached = usage.get("cache_read_input_tokens", 0) if anthropic else input_details.get("cached_tokens", 0)
        writes = usage.get("cache_creation_input_tokens", 0) if anthropic else input_details.get("cache_write_tokens", 0)
        for value in (cached, writes):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeFailure("provider_invalid_usage")
        evidence = dict(details, raw_usage=safe_evidence(usage, (self._api_key,)), cached_input_tokens=cached, cache_write_input_tokens=writes)
        if self.pricing:
            return self.pricing.usage(input_tokens, output_tokens, cached=cached, cache_write=writes,
                                      cached_in_input=not anthropic, details=evidence)
        return Usage(input_tokens if not anthropic or input_tokens is None else input_tokens + cached + writes,
                     output_tokens, None, evidence)
