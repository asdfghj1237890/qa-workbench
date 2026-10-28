"""Incremental SSE framing and provider state machines; no SDK buffering.

Protocol contracts: OpenAI /api/docs/guides/streaming-responses and Anthropic
/docs/en/build-with-claude/streaming. Only documented text/client-tool events
are assembled. Opaque provider reasoning remains private in the final response.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ..runtime import RunLimits, RuntimeFailure, StreamEvent


class CredentialSafeEmitter:
    """Keep only suffixes that could complete a known secret across deltas.

    Tool arguments are matched after incrementally decoding JSON escapes while
    retaining their original wire spelling. This also covers credentials split
    inside a Unicode escape; safe text continues to be emitted immediately.
    """
    def __init__(self, secret: str, emit: Callable[[StreamEvent], None]):
        self.secret, self.emit = secret, emit
        self.pending: dict[tuple[str, Any], list[tuple[str, str]]] = {}
        self.escapes: dict[tuple[str, Any], str] = {}
        self.templates: dict[tuple[str, Any], StreamEvent] = {}

    @staticmethod
    def _json_units(text: str) -> tuple[list[tuple[str, str]], str]:
        units: list[tuple[str, str]] = []
        index = 0
        while index < len(text):
            if text[index] != "\\":
                units.append((text[index], text[index]))
                index += 1
                continue
            if index + 1 == len(text):
                break
            length = 6 if text[index + 1] == "u" else 2
            if index + length > len(text):
                break
            raw = text[index:index + length]
            try:
                decoded = json.loads('"' + raw + '"')
            except ValueError:
                raise RuntimeFailure("provider_invalid_tool_call") from None
            if len(decoded) == 1 and 0xD800 <= ord(decoded) <= 0xDBFF:
                if index + length + 6 > len(text):
                    break
                pair = text[index:index + length + 6]
                try:
                    combined = json.loads('"' + pair + '"')
                except ValueError:
                    raise RuntimeFailure("provider_invalid_tool_call") from None
                if len(combined) == 1:
                    raw, decoded, length = pair, combined, length + 6
            units.append((raw, decoded))
            index += length
        return units, text[index:]

    def __call__(self, event: StreamEvent) -> None:
        field = "arguments_delta" if event.kind == "tool_call_delta" else "text"
        if not self.secret or event.kind not in {"text_delta", "refusal_delta", "tool_call_delta"}:
            self.emit(event)
            return
        value = event.data.get(field)
        if not isinstance(value, str):
            raise RuntimeFailure("provider_invalid_stream_delta")
        channel = (event.kind, event.data.get("id") if event.kind == "tool_call_delta" else None)
        self.templates[channel] = event
        if event.kind == "tool_call_delta":
            units, self.escapes[channel] = self._json_units(self.escapes.get(channel, "") + value)
        else:
            units = [(character, character) for character in value]
        pending = self.pending.get(channel, []) + units
        decoded = "".join(unit[1] for unit in pending)
        if self.secret in decoded:
            raise RuntimeFailure("provider_credential_echo")
        hold = 0
        for length in range(min(len(self.secret) - 1, len(decoded)), 0, -1):
            if self.secret.startswith(decoded[-length:]):
                hold = length
                break
        safe, suffix = (pending[:-hold], pending[-hold:]) if hold else (pending, [])
        self.pending[channel] = suffix
        if safe:
            self.emit(StreamEvent(event.kind, {**event.data, field: "".join(unit[0] for unit in safe)}))

    def finish(self) -> None:
        if any(self.escapes.values()):
            raise RuntimeFailure("provider_invalid_tool_call")
        for channel, units in self.pending.items():
            if units:
                event = self.templates[channel]
                field = "arguments_delta" if event.kind == "tool_call_delta" else "text"
                self.emit(StreamEvent(event.kind, {**event.data, field: "".join(unit[0] for unit in units)}))
        self.pending.clear()


def sse_events(chunks: Iterable[bytes], limits: RunLimits, check: Callable[[], None]):
    """Frame arbitrary byte chunks progressively, bounding even one giant line."""
    pending = b""
    data: list[bytes] = []
    event_name = ""
    total = count = 0
    for chunk in chunks:
        check()
        if not isinstance(chunk, bytes):
            raise RuntimeFailure("provider_invalid_stream_chunk")
        total += len(chunk)
        if total > limits.max_stream_bytes:
            raise RuntimeFailure("stream_byte_limit", raw={"stream_bytes": total})
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            line = line.removesuffix(b"\r")
            if not line:
                if data:
                    count += 1
                    if count > limits.max_stream_events:
                        raise RuntimeFailure("stream_event_limit")
                    try:
                        value = json.loads(b"\n".join(data).decode("utf-8"))
                    except (ValueError, UnicodeError):
                        raise RuntimeFailure("provider_invalid_stream_json") from None
                    if not isinstance(value, dict):
                        raise RuntimeFailure("provider_invalid_stream_event")
                    if event_name and event_name != value.get("type"):
                        raise RuntimeFailure("provider_stream_event_type_mismatch")
                    yield value
                data, event_name = [], ""
            elif line.startswith(b"data:"):
                data.append(line[5:].removeprefix(b" "))
            elif line.startswith(b"event:"):
                try:
                    event_name = line[6:].strip().decode("ascii")
                except UnicodeError:
                    raise RuntimeFailure("provider_invalid_stream_event") from None
    check()
    if pending or data:
        raise RuntimeFailure("provider_truncated_stream")


class StreamAccumulator:
    def __init__(self, provider: str, emit: Callable[[StreamEvent], None]):
        self.provider, self.emit = provider, emit
        self.text = ""
        self.response: dict[str, Any] | None = None
        self.message: dict[str, Any] = {}
        self.blocks: dict[int, dict[str, Any]] = {}
        self.arguments: dict[int, str] = {}
        self.openai_arguments: dict[str, str] = {}
        self.closed_blocks: set[int] = set()
        self.started = self.stopped = self.delta_seen = False
        self.terminal_usage = False
        self.events = 0

    def failure_evidence(self) -> dict[str, Any]:
        usage = (self.response or self.message).get("usage", {})
        complete = isinstance(usage, Mapping) and all(isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool)
                                                     and usage[key] >= 0 for key in ("input_tokens", "output_tokens"))
        return {"partial_text": self.text, "partial_usage": usage,
                "stream_events": self.events, "stream_terminal": self.stopped,
                "usage_observation_complete": self.stopped and self.terminal_usage and complete}

    def feed(self, event: Mapping[str, Any]) -> None:
        self.events += 1
        kind = event.get("type")
        if not isinstance(kind, str):
            raise RuntimeFailure("provider_invalid_stream_event")
        if self.stopped:
            raise RuntimeFailure("provider_event_after_terminal")
        if kind == "error":
            raise RuntimeFailure("provider_stream_error")
        self.emit(StreamEvent("provider_event", {"provider": self.provider, "type": kind}))
        if self.provider == "openai":
            self._openai(kind, event)
        else:
            self._anthropic(kind, event)

    def _openai(self, kind: str, event: Mapping[str, Any]) -> None:
        if kind == "response.output_text.delta":
            delta = event.get("delta")
            if not isinstance(delta, str):
                raise RuntimeFailure("provider_invalid_stream_delta")
            self.text += delta
            self.emit(StreamEvent("text_delta", {"text": delta}))
        elif kind == "response.function_call_arguments.delta":
            if not isinstance(event.get("delta"), str) or not isinstance(event.get("item_id"), str):
                raise RuntimeFailure("provider_invalid_stream_delta")
            identifier = event["item_id"]
            self.openai_arguments[identifier] = self.openai_arguments.get(identifier, "") + event["delta"]
            self.emit(StreamEvent("tool_call_delta", {"id": event.get("item_id"), "arguments_delta": event["delta"]}))
        elif kind == "response.refusal.delta":
            if not isinstance(event.get("delta"), str):
                raise RuntimeFailure("provider_invalid_stream_delta")
            self.emit(StreamEvent("refusal_delta", {"text": event["delta"]}))
        elif kind.startswith(("response.web_search_call.", "response.file_search_call.")):
            self.emit(StreamEvent("hosted_tool_progress", {"type": kind, "id": event.get("item_id"), "dispatch": "provider"}))
        elif kind == "response.output_text.annotation.added":
            self.emit(StreamEvent("citation", {"citation": event.get("annotation", {})}))
        elif kind in {"response.completed", "response.incomplete", "response.failed"}:
            response = event.get("response")
            if not isinstance(response, dict) or not isinstance(response.get("output"), list):
                raise RuntimeFailure("provider_invalid_stream_terminal")
            expected = {"response.completed": "completed", "response.incomplete": "incomplete", "response.failed": "failed"}[kind]
            if response.get("status") != expected:
                raise RuntimeFailure("provider_invalid_stream_terminal")
            if self.text:
                terminal_text = "".join(block.get("text", "") for item in response["output"] if item.get("type") == "message"
                                        for block in item.get("content", []) if block.get("type") == "output_text")
                if terminal_text != self.text:
                    raise RuntimeFailure("provider_inconsistent_stream_terminal")
            final_calls = {item.get("id"): item for item in response["output"] if item.get("type") == "function_call"}
            if any(identifier not in final_calls or final_calls[identifier].get("arguments") != arguments
                   for identifier, arguments in self.openai_arguments.items()):
                raise RuntimeFailure("provider_inconsistent_stream_terminal")
            self.response = copy.deepcopy(response)
            self.stopped = True
            self.terminal_usage = isinstance(response.get("usage"), Mapping)

    def _anthropic(self, kind: str, event: Mapping[str, Any]) -> None:
        if kind == "ping":
            return
        if kind == "message_start":
            if self.started or not isinstance(event.get("message"), dict):
                raise RuntimeFailure("provider_invalid_stream_sequence")
            self.started = True
            self.message = copy.deepcopy(event["message"])
            self.message["content"] = []
            return
        if not self.started:
            raise RuntimeFailure("provider_invalid_stream_sequence")
        if kind.startswith("content_block_"):
            index = event.get("index")
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise RuntimeFailure("provider_invalid_stream_index")
            if kind == "content_block_start":
                if index in self.blocks or not isinstance(event.get("content_block"), dict):
                    raise RuntimeFailure("provider_invalid_stream_sequence")
                self.blocks[index] = copy.deepcopy(event["content_block"])
                initial = self.blocks[index].get("text")
                if self.blocks[index].get("type") == "text" and initial:
                    if not isinstance(initial, str):
                        raise RuntimeFailure("provider_invalid_stream_delta")
                    self.text += initial
                    self.emit(StreamEvent("text_delta", {"text": initial}))
            elif kind == "content_block_delta":
                if index not in self.blocks or index in self.closed_blocks:
                    raise RuntimeFailure("provider_invalid_stream_sequence")
                delta = event.get("delta", {})
                block = self.blocks[index]
                if delta.get("type") == "text_delta" and block.get("type") == "text" and isinstance(delta.get("text"), str):
                    block["text"] += delta["text"]
                    self.text += delta["text"]
                    self.emit(StreamEvent("text_delta", {"text": delta["text"]}))
                elif delta.get("type") == "input_json_delta" and block.get("type") == "tool_use" and isinstance(delta.get("partial_json"), str):
                    self.arguments[index] = self.arguments.get(index, "") + delta["partial_json"]
                    self.emit(StreamEvent("tool_call_delta", {"id": block.get("id"), "arguments_delta": delta["partial_json"]}))
                else:
                    raise RuntimeFailure("provider_unsupported_stream_delta")
            elif kind == "content_block_stop":
                if index not in self.blocks or index in self.closed_blocks:
                    raise RuntimeFailure("provider_invalid_stream_sequence")
                if index in self.arguments:
                    try:
                        self.blocks[index]["input"] = json.loads(self.arguments[index])
                    except ValueError:
                        raise RuntimeFailure("provider_invalid_tool_call") from None
                self.closed_blocks.add(index)
        elif kind == "message_delta":
            delta = event.get("delta")
            usage = event.get("usage")
            if not isinstance(delta, Mapping) or not isinstance(usage, Mapping):
                raise RuntimeFailure("provider_invalid_stream_terminal")
            self.message.update(delta)
            self.message["usage"] = dict(self.message.get("usage") or {}, **usage)
            self.terminal_usage = "output_tokens" in usage
            self.delta_seen = True
        elif kind == "message_stop":
            if not self.delta_seen or self.closed_blocks != set(self.blocks) or not self.message.get("stop_reason"):
                raise RuntimeFailure("provider_invalid_stream_terminal")
            self.message["content"] = [self.blocks[i] for i in sorted(self.blocks)]
            if not self.terminal_usage:
                self.message["usage"].pop("output_tokens", None)
            self.response, self.stopped = self.message, True

    def finish(self) -> Mapping[str, Any]:
        if not self.stopped or self.response is None:
            raise RuntimeFailure("provider_truncated_stream")
        return self.response
