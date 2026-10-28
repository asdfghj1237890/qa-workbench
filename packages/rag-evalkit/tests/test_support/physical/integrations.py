"""Real SDK engines with free deterministic models and retrievers, no provider IO.

Contracts: LC RunnableParallel/assign and BaseRetriever from langchain_core;
LlamaIndex RetrieverQueryEngine.from_args + MockLLM + BaseRetriever;
OpenAI Agents Agent/Runner/ModelResponse/RunHooks from the installed SDK.
https://developers.openai.com/api/docs/guides/agents/results
https://reference.langchain.com/python/langchain-core/runnables/
https://developers.llamaindex.ai/python/framework-api-reference/query_engine/retriever/
Only the models/retrievers are fixtures. Framework routing/tool execution is real.
"""

import asyncio
import importlib.metadata
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

from rag_evalkit.integrations import (
    LangChainRagPipeline,
    LlamaIndexRagPipeline,
    OpenAIAgentsHarness,
)
from rag_evalkit.runtime import Message, RunLimits, ToolSpec

_TEXT = "The reference material says the observatory opens at nine."
_SECRET = "fixture-private-credential"
_ANSWER = "The observatory opens at nine. [source:source-9]"


@contextmanager
def _offline_network():
    # Windows asyncio builds its self-pipe using a loopback socket pair. Block
    # external connections while retaining that event-loop implementation detail.
    connect = socket.socket.connect

    def local_only(sock, address):
        if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1"}:
            raise RuntimeError("external_network_forbidden")
        return connect(sock, address)

    with patch("socket.socket.connect", local_only):
        yield


def _langchain(scenario, cancel):
    pytest.importorskip("langchain_core")
    from langchain_core.documents import Document
    from langchain_core.language_models.fake_chat_models import (
        FakeMessagesListChatModel,
    )
    from langchain_core.messages import AIMessage
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.runnables import (
        RunnableLambda,
        RunnableParallel,
        RunnablePassthrough,
    )

    class Retriever(BaseRetriever):
        def _get_relevant_documents(self, query, *, run_manager):
            if scenario == "error":
                raise RuntimeError(_SECRET)
            return [Document(id="chunk-9", page_content=_TEXT, metadata={"document_id": "document-9",
                             "source_id": "source-9", "title": "Observatory", "api_key": _SECRET})]

        async def _aget_relevant_documents(self, query, *, run_manager):
            if scenario == "cancel_inflight":
                cancel.set()
                await asyncio.sleep(1)
            if scenario == "timeout":
                await asyncio.sleep(1)
            return self._get_relevant_documents(query, run_manager=run_manager)

    usage = {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10} if scenario == "usage" else None
    response = AIMessage(content="" if scenario in {"empty", "refusal"} else _ANSWER, usage_metadata=usage,
                         additional_kwargs={"refusal": "Cannot answer"} if scenario == "refusal" else {})
    model = FakeMessagesListChatModel(responses=[response])
    prompt = RunnableLambda(lambda value: value["input"])
    pipeline = RunnableParallel(context=Retriever(), input=RunnablePassthrough()).assign(answer=prompt | model)
    return LangChainRagPipeline(pipeline, input_key=None, secrets=(_SECRET,)), "langchain-core"


def _llamaindex(scenario, cancel):
    pytest.importorskip("llama_index.core")
    from llama_index.core.llms import MockLLM
    from llama_index.core.query_engine import RetrieverQueryEngine
    from llama_index.core.retrievers import BaseRetriever
    from llama_index.core.schema import (
        NodeRelationship,
        NodeWithScore,
        RelatedNodeInfo,
        TextNode,
    )

    class Retriever(BaseRetriever):
        def _retrieve(self, query_bundle):
            if scenario == "error":
                raise RuntimeError(_SECRET)
            node = TextNode(id_="chunk-9", text=_TEXT,
                            metadata={"source_id": "source-9", "title": "Observatory", "api_key": _SECRET},
                            relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id="document-9")})
            return [NodeWithScore(node=node, score=0.75 if scenario == "score" else None)]

        async def _aretrieve(self, query_bundle):
            if scenario == "cancel_inflight":
                cancel.set()
                await asyncio.sleep(1)
            if scenario == "timeout":
                await asyncio.sleep(1)
            return self._retrieve(query_bundle)

    engine = RetrieverQueryEngine.from_args(retriever=Retriever(), llm=MockLLM(max_tokens=None), response_mode="compact")
    return LlamaIndexRagPipeline(engine, secrets=(_SECRET,)), "llama-index-core"


def observe_rag(framework, scenario):
    cancel = threading.Event()
    adapter, distribution = _langchain(scenario, cancel) if framework == "langchain" else _llamaindex(scenario, cancel)
    if scenario == "cancel":
        cancel.set()
    limits = RunLimits(timeout_seconds=0.03 if scenario == "timeout" else 10,
                       max_budget_usd=0.01 if scenario == "budget" else None)
    with patch.dict(os.environ, {"LANGCHAIN_TRACING_V2": "false", "LANGSMITH_TRACING": "false"}), \
            _offline_network():
        result = adapter.run("When does the observatory open?", limits=limits, cancel=cancel)
    return {"result": asdict(result), "description": adapter.describe(),
            "sdk_version": importlib.metadata.version(distribution), "leaked_secret": _SECRET in json.dumps(asdict(result))}


def observe_agents(scenario):
    sdk = pytest.importorskip("agents")
    from agents.items import ModelResponse
    from agents.usage import Usage as SdkUsage
    from openai.types.responses import (
        ResponseFunctionToolCall,
        ResponseFunctionWebSearch,
        ResponseOutputMessage,
        ResponseOutputRefusal,
        ResponseOutputText,
    )

    dispatched, tool_inputs = [], []

    class Model(sdk.Model):
        async def get_response(self, *args, **kwargs):
            dispatched.append(kwargs.get("input", args[1] if len(args) > 1 else None))
            if scenario == "cancel_inflight":
                cancel.set()
                await asyncio.sleep(1)
            if scenario == "timeout":
                await asyncio.sleep(1)
            if scenario == "error":
                raise RuntimeError(_SECRET)
            input_items = kwargs.get("input", [])
            tool_done = any(isinstance(item, dict) and item.get("type") == "function_call_output" for item in input_items)
            if scenario in {"tool", "portable_tool", "portable_tool_error", "unknown_tool", "request_limit", "turn_limit", "tool_error"} and not tool_done:
                output = [ResponseFunctionToolCall(id="fc-9", type="function_call", call_id="call-9",
                          name="unknown" if scenario == "unknown_tool" else "lookup", arguments='{"query":"observatory"}')]
            else:
                answer = _SECRET + " " + _ANSWER if scenario == "secret" else _ANSWER
                output = [ResponseOutputMessage(id="msg-9", role="assistant", status="completed", type="message",
                          content=[ResponseOutputText(type="output_text", text=answer, annotations=[])])]
                if scenario == "refusal":
                    output[0].content = [ResponseOutputRefusal(type="refusal", refusal="Cannot answer this request.")]
                if scenario == "unsupported_hosted":
                    output.insert(0, ResponseFunctionWebSearch(id="search-9", type="web_search_call", status="completed",
                                  action={"type": "search", "query": "observatory"}))
                if scenario == "empty_output":
                    output = []
            raw_usage = None
            usage = SdkUsage() if scenario == "unknown_usage" else SdkUsage(requests=1, input_tokens=7, output_tokens=3, total_tokens=10)
            if scenario == "transport_unknown_usage":
                from agents.models.openai_responses import (
                    _mark_transport_request_without_usage,
                    _usage_from_response,
                )
                from openai.types.responses import Response

                transport_response = Response.model_construct(id="transport-fixture", usage=None)
                _mark_transport_request_without_usage(transport_response)
                usage = _usage_from_response(transport_response)
            if scenario == "reported_zero_usage":
                usage = SdkUsage(requests=1)
                raw_usage = {"input_tokens": 0, "output_tokens": 0}
            return ModelResponse(output=output, usage=usage, response_id="opaque-private-state", raw_usage=raw_usage)

        async def stream_response(self, *args, **kwargs):
            raise NotImplementedError("streaming is outside this harness adapter's contract")
            yield

    @sdk.function_tool(failure_error_function=None)
    def lookup(query: str) -> str:
        """Look up observatory source material."""
        tool_inputs.append(query)
        if scenario == "tool_error":
            raise RuntimeError(_SECRET)
        return _TEXT

    has_native_tools = scenario in {"tool", "unknown_tool", "request_limit", "turn_limit", "tool_error"} or scenario.startswith("bridge")
    agent = sdk.Agent(name="Offline observatory", model=Model(), tools=[lookup] if has_native_tools else [])
    bridge = None
    transport_calls = []
    continuation_types = []
    if scenario.startswith("bridge"):
        from rag_evalkit.models import HTTPResponse, OpenAIResponsesModel, Pricing

        def transport(url, headers, body, timeout):
            transport_calls.append(url.rsplit("/", 1)[-1])
            if url.endswith("input_tokens"):
                return HTTPResponse(200, {"input_tokens": 7})
            tool_done = any(item.get("type") == "function_call_output" for item in body["input"])
            if tool_done:
                continuation_types.extend(item.get("type", "message") for item in body["input"])
                if scenario == "bridge_reasoning" and not any(item.get("type") == "reasoning" and
                        item.get("encrypted_content") == "opaque-cipher" for item in body["input"]):
                    return HTTPResponse(400, {"error": {"code": "missing_reasoning_continuation"}})
            if not tool_done:
                output = [{"type": "function_call", "id": "fc-9", "call_id": "call-9", "name": "lookup",
                           "arguments": '{"query":"observatory"}'}]
                if scenario == "bridge_reasoning":
                    output.insert(0, {"type": "reasoning", "id": "reasoning-9", "summary": [], "encrypted_content": "opaque-cipher"})
            else:
                output = [{"type": "message", "id": "msg-9", "role": "assistant", "content": [{"type": "output_text", "text": _ANSWER}]}]
            return HTTPResponse(200, {"id": "private-provider-response", "status": "completed", "model": "fixture-model",
                                "output": output, "usage": {"input_tokens": 7, "output_tokens": 3}})

        bridge = OpenAIResponsesModel("fixture-model", api_key=_SECRET, pricing=Pricing(1000, 1000),
                                      transport=transport, evidence_kind="protocol_fixture")
    harness = OpenAIAgentsHarness(agent, offline=scenario != "live_guard", secrets=(_SECRET,), model=bridge)
    options = {}
    if scenario in {"portable_tool", "portable_tool_error"}:
        spec = ToolSpec("lookup", "Read source material", {"type": "object", "properties": {"query": {"type": "string"}},
                        "required": ["query"], "additionalProperties": False})

        def handle(arguments):
            tool_inputs.append(arguments["query"])
            if scenario == "portable_tool_error":
                raise RuntimeError(_SECRET)
            return _TEXT

        options = {"tools": [spec], "handlers": {"lookup": handle}}
    cancel = threading.Event()
    if scenario == "cancel":
        cancel.set()
    limits = RunLimits(timeout_seconds=0.03 if scenario == "timeout" else 10,
                       max_requests=1 if scenario == "request_limit" else 2 if scenario == "bridge_request_exhausted" else 4,
                       max_turns=1 if scenario in {"turn_limit", "bridge_turn_exhausted"} else 4,
                       max_input_tokens=8 if bridge else 16384, max_output_tokens=4 if bridge else 1024,
                       max_budget_usd=0.01 if scenario == "budget" else 0.021 if scenario == "bridge_budget_exhausted"
                       else 0.03 if scenario == "bridge_budget" else None)
    with _offline_network():
        result = harness.run([Message("user", "When does the observatory open?")], limits=limits, cancel=cancel, **options)
    detached = asdict(result)
    return {"result": detached, "description": harness.describe(), "dispatch_count": len(dispatched),
            "tool_inputs": tool_inputs, "leaked_secret": _SECRET in json.dumps(detached),
            "leaked_state": any(secret in json.dumps(detached) for secret in ("opaque-private-state", "opaque-cipher", "reasoning-9")),
            "transport_calls": transport_calls,
            "continuation_types": continuation_types,
            "sdk_version": importlib.metadata.version("openai-agents")}


def observe_import_isolation():
    code = "import sys; import rag_evalkit.integrations; print(','.join(name for name in ('agents','langchain_core','llama_index') if name in sys.modules))"
    process = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=False)
    return {"returncode": process.returncode, "imported_frameworks": process.stdout.strip(), "stderr": process.stderr}


def observe_example_factor(framework, factor):
    pytest.importorskip("langchain_core" if framework == "langchain" else "llama_index.core")
    path = Path(__file__).resolve().parents[3] / "examples" / "integrations-plugin" / "external_evalkit_demo.py"
    spec = importlib.util.spec_from_file_location("evalkit_test_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        getattr(module, framework)({"type": "example_" + framework}, variant={factor: {"sentinel": "requested-factor"}})
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc)}
    return {"error": None, "message": ""}
