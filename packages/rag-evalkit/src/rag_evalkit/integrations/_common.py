"""Detached evidence and an explicitly cooperative asynchronous SDK boundary."""

from __future__ import annotations

import asyncio
import hashlib
import math
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from ..contracts import ContractError
from ..rag import Evidence, RagResult
from ..runtime import (
    RunLimits,
    RuntimeFailure,
    TraceEvent,
    Usage,
    bounded_call,
    safe_evidence,
)


def sdk_import(name: str, extra: str):
    import importlib
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"Install rag-evalkit[{extra}] to use this adapter") from exc


def async_call(factory: Callable, *, limits: RunLimits, cancel: threading.Event | None):
    """Cancel the async task when waiting ends; arbitrary SDK callbacks may continue.

    This uses a daemon worker rather than nesting asyncio.run in a caller's loop.
    A synchronous callback run by an SDK cannot be forcibly stopped by Python.
    """
    deadline = time.monotonic() + limits.timeout_seconds
    state: dict[str, Any] = {}
    abandoned = threading.Event()

    def worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        state["loop"] = loop
        try:
            task = loop.create_task(factory())
            state["task"] = task
            if abandoned.is_set():
                task.cancel()
            return loop.run_until_complete(task)
        finally:
            # Give cooperative SDK children one loop turn to receive cancellation.
            for pending in asyncio.all_tasks(loop):
                pending.cancel()
            loop.run_until_complete(asyncio.sleep(0))
            loop.close()

    try:
        return bounded_call(worker, deadline=deadline, cancel=cancel)
    except asyncio.CancelledError:
        raise RuntimeFailure("cancelled") from None
    except RuntimeFailure as exc:
        abandoned.set()
        loop, task = state.get("loop"), state.get("task")
        if loop is not None and task is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass
        raise RuntimeFailure(exc.code, raw={"operation_may_continue": bool(state),
                                             "cancellation": "async_task_cancel_requested"}) from None


def usage_from_mapping(raw: Any, *, secrets=()) -> Usage:
    """Only copy explicitly reported accounting. Missing fields remain unknown."""
    if not isinstance(raw, Mapping):
        return Usage(details={"reported": False})
    tokens_in = raw.get("input_tokens", raw.get("prompt_tokens"))
    tokens_out = raw.get("output_tokens", raw.get("completion_tokens"))
    return Usage(tokens_in, tokens_out, raw.get("cost_usd"),
                 safe_evidence({"reported": True, **dict(raw)}, secrets))


def evidence(text, metadata, rank, *, identity=None, parent=None, score=None, secrets=()):
    if not isinstance(text, str) or not isinstance(metadata, Mapping):
        raise ContractError("framework source requires text and mapping metadata")
    if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score)):
        raise ContractError("framework source score must be finite or unknown")
    derived = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    chunk_id = metadata.get("chunk_id") or identity or derived
    document_id = metadata.get("document_id") or parent or metadata.get("doc_id") or identity or derived
    source_id = metadata.get("source_id") or metadata.get("source") or metadata.get("url") or parent or identity or derived
    if not all(isinstance(value, str) and value for value in (chunk_id, document_id, source_id)):
        raise ContractError("framework source identifiers must be nonempty strings")
    if any(character in source_id for character in "[]\r\n"):
        raise ContractError("framework source id contains citation delimiters")
    details = {**dict(metadata), "score_kind": "framework_reported" if score is not None else "unknown",
               "source_identity": "derived_content_hash" if source_id == derived else "framework_reported"}
    return Evidence(safe_evidence(document_id, secrets), safe_evidence(chunk_id, secrets),
                    safe_evidence(source_id, secrets), safe_evidence(text, secrets), rank,
                    score, score, safe_evidence(details, secrets))


class FrameworkRag:
    name = "framework"

    def __init__(self, *, limits=None, secrets=()):
        self._limits = limits or RunLimits()
        self._secrets = tuple(secrets)

    def run(self, query: str, *, limits=None, cancel=None) -> RagResult:
        if not isinstance(query, str) or not query.strip():
            raise ContractError("query must be a nonempty string")
        limits = limits or self._limits
        start = time.monotonic()
        traces = [TraceEvent("framework_start", {"framework": self.name})]
        # External pipelines own their internal providers. A currency cap cannot
        # be promised without observing and reserving every nested provider call.
        try:
            if limits.max_budget_usd is not None:
                raise RuntimeFailure("budget_unsupported")
            answer, sources, usage, details = async_call(
                lambda: self._invoke(query, traces), limits=limits, cancel=cancel)
            if not isinstance(answer, str):
                raise ContractError("framework answer must be text")
            if not answer.strip():
                raise RuntimeFailure("incomplete")
            status = "completed"
        except RuntimeFailure as exc:
            answer, sources, usage, details, status = "", (), Usage(), {}, exc.code
            traces.append(TraceEvent("runtime_error", {"code": status, **exc.raw}))
        except Exception as exc:
            answer, sources, usage, details = "", (), Usage(), {}
            status = "contract_error" if isinstance(exc, ContractError) else "error"
            traces.append(TraceEvent("runtime_error", {"code": status, "error_type": type(exc).__name__}))
        duration = time.monotonic() - start
        traces.append(TraceEvent("framework_end", {"framework": self.name, "status": status, "latency_seconds": duration}))
        return RagResult(safe_evidence(answer, self._secrets), tuple(sources),
                         tuple(TraceEvent(item.kind, safe_evidence(item.data, self._secrets), item.timestamp) for item in traces),
                         usage, safe_evidence({"pipeline": self.name, "status": status, "latency_seconds": duration,
                                               "semantic_verdict": "not_evaluated", **details}, self._secrets))
