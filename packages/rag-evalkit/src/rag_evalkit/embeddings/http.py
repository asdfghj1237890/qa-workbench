"""HTTP embedding adapters. No retries, redirects, model downloads, or fallback.

Protocols: https://developers.openai.com/api/reference/resources/embeddings/methods/create
https://huggingface.co/docs/text-embeddings-inference/quick_tour
https://github.com/huggingface/text-embeddings-inference/blob/main/router/src/http/types.rs
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import struct
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from ..contracts import ContractError
from ..runtime import (
    RequestLedger,
    RuntimeFailure,
    Usage,
    active_request_ledger,
    bounded_call,
    observed_http_request,
    safe_evidence,
    with_request_ledger,
)


def _positive(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractError(label + " must be a positive integer")


def _timeout(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ContractError("timeout must be finite and positive")


@dataclass(frozen=True)
class EmbeddingLimits:
    timeout_seconds: float = 30
    max_requests: int = 100
    max_input_tokens: int = 100000
    max_input_bytes: int = 1048576
    max_budget_usd: float | None = None
    live_opt_in: bool = False

    def __post_init__(self) -> None:
        _timeout(self.timeout_seconds)
        for name in ("max_requests", "max_input_tokens", "max_input_bytes"):
            _positive(getattr(self, name), name)
        if self.max_budget_usd is not None:
            _timeout(self.max_budget_usd)
        if not isinstance(self.live_opt_in, bool):
            raise ContractError("live_opt_in must be boolean")


@dataclass(frozen=True)
class EmbeddingPricing:
    """Caller supplied USD per million input tokens, never an assumed price."""
    input_per_million: float

    def __post_init__(self) -> None:
        value = self.input_per_million
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ContractError("embedding price must be finite and nonnegative")


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    usage: Usage
    metadata: Mapping[str, Any] = field(default_factory=dict)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _CallLedger(RequestLedger):
    """Independently close each call's admission gate while forwarding observations."""

    def __init__(self, parent, deadline, cancel, stop, on_dispatch):
        super().__init__()
        self._parent, self._deadline, self._cancel, self._stop = parent, deadline, cancel, stop
        self._gate = threading.Lock()
        self._on_dispatch = on_dispatch

    def start(self):
        with self._gate:
            if self._stop.is_set() or (self._cancel is not None and self._cancel.is_set()):
                raise RuntimeFailure("cancelled", raw={"operation_may_continue": False})
            if time.monotonic() >= self._deadline:
                raise RuntimeFailure("timeout", raw={"operation_may_continue": False})
            if self._parent is not None:
                self._parent.start()
            super().start()
            self._on_dispatch()

    def complete(self):
        super().complete()
        if self._parent is not None:
            self._parent.complete()

    def close(self):
        with self._gate:
            self._stop.set()
            return super().close()


def _endpoint(value: str) -> tuple[str, bool]:
    if not isinstance(value, str) or any(ord(char) < 33 for char in value):
        raise ContractError("endpoint must be an HTTP(S) URL without whitespace")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ContractError("invalid embedding endpoint") from None
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or port == 0:
        raise ContractError("endpoint must not contain credentials, query or fragment")
    loopback = parts.hostname.lower() == "localhost"
    try:
        loopback = loopback or ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        pass
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
        raise ContractError("embedding endpoint requires HTTPS; HTTP is allowed only for loopback")
    return value.rstrip("/"), loopback


def _vector(value: Any, dimensions: int, normalize: bool) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != dimensions:
        raise RuntimeFailure("embedding_dimensions_mismatch")
    try:
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in value):
            raise RuntimeFailure("embedding_invalid_vector")
        vector = tuple(struct.unpack("!f", struct.pack("!f", item))[0] for item in value)
    except (OverflowError, struct.error):
        raise RuntimeFailure("embedding_invalid_float32") from None
    if any(not math.isfinite(item) for item in vector) or not any(vector):
        raise RuntimeFailure("embedding_invalid_float32")
    if normalize:
        norm = math.hypot(*vector)
        vector = tuple(struct.unpack("!f", struct.pack("!f", item / norm))[0] for item in vector)
    return vector


class _HTTPEmbedding:
    adapter = ""
    path = ""

    def __init__(self, model: str, dimensions: int, *, model_version: str, endpoint: str,
                 api_key: str = "", normalize: bool = False, timeout: float = 30, batch_size: int = 32,
                 pricing: EmbeddingPricing | None = None, limits: EmbeddingLimits | None = None,
                 billing: str = "self_hosted"):
        for name, value in (("model", model), ("model_version", model_version)):
            if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
                raise ContractError(name + " must be an explicit nonempty identifier")
        _positive(dimensions, "dimensions")
        _positive(batch_size, "batch_size")
        _timeout(timeout)
        if not isinstance(normalize, bool):
            raise ContractError("normalize must be boolean")
        if not isinstance(api_key, str) or any(ord(char) < 32 for char in api_key):
            raise ContractError("invalid API credential")
        if pricing is not None and not isinstance(pricing, EmbeddingPricing):
            raise ContractError("pricing must be EmbeddingPricing")
        if limits is not None and not isinstance(limits, EmbeddingLimits):
            raise ContractError("limits must be EmbeddingLimits")
        if billing not in {"self_hosted", "metered"}:
            raise ContractError("billing must be self_hosted or metered")
        self.endpoint, self._loopback = _endpoint(endpoint)
        self.model, self.model_version, self.dimensions = model, model_version, dimensions
        self.normalize, self.timeout, self.batch_size = normalize, timeout, batch_size
        self.pricing, self.limits, self.billing = pricing, limits or EmbeddingLimits(timeout_seconds=timeout), billing
        self._api_key = api_key
        self._state_lock, self._call_lock = threading.RLock(), threading.Lock()
        self._started = self._pending_results = self._observed_tokens = 0
        self._unknown_tokens = self._unknown_cost = self._closed = False
        self._resolved_model: str | None = None

    @property
    def usage(self) -> dict[str, Any]:
        """Lifetime usage, including failures; unknown and in-flight cost stay unknown."""
        with self._state_lock:
            unknown = self._unknown_cost or self._pending_results > 0 or (self._started > 0 and self.pricing is None)
            return {"requests": self._started,
                    "input_tokens": None if self._unknown_tokens or self._pending_results else self._observed_tokens,
                    "cost_usd": None if unknown else (self._observed_tokens * self.pricing.input_per_million / 1_000_000 if self.pricing else 0.0),
                    "known_cost_lower_bound_usd": self._observed_tokens * self.pricing.input_per_million / 1_000_000 if self.pricing else 0.0,
                    "unknown_cost": unknown,
                    "details": {"observed_input_tokens": self._observed_tokens, "pending_results": self._pending_results,
                                "scope": "embedder_lifetime", "request_accounting": "transport_observed"}}

    def close(self) -> None:
        with self._state_lock:
            self._closed = True

    def describe(self) -> dict[str, Any]:
        target = hashlib.sha256((self.endpoint + self.path).encode()).hexdigest()
        return safe_evidence({
            "adapter": self.adapter, "adapter_version": 1, "model": self.model,
            "model_version": self.model_version, "model_version_source": "caller_declared",
            "resolved_model_policy": "record_response_model; declared_version_not_server_verified",
            "dimensions": self.dimensions, "normalize": self.normalize,
            "normalization": "client_l2_after_float32" if self.normalize else "provider_output_preserved",
            "precision": "float32", "endpoint": self.endpoint, "target_sha256": target,
            "batch_size": self.batch_size, "timeout_seconds": self.timeout,
            "limits": asdict(self.limits), "pricing": asdict(self.pricing) if self.pricing else None,
            "billing": self.billing, "evidence_kind": "live_http", "synthetic": False,
            "retries": 0, "redirects": False, "request_accounting": "transport_observed",
            "cancellation": "bounded_wait; in_flight_request_may_continue; no_further_dispatch",
            "budget_policy": "reserve_configured_input_token_cap_before_dispatch",
            "limit_scope": "embedder_lifetime; request overrides can only tighten configured caps",
            "token_limit": "client_reservation_and_observed_usage_check; not_provider_enforced",
        }, (self._api_key,))

    def estimate_cost(self, limits: EmbeddingLimits | None = None) -> float | None:
        return None if self.pricing is None else (limits or self.limits).max_input_tokens * self.pricing.input_per_million / 1_000_000

    def embed(self, text: str, *, limits: EmbeddingLimits | None = None,
              cancel: threading.Event | None = None) -> tuple[float, ...]:
        return self.embed_batch([text], limits=limits, cancel=cancel).vectors[0]

    def embed_many(self, texts: Sequence[str], *, limits: EmbeddingLimits | None = None,
                   cancel: threading.Event | None = None) -> tuple[tuple[float, ...], ...]:
        return self.embed_batch(texts, limits=limits, cancel=cancel).vectors

    def embed_batch(self, texts: Sequence[str], *, limits: EmbeddingLimits | None = None,
                    cancel: threading.Event | None = None) -> EmbeddingBatch:
        limits = limits or self.limits
        if not isinstance(limits, EmbeddingLimits):
            raise ContractError("limits must be EmbeddingLimits")
        budgets = [value for value in (limits.max_budget_usd, self.limits.max_budget_usd) if value is not None]
        limits = replace(limits, max_requests=min(limits.max_requests, self.limits.max_requests),
                         timeout_seconds=min(limits.timeout_seconds, self.limits.timeout_seconds, self.timeout),
                         max_input_tokens=min(limits.max_input_tokens, self.limits.max_input_tokens),
                         max_input_bytes=min(limits.max_input_bytes, self.limits.max_input_bytes),
                         max_budget_usd=min(budgets) if budgets else None)
        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence) or not texts:
            raise ContractError("embedding batch requires a nonempty sequence of texts")
        texts = tuple(texts)
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ContractError("embedding texts must be nonempty strings")
        if sum(len(text.encode("utf-8")) for text in texts) > limits.max_input_bytes:
            raise RuntimeFailure("embedding_input_bytes_limit", raw={"api_requests": 0})
        requests = math.ceil(len(texts) / self.batch_size)
        reserve = self.estimate_cost(limits)
        if self.billing == "metered":
            if not limits.live_opt_in:
                raise RuntimeFailure("live_embedding_opt_in_required", raw={"api_requests": 0})
            if self.pricing is None or limits.max_budget_usd is None:
                raise RuntimeFailure("live_embedding_pricing_and_budget_required", raw={"api_requests": 0})
            if getattr(self, "token_bound", None) != "utf8_bytes":
                raise RuntimeFailure("embedding_token_bound_required", raw={"api_requests": 0})
        if limits.max_budget_usd is not None and (reserve is None or reserve > limits.max_budget_usd):
            raise RuntimeFailure("budget_limit", raw={"api_requests": 0})
        if not self._call_lock.acquire(blocking=False):
            raise RuntimeFailure("embedding_busy", raw={"api_requests": 0})
        try:
            with self._state_lock:
                if self._closed:
                    raise RuntimeFailure("embedding_closed", raw={"api_requests": 0})
                if self._pending_results:
                    raise RuntimeFailure("embedding_busy", raw={"api_requests": 0})
                if self._started + requests > limits.max_requests:
                    raise RuntimeFailure("request_limit", raw={"api_requests": 0})
                if self._observed_tokens >= limits.max_input_tokens:
                    raise RuntimeFailure("embedding_input_token_limit_exceeded", raw={"api_requests": 0})
                if self.billing == "metered" and self._observed_tokens + sum(len(text.encode("utf-8")) for text in texts) > limits.max_input_tokens:
                    raise RuntimeFailure("embedding_input_token_bound_exceeded", raw={"api_requests": 0})
                if limits.max_budget_usd is not None and self._unknown_cost:
                    raise RuntimeFailure("embedding_usage_unknown", raw={"api_requests": 0})
            return self._bounded_embed(texts, limits, cancel)
        finally:
            self._call_lock.release()

    def _bounded_embed(self, texts, limits, cancel):
        deadline = time.monotonic() + min(self.timeout, limits.timeout_seconds)
        # This per-call stop gate prevents late workers from dispatching another chunk.
        stop = threading.Event()
        progress: dict[str, Any] = {"completed_inputs": 0, "input_tokens": 0, "usage_known": True,
                                    "cost_usd": 0.0 if self.pricing else None, "resolved_models": [], "pending_usage": False}
        def record_dispatch():
            with self._state_lock:
                self._started += 1
                self._pending_results += 1
                progress["pending_usage"] = True
        ledger = _CallLedger(active_request_ledger(), deadline, cancel, stop, record_dispatch)
        try:
            return bounded_call(lambda: with_request_ledger(
                lambda: self._embed(texts, limits, cancel, stop, deadline, progress), ledger), deadline=deadline, cancel=cancel)
        except RuntimeFailure as exc:
            snapshot = ledger.close()
            raw = dict(exc.raw, api_requests=snapshot["started"],
                       in_flight_http_requests=snapshot["in_flight"], request_observation_complete=snapshot["in_flight"] == 0,
                       completed_inputs=progress["completed_inputs"],
                       usage={"input_tokens": progress["input_tokens"] if progress["usage_known"] and not progress["pending_usage"] else None,
                              "cost_usd": progress["cost_usd"] if not progress["pending_usage"] else None},
                       lifetime_usage=self.usage, resolved_models=list(progress["resolved_models"]))
            if snapshot["in_flight"]:
                raw["usage_observation_complete"] = False
                raw["operation_may_continue"] = True
                raw["unobserved_in_flight_cost"] = True
            raise RuntimeFailure(exc.code, raw=safe_evidence(raw, (self._api_key,))) from None
        finally:
            ledger.close()

    def _embed(self, texts, limits, cancel, stop, deadline, progress) -> EmbeddingBatch:
        vectors: list[tuple[float, ...]] = []
        requests = 0
        for start in range(0, len(texts), self.batch_size):
            if stop.is_set() or (cancel is not None and cancel.is_set()):
                raise RuntimeFailure("cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeFailure("timeout")
            chunk = texts[start:start + self.batch_size]
            # Body construction may block (e.g. a tokenizer hook). Re-check the
            # per-call gate at the transport boundary after construction finishes.
            body = self._body(chunk)
            with self._state_lock:
                if self._closed or stop.is_set() or (cancel is not None and cancel.is_set()):
                    raise RuntimeFailure("cancelled")
                if self._started >= limits.max_requests:
                    raise RuntimeFailure("request_limit")
                if self._observed_tokens >= limits.max_input_tokens:
                    raise RuntimeFailure("embedding_input_token_limit_exceeded")
            try:
                payload, headers = self._request(body, max(0.001, deadline - time.monotonic()))
                requests += 1
                raw_vectors, tokens, resolved = self._parse(payload, headers, len(chunk))
                with self._state_lock:
                    self._unknown_tokens = self._unknown_tokens or tokens is None
                    self._unknown_cost = self._unknown_cost or tokens is None or self.pricing is None
                    self._observed_tokens += tokens or 0
                    model_changed = resolved is not None and self._resolved_model not in {None, resolved}
                    if resolved is not None:
                        self._resolved_model = self._resolved_model or resolved
            except BaseException:
                with self._state_lock:
                    if progress["pending_usage"]:
                        self._unknown_tokens = self._unknown_cost = True
                raise
            finally:
                with self._state_lock:
                    if progress["pending_usage"]:
                        self._pending_results -= 1
            progress["pending_usage"] = False
            if resolved not in progress["resolved_models"]:
                progress["resolved_models"].append(resolved)
            progress["usage_known"] = progress["usage_known"] and tokens is not None
            if tokens is not None:
                progress["input_tokens"] += tokens
            progress["cost_usd"] = (progress["input_tokens"] * self.pricing.input_per_million / 1_000_000
                                    if self.pricing and progress["usage_known"] else None)
            if model_changed:
                raise RuntimeFailure("embedding_resolved_model_changed")
            if self._observed_tokens > limits.max_input_tokens:
                raise RuntimeFailure("embedding_input_token_limit_exceeded")
            if limits.max_budget_usd is not None and progress["cost_usd"] is None:
                raise RuntimeFailure("embedding_usage_unknown")
            if limits.max_budget_usd is not None and self.usage["cost_usd"] > limits.max_budget_usd:
                raise RuntimeFailure("budget_exceeded")
            vectors.extend(_vector(value, self.dimensions, self.normalize) for value in raw_vectors)
            progress["completed_inputs"] = len(vectors)
        usage = Usage(progress["input_tokens"] if progress["usage_known"] else None, 0, progress["cost_usd"],
                      {"api_requests": requests, "metering": "provider_reported" if progress["usage_known"] else "unknown"})
        return EmbeddingBatch(tuple(vectors), usage, safe_evidence({"description": self.describe(),
            "resolved_models": progress["resolved_models"], "api_requests": requests,
            "completed_inputs": len(vectors), "usage_observation_complete": True}, (self._api_key,)))

    def _request(self, body, timeout) -> tuple[Any, Mapping[str, str]]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key
        request = Request(self.endpoint + self.path, data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode(),
                          headers=headers, method="POST")
        # Loopback calls must not leave the host through an environment proxy.
        handlers = [_NoRedirect(), *([ProxyHandler({})] if self._loopback else [])]
        try:
            with observed_http_request():
                with build_opener(*handlers).open(request, timeout=timeout) as response:
                    payload = response.read(32 * 1024 * 1024 + 1)
                    if len(payload) > 32 * 1024 * 1024:
                        raise RuntimeFailure("embedding_response_too_large")
                    return json.loads(payload), {key.lower(): value for key, value in response.headers.items()}
        except HTTPError as exc:
            # Error bodies can echo input/credentials; status is the only retained field.
            exc.close()
            raise RuntimeFailure("embedding_http_error", raw={"status": exc.code}) from None
        except TimeoutError:
            raise RuntimeFailure("timeout", raw={"operation_may_continue": True,
                "usage_observation_complete": False, "unobserved_in_flight_cost": True}) from None
        except (URLError, OSError, ValueError):
            raise RuntimeFailure("embedding_transport_error") from None

    def _body(self, texts):
        raise NotImplementedError

    def _parse(self, payload, headers, count):
        raise NotImplementedError


def _tokens(value: Any) -> int | None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise RuntimeFailure("embedding_invalid_usage")
    return value


class OpenAIEmbedding(_HTTPEmbedding):
    adapter = "openai_embeddings"
    path = "/embeddings"

    def __init__(self, model: str, dimensions: int, *, model_version: str,
                 endpoint: str = "https://api.openai.com/v1", api_key: str = "", normalize: bool = False,
                 timeout: float = 30, batch_size: int = 32, pricing: EmbeddingPricing | None = None,
                 limits: EmbeddingLimits | None = None, billing: str = "metered", send_dimensions: bool = True,
                 token_bound: str | None = None):
        if not isinstance(send_dimensions, bool):
            raise ContractError("send_dimensions must be boolean")
        self.send_dimensions = send_dimensions
        if token_bound not in {None, "utf8_bytes"}:
            raise ContractError("token_bound must be utf8_bytes or absent")
        self.token_bound = token_bound
        self._token_bound_source = "caller_declared" if token_bound else "absent"
        super().__init__(model, dimensions, model_version=model_version, endpoint=endpoint, api_key=api_key,
                         normalize=normalize, timeout=timeout, batch_size=batch_size, pricing=pricing, limits=limits, billing=billing)
        if self.token_bound is None and self.endpoint == "https://api.openai.com/v1" and model in {
            "text-embedding-ada-002", "text-embedding-3-small", "text-embedding-3-large"
        }:
            self.token_bound, self._token_bound_source = "utf8_bytes", "known_openai_byte_bpe_model"

    def describe(self):
        return dict(super().describe(), encoding_format="float", send_dimensions=self.send_dimensions,
                    token_bound=self.token_bound, token_bound_source=self._token_bound_source,
                    token_limit="pre_dispatch_utf8_byte_upper_bound_and_observed_lifetime_check; provider_contract_required",
                    token_bound_contract="billed_input_tokens <= input_utf8_bytes; no hidden prompt overhead")

    def _body(self, texts):
        body = {"model": self.model, "input": list(texts), "encoding_format": "float"}
        if self.send_dimensions:
            body["dimensions"] = self.dimensions
        return body

    def _parse(self, payload, headers, count):
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list) or len(payload["data"]) != count:
            raise RuntimeFailure("embedding_result_count_mismatch")
        model = payload.get("model")
        if not isinstance(model, str) or not model:
            raise RuntimeFailure("embedding_missing_resolved_model")
        if self._api_key and self._api_key in model:
            raise RuntimeFailure("embedding_credential_echo")
        indexed = {}
        for item in payload["data"]:
            if not isinstance(item, dict):
                raise RuntimeFailure("embedding_invalid_index")
            index = item.get("index")
            if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index >= count or index in indexed:
                raise RuntimeFailure("embedding_invalid_index")
            indexed[index] = item.get("embedding")
        usage = payload.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise RuntimeFailure("embedding_invalid_usage")
        tokens = _tokens(usage.get("prompt_tokens") if usage else None)
        total = _tokens(usage.get("total_tokens") if usage else None)
        if tokens is not None and total is not None and total != tokens:
            raise RuntimeFailure("embedding_invalid_usage")
        return [indexed[index] for index in range(count)], tokens, model


class TEIEmbedding(_HTTPEmbedding):
    adapter = "tei_embeddings"
    path = "/embed"

    def __init__(self, model: str, dimensions: int, *, model_version: str, endpoint: str,
                 api_key: str = "", normalize: bool = False, timeout: float = 30, batch_size: int = 32,
                 pricing: EmbeddingPricing | None = None, limits: EmbeddingLimits | None = None,
                 billing: str = "self_hosted", truncate: bool = False, prompt_name: str | None = None):
        if not isinstance(truncate, bool):
            raise ContractError("truncate must be boolean")
        if prompt_name is not None and (not isinstance(prompt_name, str) or not prompt_name.strip()):
            raise ContractError("prompt_name must be nonempty or absent")
        self.truncate, self.prompt_name = truncate, prompt_name
        super().__init__(model, dimensions, model_version=model_version, endpoint=endpoint, api_key=api_key,
                         normalize=normalize, timeout=timeout, batch_size=batch_size, pricing=pricing, limits=limits, billing=billing)

    def describe(self):
        return safe_evidence(dict(super().describe(), truncate=self.truncate, prompt_name=self.prompt_name,
            server_model_verification="not_observed; deployment_identity_is_caller_declared"), (self._api_key,))

    def _body(self, texts):
        body = {"inputs": list(texts), "truncate": self.truncate, "normalize": self.normalize}
        if self.prompt_name is not None:
            body["prompt_name"] = self.prompt_name
        return body

    def _parse(self, payload, headers, count):
        if not isinstance(payload, list) or len(payload) != count:
            raise RuntimeFailure("embedding_result_count_mismatch")
        reported = headers.get("x-compute-tokens")
        try:
            tokens = _tokens(int(reported)) if reported is not None else None
        except (TypeError, ValueError):
            raise RuntimeFailure("embedding_invalid_usage") from None
        return payload, tokens, None
