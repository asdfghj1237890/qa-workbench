"""OpenAI Responses HTTP adapter, with stateless function-call continuation.

Protocol sources:
https://developers.openai.com/api/docs/guides/function-calling
https://developers.openai.com/api/docs/guides/token-counting
Images, incremental SSE, and explicitly configured hosted search tools are
supported without converting provider hosted calls into client function calls.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from ..contracts import ContractError, UnsupportedCapability
from ..runtime import (
    Generation,
    Message,
    RunLimits,
    RuntimeFailure,
    TextBlock,
    ToolCall,
    ToolSpec,
    TraceEvent,
    Usage,
)
from .http import HTTPModel


class OpenAIResponsesModel(HTTPModel):
    provider = "openai"
    path = "/responses"
    count_path = "/responses/input_tokens"
    default_endpoint = "https://api.openai.com/v1"
    allowed_settings = frozenset({"temperature", "top_p", "reasoning_effort"})

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json"}

    def _body(self, messages: Sequence[Message], tools: Sequence[ToolSpec], limits: RunLimits) -> dict[str, Any]:
        inputs: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "tool":
                inputs.append({"type": "function_call_output", "call_id": message.tool_call_id, "output": message.content})
            elif message.provider_state:
                inputs.extend(self._resolve_state(message.provider_state))
            elif message.provider_items:
                raise RuntimeFailure("external_provider_items_unsupported")
            else:
                if message.content:
                    content = message.content
                    if not isinstance(content, str):
                        content = [{"type": "input_text", "text": block.text} if isinstance(block, TextBlock)
                                   else {"type": "input_image", "image_url": block.url or "data:" + block.media_type + ";base64," + block.base64_data,
                                         "detail": block.detail} for block in content]
                    inputs.append({"role": message.role, "content": content})
                for call in message.tool_calls:
                    inputs.append({"type": "function_call", "call_id": call.id, "name": call.name,
                                   "arguments": json.dumps(dict(call.arguments), ensure_ascii=False, allow_nan=False)})
        body: dict[str, Any] = {"model": self.model, "input": inputs, "max_output_tokens": limits.max_output_tokens,
                                "stream": False, "store": False}
        for key, value in self.settings.items():
            if key == "reasoning_effort":
                body["reasoning"] = {"effort": value}
                body["include"] = ["reasoning.encrypted_content"]
            else:
                body[key] = value
        if tools:
            body["tools"] = [{"type": "function", "name": tool.name, "description": tool.description,
                              "parameters": dict(tool.input_schema), "strict": False} for tool in tools]
        if self.hosted_tools:
            body.setdefault("tools", []).extend({"type": tool.type, **dict(tool.config)} for tool in self.hosted_tools)
            body["max_tool_calls"] = sum(tool.max_calls for tool in self.hosted_tools)
            body.setdefault("include", []).extend(
                "web_search_call.action.sources" if tool.type == "web_search" else "file_search_call.results"
                for tool in self.hosted_tools)
        return body

    def _count_body(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in body.items() if key in {"model", "input", "tools", "reasoning"}}

    def _response_state(self, response: Mapping[str, Any], generation: Generation) -> str | None:
        output = response.get("output", [])
        return self._remember_state(output) if output else None

    def _parse(self, response: Mapping[str, Any], details: dict[str, Any]) -> Generation:
        output = response.get("output", [])
        if not isinstance(output, list):
            raise RuntimeFailure("provider_invalid_output")
        texts, calls, hosted, citations, refusal = [], [], [], [], False
        for item in output:
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        texts.append(block["text"])
                        for annotation in block.get("annotations", []):
                            if not isinstance(annotation, Mapping) or annotation.get("type") not in {"url_citation", "file_citation"}:
                                raise UnsupportedCapability("unsupported Responses citation")
                            citations.append(dict(annotation))
                    elif block.get("type") == "refusal":
                        refusal = True
                    else:
                        raise UnsupportedCapability("unsupported Responses content block")
            elif item.get("type") == "function_call":
                try:
                    arguments = json.loads(item["arguments"])
                    calls.append(ToolCall(item["call_id"], item["name"], arguments))
                except (ValueError, KeyError, TypeError, ContractError):
                    raise RuntimeFailure("provider_invalid_tool_call") from None
            elif item.get("type") in {"web_search_call", "file_search_call"}:
                tool_type = item["type"].removesuffix("_call")
                if tool_type not in {tool.type for tool in self.hosted_tools}:
                    raise UnsupportedCapability("unconfigured hosted tool output")
                if not isinstance(item.get("id"), str) or item.get("status") not in {"completed", "in_progress", "searching", "failed", "incomplete"}:
                    raise RuntimeFailure("provider_invalid_hosted_call")
                hosted.append(dict(item, dispatch="provider"))
            elif item.get("type") != "reasoning":
                raise UnsupportedCapability("unsupported Responses output item")
        status = response.get("status")
        if response.get("error") or status == "failed":
            reason = "error"
        elif status == "incomplete":
            reason = "length" if (response.get("incomplete_details") or {}).get("reason") == "max_output_tokens" else "incomplete"
        elif status != "completed":
            reason = "incomplete"
        elif refusal:
            reason = "refusal"
        elif calls:
            reason = "tool_calls"
        else:
            reason = "completed"
        usage = self._usage(response, details)
        counts = {tool.type: sum(call["type"] == tool.type + "_call" for call in hosted) for tool in self.hosted_tools}
        hosted_cost = (sum(counts[tool.type] * tool.price_per_call_usd for tool in self.hosted_tools)
                       if all(tool.price_per_call_usd is not None for tool in self.hosted_tools) else None)
        if any(call["status"] != "completed" for call in hosted) or (self.hosted_tools and status != "completed"):
            hosted_cost = None
        if self.hosted_tools:
            details = dict(usage.details, hosted_call_counts=counts, hosted_cost_usd=hosted_cost,
                           hosted_cost_policy="caller supplied complete per-call price; no assumed service prices",
                           hosted_limits_exceeded=any(counts[tool.type] > tool.max_calls for tool in self.hosted_tools))
            usage = Usage(usage.input_tokens, usage.output_tokens,
                          usage.cost_usd + hosted_cost if usage.cost_usd is not None and hosted_cost is not None else None, details)
        traces = tuple(TraceEvent("hosted_tool_call", call) for call in hosted) + tuple(TraceEvent("citation", citation) for citation in citations)
        return Generation("".join(texts), tuple(calls), reason, usage,
                          {"continuation_items": output}, self.provider, self._observed_model(response),
                          hosted_calls=tuple(hosted), citations=tuple(citations), traces=traces)
