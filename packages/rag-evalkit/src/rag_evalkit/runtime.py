"""Provider-independent runtime contracts and bounded execution primitives.

Timeout/cancellation stops waiting and prevents subsequent dispatch. Python cannot
kill an arbitrary in-process callback: timeout traces explicitly retain that fact.
Tool handlers must therefore be trusted and cooperate with cancellation for any
side effects; untrusted tools need their own process/container boundary.
"""

from __future__ import annotations

import base64
import contextvars
import copy
import json
import math
import queue
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    Protocol,
    TypeVar,
    runtime_checkable,
)
from urllib.parse import urlsplit

from .contracts import Capabilities, ContractError, UnsupportedCapability


class RuntimeFailure(RuntimeError):
    def __init__(self, code: str, *, raw: Mapping[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.raw = safe_evidence(raw or {})


def safe_evidence(value: Any, secrets: Sequence[str] = (), *, redact_patterns: bool = True, redact_fields: bool = True) -> Any:
    """Detach JSON evidence and remove credential fields and known secrets."""
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            original_key = str(key)
            clean_key = safe_evidence(original_key, secrets, redact_patterns=redact_patterns, redact_fields=redact_fields)
            if clean_key != original_key:
                clean_key = "[REDACTED_FIELD_" + str(index) + "]"
                while clean_key in output or clean_key in value:
                    clean_key += "_"
            output[clean_key] = "[REDACTED]" if redact_fields and (re.search(
                r"authorization|api.?key|access.?token|password|secret|cookie|encrypted_content|base64_data", original_key, re.I
            ) or (original_key == "data" and value.get("type") == "base64")) else safe_evidence(item, secrets, redact_patterns=redact_patterns, redact_fields=redact_fields)
        return output
    if isinstance(value, (tuple, list)):
        return [safe_evidence(item, secrets, redact_patterns=redact_patterns, redact_fields=redact_fields) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        if redact_fields and value.startswith("data:image/"):
            return "[IMAGE_DATA_REDACTED]"
        return re.sub(r"\b(?:sk|sk-ant)-[A-Za-z0-9_-]{8,}", "[REDACTED]", value) if redact_patterns else value
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return {"type": type(value).__name__}


def _count(value: int | None, name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise ContractError(name + " must be a nonnegative integer or unknown")


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not isinstance(self.name, str) or not self.id or not self.name or not isinstance(self.arguments, Mapping):
            raise ContractError("tool call requires id, name and object arguments")
        try:
            json.dumps(dict(self.arguments), allow_nan=False)
        except (TypeError, ValueError):
            raise ContractError("tool arguments must be finite JSON values") from None
        object.__setattr__(self, "arguments", copy.deepcopy(dict(self.arguments)))


@dataclass(frozen=True)
class TextBlock:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ContractError("text block requires text")


@dataclass(frozen=True)
class ImageBlock:
    """Portable image input; no implicit local file reads or network fetches."""
    url: str | None = None
    base64_data: str | None = None
    media_type: str | None = None
    detail: str = "auto"

    def __post_init__(self) -> None:
        if (self.url is None) == (self.base64_data is None):
            raise ContractError("image requires exactly one URL or base64 payload")
        if self.detail not in {"auto", "low", "high"}:
            raise UnsupportedCapability("unsupported image detail")
        if self.url is not None:
            if not isinstance(self.url, str):
                raise ContractError("image URL must be text")
            parsed = urlsplit(self.url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ContractError("image URL must be HTTPS without credentials")
        else:
            if self.media_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
                raise UnsupportedCapability("unsupported image media type")
            if not isinstance(self.base64_data, str) or not self.base64_data:
                raise ContractError("image base64 payload must be nonempty text")
            try:
                base64.b64decode(self.base64_data, validate=True)
            except (ValueError, TypeError):
                raise ContractError("invalid image base64 payload") from None


@dataclass(frozen=True)
class Message:
    role: str
    content: str | tuple[TextBlock | ImageBlock, ...] = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    provider_items: tuple[Mapping[str, Any], ...] = ()
    provider_state: str | None = None

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ContractError("message requires a supported role")
        if not isinstance(self.content, str):
            if not isinstance(self.content, (tuple, list)) or not all(isinstance(block, (TextBlock, ImageBlock)) for block in self.content):
                raise UnsupportedCapability("message content supports only text and image blocks")
            if self.role != "user" and any(isinstance(block, ImageBlock) for block in self.content):
                raise UnsupportedCapability("image input requires a user message")
            if self.role == "tool":
                raise UnsupportedCapability("tool results require text content")
            object.__setattr__(self, "content", tuple(self.content))
        if self.role == "tool" and not self.tool_call_id:
            raise ContractError("tool results require tool_call_id")
        if self.tool_calls and self.role != "assistant":
            raise ContractError("only assistant messages may contain tool calls")
        if self.provider_state is not None and (self.role != "assistant" or not isinstance(self.provider_state, str) or not self.provider_state):
            raise ContractError("provider_state requires an assistant message and a nonempty opaque string")
        if self.provider_items and self.role != "assistant":
            raise ContractError("provider_items are only valid on assistant messages")
        if self.provider_items and self.provider_state:
            raise ContractError("provider_items cannot be combined with provider_state")
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "provider_items", tuple(copy.deepcopy(self.provider_items)))


def validate_arguments(value: Any, schema: Mapping[str, Any]) -> None:
    """Validate the supported portable JSON-schema subset; reject other keywords."""
    supported = {"type", "properties", "required", "additionalProperties", "items", "enum", "description", "title"}
    if set(schema) - supported:
        raise UnsupportedCapability("unsupported tool schema keywords: " + ", ".join(sorted(set(schema) - supported)))
    kind = schema.get("type")
    types = {"object": Mapping, "array": (list, tuple), "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}
    if kind not in types:
        raise UnsupportedCapability("tool schema requires a supported explicit type")
    if not isinstance(value, types[kind]) or (kind in {"integer", "number"} and isinstance(value, bool)):
        raise ContractError("tool argument does not match schema type " + kind)
    if kind == "number" and not math.isfinite(value):
        raise ContractError("tool numbers must be finite")
    if "enum" in schema and not any(_json_equal(value, candidate) for candidate in schema["enum"]):
        raise ContractError("tool argument is outside enum")
    if kind == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise ContractError("schema properties must be an object")
        if set(schema.get("required", ())) - set(value):
            raise ContractError("missing required tool argument")
        extra = set(value) - set(properties)
        if schema.get("additionalProperties", True) is False and extra:
            raise ContractError("unknown tool argument")
        if isinstance(schema.get("additionalProperties"), Mapping):
            raise UnsupportedCapability("typed additionalProperties is not supported")
        for key in set(value) & set(properties):
            validate_arguments(value[key], properties[key])
    elif kind == "array":
        if "items" not in schema:
            raise UnsupportedCapability("portable array schema requires items")
        for item in value:
            validate_arguments(item, schema["items"])


def validate_tool_schema(schema: Mapping[str, Any]) -> None:
    supported = {"type", "properties", "required", "additionalProperties", "items", "enum", "description", "title"}
    if not isinstance(schema, Mapping) or set(schema) - supported:
        raise UnsupportedCapability("unsupported tool schema keywords")
    if schema.get("type") not in {"object", "array", "string", "integer", "number", "boolean", "null"}:
        raise UnsupportedCapability("tool schema requires a supported explicit type")
    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, Mapping) or not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            raise ContractError("invalid tool schema properties or required")
        if set(required) - set(properties):
            raise ContractError("required tool fields must be declared")
        if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
            raise UnsupportedCapability("only boolean additionalProperties is supported")
        for child in properties.values():
            validate_tool_schema(child)
    if schema.get("type") == "array":
        if "items" not in schema:
            raise UnsupportedCapability("portable array schema requires items")
        validate_tool_schema(schema["items"])


def _json_equal(left: Any, right: Any) -> bool:
    """JSON booleans are distinct from numbers, unlike Python equality."""
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(_json_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right, strict=True))
    return left == right


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.name):
            raise ContractError("portable tool names must be 1-64 letters, digits, underscores or hyphens")
        validate_tool_schema(self.input_schema)
        if self.input_schema.get("type") != "object":
            raise UnsupportedCapability("tool parameters must use an object schema")
        object.__setattr__(self, "input_schema", copy.deepcopy(dict(self.input_schema)))


@dataclass(frozen=True)
class HostedToolSpec:
    """Provider hosted tool, never dispatched to a client handler.

    Rates and a per-response call bound are explicit caller assertions. A rate
    covers the complete hosted call (including non-token service charges).
    """
    type: str
    config: Mapping[str, Any] = field(default_factory=dict)
    price_per_call_usd: float | None = None
    max_calls: int = 1

    def __post_init__(self) -> None:
        if self.type not in {"web_search", "file_search"}:
            raise UnsupportedCapability("unsupported hosted tool")
        if not isinstance(self.config, Mapping):
            raise ContractError("hosted tool config must be an object")
        allowed = {"web_search": {"search_context_size", "user_location", "filters", "external_web_access"},
                   "file_search": {"vector_store_ids", "max_num_results", "ranking_options", "filters"}}
        if set(self.config) - allowed[self.type]:
            raise UnsupportedCapability("unsupported hosted tool config")
        if self.type == "file_search":
            stores = self.config.get("vector_store_ids")
            if not isinstance(stores, (list, tuple)) or not stores or not all(isinstance(x, str) and x for x in stores):
                raise ContractError("file_search requires vector_store_ids")
        if isinstance(self.max_calls, bool) or not isinstance(self.max_calls, int) or self.max_calls < 1:
            raise ContractError("hosted max_calls must be a positive integer")
        if self.price_per_call_usd is not None and (isinstance(self.price_per_call_usd, bool) or not isinstance(self.price_per_call_usd, (int, float)) or not math.isfinite(self.price_per_call_usd) or self.price_per_call_usd < 0):
            raise ContractError("hosted price must be finite and nonnegative or unknown")
        try:
            json.dumps(dict(self.config), allow_nan=False)
        except (TypeError, ValueError):
            raise ContractError("hosted config must be finite JSON") from None
        object.__setattr__(self, "config", copy.deepcopy(dict(self.config)))


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _count(self.input_tokens, "input_tokens")
        _count(self.output_tokens, "output_tokens")
        if self.cost_usd is not None and (isinstance(self.cost_usd, bool) or not math.isfinite(self.cost_usd) or self.cost_usd < 0):
            raise ContractError("cost must be finite and nonnegative or unknown")

    def plus(self, other: Usage) -> Usage:
        def add(left: Any, right: Any) -> Any:
            return None if left is None or right is None else left + right
        return Usage(add(self.input_tokens, other.input_tokens), add(self.output_tokens, other.output_tokens),
                     add(self.cost_usd, other.cost_usd), {"summed_requests": True})


@dataclass(frozen=True)
class TraceEvent:
    kind: str
    data: Mapping[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", safe_evidence(self.data))


@dataclass(frozen=True)
class Generation:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str = "completed"
    usage: Usage = field(default_factory=Usage)
    raw: Mapping[str, Any] = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    provider_state: str | None = None
    hosted_calls: tuple[Mapping[str, Any], ...] = ()
    citations: tuple[Mapping[str, Any], ...] = ()
    traces: tuple[TraceEvent, ...] = ()

    def __post_init__(self) -> None:
        if self.finish_reason not in {"completed", "tool_calls", "length", "refusal", "error", "cancelled", "incomplete"}:
            raise ContractError("unknown normalized finish reason")
        if self.provider_state is not None and (not isinstance(self.provider_state, str) or not self.provider_state):
            raise ContractError("provider_state must be a nonempty opaque string")
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "raw", safe_evidence(self.raw))
        object.__setattr__(self, "hosted_calls", tuple(safe_evidence(self.hosted_calls)))
        object.__setattr__(self, "citations", tuple(safe_evidence(self.citations)))
        object.__setattr__(self, "traces", tuple(self.traces))


@dataclass(frozen=True)
class StreamEvent:
    kind: str
    data: Mapping[str, Any] = field(default_factory=dict)
    generation: Generation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", safe_evidence(self.data))


@dataclass(frozen=True)
class RunLimits:
    timeout_seconds: float = 30
    max_requests: int = 4
    max_turns: int = 4
    max_budget_usd: float | None = None
    live_opt_in: bool = False
    max_input_tokens: int = 16384
    max_output_tokens: int = 1024
    max_stream_bytes: int = 4 * 1024 * 1024
    max_stream_events: int = 10000

    def __post_init__(self) -> None:
        if isinstance(self.timeout_seconds, bool) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ContractError("timeout must be finite and positive")
        for name in ("max_requests", "max_turns", "max_input_tokens", "max_output_tokens", "max_stream_bytes", "max_stream_events"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractError(name + " must be a positive integer")
        if self.max_budget_usd is not None and (isinstance(self.max_budget_usd, bool) or not math.isfinite(self.max_budget_usd) or self.max_budget_usd <= 0):
            raise ContractError("budget must be finite and positive")
        if not isinstance(self.live_opt_in, bool):
            raise ContractError("live_opt_in must be boolean")


@dataclass(frozen=True)
class HarnessResult:
    answer: str
    messages: tuple[Message, ...]
    traces: tuple[TraceEvent, ...]
    usage: Usage
    status: str
    requests: int
    turns: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class ModelAdapter(Protocol):
    capabilities: Capabilities

    def describe(self) -> dict[str, Any]: ...
    def generate(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = (),
                 limits: RunLimits | None = None, cancel: threading.Event | None = None) -> Generation: ...


T = TypeVar("T")


class RequestLedger:
    """Private shared observation across bounded worker threads; never serialized."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = 0
        self._completed = 0
        self._accepting = True

    def start(self) -> None:
        with self._lock:
            if not self._accepting:
                raise RuntimeFailure("cancelled", raw={"operation_may_continue": False})
            self._started += 1

    def complete(self) -> None:
        with self._lock:
            self._completed += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"started": self._started, "completed": self._completed,
                    "in_flight": self._started - self._completed}

    def close(self) -> dict[str, int]:
        with self._lock:
            self._accepting = False
            return {"started": self._started, "completed": self._completed,
                    "in_flight": self._started - self._completed}


_REQUEST_LEDGER: contextvars.ContextVar[RequestLedger | None] = contextvars.ContextVar("rag_evalkit_request_ledger", default=None)


def active_request_ledger() -> RequestLedger | None:
    return _REQUEST_LEDGER.get()


def with_request_ledger(callback: Callable[[], T], ledger: RequestLedger) -> T:
    token = _REQUEST_LEDGER.set(ledger)
    try:
        return callback()
    finally:
        _REQUEST_LEDGER.reset(token)


@contextmanager
def observed_http_request():
    ledger = active_request_ledger()
    if ledger is not None:
        ledger.start()
    try:
        yield
    finally:
        if ledger is not None:
            ledger.complete()


def bounded_call(callback: Callable[[], T], *, deadline: float, cancel: threading.Event | None = None) -> T:
    """Bound wall time without claiming an in-flight callback has been killed."""
    if cancel is not None and cancel.is_set():
        raise RuntimeFailure("cancelled")
    if time.monotonic() >= deadline:
        raise RuntimeFailure("timeout")
    result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)
    context = contextvars.copy_context()

    def run() -> None:
        try:
            if cancel is not None and cancel.is_set():
                raise RuntimeFailure("cancelled", raw={"operation_may_continue": False})
            if time.monotonic() >= deadline:
                raise RuntimeFailure("timeout", raw={"operation_may_continue": False})
            result.put((True, context.run(callback)))
        except BaseException as exc:
            result.put((False, exc))

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    while True:
        if cancel is not None and cancel.is_set():
            raise RuntimeFailure("cancelled", raw={"operation_may_continue": worker.is_alive()})
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeFailure("timeout", raw={"operation_may_continue": worker.is_alive()})
        try:
            ok, value = result.get(timeout=min(remaining, 0.01))
        except queue.Empty:
            continue
        if ok:
            return value
        raise value


def tool_result_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ContractError("tool result must be text or JSON") from exc
