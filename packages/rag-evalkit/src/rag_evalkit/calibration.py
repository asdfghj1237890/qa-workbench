"""Independent human-labelled development calibration for a declared judge.

Full private inputs are retained so scoring can recompute every statistic and
binding. Reviewer/provider identities remain explicit external self-attestations.
"""

import math

from .contracts import ContractError
from .quality import _fixture, _object, _ratings, verify_review
from .serialization import digest, plain


def _judge_identity(annotation):
    annotation = _object(annotation, "judge annotations")
    reviewer = _object(annotation.get("reviewer"), "judge reviewer")
    descriptor = reviewer.get("descriptor")
    if not isinstance(descriptor, dict) or descriptor.get("synthetic") is not False or _fixture(descriptor) or not isinstance(descriptor.get("model"), str) or not descriptor["model"].strip() or not any(isinstance(descriptor.get(name), str) and descriptor[name].strip() for name in ("provider", "adapter")):
        raise ContractError("judge calibration requires a declared live model descriptor")
    execution = _object(reviewer.get("execution"), "judge execution configuration")
    if set(execution) != {"harness", "limits"} or not _object(execution["harness"], "judge harness") or not _object(execution["limits"], "judge limits"):
        raise ContractError("judge identity requires actual harness and limits")
    models, observations, ratings = annotation.get("observed_models"), annotation.get("model_observations"), annotation.get("ratings")
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], str) or not models[0].strip() or not isinstance(observations, list) or not isinstance(ratings, list) or len(observations) != len(ratings) or any(not isinstance(row, dict) or not isinstance(row.get("sample_id"), str) for row in ratings) or any(not isinstance(row, dict) or not isinstance(row.get("sample_id"), str) or row.get("complete") is not True or row.get("models") != models for row in observations):
        raise ContractError("judge identity requires one observed model for every sample")
    if {row["sample_id"] for row in observations} != {row["sample_id"] for row in ratings}:
        raise ContractError("judge model observations must cover every rated sample")
    return digest({"descriptor": descriptor, "execution": execution, "observed_models": models})


def calibrate_judge(bundle, key, *, report, dataset, human, judge, min_samples=20, min_class=5, min_accuracy=.8):
    """Measure sensitivity/specificity by independent case, not repeated rows."""
    if type(min_samples) is not int or min_samples < 1 or type(min_class) is not int or min_class < 1 or isinstance(min_accuracy, bool) or not isinstance(min_accuracy, (float, int)) or not math.isfinite(min_accuracy) or not 0 <= min_accuracy <= 1:
        raise ContractError("invalid judge calibration thresholds")
    verify_review(bundle, key, report, dataset)
    human_rows, judge_rows = _ratings(bundle, human, "human"), _ratings(bundle, judge, "model")
    judge_identity = _judge_identity(judge)
    bindings = key["bindings"]
    case_ids = sorted({row["case_id"] for row in bindings})
    pending = [name for name in ("real_corpus_declared", "live_model_declared") if not bundle["eligibility"][name]]
    if any(row["split"] != "dev" for row in bindings):
        pending.append("development_only")
    if len(case_ids) < min_samples:
        pending.append("insufficient_independent_cases")
    criteria = {}
    for criterion in bundle["rubric"]["criteria"]:
        clusters = {True: {}, False: {}}
        for row in bindings:
            sample = row["sample_id"]
            expected = human_rows[sample]["scores"][criterion]
            clusters[expected].setdefault(row["case_id"], []).append(judge_rows[sample]["scores"][criterion] == expected)
        rates = {value: sum(sum(rows) / len(rows) for rows in cases.values()) / len(cases) if cases else None for value, cases in clusters.items()}
        sensitivity, specificity = rates[True], rates[False]
        criteria[criterion] = {"positive_cases": len(clusters[True]), "negative_cases": len(clusters[False]),
                               "sensitivity": sensitivity, "specificity": specificity,
                               "balanced_accuracy": (sensitivity + specificity) / 2 if sensitivity is not None and specificity is not None else None}
        if min(len(clusters[True]), len(clusters[False])) < min_class:
            pending.append("insufficient_class_support:" + criterion)
    passed = all(row[name] is not None and row[name] >= min_accuracy for row in criteria.values() for name in ("sensitivity", "specificity", "balanced_accuracy"))
    return plain({"schema_version": 1, "kind": "judge_calibration", "status": "pending" if pending else "passed" if passed else "failed", "pending": pending,
                  "policy": {"min_samples": min_samples, "min_class": min_class, "min_accuracy": min_accuracy, "aggregation": "equal_weight_independent_case_within_human_class"},
                  "independent_cases": len(case_ids), "case_ids": case_ids, "families": sorted({row["family"] for row in bindings}), "criteria": criteria,
                  "judge_identity_sha": judge_identity, "identity_verification": bundle["identity_verification"],
                  "inputs": {"bundle": bundle, "key": key, "report": report, "dataset": dataset, "human": human, "judge": judge}})


def verify_calibration(artifact, quality_key, judge, *, min_samples, min_class, min_accuracy, rubric):
    """Recompute a private calibration and enforce current policy and no leakage."""
    if not isinstance(artifact, dict) or artifact.get("schema_version") != 1 or artifact.get("kind") != "judge_calibration":
        raise ContractError("invalid judge calibration artifact")
    source, policy = artifact.get("inputs"), artifact.get("policy")
    if not isinstance(source, dict) or set(source) != {"bundle", "key", "report", "dataset", "human", "judge"} or not isinstance(policy, dict) or set(policy) != {"min_samples", "min_class", "min_accuracy", "aggregation"}:
        raise ContractError("calibration requires complete original inputs and policy")
    _object(quality_key, "quality private key")
    if not isinstance(quality_key.get("bindings"), list) or any(not isinstance(row, dict) or not isinstance(row.get("case_id"), str) or not isinstance(row.get("family"), str) for row in quality_key["bindings"]):
        raise ContractError("quality private key requires complete case bindings")
    recomputed = calibrate_judge(**source, min_samples=policy["min_samples"], min_class=policy["min_class"], min_accuracy=policy["min_accuracy"])
    if digest(recomputed) != digest(artifact):
        raise ContractError("calibration artifact differs from recomputed original inputs")
    if digest(source["bundle"]["rubric"]) != digest(rubric):
        raise ContractError("calibration and quality must use the same rubric")
    if set(artifact["case_ids"]) & {row["case_id"] for row in quality_key["bindings"]} or set(artifact["families"]) & {row["family"] for row in quality_key["bindings"]}:
        raise ContractError("calibration and quality cases and families must be disjoint")
    if judge is not None and artifact["judge_identity_sha"] != _judge_identity(judge):
        raise ContractError("calibration and quality judge descriptors differ")
    return calibrate_judge(**source, min_samples=min_samples, min_class=min_class, min_accuracy=min_accuracy)
