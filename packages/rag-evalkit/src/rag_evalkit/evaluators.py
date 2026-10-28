"""Source-backed structural checks and a blinded judge calibration boundary.

Citation membership is not faithfulness. A model judge without independent human
calibration remains unvalidated and is never automatically labelled ground truth.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Protocol

from .contracts import ContractError
from .metrics import ndcg_at_k, recall_at_k
from .rag import ABSTENTION, Evidence, RagResult


@dataclass(frozen=True)
class Evaluation:
    name: str
    value: float | None
    passed: bool | None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    scope: str = "structural"


def evaluate_retrieval(result: RagResult, relevance: Mapping[str, float], *, k: int = 10,
                       identity: str = "document_id") -> tuple[Evaluation, Evaluation]:
    if identity not in {"document_id", "chunk_id", "source_id"}:
        raise ContractError("retrieval identity must be document_id, chunk_id, or source_id")
    # Multiple chunks from the same document/source count once, in first-hit order.
    ids = list(dict.fromkeys(getattr(item, identity) for item in result.evidence))
    evidence = {"ranked_ids": ids, "relevance": dict(relevance), "k": k, "identity": identity}
    return (Evaluation("recall_at_k", recall_at_k(ids, relevance, k), None, evidence, "retrieval"),
            Evaluation("ndcg_at_k", ndcg_at_k(ids, relevance, k), None, evidence, "retrieval"))


def citation_check(answer: str, evidence: Sequence[Evidence], *, require_citation: bool = True) -> Evaluation:
    """Check [source:ID] membership only; never claim the cited text entails an answer."""
    citations = re.findall(r"\[source:([^\]\n]+)\]", answer)
    known = {item.source_id for item in evidence}
    unknown = sorted(set(citations) - known)
    passed = not unknown and (bool(citations) or not require_citation)
    return Evaluation("citation_membership", float(passed), passed,
                      {"cited_source_ids": citations, "retrieved_source_ids": sorted(known),
                       "unknown_source_ids": unknown, "required": require_citation,
                       "semantic_faithfulness": "not_evaluated"})


def source_lineage_check(result: RagResult) -> Evaluation:
    invalid = [index for index, item in enumerate(result.evidence)
               if not all(isinstance(value, str) and value for value in (item.document_id, item.chunk_id, item.source_id))]
    duplicate_chunks = len({item.chunk_id for item in result.evidence}) != len(result.evidence)
    passed = not invalid and not duplicate_chunks
    return Evaluation("source_lineage", float(passed), passed,
                      {"invalid_evidence_rows": invalid, "duplicate_chunk_ids": duplicate_chunks,
                       "evidence_count": len(result.evidence), "source_content_verified": False})


def abstention_check(result: RagResult, *, should_abstain: bool) -> Evaluation:
    observed = result.answer.strip() == ABSTENTION
    passed = observed == should_abstain
    return Evaluation("explicit_abstention", float(passed), passed,
                      {"expected": should_abstain, "observed": observed, "answer": result.answer,
                       "semantic_sufficiency": "not_evaluated"})


def tool_task_check(traces: Sequence[Any], *, expected_tools: Sequence[str], ordered: bool = True) -> Evaluation:
    """Check observed tool dispatch names; task semantics need a separate evaluator."""
    observed = [str(event.data.get("name")) for event in traces
                if event.kind == "tool_start" and event.data.get("name")]
    expected = list(expected_tools)
    passed = observed == expected if ordered else sorted(observed) == sorted(expected)
    return Evaluation("tool_dispatch_sequence", float(passed), passed,
                      {"observed_tools": observed, "expected_tools": expected, "ordered": ordered,
                       "task_completion": "not_evaluated"})


@dataclass(frozen=True)
class JudgeSample:
    id: str
    query: str
    answer: str
    evidence: tuple[Evidence, ...]
    human_score: float | None = None
    human_reviewer_id: str | None = None


@dataclass(frozen=True)
class BlindedSample:
    id: str
    query: str
    answer: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class JudgeDecision:
    score: float
    rationale: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score) or not 0 <= self.score <= 1:
            raise ContractError("judge score must be finite and between zero and one")


class Judge(Protocol):
    def describe(self) -> dict[str, Any]: ...
    def judge(self, sample: BlindedSample) -> JudgeDecision: ...


def blinded_calibration(samples: Sequence[JudgeSample], judge: Judge, *, seed: int = 0,
                        tolerance: float = 0.1, min_reviewed: int = 20) -> dict[str, Any]:
    """Blind row identities/order and compare independent human scores.

    Calling a live judge is the caller's explicit, budget-bounded responsibility.
    Enough reviewed rows produces an evaluated report, not an automatic semantic
    approval. Synthetic reviewer labels must never be represented as human review.
    """
    if not isinstance(min_reviewed, int) or isinstance(min_reviewed, bool) or min_reviewed < 1:
        raise ContractError("min_reviewed must be a positive integer")
    if not 0 <= tolerance <= 1 or not math.isfinite(tolerance):
        raise ContractError("calibration tolerance must be between zero and one")
    if len({sample.id for sample in samples}) != len(samples):
        raise ContractError("judge sample ids must be unique")
    for sample in samples:
        if not isinstance(sample.id, str) or not sample.id:
            raise ContractError("judge sample id must be a nonempty string")
        if (sample.human_score is None) != (sample.human_reviewer_id is None):
            raise ContractError("human score requires an independent reviewer identifier")
        if sample.human_reviewer_id is not None and (not isinstance(sample.human_reviewer_id, str) or not sample.human_reviewer_id.strip()):
            raise ContractError("human reviewer identifier must be a nonempty string")
        if sample.human_score is not None and (isinstance(sample.human_score, bool) or not isinstance(sample.human_score, (int, float))
                                               or not math.isfinite(sample.human_score) or not 0 <= sample.human_score <= 1):
            raise ContractError("human score must be finite and between zero and one")
    ordered = list(samples)
    random.Random(seed).shuffle(ordered)
    rows = []
    errors = []
    for index, sample in enumerate(ordered):
        opaque_id = hashlib.sha256(f"{seed}:{index}:{sample.id}".encode()).hexdigest()[:20]
        blinded_evidence = tuple(replace(item, score=0.0, raw_score=0.0, metadata={}) for item in sample.evidence)
        decision = judge.judge(BlindedSample(opaque_id, sample.query, sample.answer, blinded_evidence))
        error = abs(decision.score - sample.human_score) if sample.human_score is not None else None
        if error is not None:
            errors.append(error)
        rows.append({"sample_id": sample.id, "blinded_id": opaque_id, "decision": asdict(decision),
                     "human_score": sample.human_score, "human_reviewer_id": sample.human_reviewer_id,
                     "absolute_error": error})
    return {"schema_version": 1, "judge": judge.describe(), "seed": seed, "rows": rows,
            "reviewed_rows": len(errors), "required_reviewed_rows": min_reviewed,
            "status": "evaluated" if len(errors) >= min_reviewed else "pending_human_calibration",
            "mean_absolute_error": sum(errors) / len(errors) if errors else None,
            "agreement_within_tolerance": sum(error <= tolerance for error in errors) / len(errors) if errors else None,
            "tolerance": tolerance, "semantic_acceptance": "pending_independent_review",
            "blinding": "sample labels, reviewer scores, and retrieval metadata withheld; answer style remains visible"}
