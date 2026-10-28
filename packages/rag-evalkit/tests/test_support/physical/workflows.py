"""Real CLI, loopback embeddings and RAG/tool orchestration."""

import contextlib
import copy
import io
from pathlib import Path
from unittest.mock import patch

from rag_evalkit.artifacts import RunStore, atomic_json, list_runs
from rag_evalkit.builtins import build_pipeline, default_registry
from rag_evalkit.cli import main
from rag_evalkit.datasets import dataset_metadata, validate_dataset
from rag_evalkit.models import ReplayModel
from rag_evalkit.runtime import Generation, ToolCall
from rag_evalkit.serialization import plain, read_json

from .embeddings import _Server
from .experiments import inputs


def partial_embedding_cost(path, reuse=False):
    from rag_evalkit.experiments import create_run, execute

    manifest, dataset = runtime_inputs("openai")
    manifest["repeats"] = 1
    dataset["cases"] = dataset["cases"][:1]
    with _Server("openai", "partial_http_error") as server, patch.dict("os.environ", {"EVALKIT_UNIT_EMBEDDING_ENDPOINT": server.endpoint + "/v1"}):
        def builder(config, data):
            return build_pipeline(config, data, allow_live_embeddings=True)
        if not reuse:
            report = execute(create_run(path / "runs", manifest, dataset), builder)
            return {"report": report, "requests": len(server.requests)}
        pipeline, cleanup, _ = builder(manifest["variants"][0], dataset)
        observations = []
        try:
            for _ in range(2):
                try:
                    pipeline.run(dataset["cases"][0]["query"])
                except Exception as exc:
                    observations.append({"type": type(exc).__name__, "usage": getattr(exc, "adapter_usage", None)})
            lifetime = pipeline._embedder.usage
        finally:
            cleanup()
        return {"observations": observations, "lifetime": lifetime, "requests": len(server.requests)}


def judge_config_rejection(path, field):
    manifest, dataset = inputs()
    manifest["dataset"] = "dataset.json"
    atomic_json(path / "manifest.json", manifest)
    atomic_json(path / "dataset.json", dataset)
    config = read_json(Path(__file__).resolve().parents[3] / "examples/judge-model.template.json")
    if field != "pricing":
        config["model"]["pricing"] = {"input_per_million": 1, "output_per_million": 2}
    if field == "missing_model":
        config["model"].pop("model")
    elif field == "unknown_price":
        config["model"]["pricing"]["unknown"] = 1
    elif field == "hosted_shape":
        config["model"]["hosted_tools"] = {}
    elif field == "hosted_field":
        config["model"]["hosted_tools"] = [{"unknown": True}]
    atomic_json(path / "judge.json", config)
    stderr = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
        run_exit = main(["run", str(path / "manifest.json"), "--output", str(path / "runs")])
        run = path / "runs" / list_runs(path / "runs")[0]["run_id"]
        prepare_exit = main(["quality-prepare", str(run), "--output", str(path / "review")])
        with patch.dict("os.environ", {"OPENAI_API_KEY": "unit-placeholder-key", "OPENAI_BASE_URL": "https://example.invalid/v1"}), patch("socket.create_connection") as network:
            code = main(["quality-judge", str(path / "review/blind/bundle.json"), str(path / "judge.json"), "--allow-live-models", "--max-total-usd", ".2", "--output", str(path / "judge-result.json")])
    return {"run_exit": run_exit, "prepare_exit": prepare_exit, "exit": code, "network_calls": network.call_count, "stderr": stderr.getvalue()}


def runtime_inputs(backend):
    manifest, dataset = inputs()
    manifest["dataset"] = "dataset.json"
    dataset = copy.deepcopy(dataset)
    dataset.update(vector_policy="runtime", dimensions=2)
    for row in dataset["documents"]:
        row.pop("vector")
    for row in dataset["cases"]:
        row.pop("query_vector")
    variant = copy.deepcopy(manifest["variants"][0])
    variant["store"] = {"type": "memory", "dimensions": 2}
    variant["embedding"] = {"type": "openai_embeddings" if backend == "openai" else "tei_embeddings", "model": "test-model", "model_version": "unit-model-v1", "dimensions": 2,
                            "endpoint_env": "EVALKIT_UNIT_EMBEDDING_ENDPOINT", "limits": {"max_input_tokens": 4096, "max_requests": 8}}
    if backend == "openai":
        variant["embedding"].update(token_bound="utf8_bytes", pricing={"input_per_million": 1.}, billing="metered")
        variant["embedding"]["limits"]["max_budget_usd"] = .01
    manifest["variants"] = [variant]
    return manifest, dataset


def runtime_embedding_cli(path, backend="openai", mode="run"):
    manifest, dataset = runtime_inputs(backend)
    with _Server(backend, "partial_http_error" if mode == "store_failure" else "valid") as server:
        atomic_json(path / "dataset.json", dataset)
        atomic_json(path / "manifest.json", manifest)
        arguments = ["run", str(path / "manifest.json"), "--output", str(path / "runs")]
        if mode == "load":
            arguments = ["benchmark", str(path / "manifest.json"), "--variant", manifest["variants"][0]["id"], "--scope", "pipeline", "--repeats", "2", "--warmup", "1", "--concurrency", "2", "--output", str(path / "load.json")]
        elif mode in {"store", "store_failure"}:
            arguments = ["benchmark", str(path / "manifest.json"), "--variant", manifest["variants"][0]["id"], "--scope", "store", "--output", str(path / "load.json")]
        if mode != "no_opt_in":
            arguments.append("--allow-live-embeddings")
        arguments += ["--max-total-usd", ".001" if mode == "budget" else ".2"]
        endpoint = server.endpoint + ("/v1" if backend == "openai" else "")
        output, error = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", {"EVALKIT_UNIT_EMBEDDING_ENDPOINT": endpoint}), contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main(arguments)
        runs = list_runs(path / "runs")
        report = RunStore(path / "runs" / runs[0]["run_id"]).export() if runs else None
        if report is None and (path / "load.json").is_file():
            report = read_json(path / "load.json")
        return {"exit": code, "stderr": error.getvalue(), "requests": list(server.requests), "report": report, "metadata": dataset_metadata(validate_dataset(dataset))}


def runtime_validation(kind):
    manifest, dataset = runtime_inputs("openai")
    if kind == "missing_dimensions":
        dataset.pop("dimensions")
    if kind == "provided_document":
        dataset["documents"][0]["vector"] = [1, 0]
    if kind == "provided_query":
        dataset["cases"][0]["query_vector"] = [1, 0]
    if kind == "policy":
        dataset["vector_policy"] = "invented"
    try:
        validate_dataset(dataset)
        if kind == "fixture":
            manifest["variants"][0]["embedding"] = {"type": "fixture"}
            build_pipeline(manifest["variants"][0], dataset)
        return None
    except ValueError as exc:
        return str(exc)


def prompt_tools():
    manifest, dataset = inputs()
    variant = copy.deepcopy(manifest["variants"][0])
    source_id = dataset["documents"][0]["source_id"]
    captured = []

    class RecordingReplay(ReplayModel):
        def generate(self, messages, **kwargs):
            captured.append([plain(message) for message in messages])
            return super().generate(messages, **kwargs)

    registry = default_registry()
    registry.register("model", "unit_tool_replay", lambda config, **context: RecordingReplay([
        Generation("", (ToolCall("unit-read", "read_source", {"source_id": source_id}),), "tool_calls"),
        "Unit answer [source:" + source_id + "]",
    ]))
    variant.update(model={"type": "unit_tool_replay"}, harness={"type": "tool_loop"}, prompt={"system": "Unit custom source prompt."}, tools={"type": "retrieved_sources"})
    pipeline, cleanup, resolved = build_pipeline(variant, dataset, registry=registry)
    try:
        result = pipeline.run(dataset["cases"][0]["query"])
        return {"result": plain(result), "messages": captured, "resolved": resolved}
    finally:
        cleanup()
