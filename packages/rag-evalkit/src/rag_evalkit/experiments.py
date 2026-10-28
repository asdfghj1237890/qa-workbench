"""Paired experiments with explicit change axes and durable trial evidence."""

from __future__ import annotations

import platform
import random
import time
from collections import defaultdict

from . import __version__
from .artifacts import RunStore
from .contracts import ContractError, UnsupportedCapability
from .datasets import FACTORS, dataset_metadata
from .metrics import paired_bootstrap, percentile, wilson
from .serialization import digest, plain


def schedule(manifest, dataset):
    cases = [case for case in dataset["cases"] if manifest["split"] == "all" or case["split"] == manifest["split"]]
    if not cases:
        raise ContractError("selection contains no cases")
    generator, result = random.Random(manifest["seed"]), []
    for trial in range(manifest["repeats"]):
        case_order = list(cases)
        generator.shuffle(case_order)
        for case in case_order:
            variants = [variant["id"] for variant in manifest["variants"]]
            generator.shuffle(variants)
            result.extend((variant, case["id"], trial) for variant in variants)
    return result


def environment():
    return {"evalkit_version": __version__, "python": platform.python_version(), "system": platform.system(), "machine": platform.machine(), "measurement_scope": "wall_time; shared_host_load_not_controlled"}


def create_run(output, manifest, dataset):
    metadata = {**dataset_metadata(dataset), "environment": environment(), "selection": {"seed": manifest["seed"], "repeats": manifest["repeats"], "split": manifest["split"]}, "comparison_axes": manifest["comparison_axes"], "variant_factors": {variant["id"]: {factor: variant.get(factor, {}) for factor in sorted(FACTORS)} for variant in manifest["variants"]}, "semantic_verdict": "not_evaluated"}
    return RunStore.create(output, manifest, dataset, schedule(manifest, dataset), metadata)


def grade(result, case, k, dataset):
    from .evaluators import (
        abstention_check,
        citation_check,
        evaluate_retrieval,
        source_lineage_check,
        tool_task_check,
    )
    evaluations = [*evaluate_retrieval(result, case["relevance"], k=k), source_lineage_check(result), abstention_check(result, should_abstain=case.get("should_abstain", False)), citation_check(result.answer, result.evidence, require_citation=not case.get("should_abstain", False)), tool_task_check(result.traces, expected_tools=case.get("expected_tools", []))]
    expected = set(case.get("expected_source_ids", []))
    observed = {item.source_id for item in result.evidence}
    corpus = {row["id"]: row for row in dataset["documents"]}
    content_matches = True
    for item in result.evidence:
        document = corpus.get(item.document_id)
        start, end = item.metadata.get("start"), item.metadata.get("end")
        if document is None or item.source_id != document["source_id"] or type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(document["text"]) or document["text"][start:end] != item.text:
            content_matches = False
    return {"metrics": {item.name: item.value for item in evaluations}, "checks": {item.name: item.passed for item in evaluations if item.passed is not None} | {"expected_sources_retrieved": expected <= observed, "corpus_evidence_matches": content_matches}, "evaluations": plain(evaluations), "semantic_verdict": "not_evaluated"}


def execute(store: RunStore, builder, *, progress=None, stop_after=None):
    """builder(config,dataset) -> (pipeline,cleanup,resolved_factor_descriptors).

    Inputs are snapshotted. A restarted run reuses its schedule and completed
    observations; it only retries a trial interrupted before a committed result.
    """
    payload = store.inputs["payload"]
    manifest, dataset = payload["manifest"], payload["dataset"]
    variants = {item["id"]: item for item in manifest["variants"]}
    cases = {item["id"]: item for item in dataset["cases"]}
    completed = 0
    with store.lease():
        store.recover()
        for row in store.rows():
            if row["status"] != "pending":
                continue
            store.start(row["ordinal"])
            variant = variants[row["variant"]]
            started, cleanup, result, resolved = time.perf_counter(), None, None, None
            status, error, cleanup_error = "failed", None, None
            initialization_cleanup = None
            try:
                pipeline, cleanup, resolved = builder(variant, dataset)
                prepared = time.perf_counter()
                result = pipeline.run(cases[row["case_id"]]["query"])
                elapsed = (time.perf_counter() - prepared) * 1000
                observed_status = result.metadata.get("status", "unknown")
                status = observed_status if observed_status in {"completed", "cancelled", "unsupported"} else "failed"
                resolved = plain(resolved)
                resolved["model"]["observed_models"] = sorted({str(event.data.get("resolved_model")) for event in result.traces if event.kind == "model_end" and event.data.get("resolved_model")})
                observation = {"result": plain(result), "grade": grade(result, cases[row["case_id"]], variant["rag"].get("top_k", 3), dataset), "latency_ms": elapsed, "setup_ms": (prepared - started) * 1000, "resolved_factors": resolved}
            except Exception as exc:
                # Provider/database exceptions may embed URLs or secrets. The adapter
                # retains sanitized evidence; generic exceptions expose type only.
                status = "unsupported" if isinstance(exc, UnsupportedCapability) else "failed"
                error = {"type": type(exc).__name__, "message": str(exc) if isinstance(exc, (ContractError, UnsupportedCapability)) else "adapter execution failed"}
                observation = {}
                adapter_usage = getattr(exc, "adapter_usage", None)
                if adapter_usage is None:
                    adapter_usage = getattr(exc, "raw", {}).get("lifetime_usage")
                if adapter_usage is not None:
                    observation["adapter_usage"] = plain(adapter_usage)
                initialization_cleanup = getattr(exc, "adapter_cleanup", None)
                if initialization_cleanup is not None and initialization_cleanup["status"] == "failed":
                    cleanup_error = plain(initialization_cleanup["error"])
                    status = "failed"
            finally:
                if cleanup is not None:
                    try:
                        cleanup()
                    except Exception as exc:
                        cleanup_error = {"type": type(exc).__name__, "message": "owned resource cleanup failed"}
                        status = "failed"
            cleanup_attempted = cleanup is not None or initialization_cleanup is not None
            cleanup_status = "failed" if cleanup_error else ("completed" if cleanup_attempted else "adapter_initialization_not_completed")
            observation.update({"error": error, "cleanup": {"status": cleanup_status, "attempted": cleanup_attempted, "error": cleanup_error}, "total_ms": (time.perf_counter() - started) * 1000})
            if resolved is not None:
                observation["resolved_factors"] = plain(resolved)
            store.finish(row["ordinal"], status, observation)
            report = store.export()
            completed += 1
            if progress:
                progress({"finished": sum(item["status"] not in {"pending", "running"} for item in report["rows"]), "total": len(report["rows"]), "variant": row["variant"], "case_id": row["case_id"], "status": status})
            if stop_after is not None and completed >= stop_after:
                break
        return summarize(store.export())


def summarize(report):
    result = dict(report)
    groups = defaultdict(list)
    for row in report["rows"]:
        groups[row["variant"]].append(row)
    summaries = {}
    for name, rows in groups.items():
        finished = [row for row in rows if row["status"] == "completed"]
        observations = [row["observation"] for row in finished]
        usage_rows = [(row.get("observation") or {}).get("result", {}).get("usage", (row.get("observation") or {}).get("adapter_usage", {})) for row in rows]
        costs = [usage.get("cost_usd") for usage in usage_rows]
        from .serialization import usage_cost_lower_bound
        known_cost = sum(usage_cost_lower_bound(usage) for usage in usage_rows)
        structural = [all(obs["grade"]["checks"].values()) for obs in observations]
        times = [obs["latency_ms"] for obs in observations]
        # Wilson assumes independent observations: aggregate repeated trials by case.
        by_case = defaultdict(list)
        for row, passed in zip(finished, structural, strict=True):
            by_case[row["case_id"]].append(passed)
        passed_cases = sum(all(values) for values in by_case.values())
        summaries[name] = {"scheduled": len(rows), "statuses": {status: sum(row["status"] == status for row in rows) for status in sorted({row["status"] for row in rows})}, "structural_passes": sum(structural), "case_wilson95": wilson(passed_cases, len(by_case)), "latency_ms": {"p50": percentile(times, .5), "p95": percentile(times, .95), "p99": percentile(times, .99)}, "cost_usd": sum(costs) if costs and all(cost is not None for cost in costs) else None, "observed_cost_usd": known_cost, "cost_complete": all(cost is not None for cost in costs), "semantic_verdict": "not_evaluated"}
    result["summary"] = summaries
    return result


def compare(report, baseline, candidate, *, axes, metric="recall_at_k", seed=0):
    axes = set(axes)
    if not report.get("complete") or axes - FACTORS:
        raise ContractError("comparison requires a complete run and known axes")
    metadata = report["metadata"]
    if not axes <= set(metadata["comparison_axes"]):
        raise ContractError("comparison axes were not declared before execution")
    configured = metadata["variant_factors"]
    if baseline == candidate or baseline not in configured or candidate not in configured:
        raise ContractError("comparison requires two distinct known variants")
    for factor in FACTORS - axes:
        if configured[baseline][factor] != configured[candidate][factor]:
            raise ContractError("incomparable configured factor: " + factor)
    pairs = {}
    for name in (baseline, candidate):
        rows = [row for row in report["rows"] if row["variant"] == name]
        if not rows or any(row["status"] != "completed" for row in rows):
            raise ContractError("comparison contains failed/unsupported/incomplete trials")
        pairs[name] = {(row["case_id"], row["trial"]): row["observation"] for row in rows}
        if len(pairs[name]) != len(rows):
            raise ContractError("duplicate paired observations")
        descriptors = {digest(row["observation"]["resolved_factors"]) for row in rows}
        if len(descriptors) != 1:
            raise ContractError("resolved configuration changed within variant")
    if set(pairs[baseline]) != set(pairs[candidate]):
        raise ContractError("missing paired observations")
    left, right = next(iter(pairs[baseline].values())), next(iter(pairs[candidate].values()))
    for factor in FACTORS - axes:
        if left["resolved_factors"].get(factor) != right["resolved_factors"].get(factor):
            raise ContractError("incomparable resolved factor: " + factor)
    deltas = defaultdict(list)
    for key in sorted(pairs[baseline]):
        before = pairs[baseline][key]["grade"]["metrics"].get(metric)
        after = pairs[candidate][key]["grade"]["metrics"].get(metric)
        if before is None or after is None:
            raise ContractError("metric unavailable in paired observations")
        deltas[key[0]].append(after - before)
    return {"baseline": baseline, "candidate": candidate, "axes": sorted(axes), "metric": metric, "paired_trials": len(pairs[baseline]), **paired_bootstrap(deltas, seed=seed), "semantic_verdict": "not_evaluated"}
