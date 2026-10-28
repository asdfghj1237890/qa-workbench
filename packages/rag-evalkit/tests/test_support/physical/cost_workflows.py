"""Contract: builtins.build_pipeline, VectorRagPipeline.run, execute and benchmark.

The embedding ledger below simulates known charges solely for offline unit
regressions. It sends no provider requests and is not real billing evidence.
MemoryStore, pipeline construction, generation harness and report writers are
the real implementations; failures are injected at their adapter boundaries.
"""

from pathlib import Path

from rag_evalkit.benchmark import benchmark_pipeline
from rag_evalkit.builtins import build_pipeline, default_registry
from rag_evalkit.contracts import UnsupportedCapability
from rag_evalkit.datasets import load_experiment
from rag_evalkit.experiments import create_run, execute
from rag_evalkit.models import ReplayModel
from rag_evalkit.runtime import Generation, RuntimeFailure, ToolCall, Usage
from rag_evalkit.serialization import plain
from rag_evalkit.stores.memory import MemoryStore


class _ChargedFixtureEmbedder:
    def __init__(self, state, charge, fail_close=False):
        self.state, self.charge = state, charge
        self.fail_close = fail_close
        self.requests = 0

    def describe(self):
        return {"adapter": "simulated_charged_embedding", "dimensions": 3,
                "evidence_kind": "offline_unit_cost_fixture", "semantic_quality": "not_evaluated"}

    @property
    def usage(self):
        return {"requests": self.requests, "input_tokens": self.requests * 10,
                "cost_usd": self.requests * self.charge}

    def embed_many(self, texts):
        self.requests += 1
        return [(1.0, 0.0, 0.0) for _ in texts]

    def embed(self, text):
        return self.embed_many([text])[0]

    def close(self):
        self.state["embedding_closes"] += 1
        if self.fail_close:
            raise RuntimeError("fixture-cleanup-sensitive")


class _FailingMemoryStore(MemoryStore):
    def __init__(self, state, failure):
        super().__init__(3)
        self.state, self.failure = state, failure

    def upsert(self, documents):
        if self.failure == "unsupported_ingest_cleanup":
            raise UnsupportedCapability("fixture unsupported ingest")
        if self.failure in {"ingest", "ingest_cleanup", "ingest_embedder_cleanup"}:
            raise RuntimeFailure("fixture_ingest_failure")
        return super().upsert(documents)

    def search(self, query):
        if self.failure == "search":
            raise RuntimeFailure("fixture_search_failure")
        return super().search(query)

    def close(self):
        self.state["store_closes"] += 1
        result = super().close()
        if self.failure in {"ingest_cleanup", "unsupported_ingest_cleanup"}:
            raise RuntimeError("fixture-cleanup-sensitive")
        return result


class _UnobservedModel(ReplayModel):
    def __init__(self):
        super().__init__(["unreachable"], name="offline-unobserved-provider-cost")

    def generate(self, *args, **kwargs):
        raise RuntimeFailure("fixture_model_connection_lost")


class _PartiallyMeteredToolModel(ReplayModel):
    def __init__(self, state, source_id, partial_cost):
        super().__init__(["unreachable"], name="offline-partially-metered-tool-loop")
        self.state, self.source_id, self.partial_cost = state, source_id, partial_cost
        state["model_calls"] = 0
        state["tool_result_received"] = False

    def generate(self, messages, **kwargs):
        self.state["model_calls"] += 1
        if self.state["model_calls"] == 1:
            return Generation("", (ToolCall("read-1", "read_source", {"source_id": self.source_id}),),
                              "tool_calls", Usage(10, 5, 0.05, {"api_requests": 1}))
        self.state["tool_result_received"] = any(message.role == "tool" for message in messages)
        partial = {"cost_usd": self.partial_cost} if self.partial_cost is not None else {}
        raise RuntimeFailure("fixture_model_connection_lost", raw={"partial_usage": partial})


class _ThrowingHarness:
    def describe(self):
        return {"harness": "offline_throwing_harness"}

    def run(self, *args, **kwargs):
        raise RuntimeFailure("fixture_generation_failure")


def _setup(failure, charge=0.1):
    root = Path(__file__).resolve().parents[3]
    manifest, dataset = load_experiment(root / "examples" / "experiment.json")
    manifest["variants"] = manifest["variants"][:1]
    manifest["repeats"] = 1
    dataset["cases"] = dataset["cases"][:1]
    config = manifest["variants"][0]
    config["embedding"] = {"type": "charged_fixture"}
    config["store"] = {"type": "fault_memory"}
    if failure == "unsupported_search":
        config["rag"]["exact"] = False
    state = {"embedding_closes": 0, "store_closes": 0, "store_attempts": 0}
    registry = default_registry()
    registry.register("embedding", "charged_fixture", lambda *args, **kwargs: _ChargedFixtureEmbedder(
        state, charge, fail_close=failure == "ingest_embedder_cleanup"))

    def store_factory(*args, **kwargs):
        state["store_attempts"] += 1
        if failure == "constructor":
            raise RuntimeFailure("fixture_store_constructor_failure")
        return _FailingMemoryStore(state, failure)

    registry.register("store", "fault_memory", store_factory)
    if failure == "model_unknown":
        registry.register("model", "unobserved_model", lambda *args, **kwargs: _UnobservedModel())
        config["model"] = {"type": "unobserved_model"}
    elif failure in {"tool_model_unknown", "tool_model_partial_unknown"}:
        registry.register("model", "partially_metered_model", lambda *args, **kwargs: _PartiallyMeteredToolModel(
            state, dataset["documents"][0]["source_id"], 0.03 if failure == "tool_model_partial_unknown" else None))
        config["model"] = {"type": "partially_metered_model"}
        config["harness"] = {"type": "tool_loop"}
        config["tools"] = {"type": "retrieved_sources"}
    elif failure == "generation_exception":
        registry.register("harness", "throwing_harness", lambda *args, **kwargs: _ThrowingHarness())
        config["harness"] = {"type": "throwing_harness"}

    def builder(variant=config, selected_dataset=dataset):
        return build_pipeline(variant, selected_dataset, registry=registry)

    return manifest, dataset, state, builder


def constructor_failure():
    _, _, state, builder = _setup("constructor")
    failure = None
    try:
        builder()
    except RuntimeFailure as exc:
        failure = {"code": exc.code, "adapter_usage": plain(getattr(exc, "adapter_usage", None))}
    return {"state": state, "failure": failure}


def initialization_failure(failure="ingest_cleanup"):
    _, _, state, builder = _setup(failure)
    observed = None
    try:
        builder()
    except Exception as exc:
        observed = {"type": type(exc).__name__, "code": getattr(exc, "code", None),
                    "adapter_usage": plain(getattr(exc, "adapter_usage", None)),
                    "adapter_cleanup": plain(getattr(exc, "adapter_cleanup", None))}
    return {"state": state, "failure": observed}


def reused_failures(failure="search"):
    _, dataset, state, builder = _setup(failure)
    pipeline, cleanup, _ = builder()
    failures = []
    try:
        for _ in range(2):
            try:
                pipeline.run(dataset["cases"][0]["query"])
            except RuntimeFailure as exc:
                failures.append({"code": exc.code, "adapter_usage": plain(getattr(exc, "adapter_usage", None))})
    finally:
        cleanup()
    return {"state": state, "failures": failures}


def experiment_failure(output, failure="search"):
    manifest, dataset, state, builder = _setup(failure)
    report = execute(create_run(output, manifest, dataset), builder)
    return {"state": state, "report": report}


def benchmark_failure(failure="ingest"):
    _, dataset, state, builder = _setup(failure, charge=0.25 if failure.startswith("ingest") else 0.1)
    report = benchmark_pipeline(builder, [dataset["cases"][0]["query"]], repeats=1, warmup=1, concurrency=1)
    return {"state": state, "report": report}
