"""Anthropic Messages HTTP protocol adapter (text and client tools only).

Protocol sources:
https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
https://platform.claude.com/docs/en/build-with-claude/token-counting
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..contracts import UnsupportedCapability
from ..runtime import (
    Generation,
    ImageBlock,
    Message,
    RunLimits,
    RuntimeFailure,
    TextBlock,
    ToolCall,
    ToolSpec,
)
from .http import HTTPModel


class AnthropicMessagesModel(HTTPModel):
    provider = "anthropic"
    path = "/messages"
    count_path = "/messages/count_tokens"
    default_endpoint = "https://api.anthropic.com/v1"
    allowed_settings = frozenset({"temperature", "top_p", "top_k", "stop_sequences"})

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}

    def describe(self) -> dict[str, Any]:
        return dict(super().describe(), api_version="2023-06-01", thinking=False,
                    token_count_accuracy="provider_estimate; actual input usage can differ")

    def _body(self, messages: Sequence[Message], tools: Sequence[ToolSpec], limits: RunLimits) -> dict[str, Any]:
        system: list[str] = []
        turns: list[dict[str, Any]] = []
        seen_conversation = False
        for message in messages:
            if message.role == "system":
                if seen_conversation:
                    raise UnsupportedCapability("Anthropic system messages must precede conversation")
                system.append(message.content if isinstance(message.content, str) else "".join(block.text for block in message.content))
                continue
            seen_conversation = True
            role = "user" if message.role == "tool" else message.role
            blocks: list[dict[str, Any]] = []
            if message.provider_state:
                blocks.extend(self._resolve_state(message.provider_state))
            elif message.provider_items:
                raise RuntimeFailure("external_provider_items_unsupported")
            elif message.role == "tool":
                blocks.append({"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content})
            else:
                if message.content:
                    if isinstance(message.content, str):
                        blocks.append({"type": "text", "text": message.content})
                    else:
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                blocks.append({"type": "text", "text": block.text})
                            elif isinstance(block, ImageBlock):
                                if block.detail != "auto":
                                    raise UnsupportedCapability("Anthropic image detail must be auto")
                                source = {"type": "url", "url": block.url} if block.url else {
                                    "type": "base64", "media_type": block.media_type, "data": block.base64_data}
                                blocks.append({"type": "image", "source": source})
                blocks.extend({"type": "tool_use", "id": call.id, "name": call.name, "input": dict(call.arguments)}
                              for call in message.tool_calls)
            if turns and turns[-1]["role"] == role:
                turns[-1]["content"].extend(blocks)
            else:
                turns.append({"role": role, "content": blocks})
        body: dict[str, Any] = {"model": self.model, "messages": turns, "max_tokens": limits.max_output_tokens,
                                "stream": False, **self.settings}
        if system:
            body["system"] = "\n\n".join(system)
        if tools:
            body["tools"] = [{"name": tool.name, "description": tool.description, "input_schema": dict(tool.input_schema)} for tool in tools]
        return body

    def _count_body(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in body.items() if key in {"model", "messages", "system", "tools"}}

    def _response_state(self, response: Mapping[str, Any], generation: Generation) -> str | None:
        content = response.get("content", [])
        return self._remember_state(content) if content else None

    def _parse(self, response: Mapping[str, Any], details: dict[str, Any]) -> Generation:
        texts, calls = [], []
        content = response.get("content", [])
        if not isinstance(content, list):
            raise RuntimeFailure("provider_invalid_content")
        for block in content:
            if block.get("type") == "text":
                texts.append(block["text"])
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(block["id"], block["name"], block["input"]))
            else:
                raise UnsupportedCapability("unsupported Anthropic content block")
        stop = response.get("stop_reason")
        reason = {"end_turn": "completed", "stop_sequence": "completed", "tool_use": "tool_calls",
                  "max_tokens": "length", "refusal": "refusal"}.get(stop, "incomplete")
        if response.get("type") == "error" or response.get("error"):
            reason = "error"
        if bool(calls) != (reason == "tool_calls") and reason in {"tool_calls", "completed"}:
            raise RuntimeFailure("provider_inconsistent_tool_stop")
        return Generation("".join(texts), tuple(calls), reason, self._usage(response, details, anthropic=True),
                          {}, self.provider, self._observed_model(response))
