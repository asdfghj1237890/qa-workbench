"""Real socket HTTP fixture and explicitly opted-in embedding services.

Contract: OpenAI /embeddings request/data[].index/usage follows
https://developers.openai.com/api/reference/resources/embeddings/methods/create.
TEI /embed inputs/normalize/truncate/prompt_name and array response follow
https://github.com/huggingface/text-embeddings-inference/blob/main/router/src/http/types.rs.
Loopback responses exercise transport and protocol, not semantic model quality.
"""

import json
import os
import struct
import threading
import time
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rag_evalkit.contracts import ContractError
from rag_evalkit.embeddings import (
    EmbeddingLimits,
    EmbeddingPricing,
    OpenAIEmbedding,
    TEIEmbedding,
)
from rag_evalkit.runtime import RequestLedger, RuntimeFailure, with_request_ledger

_CREDENTIAL = "fixture-only-sensitive"
_TEXTS = ["A newly supplied English passage.", "任意的新文字，可直接批次嵌入。", "A third unseen passage."]


class _Server:
    def __init__(self, backend, scenario):
        self.requests, self.redirect_hits, self.entered = [], [], threading.Event()
        self.release = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                if self.path == "/redirected":
                    outer.redirect_hits.append(self.headers.get("Authorization"))
                request_bytes = self.rfile.read(int(self.headers["Content-Length"]))
                body = json.loads(request_bytes)
                outer.requests.append({"path": self.path, "body": body,
                                       "wire_utf8_hex": request_bytes.hex(),
                                       "credential_received": self.headers.get("Authorization") == "Bearer " + _CREDENTIAL})
                outer.entered.set()
                if scenario in {"timeout", "cancel_in_flight"}:
                    outer.release.wait(0.5)
                texts = body.get("input", body.get("inputs"))
                vectors = [[3.0, 4.0] if index == 0 else [0.1000000001, 0.2] for index in range(len(texts))]
                if scenario == "dimensions":
                    vectors[0] = [1.0]
                elif scenario == "zero":
                    vectors[0] = [0.0, 0.0]
                elif scenario == "nan":
                    vectors[0] = [float("nan"), 1.0]
                elif scenario == "infinity":
                    vectors[0] = [float("inf"), 1.0]
                elif scenario == "bool":
                    vectors[0] = [True, 1.0]
                elif scenario == "overflow":
                    vectors[0] = [1e40, 1.0]
                elif scenario == "underflow":
                    vectors[0] = [1e-100, 1e-100]
                count = len(texts)
                if backend == "openai":
                    payload = {"model": "test-model-resolved", "data": [
                        {"index": index, "embedding": vector} for index, vector in reversed(list(enumerate(vectors)))],
                        "usage": {"prompt_tokens": count * 3, "total_tokens": count * 3}}
                    if scenario == "duplicate_index":
                        payload["data"][-1]["index"] = payload["data"][0]["index"]
                    elif scenario == "invalid_index":
                        payload["data"][0]["index"] = True
                    elif scenario == "missing_index":
                        del payload["data"][0]["index"]
                    elif scenario == "usage_unknown":
                        del payload["usage"]
                    elif scenario == "usage_negative":
                        payload["usage"]["prompt_tokens"] = -1
                    elif scenario == "model_echo":
                        payload["model"] = _CREDENTIAL
                    elif scenario == "model_change" and len(outer.requests) > 1:
                        payload["model"] = "another-model"
                    elif scenario == "count":
                        payload["data"].pop()
                else:
                    payload = vectors[:-1] if scenario == "count" else vectors
                failed = scenario == "http_error" or (scenario == "partial_http_error" and len(outer.requests) > 1)
                status = 307 if scenario == "redirect" else 429 if failed else 200
                if failed:
                    payload = {"error": _CREDENTIAL}
                encoded = b"{" if scenario == "invalid_json" else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                if scenario == "redirect":
                    self.send_header("Location", outer.endpoint + "/redirected")
                if backend == "tei" and scenario != "usage_unknown":
                    self.send_header("x-compute-tokens", "-1" if scenario == "usage_negative" else str(count * 3))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except OSError:
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.endpoint = "http://127.0.0.1:" + str(self.server.server_port)
        self.worker = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, *_args):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=1)


def _adapter(backend, endpoint, **options):
    kind = OpenAIEmbedding if backend == "openai" else TEIEmbedding
    defaults = {"model_version": "declared-model-v1", "endpoint": endpoint, "api_key": _CREDENTIAL,
                "limits": EmbeddingLimits(live_opt_in=True, max_input_tokens=1000, max_budget_usd=0.001),
                "pricing": EmbeddingPricing(1.0)}
    if backend == "openai":
        defaults["token_bound"] = "utf8_bytes"
    defaults.update(options)
    return kind("test-model", 2, **defaults)


def observe_embeddings(backend="openai", scenario="valid", *, normalize=False, batch_size=32, unpriced=False):
    with _Server(backend, scenario) as server:
        limits = EmbeddingLimits(live_opt_in=True, max_input_tokens=1000, max_budget_usd=None if unpriced else 0.001)
        options = {"normalize": normalize, "batch_size": batch_size, "limits": limits}
        if unpriced:
            options.update(pricing=None, billing="self_hosted")
        if backend == "tei":
            options.update(truncate=False, prompt_name="query")
        elif scenario == "no_token_bound":
            options["token_bound"] = None
        adapter = _adapter(backend, server.endpoint + ("/v1" if backend == "openai" else ""), **options)
        cancel, trigger = threading.Event(), None
        if scenario == "cancel_before":
            cancel.set()
        elif scenario == "cancel_in_flight":
            def cancel_after_dispatch():
                server.entered.wait(1)
                cancel.set()
            trigger = threading.Thread(target=cancel_after_dispatch, daemon=True)
            trigger.start()
        if scenario == "timeout":
            limits = replace(limits, timeout_seconds=0.04)
        if scenario == "request_limit":
            limits = replace(limits, max_requests=1)
            adapter.batch_size = 1
        elif scenario == "input_bytes":
            limits = replace(limits, max_input_bytes=1)
        elif scenario in {"input_tokens", "large_input", "provider_token_overrun"}:
            limits = replace(limits, max_input_tokens=1)
        elif scenario == "budget":
            limits = replace(limits, max_budget_usd=0.000001)
        elif scenario == "no_opt_in":
            limits = replace(limits, live_opt_in=False)
        elif scenario == "lifetime_requests":
            adapter.limits = replace(limits, max_requests=1)
        elif scenario == "lifetime_tokens":
            adapter.limits = replace(limits, max_input_tokens=5)
        if scenario == "close":
            adapter.close()
        started = time.monotonic()
        result, error, error_raw = None, None, None
        try:
            if scenario in {"lifetime_requests", "lifetime_tokens"}:
                adapter.embed("x")
                adapter.embed("y")
            elif scenario == "single_and_many":
                single = adapter.embed(_TEXTS[0])
                many = adapter.embed_many(_TEXTS[:2])
                result = {"single": single, "many": many}
            else:
                texts = {"empty_batch": [], "blank_text": [" "], "nontext": [1], "string_batch": "text",
                         "provider_token_overrun": ["x"], "large_input": ["x" * 1048576]}.get(scenario, _TEXTS)
                result = adapter.embed_batch(texts, limits=limits, cancel=cancel)
        except (RuntimeFailure, ContractError) as exc:
            error, error_raw = str(exc), getattr(exc, "raw", {})
        elapsed = time.monotonic() - started
        if trigger is not None:
            trigger.join(timeout=1)
        observation = {"result": result if isinstance(result, dict) else asdict(result) if result else None, "error": error, "error_raw": error_raw,
                       "description": adapter.describe(), "usage": adapter.usage,
                       "requests": list(server.requests), "redirect_hits": list(server.redirect_hits), "elapsed": elapsed,
                       "first_float32": struct.unpack("!f", struct.pack("!f", 0.1000000001))[0],
                       "physical": "loopback_http_protocol_fixture"}
        adapter.close()
        return observation


def observe_dispatch_gate(backend="tei", *, inherited=True, scenario="timeout"):
    with _Server(backend, "valid") as server:
        release, entered, body_finished, cancel = (threading.Event() for _ in range(4))
        limits = EmbeddingLimits(timeout_seconds=0.5 if scenario == "timeout" else 1,
                                 live_opt_in=True, max_input_tokens=1000, max_budget_usd=0.001)
        adapter = _adapter(backend, server.endpoint + ("/v1" if backend == "openai" else ""), limits=limits)
        original = adapter._body

        def delayed_body(texts):
            entered.set()
            release.wait(3)
            try:
                return original(texts)
            finally:
                body_finished.set()

        adapter._body = delayed_body
        if scenario == "success":
            release.set()
        ledger = RequestLedger()
        trigger = None
        if scenario == "cancel":
            def cancel_during_body():
                entered.wait(1)
                cancel.set()
            trigger = threading.Thread(target=cancel_during_body, daemon=True)
            trigger.start()
        error = error_raw = None
        try:
            def call():
                return adapter.embed("new text", cancel=cancel)
            with_request_ledger(call, ledger) if inherited else call()
        except RuntimeFailure as exc:
            error, error_raw = exc.code, exc.raw
        requests_at_return = len(server.requests)
        release.set()
        body_finished.wait(1)
        server.entered.wait(0.1)
        parent_before_reuse = ledger.snapshot()
        ledger.start()
        ledger.complete()
        if trigger is not None:
            trigger.join(timeout=1)
        observed = {"error": error, "error_raw": error_raw, "body_entered": entered.is_set(),
                    "requests_at_return": requests_at_return, "requests_after_return": len(server.requests),
                    "parent_before_reuse": parent_before_reuse, "parent_after_reuse": ledger.snapshot(), "usage": adapter.usage}
        adapter.close()
        return observed


def observe_timeout_override(backend="tei"):
    with _Server(backend, "timeout") as server:
        adapter = _adapter(backend, server.endpoint + ("/v1" if backend == "openai" else ""),
                           limits=EmbeddingLimits(timeout_seconds=0.04, live_opt_in=True, max_budget_usd=0.1))
        started, error = time.monotonic(), None
        try:
            adapter.embed("new text", limits=EmbeddingLimits(timeout_seconds=1, live_opt_in=True, max_budget_usd=0.1))
        except RuntimeFailure as exc:
            error = exc.code
        observed = {"error": error, "elapsed": time.monotonic() - started, "requests": len(server.requests)}
        adapter.close()
        return observed


def observe_configuration(case):
    defaults = {"model_version": "v1", "endpoint": "https://embeddings.example.invalid/v1"}
    cases = {"http_remote": {"endpoint": "http://embeddings.example.invalid"},
             "endpoint_credentials": {"endpoint": "https://user:pass@example.invalid"},
             "endpoint_query": {"endpoint": "https://example.invalid/?api_key=x"},
             "endpoint_fragment": {"endpoint": "https://example.invalid/#private"},
             "endpoint_whitespace": {"endpoint": "https://example.invalid/\n"},
             "endpoint_port": {"endpoint": "https://example.invalid:bad"},
             "model_version": {"model_version": ""}, "timeout": {"timeout": 0},
             "normalize": {"normalize": "yes"}, "batch_size": {"batch_size": True},
             "header_injection": {"api_key": "test\r\nInjected: yes"}}
    defaults.update(cases[case])
    try:
        OpenAIEmbedding("test-model", 2, **defaults)
    except ContractError as exc:
        return str(exc)
    return None


def live_available(backend):
    prefix = "EVALKIT_" + backend.upper() + "_EMBEDDING_"
    required = ["ENDPOINT", "MODEL", "VERSION", "DIMENSIONS"]
    if backend == "openai":
        required += ["API_KEY", "PRICE_PER_MILLION", "MAX_BUDGET_USD"]
    return os.environ.get("EVALKIT_LIVE_EMBEDDINGS") == "1" and all(os.environ.get(prefix + key) for key in required)


def observe_live(backend):
    if not live_available(backend):
        raise ContractError("actual embedding service requires EVALKIT_LIVE_EMBEDDINGS=1 and explicit service configuration")
    prefix = "EVALKIT_" + backend.upper() + "_EMBEDDING_"
    def env(name):
        return os.environ.get(prefix + name)
    options = {"model_version": env("VERSION"), "endpoint": env("ENDPOINT"), "api_key": env("API_KEY") or "",
               "normalize": True, "batch_size": 2,
               "limits": EmbeddingLimits(live_opt_in=True, max_requests=2, max_input_tokens=1000,
                   max_budget_usd=float(env("MAX_BUDGET_USD")) if env("MAX_BUDGET_USD") else None)}
    if env("PRICE_PER_MILLION"):
        options["pricing"] = EmbeddingPricing(float(env("PRICE_PER_MILLION")))
    if backend == "openai" and env("TOKEN_BOUND"):
        options["token_bound"] = env("TOKEN_BOUND")
    kind = OpenAIEmbedding if backend == "openai" else TEIEmbedding
    adapter = kind(env("MODEL"), int(env("DIMENSIONS")), **options)
    try:
        batch = adapter.embed_batch(_TEXTS[:2])
        return {"result": asdict(batch), "usage": adapter.usage, "description": adapter.describe()}
    finally:
        adapter.close()
