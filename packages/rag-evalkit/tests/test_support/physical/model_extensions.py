"""Physical protocol fixtures plus actual loopback HTTP SSE.

Contract: models/streaming.py StreamAccumulator, OpenAI Responses
streaming-responses/images-vision/tools-web-search/tools-file-search guides;
Anthropic build-with-claude/streaming and vision. These are synthetic protocol
tests with no model API access, not live model quality or billing evidence.
"""

import copy
import json
import re
import threading
import time
from contextlib import nullcontext
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from rag_evalkit.builtins import build_pipeline, default_registry
from rag_evalkit.contracts import ContractError, UnsupportedCapability
from rag_evalkit.datasets import load_experiment
from rag_evalkit.experiments import create_run, execute
from rag_evalkit.harnesses import ToolLoopHarness
from rag_evalkit.models import (
    AnthropicMessagesModel,
    HTTPResponse,
    HTTPStreamResponse,
    OpenAIResponsesModel,
    Pricing,
)
from rag_evalkit.models.http import urllib_stream_transport, urllib_transport
from rag_evalkit.runtime import (
    HostedToolSpec,
    ImageBlock,
    Message,
    RunLimits,
    RuntimeFailure,
    TextBlock,
    ToolSpec,
)

EXPECTED_CREDENTIAL = "fixture-key-sensitive"
REQUESTED_MODEL = "fixture-configured-alias"
OBSERVED_MODEL = "fixture-snapshot-2026-10-21"


def _identity_model(provider, actual_mode, streaming):
    def identity(response):
        result = copy.deepcopy(response)
        if actual_mode == "missing":
            result.pop("model", None)
        else:
            result["model"] = {"changed": OBSERVED_MODEL, "null": None,
                               "bad_type": {"alias": REQUESTED_MODEL}, "credential": EXPECTED_CREDENTIAL}[actual_mode]
        return result

    response = identity(_response(provider))

    def transport(url, headers, body, timeout):
        return HTTPResponse(200, {"input_tokens": 10} if url.endswith(("input_tokens", "count_tokens")) else response)

    def stream_transport(url, headers, body, timeout):
        events = _events(provider)
        if provider == "openai":
            events[-1]["response"] = response
        else:
            events[0]["message"] = identity(events[0]["message"])
        return HTTPStreamResponse(200, [_frame(event) for event in events])

    model = _model_type(provider)(REQUESTED_MODEL, api_key=EXPECTED_CREDENTIAL, evidence_kind="protocol_fixture",
                                 pricing=Pricing(1, 2), transport=transport, stream_transport=stream_transport, streaming=streaming)
    return model, response


def model_identity_run(provider, actual_mode, streaming):
    model, response = _identity_model(provider, actual_mode, streaming)
    parsed = generation = error = None
    try:
        parsed = model._parse(response, {})
        generation = model.generate([Message("user", "Question")])
    except RuntimeFailure as exc:
        error = {"type": type(exc).__name__, "code": exc.code, "raw": copy.deepcopy(exc.raw)}
    result = ToolLoopHarness(model).run([Message("user", "Question")])
    return {"parsed": parsed, "generation": generation, "error": error, "result": result,
            "description": model.describe()}


def model_identity_experiment(output, provider, actual_mode, streaming):
    """Exercise experiments.execute's persisted observation of real model traces."""
    root = Path(__file__).resolve().parents[3]
    manifest, dataset = load_experiment(root / "examples" / "experiment.json")
    manifest["variants"] = [manifest["variants"][0]]
    manifest["repeats"] = 1
    manifest["variants"][0]["model"] = {"type": "identity_fixture"}
    registry = default_registry()
    registry.register("model", "identity_fixture", lambda config, **context: _identity_model(provider, actual_mode, streaming)[0])
    store = create_run(output, manifest, dataset)
    report = execute(store, lambda config, data: build_pipeline(config, data, registry=registry))
    return report["rows"][0]


def split_credential_stream(provider, channel, fragment_size, escaped=False, partial_prefix=False):
    """Drive real public stream delivery, including deltas received before error.

    Contract: HTTPModel.stream must protect configured credentials across delta
    boundaries; function argument strings can legally use JSON Unicode escapes.
    """
    secret = EXPECTED_CREDENTIAL
    text = "Safe " + (secret[:12] if partial_prefix else secret)
    is_tool = channel == "tool"
    argument = json.dumps({"query": text})
    if escaped:
        argument = "".join("\\u" + format(ord(character), "04x") if character.isalpha() or character == "-" else character for character in argument)
    payload = argument if is_tool else text
    parts = [payload[index:index + fragment_size] for index in range(0, len(payload), fragment_size)]
    if provider == "openai":
        if is_tool:
            events = [{"type": "response.function_call_arguments.delta", "item_id": "fc1", "delta": part} for part in parts]
            response = _response(provider, "tool")
            response["output"][0]["arguments"] = argument
        else:
            events = [{"type": "response.output_text.delta", "delta": part} for part in parts]
            response = _response(provider)
            response["output"][0]["content"][0]["text"] = text
        events.append({"type": "response.completed", "response": response})
    else:
        original = _events(provider, "tool" if is_tool else "normal")
        events = original[:2] + [
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "input_json_delta", "partial_json": part} if is_tool else {"type": "text_delta", "text": part}}
            for part in parts] + original[-3:]
    model = _model_type(provider)("fixture", api_key=secret, evidence_kind="protocol_fixture", pricing=Pricing(1, 2),
                                 transport=lambda *args: HTTPResponse(200, {"input_tokens": 10}),
                                 stream_transport=lambda *args: HTTPStreamResponse(200, [_frame(event) for event in events]))
    public_events, failure = [], None
    try:
        for event in model.stream([Message("user", "Question")]):
            public_events.append(event)
    except RuntimeFailure as exc:
        failure = {"type": type(exc).__name__, "code": exc.code, "raw": copy.deepcopy(exc.raw)}
    field = "arguments_delta" if is_tool else "text"
    public_text = "".join(event.data[field] for event in public_events if event.kind == ("tool_call_delta" if is_tool else "text_delta"))
    decoded_public = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), public_text)
    return {"public_events": public_events, "public_text": public_text, "decoded_public": decoded_public,
            "failure": failure, "expected_text": payload,
            "final": next((event.generation for event in public_events if event.generation is not None), None)}


def _model_type(provider):
    return OpenAIResponsesModel if provider == "openai" else AnthropicMessagesModel


def _response(provider, mode="normal"):
    if provider == "openai":
        response = {"id": "response-fixture", "model": "fixture-resolved", "status": "completed",
                    "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hello 世界"}]}],
                    "usage": {"input_tokens": 10, "output_tokens": 5}}
        if mode == "tool":
            response["output"] = [{"type": "function_call", "id": "fc1", "call_id": "call1", "name": "lookup", "arguments": '{"query":"evidence"}'}]
        if mode == "hosted":
            response["output"].insert(0, {"type": "web_search_call", "id": "web1", "status": "completed", "action": {"type": "search", "query": "evidence", "sources": [{"type": "url", "url": "https://example.org/source"}]}})
            response["output"].insert(1, {"type": "file_search_call", "id": "file1", "status": "completed", "queries": ["evidence"], "results": [{"file_id": "f1", "text": "Source evidence", "score": 0.9}]})
            response["output"][-1]["content"][0]["annotations"] = [{"type": "url_citation", "url": "https://example.org/source", "start_index": 0, "end_index": 5, "title": "Source"}, {"type": "file_citation", "file_id": "f1", "filename": "source.txt", "index": 0}]
    else:
        response = {"id": "message-fixture", "type": "message", "model": "fixture-resolved", "role": "assistant",
                    "content": [{"type": "text", "text": "Hello 世界"}], "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5}}
    if mode == "missing_usage":
        response.pop("usage")
    if mode == "opaque":
        response["output"].insert(0, {"type": "reasoning", "id": "r1", "summary": [], "encrypted_content": "opaque-secret-blob"})
    return response


def _events(provider, mode="normal"):
    response = _response(provider, mode)
    if provider == "openai":
        events = [{"type": "response.created", "response": {"id": "response-fixture", "status": "in_progress"}},
                  {"type": "response.output_text.delta", "delta": "Hello "},
                  {"type": "response.output_text.delta", "delta": "世界"},
                  {"type": "response.completed", "response": response}]
        if mode == "tool":
            events = [{"type": "response.function_call_arguments.delta", "item_id": "fc1", "delta": '{"query":'},
                      {"type": "response.function_call_arguments.delta", "item_id": "fc1", "delta": '"evidence"}'},
                      {"type": "response.completed", "response": response}]
        if mode == "hosted":
            events.insert(1, {"type": "response.web_search_call.searching", "item_id": "web1"})
        if mode == "inconsistent":
            events[-1]["response"]["output"][0]["content"][0]["text"] = "Different terminal"
        if mode == "tool_inconsistent":
            events = _events(provider, "tool")
            events[-1]["response"]["output"][0]["arguments"] = '{"query":"different"}'
    else:
        events = [{"type": "message_start", "message": {"id": "message-fixture", "type": "message", "model": "fixture-resolved", "role": "assistant", "content": [], "usage": {"input_tokens": 10, "output_tokens": 0}}},
                  {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello "}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "世界"}},
                  {"type": "content_block_stop", "index": 0},
                  {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 5}},
                  {"type": "message_stop"}]
        if mode == "tool":
            events[1]["content_block"] = {"type": "tool_use", "id": "call1", "name": "lookup", "input": {}}
            events[2]["delta"] = {"type": "input_json_delta", "partial_json": '{"query":'}
            events[3]["delta"] = {"type": "input_json_delta", "partial_json": '"evidence"}'}
            events[5]["delta"]["stop_reason"] = "tool_use"
        if mode == "missing_usage":
            events[0]["message"].pop("usage")
            events[5]["usage"] = {}
        if mode == "inconsistent":
            events.pop(4)
        if mode == "tool_inconsistent":
            events = _events(provider, "tool")
            events[3]["delta"]["partial_json"] = "broken"
    if mode in {"truncated", "cancel", "timeout", "error", "malformed", "credential"}:
        events = events[:3]
        if mode == "error":
            events.append({"type": "error", "error": {"type": "overloaded_error", "message": "synthetic"}})
        if mode == "credential":
            events.append({"type": "response.output_text.delta", "delta": "fixture-key-sensitive"})
    return events


def _frame(event):
    return ("event: " + event["type"] + "\r\ndata: " + json.dumps(event, ensure_ascii=False) + "\r\n\r\n").encode("utf-8")


def streaming_run(provider, mode="normal", *, iterator=False):
    requests = []
    closed = []
    cancel = threading.Event()
    entered_stream, expire_deadline, stream_closed = threading.Event(), threading.Event(), threading.Event()
    clock_origin = time.monotonic()

    def controlled_clock():
        # HTTPModel/harness/runtime all use monotonic deadlines. Keep their
        # elapsed time fixed until both observed HTTP starts and partial SSE
        # parsing have occurred; scheduler load cannot skip those premises.
        return clock_origin + (1 if expire_deadline.is_set() else 0)

    def transport(url, headers, body, timeout):
        requests.append(copy.deepcopy(body))
        return HTTPResponse(200, {"input_tokens": 10})

    def stream_transport(url, headers, body, timeout):
        requests.append(copy.deepcopy(body))
        entered_stream.set()

        def chunks():
            for event in _events(provider, mode):
                framed = _frame(event)
                # Byte-level fragmentation also splits multibyte UTF-8 text.
                for index in range(0, len(framed), 7):
                    yield framed[index:index + 7]
            if mode == "cancel":
                cancel.set()
                yield b": cancelled\n\n"
            if mode == "timeout":
                if not entered_stream.is_set():
                    raise AssertionError("deadline advanced before entering the observed HTTP stream")
                expire_deadline.set()
                yield b": controlled deadline expired\n\n"
            if mode == "malformed":
                yield b'data: {broken}\n\n'

        def close():
            closed.append(True)
            stream_closed.set()

        return HTTPStreamResponse(200, chunks(), close)

    model = _model_type(provider)("fixture", api_key="fixture-key-sensitive", transport=transport,
                                 stream_transport=stream_transport, evidence_kind="protocol_fixture", streaming=True,
                                 pricing=Pricing(1, 2))
    limits = RunLimits(timeout_seconds=0.05 if mode == "timeout" else 2,
                       max_stream_bytes=100 if mode == "bytes" else 4 * 1024 * 1024,
                       max_stream_events=1 if mode == "events" else 10000)
    events = []
    with patch.object(time, "monotonic", controlled_clock) if mode == "timeout" else nullcontext():
        try:
            if iterator:
                error = None
                try:
                    events = list(model.stream([Message("user", "Question")], limits=limits, cancel=cancel))
                except RuntimeFailure as exc:
                    error = {"type": type(exc).__name__, "code": exc.code, "raw": copy.deepcopy(exc.raw)}
                result = next((event.generation for event in events if event.generation), None)
            else:
                error = None
                result = ToolLoopHarness(model).run([Message("user", "Question")], limits=limits, cancel=cancel)
        finally:
            if mode == "timeout" and not stream_closed.wait(2):
                raise AssertionError("timed-out HTTP stream did not close before restoring the clock")
    return {"result": result, "events": events, "requests": requests, "closed": closed, "error": error,
            "description": model.describe()}


def progressive_loopback(provider):
    release = threading.Event()
    terminal_sent = threading.Event()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if self.path.endswith(("input_tokens", "count_tokens")) else "text/event-stream")
            self.end_headers()
            if self.path.endswith(("input_tokens", "count_tokens")):
                self.wfile.write(b'{"input_tokens":10}')
                return
            events = _events(provider)
            for index, event in enumerate(events):
                self.wfile.write(_frame(event))
                self.wfile.flush()
                if index == (1 if provider == "openai" else 2):
                    release.wait(1)
            terminal_sent.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def local_url(url):
        return "http://127.0.0.1:" + str(server.server_port) + urlsplit(url).path

    def json_transport(url, headers, body, timeout):
        return urllib_transport(local_url(url), headers, body, timeout)

    def sse_transport(url, headers, body, timeout):
        return urllib_stream_transport(local_url(url), headers, body, timeout)

    model = _model_type(provider)("fixture", api_key=EXPECTED_CREDENTIAL, transport=json_transport, stream_transport=sse_transport,
                                 evidence_kind="protocol_fixture", pricing=Pricing(1, 2))
    observed = []
    progressive = False
    try:
        for event in model.stream([Message("user", "Question")], limits=RunLimits(timeout_seconds=2)):
            observed.append(event)
            if event.kind == "text_delta" and not release.is_set():
                progressive = not terminal_sent.is_set()
                release.set()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
    return {"events": observed, "progressive": progressive, "requests": requests}


def image_run(provider, mode="url"):
    requests = []
    image = ImageBlock(base64_data="aW1hZ2U=", media_type="image/png") if mode == "base64" else ImageBlock(url="https://example.org/image.png")

    def transport(url, headers, body, timeout):
        requests.append(copy.deepcopy(body))
        return HTTPResponse(200, {"input_tokens": 10} if url.endswith(("input_tokens", "count_tokens")) else _response(provider))

    model = _model_type(provider)("fixture", transport=transport, evidence_kind="protocol_fixture", image_input=mode != "disabled")
    result = ToolLoopHarness(model).run([Message("user", (TextBlock("Describe"), image))])
    return {"result": result, "requests": requests, "description": model.describe()}


def hosted_run(mode="normal"):
    requests, dispatched = [], []
    tools = [HostedToolSpec("web_search", price_per_call_usd=None if mode in {"unknown", "live_unknown"} else 0.01, max_calls=2),
             HostedToolSpec("file_search", {"vector_store_ids": ["vs_fixture"], "max_num_results": 2}, 0.02, 1)]

    def transport(url, headers, body, timeout):
        requests.append(copy.deepcopy(body))
        response = _response("openai", "hosted")
        if mode == "limit":
            response["output"].pop(1)
            response["output"].extend(dict(copy.deepcopy(response["output"][0]), id="web" + str(i)) for i in (2, 3))
        return HTTPResponse(200, {"input_tokens": 10} if url.endswith("input_tokens") else response)

    def stream_transport(url, headers, body, timeout):
        requests.append(copy.deepcopy(body))
        return HTTPStreamResponse(200, [_frame(event) for event in _events("openai", "hosted")])

    model = OpenAIResponsesModel("fixture", transport=transport, api_key="fixture-key-sensitive",
                                evidence_kind="live_http" if mode == "live_unknown" else "protocol_fixture",
                                pricing=Pricing(1, 2), hosted_tools=tools,
                                streaming=mode == "streaming", stream_transport=stream_transport)
    result = ToolLoopHarness(model).run([Message("user", "Research")],
                                       tools=[ToolSpec("lookup", "Lookup", {"type": "object"})],
                                       handlers={"lookup": lambda arguments: dispatched.append(arguments)},
                                       limits=RunLimits(live_opt_in=True, max_budget_usd=0.01 if mode == "budget" else (None if mode == "unknown" else 1)))
    return {"result": result, "requests": requests, "dispatched": dispatched, "reservation": model.estimate_cost(RunLimits())}


def failure_after_paid_turn():
    generation_count = 0
    dispatched = []

    def stream_transport(url, headers, body, timeout):
        nonlocal generation_count
        generation_count += 1
        return HTTPStreamResponse(200, [_frame(event) for event in _events("openai", "tool" if generation_count == 1 else "truncated")])

    model = OpenAIResponsesModel("fixture", streaming=True, evidence_kind="protocol_fixture", pricing=Pricing(1, 2),
                                transport=lambda *args: HTTPResponse(200, {"input_tokens": 10}), stream_transport=stream_transport)
    result = ToolLoopHarness(model).run([Message("user", "Question")],
                                       tools=[ToolSpec("lookup", "Lookup", {"type": "object"})],
                                       handlers={"lookup": lambda arguments: dispatched.append(arguments)})
    return {"result": result, "dispatched": dispatched}


def invalid_content(mode):
    try:
        if mode == "audio":
            Message("user", ({"type": "audio", "data": "payload"},))
        elif mode == "bad_base64":
            ImageBlock(base64_data="?", media_type="image/png")
        elif mode == "credential_url":
            ImageBlock(url="https://name:password@example.org/image")
        elif mode == "hosted_anthropic":
            AnthropicMessagesModel("fixture", hosted_tools=[HostedToolSpec("web_search")])
        elif mode == "assistant_image":
            Message("assistant", (ImageBlock(url="https://example.org/image"),))
    except (ContractError, UnsupportedCapability) as exc:
        return type(exc).__name__
    return None


def opaque_stream():
    response = _response("openai", "opaque")
    model = OpenAIResponsesModel("fixture", evidence_kind="protocol_fixture", streaming=True,
                                transport=lambda *args: HTTPResponse(200, {"input_tokens": 10}),
                                stream_transport=lambda *args: HTTPStreamResponse(200, [_frame({"type": "response.completed", "response": response})]))
    generation = model.generate([Message("user", "Question")])
    return {"public": asdict(generation), "private": model._resolve_state(generation.provider_state)}
