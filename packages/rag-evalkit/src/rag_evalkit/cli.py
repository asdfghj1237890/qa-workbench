"""Portable command line; no implicit paid requests or repository imports."""

import argparse
import functools
import json
import sys
from pathlib import Path

from .artifacts import RunStore, atomic_json, list_runs
from .builtins import build_pipeline, check_live_budget, default_registry
from .contracts import ContractError, Document, SearchSpec, UnsupportedCapability
from .datasets import dataset_metadata, load_experiment
from .experiments import compare, create_run, execute, summarize
from .serialization import read_json


def _parser():
    parser = argparse.ArgumentParser(prog="rag-eval")
    parser.add_argument("--plugin", action="append", default=[], help="explicit installed rag_evalkit.plugins entry point")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("adapters")
    validate = commands.add_parser("validate")
    validate.add_argument("manifest")
    run = commands.add_parser("run")
    run.add_argument("manifest")
    run.add_argument("--output", default="runs")
    resume = commands.add_parser("resume")
    resume.add_argument("run_directory")
    for command in (run, resume):
        command.add_argument("--allow-live-models", action="store_true")
        command.add_argument("--allow-live-embeddings", action="store_true")
        command.add_argument("--max-total-usd", type=float)
    status = commands.add_parser("status")
    status.add_argument("output")
    comparison = commands.add_parser("compare")
    comparison.add_argument("run_directory")
    comparison.add_argument("--baseline", required=True)
    comparison.add_argument("--candidate", required=True)
    comparison.add_argument("--axes", nargs="+", required=True)
    comparison.add_argument("--metric", default="recall_at_k")
    comparison.add_argument("--seed", type=int, default=0)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("manifest")
    benchmark.add_argument("--variant", required=True)
    benchmark.add_argument("--output", required=True)
    benchmark.add_argument("--repeats", type=int, default=3)
    benchmark.add_argument("--warmup", type=int, default=1)
    benchmark.add_argument("--concurrency", type=int, default=1)
    benchmark.add_argument("--scope", choices=("store", "pipeline"), default="store")
    benchmark.add_argument("--allow-live-models", action="store_true")
    benchmark.add_argument("--allow-live-embeddings", action="store_true")
    benchmark.add_argument("--max-total-usd", type=float)
    prepare = commands.add_parser("quality-prepare")
    prepare.add_argument("run_directory")
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--seed", type=int, default=0)
    judge = commands.add_parser("quality-judge")
    judge.add_argument("bundle")
    judge.add_argument("model_config")
    judge.add_argument("--output", required=True)
    judge.add_argument("--allow-live-models", action="store_true")
    judge.add_argument("--max-total-usd", type=float)
    calibration = commands.add_parser("quality-calibrate")
    calibration.add_argument("bundle")
    calibration.add_argument("private_key")
    calibration.add_argument("run_directory")
    calibration.add_argument("--human", required=True)
    calibration.add_argument("--judge", required=True)
    calibration.add_argument("--output", required=True)
    calibration.add_argument("--min-samples", type=int, default=20)
    calibration.add_argument("--min-calibration-class", type=int, default=5)
    calibration.add_argument("--min-agreement", type=float, default=.8)
    audit = commands.add_parser("quality-audit-template")
    audit.add_argument("bundle")
    audit.add_argument("--human", required=True)
    audit.add_argument("--judge", required=True)
    audit.add_argument("--calibration", required=True)
    audit.add_argument("--output", required=True)
    quality = commands.add_parser("quality-score")
    quality.add_argument("bundle")
    quality.add_argument("private_key")
    quality.add_argument("run_directory")
    quality.add_argument("--human")
    quality.add_argument("--judge")
    quality.add_argument("--audit")
    quality.add_argument("--calibration")
    quality.add_argument("--output", required=True)
    quality.add_argument("--min-samples", type=int, default=20)
    quality.add_argument("--min-calibration-class", type=int, default=5)
    quality.add_argument("--min-agreement", type=float, default=.8)
    quality.add_argument("--min-pass-rate", type=float, default=.8)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        registry = default_registry()
        registry.load_plugins(args.plugin)
        if args.command == "adapters":
            result = registry.describe()
        elif args.command == "validate":
            manifest, dataset = load_experiment(args.manifest)
            known = {(row["kind"], row["name"]) for row in registry.describe()}
            for variant in manifest["variants"]:
                for kind in ("store", "embedding", "rag", "model", "harness"):
                    if (kind, variant[kind]["type"]) not in known:
                        raise UnsupportedCapability("unregistered adapter: " + kind + "/" + variant[kind]["type"])
            result = {"valid": True, **dataset_metadata(dataset), "variants": [row["id"] for row in manifest["variants"]], "executes_adapters": False}
        elif args.command in {"run", "resume"}:
            if args.command == "run":
                manifest, dataset = load_experiment(args.manifest)
                check_live_budget(manifest, dataset, args.max_total_usd)
                store = create_run(args.output, manifest, dataset)
            else:
                store = RunStore(args.run_directory)
                manifest, dataset = store.inputs["payload"]["manifest"], store.inputs["payload"]["dataset"]
                check_live_budget(manifest, dataset, args.max_total_usd)
            print("run_directory=" + str(store.directory), flush=True)
            builder = functools.partial(build_pipeline, registry=registry, allow_live_models=args.allow_live_models, allow_live_embeddings=args.allow_live_embeddings)
            report = execute(store, builder, progress=lambda row: print(json.dumps(row), file=sys.stderr, flush=True))
            atomic_json(store.directory / "report.json", report)
            result = {"run_directory": str(store.directory), "complete": report["complete"], "summary": report["summary"]}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not report["complete"] or any(row["status"] != "completed" for row in report["rows"]):
                return 1
            return 0 if all(all(row["observation"]["grade"]["checks"].values()) for row in report["rows"]) else 1
        elif args.command == "status":
            result = list_runs(args.output)
        elif args.command == "compare":
            result = compare(summarize(RunStore(args.run_directory).export()), args.baseline, args.candidate, axes=args.axes, metric=args.metric, seed=args.seed)
        elif args.command == "quality-prepare":
            from .quality import annotation_template, prepare_review
            store = RunStore(args.run_directory)
            bundle, key = prepare_review(store.export(), store.inputs["payload"]["dataset"], seed=args.seed)
            output = Path(args.output)
            output.mkdir(parents=True, exist_ok=False)
            atomic_json(output / "blind" / "bundle.json", bundle)
            atomic_json(output / "blind" / "human-template.json", annotation_template(bundle))
            atomic_json(output / "private" / "key.json", key)
            result = {"output": str(output), "samples": len(bundle["samples"]), "eligibility": bundle["eligibility"], "semantic_acceptance": "pending", "instructions": "Share only blind/ with annotators; retain private/ separately. Do not represent model ratings as human labels."}
        elif args.command == "quality-judge":
            from .quality import _object, annotate_with_model
            from .runtime import RunLimits
            bundle, config = read_json(args.bundle), read_json(args.model_config)
            _object(config, "judge configuration")
            model_config = _object(config.get("model"), "judge model configuration")
            if not isinstance(model_config.get("type"), str) or not model_config["type"]:
                raise ContractError("judge model configuration requires a type")
            limit_options = _object(config.get("limits", {}), "judge limits")
            if set(config) - {"model", "limits"} or "live_opt_in" in limit_options:
                raise ContractError("judge config supports model/limits; live opt-in is a CLI flag")
            model = registry.build("model", model_config, allow_live_models=args.allow_live_models)
            try:
                limits = RunLimits(**limit_options, live_opt_in=args.allow_live_models)
            except TypeError as exc:
                raise ContractError("judge limits require valid field names and numeric types") from exc
            result = annotate_with_model(bundle, model, limits, max_total_usd=args.max_total_usd, progress=lambda partial: atomic_json(args.output, partial))
            atomic_json(args.output, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "completed" else 1
        elif args.command == "quality-audit-template":
            from .quality import audit_template
            template = audit_template(read_json(args.bundle), human=read_json(args.human), judge=read_json(args.judge), calibration=read_json(args.calibration))
            atomic_json(args.output, template)
            result = {"output": args.output, "status": "requires_independent_human_review"}
        elif args.command == "quality-calibrate":
            from .calibration import calibrate_judge
            store = RunStore(args.run_directory)
            result = calibrate_judge(read_json(args.bundle), read_json(args.private_key), report=store.export(), dataset=store.inputs["payload"]["dataset"], human=read_json(args.human), judge=read_json(args.judge),
                                     min_samples=args.min_samples, min_class=args.min_calibration_class, min_accuracy=args.min_agreement)
            atomic_json(args.output, result)
            print(json.dumps({name: value for name, value in result.items() if name != "inputs"}, ensure_ascii=False, indent=2))
            return {"passed": 0, "failed": 1, "pending": 2}[result["status"]]
        elif args.command == "quality-score":
            from .quality import assess_quality
            store = RunStore(args.run_directory)
            result = assess_quality(read_json(args.bundle), read_json(args.private_key), report=store.export(), dataset=store.inputs["payload"]["dataset"], human=read_json(args.human) if args.human else None,
                                    judge=read_json(args.judge) if args.judge else None, audit=read_json(args.audit) if args.audit else None, calibration=read_json(args.calibration) if args.calibration else None,
                                    min_samples=args.min_samples, min_calibration_class=args.min_calibration_class, min_agreement=args.min_agreement, min_pass_rate=args.min_pass_rate)
            atomic_json(args.output, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return {"passed": 0, "failed": 1, "pending": 2}[result["status"]]
        elif args.command == "benchmark":
            from .benchmark import benchmark_pipeline, benchmark_store
            manifest, dataset = load_experiment(args.manifest)
            variant = next((row for row in manifest["variants"] if row["id"] == args.variant), None)
            if variant is None:
                raise ContractError("unknown benchmark variant")
            cases = [row for row in dataset["cases"] if manifest["split"] == "all" or row["split"] == manifest["split"]]
            if args.scope == "pipeline":
                budget_manifest = {**manifest, "variants": [variant], "repeats": args.repeats + args.warmup}
                check_live_budget(budget_manifest, dataset, args.max_total_usd)
                factory = functools.partial(build_pipeline, variant, dataset, registry=registry, allow_live_models=args.allow_live_models, allow_live_embeddings=args.allow_live_embeddings)
                result = benchmark_pipeline(factory, [row["query"] for row in cases], repeats=args.repeats, warmup=args.warmup, concurrency=args.concurrency)
            else:
                embedder = None
                result = None
                try:
                    if dataset.get("vector_policy") == "runtime":
                        budget_variant = {**variant, "model": {"type": "replay"}}
                        check_live_budget({**manifest, "variants": [budget_variant], "repeats": 1, "split": "all"}, {**dataset, "cases": cases[:1]}, args.max_total_usd)
                        embedder = registry.build("embedding", variant["embedding"], dataset=dataset, allow_live_embeddings=args.allow_live_embeddings)
                        doc_vectors = [embedder.embed(row["text"]) for row in dataset["documents"]]
                        query_vectors = [embedder.embed(row["query"]) for row in cases]
                    else:
                        doc_vectors = [row["vector"] for row in dataset["documents"]]
                        query_vectors = [row["query_vector"] for row in cases]
                    docs = [Document(row["id"], row["text"], tuple(vector), row.get("metadata", {})) for row, vector in zip(dataset["documents"], doc_vectors, strict=True)]
                    queries = [SearchSpec(tuple(vector), variant["rag"].get("top_k", 3), variant["rag"].get("filters", {}), variant["rag"].get("metric", "cosine"), variant["rag"].get("exact", True)) for vector in query_vectors]
                    result = benchmark_store(lambda: registry.build("store", variant["store"], dataset=dataset), docs, queries, repeats=args.repeats, warmup=args.warmup, concurrency=args.concurrency)
                    if embedder is not None:
                        result["embedding_usage"] = getattr(embedder, "usage", None)
                except Exception as exc:
                    if embedder is None:
                        raise
                    # Runtime embedding preparation can incur fees even before
                    # the store benchmark begins. Persist its partial ledger.
                    result = {"schema_version": 1, "kind": "store_load", "status": "failed",
                              "error": {"type": type(exc).__name__, "message": "store benchmark preparation or execution failed"},
                              "embedding_usage": getattr(embedder, "usage", None),
                              "cleanup": {"status": "not_completed_or_unobserved"}}
                finally:
                    if embedder is not None and callable(getattr(embedder, "close", None)):
                        try:
                            embedder.close()
                            if result is not None:
                                result["embedding_cleanup"] = {"status": "completed"}
                        except Exception as exc:
                            if result is None:
                                raise
                            result["status"] = "failed"
                            result["embedding_cleanup"] = {"status": "failed", "error": {"type": type(exc).__name__}}
            atomic_json(args.output, result)
            if result.get("status") == "failed":
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, UnsupportedCapability, OSError, ValueError) as exc:
        # OSError can embed paths/DSNs; do not print it verbatim.
        message = str(exc) if isinstance(exc, ContractError | UnsupportedCapability) else type(exc).__name__
        print("rag-eval: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
