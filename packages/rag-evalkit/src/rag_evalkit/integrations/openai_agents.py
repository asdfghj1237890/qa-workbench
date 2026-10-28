"""Actual OpenAI Agents SDK Agent/Runner bridge with local detached traces.

SDK contracts: https://developers.openai.com/api/docs/guides/agents/running-agents
and https://developers.openai.com/api/docs/guides/agents/results . The SDK owns
the tool loop; rag-evalkit never substitutes an answer for an unexecuted task.
"""

from __future__ import annotations

import asyncio
import copy
import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, replace
from typing import Any

from ..contracts import ContractError, UnsupportedCapability
from ..runtime import (
    HarnessResult,
    Message,
    RunLimits,
    RuntimeFailure,
    ToolCall,
    ToolSpec,
    TraceEvent,
    Usage,
    safe_evidence,
    tool_result_text,
    validate_arguments,
)
from ._common import async_call, sdk_import


def _sdk_input(messages):
    inputs = []
    for message in messages:
        if message.provider_items or message.provider_state:
            raise UnsupportedCapability("SDK adapter does not accept opaque provider state")
        if not isinstance(message.content, str):
            raise UnsupportedCapability("SDK adapter currently accepts text messages only")
        if message.role == "tool":
            inputs.append({"type": "function_call_output", "call_id": message.tool_call_id, "output": message.content})
            continue
        if message.content or not message.tool_calls:
            inputs.append({"role": message.role, "content": message.content})
        for call in message.tool_calls:
            inputs.append({"type": "function_call", "call_id": call.id, "name": call.name,
                           "arguments": json.dumps(dict(call.arguments))})
    return inputs


def _portable_input(system, items, continuations=None):
    """Translate supported SDK protocol items; never stringify opaque state."""
    output = [Message("system", system)] if system else []
    continued = set()
    if isinstance(items, str):
        return [*output, Message("user", items)]
    for raw in items:
        item = raw if isinstance(raw, Mapping) else raw.model_dump()
        kind = item.get("type", "message")
        key = ("call", item.get("call_id")) if kind == "function_call" else ("message", item.get("id"))
        continuation = (continuations or {}).get(key)
        if continuation is not None:
            # The SDK sees normalized outputs. The originating portable model
            # alone owns opaque continuation state; restore its exact assistant
            # message once for the whole text/tool-call response, in place.
            identity = id(continuation)
            if identity not in continued:
                output.append(continuation)
                continued.add(identity)
            continue
        if kind == "function_call":
            output.append(Message("assistant", tool_calls=(ToolCall(item["call_id"], item["name"], json.loads(item["arguments"])),)))
        elif kind == "function_call_output":
            if not isinstance(item["output"], str):
                raise UnsupportedCapability("portable SDK bridge requires text tool outputs")
            output.append(Message("tool", item["output"], tool_call_id=item["call_id"]))
        elif kind == "message":
            role = "system" if item["role"] == "developer" else item["role"]
            content = item.get("content", "")
            if not isinstance(content, str):
                if not all(block.get("type") in {"input_text", "output_text"} for block in content):
                    raise UnsupportedCapability("portable SDK bridge supports text items only")
                content = "".join(block.get("text", "") for block in content)
            output.append(Message(role, content))
        else:
            raise UnsupportedCapability("unsupported SDK input item: " + str(kind))
    return output


class OpenAIAgentsHarness:
    """Inject an SDK Agent and optionally an SDK Runner instance.

    ``offline=True`` is an explicit declaration that the injected agent's models
    and tools perform no paid provider calls (for example an SDK Model fixture).
    Otherwise RunLimits.live_opt_in is required. SDK/provider HTTP retry counts
    are opaque: request limits bound logical model calls, with SDK retries off.
    A monetary budget on an opaque SDK model fails closed. Supplying a portable
    ``model=`` enables its preflight cost reservation and cumulative accounting;
    the SDK Runner still owns actual function-tool execution and conversation.
    """

    def __init__(self, agent, *, runner=None, offline=False, secrets=(), context=None, model=None):
        sdk = sdk_import("agents", "openai-agents")
        if not isinstance(agent, sdk.Agent):
            raise ContractError("OpenAI Agents adapter requires an SDK Agent")
        if runner is not None and runner is not sdk.Runner and not isinstance(runner, sdk.Runner):
            raise ContractError("runner must be the SDK Runner class or an instance")
        if not isinstance(offline, bool):
            raise ContractError("offline must be boolean")
        self._agent, self._runner = agent, runner or sdk.Runner()
        self._offline, self._secrets, self._context = offline, tuple(secrets), context
        self._model = model
        if model is not None and (not callable(getattr(model, "generate", None)) or not callable(getattr(model, "describe", None))):
            raise ContractError("portable SDK model must implement ModelAdapter")

    def describe(self):
        return safe_evidence({"harness": "openai_agents", "agent_name": self._agent.name,
                              "runner_type": self._runner.__name__ if isinstance(self._runner, type) else type(self._runner).__name__, "evidence_kind": "synthetic" if self._offline else "external_sdk",
                              "synthetic": self._offline, "request_unit": "logical_model_calls",
                              "budget": "portable_model_preflight_reservation" if self._model else "unsupported_fail_closed", "cancellation": "cooperative_async",
                              "model": self._model.describe() if self._model else {"ownership": "sdk_agent"},
                              "token_limits": "output_cap_and_postflight_input",
                              "provider_state": "not_exported", "remote_tracing": "disabled"}, self._secrets)

    def run(self, messages: Sequence[Message], *, tools: Sequence[ToolSpec] = (),
            handlers: Mapping[str, Callable[[Mapping[str, Any]], Any]] | None = None,
            limits: RunLimits | None = None, cancel: threading.Event | None = None) -> HarnessResult:
        sdk = sdk_import("agents", "openai-agents")
        limits = limits or RunLimits()
        history = list(copy.deepcopy(tuple(messages)))
        if not history or not all(isinstance(message, Message) for message in history):
            raise ContractError("harness requires messages")
        inputs = _sdk_input(history)
        specs, handlers = {tool.name: tool for tool in tools}, dict(handlers or {})
        if len(specs) != len(tools) or set(handlers) != set(specs):
            raise ContractError("portable tools require unique names and exactly matching handlers")
        native_names = {getattr(tool, "name", None) for tool in self._agent.tools}
        if native_names & set(specs):
            raise ContractError("portable tool names must not collide with SDK tools")
        traces = [TraceEvent("run_start", {"description": self.describe(), "limits": asdict(limits)})]
        state = {"requests": 0, "completed": 0, "usage": Usage(0, 0, 0.0 if self._model else None),
                 "inflight_tools": 0, "provider_requests": 0, "portable_uncertain": False,
                 "portable_tool_failure": None, "preflight_failure": None}
        lock = threading.Lock()
        stop = threading.Event()
        started = time.monotonic()
        deadline = started + limits.timeout_seconds
        secrets = self._secrets
        portable_model = self._model
        model_sanitize = getattr(portable_model, "sanitize_evidence", lambda value: value)

        def sanitize(value):
            return safe_evidence(model_sanitize(value), secrets)

        def check():
            if stop.is_set() or cancel is not None and cancel.is_set():
                raise RuntimeFailure("cancelled")
            if time.monotonic() >= deadline:
                raise RuntimeFailure("timeout")

        def remaining_model_limits(*, continuation=False):
            """Admission guard shared by model dispatch and pending tool effects."""
            check()
            with lock:
                if continuation and state["requests"] >= limits.max_turns:
                    raise RuntimeFailure("turn_limit")
                if continuation and state["requests"] >= limits.max_requests:
                    raise RuntimeFailure("request_limit")
                available_requests = limits.max_requests - state["provider_requests"]
                used = state["usage"].cost_usd
            expected = 2 if portable_model is not None and portable_model.describe().get("token_count") == "provider_endpoint" else 1
            if available_requests < expected:
                raise RuntimeFailure("request_limit")
            remaining = None
            if limits.max_budget_usd is not None:
                if used is None:
                    raise RuntimeFailure("usage_unknown")
                remaining = limits.max_budget_usd - used
                if remaining <= 0:
                    raise RuntimeFailure("budget_limit")
            call_limits = replace(limits, timeout_seconds=max(0.000001, deadline - time.monotonic()),
                                  max_requests=available_requests, max_budget_usd=remaining)
            if remaining is not None:
                estimate = getattr(portable_model, "estimate_cost", None)
                reserve = estimate(call_limits) if callable(estimate) else None
                if reserve is None:
                    raise RuntimeFailure("budget_unsupported")
                if reserve > remaining:
                    raise RuntimeFailure("budget_limit")
            return call_limits

        def before_tool(agent, tool):
            check()
            behavior = agent.tool_use_behavior
            stops = behavior == "stop_on_first_tool" or isinstance(behavior, Mapping) and tool.name in behavior.get("stop_at_tool_names", ())
            if not stops:
                try:
                    remaining_model_limits(continuation=True)
                except RuntimeFailure as exc:
                    state["preflight_failure"] = exc.code
                    raise

        class Hooks(sdk.RunHooks):
            async def on_llm_start(self, context, agent, system_prompt, input_items):
                check()
                with lock:
                    if state["requests"] >= limits.max_requests:
                        raise RuntimeFailure("request_limit")
                    state["requests"] += 1
                traces.append(TraceEvent("model_start", {"agent": safe_evidence(agent.name, secrets),
                                                         "request": state["requests"]}))

            async def on_llm_end(self, context, agent, response):
                raw = response.usage
                # SDK Usage defaults absent counters to zero. requests=0 cannot
                # establish that those defaults are reported provider usage.
                if portable_model is not None and response.raw_usage is not None:
                    part = Usage(**response.raw_usage["evalkit_usage"])
                elif raw is None or raw.requests < 1 or not (
                    raw.input_tokens or raw.output_tokens or getattr(raw, "request_usage_entries", ())
                    or isinstance(response.raw_usage, Mapping) and any(key in response.raw_usage for key in
                        ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens"))
                ):
                    part = Usage(details={"reported": False})
                else:
                    part = Usage(raw.input_tokens, raw.output_tokens, None, {"reported": True,
                                 "sdk_requests": raw.requests})
                with lock:
                    state["completed"] += 1
                    state["usage"] = state["usage"].plus(part)
                traces.append(TraceEvent("model_end", {"agent": safe_evidence(agent.name, secrets),
                                                       "usage": asdict(part)}))
                for item in response.output:
                    if getattr(item, "type", None) == "function_call":
                        traces.append(TraceEvent("tool_call", {"id": item.call_id, "name": item.name,
                                                               "arguments_json": sanitize(item.arguments)}))
                check()
                if part.input_tokens is not None and part.input_tokens > limits.max_input_tokens:
                    raise RuntimeFailure("input_token_limit_exceeded")
                if part.output_tokens is not None and part.output_tokens > limits.max_output_tokens:
                    raise RuntimeFailure("output_token_limit_exceeded")

            async def on_tool_start(self, context, agent, tool):
                before_tool(agent, tool)
                with lock:
                    state["inflight_tools"] += 1
                traces.append(TraceEvent("tool_start", {"tool": safe_evidence(getattr(tool, "name", type(tool).__name__), secrets)}))

            async def on_tool_end(self, context, agent, tool, result):
                with lock:
                    state["inflight_tools"] -= 1
                traces.append(TraceEvent("tool_end", {"tool": safe_evidence(getattr(tool, "name", type(tool).__name__), secrets),
                                                      "output": sanitize(result)}))
                check()

            async def on_handoff(self, context, from_agent, to_agent):
                check()
                traces.append(TraceEvent("handoff", {"from": safe_evidence(from_agent.name, secrets),
                                                    "to": safe_evidence(to_agent.name, secrets)}))

        portable = []
        for name, spec in specs.items():
            async def invoke(context, arguments, spec=spec, name=name):
                check()
                try:
                    decoded = json.loads(arguments)
                    validate_arguments(decoded, spec.input_schema)
                    result = await asyncio.to_thread(handlers[name], decoded)
                    check()
                    return tool_result_text(result)
                except RuntimeFailure as exc:
                    state["portable_tool_failure"] = exc.code
                    raise
                except Exception:
                    state["portable_tool_failure"] = "tool_error"
                    raise RuntimeFailure("tool_error") from None
            portable.append(sdk.FunctionTool(name, spec.description, dict(spec.input_schema), invoke,
                                             strict_json_schema=False, _use_default_failure_error_function=False))
        agent = self._agent.clone(tools=[*self._agent.tools, *portable])
        if portable_model is not None:
            if agent.handoffs or agent.mcp_servers or any(not isinstance(tool, sdk.FunctionTool)
                    or getattr(tool, "_is_agent_tool", False) for tool in agent.tools):
                raise UnsupportedCapability("portable model bridge supports function tools without nested agents, hosted tools or MCP")
            openai_types = sdk_import("openai.types.responses", "openai-agents")
            sdk_usage = sdk_import("agents.usage", "openai-agents")
            continuations = {}

            class PortableModel(sdk.Model):
                async def get_response(self, system_instructions, input, model_settings, tools, output_schema,
                                       handoffs, tracing, **kwargs):
                    check()
                    call_limits = remaining_model_limits()
                    remaining = call_limits.max_budget_usd
                    declarations = [ToolSpec(tool.name, tool.description, tool.params_json_schema) for tool in tools]
                    translated = _portable_input(system_instructions, input, continuations)
                    try:
                        with lock:
                            state["portable_uncertain"] = True
                        generation = await asyncio.to_thread(portable_model.generate, translated, tools=declarations,
                                                             limits=call_limits, cancel=cancel)
                    except RuntimeFailure as exc:
                        with lock:
                            state["provider_requests"] += exc.raw.get("api_requests", 0)
                        raise
                    consumed = generation.usage.details.get("api_requests", 1)
                    if isinstance(consumed, bool) or not isinstance(consumed, int) or consumed < 0:
                        raise RuntimeFailure("invalid_request_accounting")
                    with lock:
                        state["provider_requests"] += consumed
                        state["portable_uncertain"] = False
                    if state["provider_requests"] > limits.max_requests:
                        raise RuntimeFailure("request_limit")
                    if generation.finish_reason not in {"completed", "tool_calls"}:
                        raise RuntimeFailure(generation.finish_reason)
                    if getattr(generation, "hosted_calls", ()):
                        raise UnsupportedCapability("hosted portable model output cannot be normalized by this bridge")
                    if remaining is not None:
                        if generation.usage.cost_usd is None:
                            raise RuntimeFailure("usage_unknown")
                        if generation.usage.cost_usd > remaining:
                            raise RuntimeFailure("budget_exceeded")
                    outputs = []
                    continuation = Message("assistant", generation.text, generation.tool_calls,
                                           provider_state=generation.provider_state)
                    for call in generation.tool_calls:
                        outputs.append(openai_types.ResponseFunctionToolCall(type="function_call", call_id=call.id,
                                       name=call.name, arguments=json.dumps(dict(call.arguments))))
                        if generation.provider_state:
                            continuations[("call", call.id)] = continuation
                    if generation.text:
                        message_id = "evalkit-output-" + str(state["requests"])
                        outputs.append(openai_types.ResponseOutputMessage(id=message_id, type="message", role="assistant",
                                       status="completed", content=[openai_types.ResponseOutputText(type="output_text",
                                       text=generation.text, annotations=[])]))
                        if generation.provider_state:
                            continuations[("message", message_id)] = continuation
                    sdk_observation = sdk_usage.Usage(requests=1, input_tokens=generation.usage.input_tokens or 0,
                                                      output_tokens=generation.usage.output_tokens or 0,
                                                      total_tokens=(generation.usage.input_tokens or 0) + (generation.usage.output_tokens or 0))
                    return sdk.ModelResponse(output=outputs, usage=sdk_observation, response_id=None,
                                             raw_usage={"evalkit_usage": asdict(generation.usage)})

                async def stream_response(self, *args, **kwargs):
                    raise UnsupportedCapability("portable SDK bridge is non-streaming")
                    yield

            agent = agent.clone(model=PortableModel())
        settings = sdk.ModelSettings(max_tokens=limits.max_output_tokens, parallel_tool_calls=False,
                                     preserve_raw_usage=True,
                                     retry=sdk_import("agents.model_settings", "openai-agents").ModelRetrySettings(max_retries=0))
        config = sdk.RunConfig(tracing_disabled=True, trace_include_sensitive_data=False,
                               model_settings=settings)
        status, answer = "incomplete", ""
        try:
            check()
            if callable(getattr(portable_model, "contains_credentials", None)) and portable_model.contains_credentials([asdict(message) for message in history]):
                raise RuntimeFailure("credential_input")
            if not self._offline and not limits.live_opt_in:
                raise RuntimeFailure("live_opt_in_required")
            if limits.max_budget_usd is not None and portable_model is None:
                raise RuntimeFailure("budget_unsupported")

            async def execute():
                return await self._runner.run(agent, input=inputs, context=self._context,
                                              max_turns=limits.max_turns, hooks=Hooks(), run_config=config)

            result = async_call(execute, limits=limits, cancel=cancel)
            check()
            if state["portable_tool_failure"]:
                raise RuntimeFailure(state["portable_tool_failure"])
            if state["preflight_failure"]:
                raise RuntimeFailure(state["preflight_failure"])
            if getattr(result, "interruptions", None):
                raise RuntimeFailure("approval_required")
            answer = result.final_output
            if not isinstance(answer, str):
                # Structured output must remain structured; silently str() would
                # misrepresent the SDK's final output contract.
                raise RuntimeFailure("unsupported_structured_output")
            if not answer.strip():
                raise RuntimeFailure("incomplete")
            history.extend(self._messages(result.new_items, traces))
            status = "completed"
        except RuntimeFailure as exc:
            status, answer = exc.code, ""
            traces.append(TraceEvent("runtime_error", {"code": status, **exc.raw}))
        except Exception as exc:
            if state["preflight_failure"]:
                status = state["preflight_failure"]
            elif state["portable_tool_failure"]:
                status = state["portable_tool_failure"]
            elif isinstance(exc, getattr(sdk, "ModelRefusalError", ())):
                status = "refusal"
            elif isinstance(exc, sdk.MaxTurnsExceeded):
                status = "turn_limit"
            elif isinstance(exc, (ContractError, ValueError)):
                status = "contract_error"
            else:
                status = "error"
            traces.append(TraceEvent("runtime_error", {"code": status, "error_type": type(exc).__name__}))
        finally:
            stop.set()
        with lock:
            requests, completed, inflight_tools = state["requests"], state["completed"], state["inflight_tools"]
            observed_all_costs = requests == completed or portable_model is not None and not state["portable_uncertain"]
            usage = state["usage"] if observed_all_costs else Usage(details={"incomplete_observation": True})
        elapsed = time.monotonic() - started
        accounting = {"unit": "logical_model_calls", "started": requests, "completed": completed,
                      "in_flight": requests - completed, "http_requests": None,
                      "portable_model_requests": state["provider_requests"] if portable_model else None,
                      "operation_may_continue": requests != completed or inflight_tools > 0}
        traces.append(TraceEvent("run_end", {"status": status, "requests": requests,
                                            "latency_seconds": elapsed, "request_accounting": accounting}))
        public_history = tuple(Message(message.role, sanitize(message.content),
                                      tuple(ToolCall(sanitize(call.id), sanitize(call.name),
                                                     sanitize(call.arguments)) for call in message.tool_calls),
                                      tool_call_id=sanitize(message.tool_call_id)) for message in history)
        public_usage = Usage(usage.input_tokens, usage.output_tokens, usage.cost_usd, sanitize(usage.details))
        return HarnessResult(sanitize(answer), public_history,
                             tuple(TraceEvent(item.kind, sanitize(item.data), item.timestamp) for item in traces),
                             public_usage, status, requests, requests,
                             sanitize({"harness": self.describe(), "request_accounting": accounting,
                                            "latency_seconds": elapsed, "usage_complete": all(value is not None for value in
                                                (public_usage.input_tokens, public_usage.output_tokens, public_usage.cost_usd)),
                                            "evidence_kind": "synthetic" if self._offline else "external_sdk"}))

    def _messages(self, items, traces):
        sdk_items = sdk_import("agents.items", "openai-agents")
        output = []
        for item in items:
            kind = item.type
            raw = item.raw_item
            if kind == "message_output_item":
                if any(getattr(block, "type", None) == "refusal" for block in raw.content):
                    raise RuntimeFailure("refusal")
                output.append(Message("assistant", sdk_items.ItemHelpers.text_message_output(item)))
            elif kind == "tool_call_item" and getattr(raw, "type", None) == "function_call":
                try:
                    arguments = json.loads(raw.arguments)
                    output.append(Message("assistant", tool_calls=(ToolCall(raw.call_id, raw.name, arguments),)))
                except (TypeError, ValueError):
                    raise RuntimeFailure("invalid_tool_call") from None
            elif kind == "tool_call_output_item":
                value = raw if isinstance(raw, Mapping) else raw.model_dump()
                if value.get("type") != "function_call_output":
                    raise RuntimeFailure("unsupported_tool_output")
                output.append(Message("tool", tool_result_text(item.output), tool_call_id=value["call_id"]))
            elif kind in {"handoff_call_item", "handoff_output_item", "reasoning_item"}:
                # Reasoning/opaque state must never be copied into public traces.
                traces.append(TraceEvent("sdk_item", {"type": kind}))
            else:
                raise RuntimeFailure("unsupported_sdk_item")
        return output


def build_openai_agents_harness(config, **context):
    """Registry factory using the configured portable model, with no dynamic import.

    The SDK Agent is a real orchestration layer over the same separately selected
    model factor used by the other harnesses. The experiment runner owns limits.
    """
    unknown = set(config) - {"type", "agent_name", "instructions", "limits"}
    if unknown:
        raise ContractError("unknown OpenAI Agents harness options: " + ", ".join(sorted(unknown)))
    sdk = sdk_import("agents", "openai-agents")
    model = context["model"]
    agent = sdk.Agent(name=config.get("agent_name", "rag-evalkit"), instructions=config.get("instructions"))
    return OpenAIAgentsHarness(agent, model=model, offline=bool(model.describe().get("synthetic", False)))
