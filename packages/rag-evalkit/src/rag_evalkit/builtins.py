"""Default adapters. Optional dependencies and credentials are resolved lazily."""

from __future__ import annotations

import inspect
import os
from pathlib import Path

from .contracts import ContractError, UnsupportedCapability
from .datasets import FACTORS, dataset_metadata
from .registry import Registry
from .serialization import digest


def _options(config, allowed):
    extra = set(config) - set(allowed) - {"type"}
    if extra:
        raise ContractError("unknown adapter options: " + ", ".join(sorted(extra)))
    return {key: value for key, value in config.items() if key != "type"}


def _env(config, key, default=None):
    name = config.get(key)
    if name is None:
        if default is not None:
            return default
        raise ContractError("missing environment reference: " + key)
    if not isinstance(name, str) or not name or not os.environ.get(name):
        raise ContractError("environment variable is unset for " + key)
    return os.environ[name]


def _generation_options(variant):
    prompt, tools = variant.get("prompt", {}), variant.get("tools", {})
    if set(prompt) - {"system"}:
        raise ContractError("built-in RAG prompt supports only system")
    if tools and tools != {"type": "retrieved_sources"}:
        raise UnsupportedCapability("built-in RAG tools support retrieved_sources; custom handlers require a plugin")
    return {"system_prompt": prompt.get("system"), "tool_mode": tools.get("type")}


def default_registry():
    from .harnesses import SingleTurnHarness, ToolLoopHarness
    from .models import AnthropicMessagesModel, OpenAIResponsesModel, ReplayModel
    from .models.http import Pricing
    from .rag import LexicalRagPipeline, SyntheticFixtureEmbedder, VectorRagPipeline
    from .stores.elasticsearch import ElasticsearchStore
    from .stores.memory import MemoryStore
    from .stores.postgres import PostgresStore
    registry = Registry()

    def memory(config, **context):
        return MemoryStore(**_options(config, {"dimensions"}))

    def elastic(config, **context):
        opts = _options(config, {"dimensions", "url_env", "api_key_env", "username_env", "password_env", "timeout", "ann_metric", "num_candidates"})
        for key in ("url_env", "api_key_env", "username_env", "password_env"):
            opts.pop(key, None)
        return ElasticsearchStore(_env(config, "url_env"), **opts, **{name: _env(config, name + "_env") for name in ("api_key", "username", "password") if name + "_env" in config})

    def postgres(config, **context):
        opts = _options(config, {"dimensions", "dsn_env", "schema", "ann_metric", "hnsw_m", "hnsw_ef_construction", "hnsw_ef_search", "timeout"})
        opts.pop("dsn_env", None)
        return PostgresStore(_env(config, "dsn_env"), **opts)

    def replay(config, **context):
        opts = _options(config, {"text", "name"})
        return ReplayModel([opts.get("text", "")], name=opts.get("name", "synthetic-replay"))

    def provider(model_type):
        def factory(config, **context):
            from .runtime import HostedToolSpec
            opts = _options(config, {"model", "api_key_env", "endpoint_env", "settings", "pricing", "streaming", "image_input", "hosted_tools"})
            if not context.get("allow_live_models"):
                raise UnsupportedCapability("live model requests require --allow-live-models and explicit budgets")
            if not isinstance(opts.get("model"), str) or not opts["model"].strip():
                raise ContractError("live model requires a nonempty model identifier")
            if not isinstance(opts.get("pricing"), dict) or not opts["pricing"]:
                raise ContractError("live model requires explicit pricing")
            extra = {key: opts[key] for key in ("streaming", "image_input") if key in opts}
            if "hosted_tools" in opts:
                if not isinstance(opts["hosted_tools"], list) or any(not isinstance(row, dict) for row in opts["hosted_tools"]):
                    raise ContractError("hosted_tools requires a list of tool objects")
            try:
                pricing = Pricing(**opts["pricing"])
                if "hosted_tools" in opts:
                    extra["hosted_tools"] = tuple(HostedToolSpec(**row) for row in opts["hosted_tools"])
            except TypeError as exc:
                raise ContractError("invalid pricing or hosted tool fields") from exc
            return model_type(opts["model"], api_key=_env(config, "api_key_env"), endpoint=_env(config, "endpoint_env") if "endpoint_env" in config else None, settings=opts.get("settings"), pricing=pricing, **extra)
        return factory

    def fixture(config, **context):
        _options(config, set())
        if context["dataset"].get("vector_policy") == "runtime":
            raise ContractError("runtime vector dataset requires a real embedding adapter")
        vectors = {}
        for row in context["dataset"]["documents"]:
            if row["text"] in vectors and vectors[row["text"]] != row["vector"]:
                raise ContractError("same text has inconsistent fixture vectors")
            vectors[row["text"]] = row["vector"]
        for row in context["dataset"]["cases"]:
            if row["query"] in vectors and vectors[row["query"]] != row["query_vector"]:
                raise ContractError("same text has inconsistent fixture vectors")
            vectors[row["query"]] = row["query_vector"]
        return SyntheticFixtureEmbedder(vectors)

    def embedding(embedding_type):
        def factory(config, **context):
            from .embeddings import (
                EmbeddingLimits,
                EmbeddingPricing,
                OpenAIEmbedding,
                TEIEmbedding,
            )
            if not context.get("allow_live_embeddings"):
                raise UnsupportedCapability("real embedding requests require --allow-live-embeddings")
            opts = _options(config, {"model", "dimensions", "model_version", "endpoint_env", "api_key_env", "normalize", "timeout", "batch_size", "pricing", "limits", "billing", "send_dimensions", "truncate", "prompt_name", "token_bound"})
            for key in ("endpoint_env", "api_key_env"):
                opts.pop(key, None)
            limits = dict(opts.pop("limits", {}))
            if "live_opt_in" in limits:
                raise ContractError("embedding live_opt_in is a CLI authorization flag")
            opts["limits"] = EmbeddingLimits(**limits, live_opt_in=True)
            if "pricing" in opts:
                opts["pricing"] = EmbeddingPricing(**opts["pricing"])
            if "endpoint_env" in config:
                opts["endpoint"] = _env(config, "endpoint_env")
            if "api_key_env" in config:
                opts["api_key"] = _env(config, "api_key_env")
            dimensions = dataset_metadata(context["dataset"])["dimensions"]
            if opts.get("dimensions") != dimensions:
                raise ContractError("embedding dimensions differ from dataset")
            return {"openai_embeddings": OpenAIEmbedding, "tei_embeddings": TEIEmbedding}[embedding_type](**opts)
        return factory

    def vector(config, **context):
        opts = _options(config, {"top_k", "metric", "exact", "filters"})
        pipeline = VectorRagPipeline(context["store"], context["embedder"], context["harness"], limits=context["limits"], **_generation_options(context["variant"]), **opts)
        pipeline.ingest(context["chunks"])
        return pipeline

    def lexical(config, **context):
        # metric/exact have no lexical meaning and therefore are not accepted.
        opts = _options(config, {"top_k", "filters"})
        return LexicalRagPipeline(context["chunks"], context["harness"], limits=context["limits"], **_generation_options(context["variant"]), **opts)

    def agents_harness(config, **context):
        from .integrations import build_openai_agents_harness
        return build_openai_agents_harness(config, **context)

    registry.register("store", "memory", memory)
    registry.register("store", "elasticsearch", elastic)
    registry.register("store", "postgres", postgres)
    registry.register("embedding", "fixture", fixture)
    registry.register("embedding", "openai_embeddings", embedding("openai_embeddings"))
    registry.register("embedding", "tei_embeddings", embedding("tei_embeddings"))
    registry.register("model", "replay", replay)
    registry.register("model", "openai", provider(OpenAIResponsesModel))
    registry.register("model", "anthropic", provider(AnthropicMessagesModel))
    for name, constructor in (("single_turn", SingleTurnHarness), ("tool_loop", ToolLoopHarness)):
        def harness(config, _constructor=constructor, **context):
            _options(config, {"limits"})
            return _constructor(context["model"])
        registry.register("harness", name, harness)
    registry.register("harness", "openai_agents", agents_harness)
    registry.register("rag", "vector", vector)
    registry.register("rag", "lexical", lexical)
    return registry


def _implementation(value):
    module = inspect.getmodule(type(value))
    path = Path(module.__file__) if module and module.__file__ else None
    return digest(path.read_text(encoding="utf-8")) if path and path.is_file() else "unavailable"


def build_pipeline(config, dataset, *, registry=None, allow_live_models=False, allow_live_embeddings=False):
    from .rag import Chunk
    from .runtime import RunLimits
    registry = registry or default_registry()
    builtin_rag = config["rag"]["type"] in {"vector", "lexical"}
    if builtin_rag and config.get("environment"):
        raise UnsupportedCapability("environment controls are not implemented; actual runtime environment is recorded separately")
    limit_options = dict(config["harness"].get("limits", {}))
    if "live_opt_in" in limit_options:
        raise ContractError("live_opt_in is a CLI authorization flag, not a manifest setting")
    limits = RunLimits(**limit_options, live_opt_in=allow_live_models)
    model = registry.build("model", config["model"], allow_live_models=allow_live_models)
    harness = registry.build("harness", config["harness"], model=model)
    embedder = registry.build("embedding", config["embedding"], dataset=dataset, allow_live_embeddings=allow_live_embeddings)
    chunks = tuple(Chunk(row["id"] + ":0", row["id"], row["source_id"], row["text"], 0, len(row["text"]), row.get("metadata", {})) for row in dataset["documents"])
    store = None

    def cleanup():
        try:
            if store is not None:
                store.close()
        finally:
            if callable(getattr(embedder, "close", None)):
                embedder.close()
    try:
        store = registry.build("store", config["store"], dataset=dataset)
        pipeline = registry.build("rag", config["rag"], store=store, embedder=embedder, harness=harness, model=model, limits=limits, chunks=chunks, dataset=dataset, variant=config)
        harness_description = dict(harness.describe())
        harness_description.pop("model", None)
        pipeline_description = dict(pipeline.describe())
        rag_description = dict(pipeline_description)
        for nested in ("retriever", "store", "embedder", "embedding", "harness", "model", "prompt", "tools"):
            rag_description.pop(nested, None)
        resolved = {factor: config.get(factor, {}) for factor in FACTORS}
        resolved.update({"store": {**store.describe(), "implementation_sha": _implementation(store)}, "embedding": {**embedder.describe(), "implementation_sha": _implementation(embedder)}, "model": {**model.describe(), "implementation_sha": _implementation(model)}, "harness": {**harness_description, "limits": {key: value for key, value in vars(limits).items() if key != "live_opt_in"}, "implementation_sha": _implementation(harness)}, "rag": {**config["rag"], "resolved": rag_description, "implementation_sha": _implementation(pipeline), "chunking": "one_document_one_chunk"}, "prompt": {"template": config.get("prompt") or ("source_only_citation_v1" if builtin_rag else {}), "implementation_sha": _implementation(pipeline)}, "tools": config.get("tools", {})})
        # Preserve effective defaults reported by plugin pipelines in their own
        # factors. Removing nested descriptors without relocating them would
        # erase precisely the differences a controlled comparison must detect.
        aliases = {"store": ("store", "retriever"), "embedding": ("embedding", "embedder"), "model": ("model",), "harness": ("harness",), "prompt": ("prompt",), "tools": ("tools",)}
        for factor, names in (aliases.items() if not builtin_rag else ()):
            reported = {name: pipeline_description[name] for name in names if name in pipeline_description}
            if factor == "harness" and isinstance(reported.get("harness"), dict):
                reported["harness"] = dict(reported["harness"])
                nested_model = reported["harness"].pop("model", None)
                if nested_model is not None:
                    resolved["model"]["pipeline_harness_model"] = nested_model
            if reported:
                resolved[factor] = {**resolved[factor], "pipeline_reported": reported}
        return pipeline, cleanup, resolved
    except BaseException as exc:
        if hasattr(embedder, "usage"):
            exc.adapter_usage = embedder.usage
        # Construction may have consumed paid work before failing. Cleanup must
        # not replace that original failure or detach its observed usage.
        exc.adapter_cleanup = {"status": "completed", "attempted": True, "error": None}
        try:
            cleanup()
        except BaseException as cleanup_exc:
            # Never persist cleanup messages: adapter exceptions may carry
            # credentials, connection strings or response payloads.
            exc.adapter_cleanup = {"status": "failed", "attempted": True,
                                   "error": {"type": type(cleanup_exc).__name__, "message": "owned resource cleanup failed"}}
        raise


def check_live_budget(manifest, dataset, max_total_usd):
    live = [(variant, "model") for variant in manifest["variants"] if variant["model"]["type"] != "replay"]
    live += [(variant, "embedding") for variant in manifest["variants"] if variant["embedding"]["type"] != "fixture" and variant["embedding"].get("billing", "self_hosted" if variant["embedding"]["type"] == "tei_embeddings" else "metered") != "self_hosted"]
    if not live:
        return
    import math
    if isinstance(max_total_usd, bool) or not isinstance(max_total_usd, (float, int)) or not math.isfinite(max_total_usd) or max_total_usd <= 0:
        raise ContractError("live run requires --max-total-usd")
    count = sum(manifest["split"] == "all" or row["split"] == manifest["split"] for row in dataset["cases"]) * manifest["repeats"]
    reservation = 0.0
    for variant, component in live:
        cap = variant["harness" if component == "model" else "embedding"].get("limits", {}).get("max_budget_usd")
        if isinstance(cap, bool) or not isinstance(cap, (float, int)) or not math.isfinite(cap) or cap <= 0:
            raise ContractError("each live trial requires a max_budget_usd")
        reservation += count * cap
    if reservation > max_total_usd:
        raise ContractError("sum of per-trial reservations exceeds total run budget")
