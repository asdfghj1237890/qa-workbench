"""Measured vector-store latency/throughput against a frozen exact oracle."""

import concurrent.futures
import time

from .contracts import ContractError, SearchSpec
from .metrics import percentile
from .serialization import digest, usage_cost_lower_bound
from .stores.memory import MemoryStore


def benchmark_pipeline(factory, queries, *, repeats=3, warmup=1, concurrency=1):
    """Measure owned pipeline creation, query and cleanup under bounded load.

    Each request gets its own pipeline/model/resource lifetime. This avoids
    sharing a provider ledger or mutable SDK agent across concurrent requests.
    Warmup requests also execute and are included in the cost ledger.
    """
    from .experiments import environment
    from .serialization import plain

    if not queries or any(not isinstance(query, str) or not query.strip() for query in queries) or type(repeats) is not int or repeats < 1 or type(warmup) is not int or warmup < 0 or type(concurrency) is not int or not 1 <= concurrency <= 64:
        raise ContractError("invalid pipeline benchmark workload")

    def measure(task):
        index, warming = task
        started = time.perf_counter()
        cleanup = None
        initialization_cleanup = None
        row = {"query_index": index, "warmup": warming, "status": "failed", "usage": None, "error": None}
        try:
            pipeline, cleanup, resolved = factory()
            prepared = time.perf_counter()
            row["setup_ms"] = (prepared - started) * 1000
            result = pipeline.run(queries[index])
            row["query_ms"] = (time.perf_counter() - prepared) * 1000
            row["status"] = "completed" if result.metadata.get("status") == "completed" else "failed"
            row["usage"] = plain(result.usage)
            row["resolved_factors_sha"] = digest(resolved)
            row["result_sha"] = digest(result)
            row["answer_characters"] = len(result.answer)
            row["evidence_items"] = len(result.evidence)
        except Exception as exc:
            row["error"] = {"type": type(exc).__name__, "message": str(exc) if isinstance(exc, ContractError) else "pipeline benchmark request failed"}
            usage = getattr(exc, "adapter_usage", None)
            if usage is None:
                raw = getattr(exc, "raw", {})
                usage = raw.get("lifetime_usage", raw.get("usage"))
            if usage is not None:
                row["usage"] = plain(usage)
            initialization_cleanup = getattr(exc, "adapter_cleanup", None)
        finally:
            cleanup_started = time.perf_counter()
            row["cleanup_attempted"] = cleanup is not None or initialization_cleanup is not None
            if cleanup is None:
                row["cleanup"] = initialization_cleanup["status"] if initialization_cleanup is not None else "not_initialized"
                if initialization_cleanup is not None and initialization_cleanup["error"] is not None:
                    row["cleanup_error"] = plain(initialization_cleanup["error"])
            else:
                try:
                    cleanup()
                    row["cleanup"] = "completed"
                except Exception as exc:
                    row["cleanup"] = "failed"
                    row["status"] = "failed"
                    row["cleanup_error"] = {"type": type(exc).__name__}
            row["cleanup_ms"] = (time.perf_counter() - cleanup_started) * 1000
            row["total_ms"] = (time.perf_counter() - started) * 1000
        return row

    warm_rows = [measure((index, True)) for _ in range(warmup) for index in range(len(queries))]
    work = [(index, False) for _ in range(repeats) for index in range(len(queries))]
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        rows = list(executor.map(measure, work))
    duration = time.perf_counter() - started
    successes = [row for row in rows if row["status"] == "completed"]
    latencies = [row["total_ms"] for row in successes]
    all_rows = [*warm_rows, *rows]
    known_costs = [row["usage"]["cost_usd"] for row in all_rows if row["usage"] is not None and row["usage"].get("cost_usd") is not None]
    unknown_costs = len(all_rows) - len(known_costs)
    lower_bound = sum(usage_cost_lower_bound(row["usage"]) for row in all_rows)
    return {"schema_version": 1, "kind": "pipeline_load", "status": "completed" if all(row["status"] == "completed" for row in all_rows) else "failed",
            "environment": environment(), "workload_sha": digest(queries), "parameters": {"repeats": repeats, "warmup": warmup, "concurrency": concurrency},
            "attempts": len(rows), "completed": len(successes), "failed": len(rows) - len(successes),
            "latency_ms": {"p50": percentile(latencies, .5) if latencies else None, "p95": percentile(latencies, .95) if latencies else None, "p99": percentile(latencies, .99) if latencies else None},
            "throughput_qps": len(successes) / duration, "attempted_qps": len(rows) / duration,
            "cost_usd": None if unknown_costs else sum(known_costs), "known_cost_lower_bound_usd": lower_bound, "unknown_cost_requests": unknown_costs,
            "rows": all_rows, "semantic_acceptance": "not_evaluated",
            "measurement_limits": {"lifecycle": "one owned pipeline and model per request; total latency includes setup and cleanup",
                                   "cache": "uncontrolled", "hardware_isolation": "not_controlled", "server_resources": "not_measured",
                                   "warmup_costs": "included", "callbacks": "timeouts require cooperative adapter cancellation"}}


def benchmark_store(factory, documents, queries, *, repeats=3, warmup=1, concurrency=1):
    if not documents or not queries or type(repeats) is not int or repeats < 1 or type(warmup) is not int or warmup < 0 or type(concurrency) is not int or not 1 <= concurrency <= 64:
        raise ContractError("invalid benchmark workload")
    oracle = MemoryStore(len(documents[0].vector))
    oracle.upsert(documents)
    references = []
    for query in queries:
        full = oracle.search(SearchSpec(query.vector, len(documents), query.filters, query.metric, True))
        expected = min(query.top_k, len(full))
        cutoff = full[expected - 1].score if expected else None
        eligible = {hit.document.id for hit in full if cutoff is not None and hit.score >= cutoff - 1e-7}
        references.append((expected, eligible))
    oracle.close()

    store, setup_start = None, time.perf_counter()
    cleanup = {"status": "pending"}
    try:
        store = factory()
        created = time.perf_counter()
        store.upsert(documents)
        loaded = time.perf_counter()
        description = store.describe()
        # The first query is measured separately; OS/database cache state is not
        # controlled and is therefore never labelled a cold-cache benchmark.
        first_start = time.perf_counter()
        store.search(queries[0])
        first_ms = (time.perf_counter() - first_start) * 1000
        for _ in range(warmup):
            for query in queries:
                store.search(query)

        def measure(index):
            started = time.perf_counter()
            hits = store.search(queries[index])
            elapsed = (time.perf_counter() - started) * 1000
            expected, eligible = references[index]
            ids = [hit.document.id for hit in hits]
            if len(ids) != len(set(ids)) or len(ids) > queries[index].top_k:
                raise ContractError("backend returned duplicate/excess hits")
            recall = min(expected, len(set(ids) & eligible)) / expected if expected else None
            return {"query_index": index, "latency_ms": elapsed, "ann_recall_at_k": recall, "returned": len(ids)}

        work = [i for _ in range(repeats) for i in range(len(queries))]
        measured_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            rows = list(executor.map(measure, work))
        duration = time.perf_counter() - measured_start
        latencies = [row["latency_ms"] for row in rows]
        recalls = [row["ann_recall_at_k"] for row in rows if row["ann_recall_at_k"] is not None]
        report = {"schema_version": 1, "backend": description, "workload_sha": digest({"documents": documents, "queries": queries}), "parameters": {"repeats": repeats, "warmup": warmup, "concurrency": concurrency}, "setup_ms": (created - setup_start) * 1000, "ingest_ms": (loaded - created) * 1000, "first_query_ms": first_ms, "latency_ms": {"p50": percentile(latencies, .5), "p95": percentile(latencies, .95), "p99": percentile(latencies, .99)}, "throughput_qps": len(work) / duration, "ann_recall_at_k": sum(recalls) / len(recalls) if recalls else None, "rows": rows, "measurement_limits": {"cache": "uncontrolled; first query plus warmed measurements", "connections": "one shared adapter; backend connection serialization may apply", "server_resource_usage": "not_measured", "hardware_isolation": "not_controlled", "tie_tolerance": 1e-7}}
    finally:
        if store is not None:
            store.close()
        cleanup = {"status": "completed"}
    report["cleanup"] = cleanup
    return report
