"""Quality artifacts and real runner/CLI wiring; labels here are unit fixtures.

Contract: rag_evalkit.quality.prepare_review/assess_quality and
rag_evalkit.calibration.calibrate_judge bind original runs and self-attested labels.
"""

import contextlib
import copy
import io
import json

from rag_evalkit.artifacts import RunStore, atomic_json
from rag_evalkit.benchmark import benchmark_pipeline
from rag_evalkit.builtins import build_pipeline
from rag_evalkit.calibration import calibrate_judge
from rag_evalkit.cli import main
from rag_evalkit.models import ReplayModel
from rag_evalkit.models.http import HTTPResponse, Pricing
from rag_evalkit.models.openai import OpenAIResponsesModel
from rag_evalkit.quality import (
    annotate_with_model,
    annotation_template,
    assess_quality,
    prepare_review,
)
from rag_evalkit.runtime import RunLimits, RuntimeFailure
from rag_evalkit.serialization import digest, plain, read_json

from .experiments import inputs, run_example


def declared_records(*, split="holdout", prefix="", case_count=2, repeats=1):
    # Representative records exercise the offline gate. They are deliberately
    # not exported or presented as actual live-model/human quality evidence.
    dataset = {"schema_version": 1, "id": "unit-review-policy", "documents": [{"id": "d", "text": "Source text.", "source_id": "source:d", "vector": [1, 0]}],
               "provenance": {"evidence_kind": "real_corpus", "source": "unit declared source", "version": "unit-v1"},
               "cases": [{"id": prefix + "c" + str(index), "family": prefix + "f" + str(index), "split": split, "query": "Question " + str(index), "query_vector": [1, 0], "relevance": {"d": 1}} for index in range(case_count)]}
    evidence = [{"document_id": "d", "chunk_id": "d:0", "source_id": "source:d", "text": "Source text.", "rank": 1, "score": 1., "raw_score": 1., "metadata": {"start": 0, "end": 12}}]
    rows = []
    for variant in ("a", "b"):
        for trial in range(repeats):
            for case in dataset["cases"]:
                rows.append({"ordinal": len(rows), "case_id": case["id"], "variant": variant, "trial": trial, "status": "completed",
                             "observation": {"result": {"answer": "Answer [source:source:d]", "evidence": evidence, "metadata": {"status": "completed"}},
                                             "resolved_factors": {"model": {"synthetic": False, "provider": "unit-declared-live", "model": variant}}}})
    report = {"inputs_sha": digest(dataset), "metadata": {"dataset_sha": digest(dataset)}, "complete": True, "rows": rows}
    return report, dataset


def _annotations(bundle, key, *, alternating=False):
    human, judge = annotation_template(bundle), annotation_template(bundle, kind="model")
    case_ids = sorted({row["case_id"] for row in key["bindings"]})
    values = {row["sample_id"]: case_ids.index(row["case_id"]) % 2 == 0 for row in key["bindings"]}
    for annotation, identity in ((human, "unit-human"), (judge, "unit-model")):
        annotation["reviewer"].update(id=identity, attestation="Unit fixture representing a declared reviewer.")
        for row in annotation["ratings"]:
            row.update(scores={name: values[row["sample_id"]] if alternating else True for name in bundle["rubric"]["criteria"]}, rationale="Unit decision fixture.")
    judge["reviewer"]["descriptor"] = {"synthetic": False, "provider": "unit-declared-live", "model": "unit-judge-v1"}
    judge["reviewer"]["execution"] = {"harness": {"harness": "SingleTurnHarness", "harness_version": 1}, "limits": {key: value for key, value in plain(RunLimits()).items() if key != "live_opt_in"}}
    judge.update(status="completed", errors=[], observed_models=["unit-resolved-judge-v1"], model_observations=[{"sample_id": row["sample_id"], "models": ["unit-resolved-judge-v1"], "complete": True} for row in judge["ratings"]])
    return human, judge


def _calibration(kind="pass"):
    report, dataset = declared_records(split="holdout" if kind == "holdout_calibration" else "dev", prefix="cal-", case_count=20 if kind == "default_policy" else 4 if kind == "case_weights" else 2, repeats=5 if kind == "repeated_cases" else 1)
    if kind == "case_weights":
        for trial in range(1, 10):
            row = copy.deepcopy(report["rows"][0])
            row.update(ordinal=len(report["rows"]), trial=trial)
            report["rows"].append(row)
    if kind in {"case_leak", "family_leak"}:
        for index, case in enumerate(dataset["cases"]):
            case["family"] = "f" + str(index)
            if kind == "case_leak":
                original = case["id"]
                case["id"] = "c" + str(index)
                for row in report["rows"]:
                    if row["case_id"] == original:
                        row["case_id"] = case["id"]
    if kind == "synthetic_calibration":
        dataset["provenance"]["synthetic"] = True
    report["metadata"]["dataset_sha"] = digest(dataset)
    bundle, key = prepare_review(report, dataset, seed=11)
    human, judge = _annotations(bundle, key, alternating=kind != "positive_only")
    if kind in {"low_sensitivity", "low_specificity"}:
        for row in judge["ratings"]:
            row["scores"] = dict.fromkeys(row["scores"], kind == "low_specificity")
    if kind == "case_weights":
        samples = {row["sample_id"] for row in key["bindings"] if row["case_id"] == "cal-c0"}
        for row in judge["ratings"]:
            if row["sample_id"] in samples:
                row["scores"] = dict.fromkeys(row["scores"], False)
    policy = {} if kind in {"default_policy", "default_insufficient"} else {"min_samples": 2, "min_class": 1}
    return calibrate_judge(bundle, key, report=report, dataset=dataset, human=human, judge=judge, **policy)


def review_scenario(kind):
    report, dataset = declared_records()
    if kind == "dev":
        dataset["cases"][0]["split"] = "dev"
    if kind == "corpus":
        dataset.pop("provenance")
    if kind == "dataset_fixture":
        dataset["synthetic"] = True
    if kind == "provenance_fixture":
        dataset["provenance"]["synthetic"] = True
    if kind == "replay":
        report["rows"][0]["observation"]["resolved_factors"]["model"]["synthetic"] = True
    report["metadata"]["dataset_sha"] = digest(dataset)
    bundle, key = prepare_review(report, dataset, seed=17)
    human, judge = _annotations(bundle, key)
    if kind == "bad_quality":
        human["ratings"][0]["scores"]["grounded"] = False
        judge["ratings"][0]["scores"]["grounded"] = False
    if kind == "disagreement":
        for row in judge["ratings"]:
            row["scores"] = dict.fromkeys(row["scores"], False)
    calibration = _calibration(kind)
    if kind == "calibration_tamper":
        calibration["criteria"]["grounded"]["specificity"] = .9
    if kind == "calibration_status_tamper":
        calibration["status"] = "failed"
    if kind == "calibration_input_tamper":
        calibration["inputs"]["report"]["rows"][0]["observation"]["result"]["answer"] = "Changed calibration answer"
    if kind == "judge_identity":
        judge["reviewer"]["descriptor"]["model"] = "other-judge"
    if kind == "judge_limits":
        judge["reviewer"]["execution"]["limits"]["max_output_tokens"] = 16
    if kind == "observed_model_change":
        judge["observed_models"] = ["different-resolved-judge"]
        for row in judge["model_observations"]:
            row["models"] = judge["observed_models"]
    if kind == "unknown_observed_model":
        judge["observed_models"] = []
    if kind == "mixed_observed_model":
        judge["observed_models"].append("other-resolved-model")
    if kind == "failed_judge":
        judge["status"] = "failed"
    if kind == "judge_errors":
        judge["errors"] = [{"type": "BudgetExceeded"}]
    if kind == "missing_calibration":
        calibration = None
    audit = {"schema_version": 1, "bundle_sha": digest(bundle), "human_annotations_sha": digest(human), "judge_annotations_sha": digest(judge), "calibration_sha": digest(calibration),
             "reviewer": {"id": "unit-independent", "kind": "human"}, "decision": "approve", "rationale": "Unit audit fixture.", "reviewed_at": "2026-10-20T00:00:00Z"}
    if kind == "tamper":
        bundle["samples"][0]["answer"] = "A changed answer"
    if kind == "rehash_tamper":
        bundle["samples"][0]["answer"] = "A changed answer"
        key["bundle_sha"] = digest(bundle)
    if kind == "stale_annotations":
        human["bundle_sha"] = "0" * 64
    if kind == "missing_sample":
        human["ratings"].pop()
    if kind == "duplicate_sample":
        human["ratings"][0] = copy.deepcopy(human["ratings"][1])
    if kind == "synthetic_labels":
        human["synthetic"] = True
    if kind == "same_reviewer":
        audit["reviewer"]["id"] = human["reviewer"]["id"]
    if kind == "audit_mismatch":
        audit["human_annotations_sha"] = "0" * 64
    if kind == "audit_calibration_mismatch":
        audit["calibration_sha"] = "0" * 64
    if kind == "synthetic_audit":
        audit.update(synthetic=True, evidence_kind="synthetic_fixture")
    if kind == "missing_review":
        audit = None
    if kind == "pending":
        human = judge = audit = None
    try:
        result = assess_quality(bundle, key, report=report, dataset=dataset, human=human, judge=judge, audit=audit, calibration=calibration, min_samples=3 if kind == "sample_floor" else 2, min_calibration_class=2 if kind == "class_floor" else 1)
        return {"result": result, "error": None, "bundle": bundle, "calibration": calibration}
    except ValueError as exc:
        return {"result": None, "error": str(exc)}


def calibration_scenario(kind):
    return _calibration(kind)


def model_judge(kind):
    report, dataset = declared_records()
    bundle, _ = prepare_review(report, dataset)
    output = json.dumps({"scores": dict.fromkeys(bundle["rubric"]["criteria"], True), "rationale": "Unit model decision."})
    model = ReplayModel(["invalid"] * 4 if kind == "invalid" else [output] * 4)
    return annotate_with_model(bundle, model, RunLimits())


def live_judge_stub(kind):
    # Contract: actual OpenAIResponsesModel transport and SingleTurnHarness budget
    # handling; transport is an in-process stub and never sends an HTTP request.
    report, dataset = declared_records()
    bundle, _ = prepare_review(report, dataset)
    bundle["samples"] = bundle["samples"][:2]
    calls = []

    def transport(url, headers, body, timeout):
        calls.append(url)
        if url.endswith("/input_tokens"):
            return HTTPResponse(200, {"input_tokens": 1})
        index = sum(item.endswith("/responses") for item in calls)
        if kind == "unknown_cost":
            raise RuntimeFailure("provider_stream_error", raw={"partial_usage": {"input_tokens": 10, "output_tokens": 1}})
        output = json.dumps({"scores": dict.fromkeys(bundle["rubric"]["criteria"], True), "rationale": "Unit decision."})
        payload = {"status": "completed", "model": "actual-judge-b" if kind == "model_change" and index > 1 else "actual-judge-a",
                   "output": [{"type": "message", "content": [{"type": "output_text", "text": output}]}],
                   "usage": {"input_tokens": 2000 if kind == "overrun" else 1, "output_tokens": 0}}
        if kind == "unknown_model":
            payload.pop("model")
        return HTTPResponse(200, payload)

    model = OpenAIResponsesModel("configured-alias", api_key="unit-key", endpoint="https://unit.invalid/v1", transport=transport, pricing=Pricing(1, 0))
    result = annotate_with_model(bundle, model, RunLimits(live_opt_in=True, max_budget_usd=.001, max_input_tokens=1000), max_total_usd=.002)
    return {"result": result, "generation_dispatches": sum(item.endswith("/responses") for item in calls)}


def synthetic_marker(kind, value):
    report, dataset = declared_records()
    if kind == "dataset":
        dataset["synthetic"] = value
    elif kind == "provenance":
        dataset["provenance"]["synthetic"] = value
    else:
        report["rows"][0]["observation"]["resolved_factors"]["model"]["synthetic"] = value
    report["metadata"]["dataset_sha"] = digest(dataset)
    try:
        bundle, _ = prepare_review(report, dataset)
        return {"bundle": bundle, "error": None}
    except ValueError as exc:
        return {"bundle": None, "error": str(exc)}


def benchmark_scenario(kind):
    manifest, dataset = inputs()
    variant = manifest["variants"][0]
    cleaned = []

    def factory():
        pipeline, cleanup, resolved = build_pipeline(variant, dataset)
        if kind == "failure":
            def fail(query):
                raise RuntimeError("Sensitive failure text should not escape")
            pipeline.run = fail

        def close():
            cleaned.append(1)
            cleanup()
        return pipeline, close, resolved

    result = benchmark_pipeline(factory, [dataset["cases"][0]["query"]], repeats=3, warmup=1, concurrency=2)
    return {"result": result, "cleanup_calls": len(cleaned)}


def cli_review(path):
    run = run_example(path / "runs")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        prepared = main(["quality-prepare", run["directory"], "--output", str(path / "review")])
        scored = main(["quality-score", str(path / "review/blind/bundle.json"), str(path / "review/private/key.json"), run["directory"], "--output", str(path / "score.json")])
    return {"prepare_exit": prepared, "score_exit": scored, "score": read_json(path / "score.json"), "private_is_separate": (path / "review/private/key.json").is_file()}


def _persist_declared(path, *, calibration=False):
    report, dataset = declared_records(split="dev" if calibration else "holdout", prefix="cal-" if calibration else "")
    # Persist representative provider records through the real immutable journal.
    # These remain unit fixtures, never actual human/live-provider evidence.
    schedule = [(row["variant"], row["case_id"], row["trial"]) for row in report["rows"]]
    manifest, _ = inputs()
    manifest.update(split="dev" if calibration else "holdout", repeats=1,
                    variants=[{**manifest["variants"][0], "id": name} for name in ("a", "b")])
    store = RunStore.create(path, manifest, dataset, schedule, report["metadata"])
    for row in report["rows"]:
        store.start(row["ordinal"])
        store.finish(row["ordinal"], row["status"], row["observation"])
    return store


def cli_calibration(path, malformed=None):
    stores = [_persist_declared(path / "calibration-runs", calibration=True), _persist_declared(path / "quality-runs")]
    exits, records = [], []
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        for index, store in enumerate(stores):
            folder = path / ("calibration" if index == 0 else "quality")
            exits.append(main(["quality-prepare", str(store.directory), "--output", str(folder)]))
            bundle, key = read_json(folder / "blind/bundle.json"), read_json(folder / "private/key.json")
            human, judge = _annotations(bundle, key, alternating=index == 0)
            atomic_json(folder / "human.json", human)
            atomic_json(folder / "judge.json", judge)
            records.append((folder, bundle, human, judge))
        folder, _, _, _ = records[0]
        exits.append(main(["quality-calibrate", str(folder / "blind/bundle.json"), str(folder / "private/key.json"), str(stores[0].directory),
                           "--human", str(folder / "human.json"), "--judge", str(folder / "judge.json"), "--output", str(path / "calibration.json"), "--min-samples", "2", "--min-calibration-class", "1"]))
        calibration = read_json(path / "calibration.json")
        folder, _, _, _ = records[1]
        exits.append(main(["quality-audit-template", str(folder / "blind/bundle.json"), "--human", str(folder / "human.json"), "--judge", str(folder / "judge.json"), "--calibration", str(path / "calibration.json"), "--output", str(folder / "audit.json")]))
        template = read_json(folder / "audit.json")
        score_args = ["quality-score", str(folder / "blind/bundle.json"), str(folder / "private/key.json"), str(stores[1].directory),
                           "--human", str(folder / "human.json"), "--judge", str(folder / "judge.json"), "--audit", str(folder / "audit.json"), "--calibration", str(path / "calibration.json"),
                           "--output", str(path / "score.json"), "--min-samples", "2", "--min-calibration-class", "1"]
        incomplete_exit = main(score_args)
        audit = copy.deepcopy(template)
        audit.update(decision="approve", rationale="Unit audit fixture.", reviewed_at="2026-10-20T00:00:00Z")
        audit["reviewer"]["id"] = "unit-independent"
        atomic_json(folder / "audit.json", audit)
        if malformed is not None:
            paths = {"bundle": folder / "blind/bundle.json", "key": folder / "private/key.json", "human": folder / "human.json", "judge": folder / "judge.json", "audit": folder / "audit.json", "calibration": path / "calibration.json"}
            name = "audit" if malformed == "audit_reviewer" else "calibration" if malformed == "calibration_bundle" else malformed
            value = read_json(paths[name])
            if malformed == "audit_reviewer":
                value["reviewer"] = []
            elif malformed == "calibration_bundle":
                value["inputs"]["bundle"] = []
            else:
                value = []
            atomic_json(paths[name], value)
        exits.append(main(score_args))
    return {"exits": exits, "incomplete_template_exit": incomplete_exit, "template": template, "calibration": calibration, "score": read_json(path / "score.json") if (path / "score.json").is_file() else None}
