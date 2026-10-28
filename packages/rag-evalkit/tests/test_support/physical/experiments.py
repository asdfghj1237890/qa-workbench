"""Contract: CLI.main, experiments.execute/compare, RunStore journal.

All filesystem, subprocess and corruption wiring stays in this physical layer.
Behavioral assertions live in test_experiments.py.
"""

import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from rag_evalkit.artifacts import RunStore, list_runs
from rag_evalkit.benchmark import benchmark_store
from rag_evalkit.builtins import build_pipeline, check_live_budget, default_registry
from rag_evalkit.contracts import Document, SearchSpec
from rag_evalkit.datasets import load_experiment, validate_dataset, validate_manifest
from rag_evalkit.experiments import compare, create_run, execute, schedule
from rag_evalkit.metrics import ndcg_at_k, paired_bootstrap, recall_at_k
from rag_evalkit.serialization import plain
from rag_evalkit.stores import MemoryStore


def inputs():
    root = Path(__file__).resolve().parents[3]
    return load_experiment(root / "examples" / "experiment.json")


def run_example(output, stop_after=None):
    manifest, dataset = inputs()
    store = create_run(output, manifest, dataset)
    report = execute(store, build_pipeline, stop_after=stop_after)
    return {"directory": str(store.directory), "report": report, "index": list_runs(output)}


def resume(directory):
    return execute(RunStore(directory), build_pipeline)


def compare_run(directory, axes, metric="recall_at_k"):
    try:
        return {"result": compare(RunStore(directory).export(), "vector", "lexical", axes=axes, metric=metric), "error": None}
    except ValueError as exc:
        return {"result": None, "error": str(exc)}


def changed_condition(output, *, factor="model", declared=()):
    manifest, dataset = inputs()
    manifest["comparison_axes"] = list(declared)
    if factor == "model":
        manifest["variants"][1]["model"]["name"] = "changed-model"
    elif factor == "harness":
        manifest["variants"][1]["harness"]["type"] = "tool_loop"
    store = create_run(output, manifest, dataset)
    execute(store, build_pipeline)
    return compare_run(store.directory, declared)


def invalid_input(kind):
    manifest, dataset = inputs()
    try:
        if kind == "leak":
            case = copy.deepcopy(dataset["cases"][0])
            case.update(id="other", split="holdout")
            dataset["cases"].append(case)
            validate_dataset(dataset)
        elif kind == "secrets":
            manifest["variants"][0]["model"]["api_key"] = "fake-key"
            validate_manifest(manifest)
        elif kind == "unknown_field":
            manifest["surprise"] = True
            validate_manifest(manifest)
        elif kind == "unknown_gold":
            dataset["cases"][0]["relevance"]["missing"] = 1
            validate_dataset(dataset)
        elif kind == "budget":
            variant = manifest["variants"][0]
            variant["model"]["type"] = "openai"
            variant["harness"]["limits"] = {"max_budget_usd": 2}
            check_live_budget(manifest, dataset, 1)
        elif kind == "unknown_cost":
            manifest["variants"][0]["model"]["type"] = "openai"
            check_live_budget(manifest, dataset, 100)
        return None
    except ValueError as exc:
        return str(exc)


def journal_corruption(output, kind):
    completed = run_example(output)
    store = RunStore(completed["directory"])
    with sqlite3.connect(store.path) as connection:
        if kind == "observation":
            connection.execute("UPDATE trials SET observation='{}' WHERE ordinal=0")
        else:
            connection.execute("DELETE FROM trials WHERE ordinal=0")
    try:
        store.export()
        return None
    except ValueError as exc:
        return str(exc)


def concurrent_executor(output):
    manifest, dataset = inputs()
    store = create_run(output, manifest, dataset)
    with store.lease():
        try:
            with RunStore(store.directory).lease():
                return None
        except ValueError as exc:
            return str(exc)


def interrupted_trial(output):
    manifest, dataset = inputs()
    store = create_run(output, manifest, dataset)
    store.start(0)
    before = store.rows()
    after = execute(store, build_pipeline)
    return {"before": before, "after": after}


def cli_outside_repo(output):
    manifest, dataset = inputs()
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    (root / "corpus.json").write_text(json.dumps(dataset), encoding="utf-8")
    manifest["dataset"] = "corpus.json"
    (root / "experiment.json").write_text(json.dumps(manifest), encoding="utf-8")
    run = subprocess.run([sys.executable, "-m", "rag_evalkit.cli", "run", "experiment.json", "--output", "runs"], cwd=root, capture_output=True, text=True)
    return {"code": run.returncode, "stdout": run.stdout, "stderr": run.stderr, "runs": list_runs(root / "runs")}


def metric_observations():
    return {"recall": recall_at_k(["b", "a"], {"a": 3, "b": 1}, 2), "ndcg": ndcg_at_k(["a", "b"], {"a": 3, "b": 1}, 2), "empty": recall_at_k([], {}, 2), "clustered": paired_bootstrap({"a": [1, 1, 1], "b": [-1]}, seed=4)}


def benchmark():
    return plain(benchmark_store(lambda: MemoryStore(2), [Document("a", "alpha", (1, 0)), Document("b", "beta", (0, 1))], [SearchSpec((1, 0), 1)], repeats=3, concurrency=2))


def repeat_schedule():
    manifest, dataset = inputs()
    return {"first": schedule(manifest, dataset), "second": schedule(manifest, dataset)}


def explicit_unsupported(output):
    manifest, dataset = inputs()
    manifest["variants"][0]["rag"]["type"] = "unregistered"
    store = create_run(output, manifest, dataset)
    return execute(store, build_pipeline)


def hidden_effective_factor(output, factor):
    manifest, dataset = inputs()
    manifest["comparison_axes"] = ["model"]
    manifest["variants"][1] = copy.deepcopy(manifest["variants"][0])
    manifest["variants"][1]["id"] = "lexical"
    for variant in manifest["variants"]:
        variant["rag"] = {"type": "custom_effective"}
        variant["prompt"] = {"label": "same-configured-prompt"}
    registry = default_registry()

    class Pipeline:
        def __init__(self, original, variant_id):
            self.original, self.variant_id = original, variant_id

        def run(self, query):
            return self.original.run(query)

        def describe(self):
            description = self.original.describe()
            description[factor] = {"effective_value": self.variant_id}
            return description

    def factory(config, **context):
        from rag_evalkit.rag import VectorRagPipeline
        pipeline = VectorRagPipeline(context["store"], context["embedder"], context["harness"], limits=context["limits"])
        pipeline.ingest(context["chunks"])
        return Pipeline(pipeline, context["variant"]["id"])

    registry.register("rag", "custom_effective", factory)
    store = create_run(output, manifest, dataset)
    report = execute(store, lambda config, data: build_pipeline(config, data, registry=registry))
    try:
        return {"report": report, "result": compare(report, "vector", "lexical", axes=["model"]), "error": None}
    except ValueError as exc:
        return {"report": report, "result": None, "error": str(exc)}
