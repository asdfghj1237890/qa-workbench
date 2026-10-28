"""RAG wiring and observations.

Contract: rag.VectorRagPipeline/LexicalRagPipeline and runtime.ModelAdapter.
The local model, fixed vectors, and reviewer labels below are synthetic protocol
fixtures. They supply no live-provider or human semantic acceptance evidence.
"""

import re
from dataclasses import asdict, replace

from rag_evalkit.contracts import Capabilities, Document
from rag_evalkit.evaluators import (
    JudgeDecision,
    JudgeSample,
    abstention_check,
    blinded_calibration,
    citation_check,
    evaluate_retrieval,
    source_lineage_check,
    tool_task_check,
)
from rag_evalkit.rag import (
    LexicalRagPipeline,
    SourceDocument,
    SyntheticFixtureEmbedder,
    VectorRagPipeline,
    chunk_documents,
)
from rag_evalkit.runtime import Generation, TraceEvent, Usage
from rag_evalkit.stores.memory import MemoryStore

DOCUMENTS = (
    SourceDocument("solar", "The fictional Helio battery stores solar energy for six hours.", "lab:solar", {"domain": "energy"}),
    SourceDocument("water", "The fictional Aqua filter cleans water using a ceramic cartridge.", "lab:water", {"domain": "water"}),
    SourceDocument("wind", "The fictional Aero turbine has three blades and uses wind energy.", "lab:wind", {"domain": "energy"}),
)
QUERY = "How does the Helio solar battery store energy?"


class SyntheticEvidenceModel:
    capabilities = Capabilities(frozenset({"text", "system", "tool_calls"}))

    def __init__(self, *, finish_reason="completed"):
        self.calls = 0
        self.finish_reason = finish_reason

    def describe(self):
        return {"provider": "synthetic", "model": "source-citation-protocol-fixture", "live": False,
                "evidence_kind": "synthetic", "synthetic": True, "semantic_quality": "not_evaluated"}

    def generate(self, messages, *, tools=(), limits=None, cancel=None):
        self.calls += 1
        sources = re.findall(r"\[source:([^\]\n]+)\]", messages[-1].content)
        text = "Synthetic answer " + (f"[source:{sources[0]}]" if sources else "without evidence")
        return Generation(text, finish_reason=self.finish_reason,
                          usage=Usage(None, None, 0.0), provider="synthetic", model="citation-protocol-fixture")


def _harness(model):
    from rag_evalkit.harnesses import SingleTurnHarness
    return SingleTurnHarness(model)


def _fixture():
    chunks = chunk_documents(DOCUMENTS, chunk_size=200, overlap=0)
    vectors = {chunk.text: vector for chunk, vector in zip(chunks, ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)), strict=True)}
    vectors[QUERY] = (1., 0., 0.)
    return chunks, SyntheticFixtureEmbedder(vectors)


def run_pair():
    chunks, embedder = _fixture()
    store = MemoryStore(3)
    try:
        vector = VectorRagPipeline(store, embedder, _harness(SyntheticEvidenceModel()), top_k=1)
        vector.ingest(chunks)
        lexical = LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel()), top_k=1)
        return {"vector": asdict(vector.run(QUERY)), "lexical": asdict(lexical.run(QUERY)),
                "descriptions": [vector.describe(), lexical.describe()]}
    finally:
        store.close()


def chunk_observation():
    source = SourceDocument("span", "abcdefghij", "lab:span", {"label": "synthetic"})
    return [asdict(chunk) for chunk in chunk_documents((source,), chunk_size=6, overlap=2)]


def empty_result(kind):
    _, embedder = _fixture()
    model = SyntheticEvidenceModel()
    store = MemoryStore(3)
    try:
        pipeline = (VectorRagPipeline(store, embedder, _harness(model)) if kind == "vector"
                    else LexicalRagPipeline((), _harness(model)))
        result = pipeline.run(QUERY)
        return {"result": asdict(result), "model_requests": model.calls,
                "abstention": asdict(abstention_check(result, should_abstain=True))}
    finally:
        store.close()


def retrieval_evaluation():
    chunks, _ = _fixture()
    result = LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel()), top_k=1).run(QUERY)
    return [asdict(item) for item in evaluate_retrieval(result, {"solar": 2, "water": 0}, k=1)]


def citation_observation(unknown=False):
    chunks, _ = _fixture()
    result = LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel()), top_k=1).run(QUERY)
    answer = "A fabricated citation [source:missing]" if unknown else result.answer
    return asdict(citation_check(answer, result.evidence))


def failure_status():
    chunks, _ = _fixture()
    result = LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel(finish_reason="length")), top_k=1).run(QUERY)
    return asdict(result)


def lineage_observation(duplicate=False):
    chunks, _ = _fixture()
    result = LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel()), top_k=1).run(QUERY)
    if duplicate:
        result = replace(result, evidence=result.evidence + result.evidence)
    return asdict(source_lineage_check(result))


def reject_invalid(case):
    chunks, embedder = _fixture()
    if case == "unknown_embedding":
        embedder.embed("text that is not in the frozen fixture")
    elif case == "invalid_chunker":
        chunk_documents(DOCUMENTS, chunk_size=10, overlap=10)
    elif case == "bad_source_id":
        SourceDocument("a", "text", "injected]\nsource")
    elif case == "duplicate_chunks":
        LexicalRagPipeline((chunks[0], chunks[0]), _harness(SyntheticEvidenceModel()))
    elif case == "blank_query":
        LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel())).run("  ")
    else:
        class BrokenStore(MemoryStore):
            def search(self, spec):
                hits = super().search(spec)
                if case == "invalid_rank":
                    return [replace(hits[0], rank=0)]
                if case == "invalid_score":
                    return [replace(hits[0], score=float("nan"))]
                if case == "duplicate_hits":
                    return [hits[0], replace(hits[0], rank=2)]
                return hits
        store = BrokenStore(3)
        try:
            pipeline = VectorRagPipeline(store, embedder, _harness(SyntheticEvidenceModel()), exact=case != "unsupported_ann")
            if case == "missing_lineage":
                store.upsert([Document("raw", "source without provenance", (1., 0., 0.))])
            else:
                pipeline.ingest(chunks)
            pipeline.run(QUERY)
        finally:
            store.close()


class SyntheticJudge:
    def __init__(self):
        self.seen = []

    def describe(self):
        return {"adapter": "synthetic-judge-fixture", "live": False, "calibration": "synthetic_only"}

    def judge(self, sample):
        self.seen.append(asdict(sample))
        return JudgeDecision(1.0, "Synthetic rubric output", {"evidence_kind": "synthetic"})


def calibration_observation(reviewed=False):
    chunks, _ = _fixture()
    result = LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel()), top_k=1).run(QUERY)
    labelled_evidence = tuple(replace(item, metadata={"candidate": "hidden-provider", "human_score": 1.0}) for item in result.evidence)
    sample = JudgeSample("candidate:secret-provider", QUERY, result.answer, labelled_evidence,
                         human_score=1.0 if reviewed else None,
                         human_reviewer_id="synthetic-reviewer-fixture" if reviewed else None)
    judge = SyntheticJudge()
    report = blinded_calibration((sample,), judge, min_reviewed=1)
    return {"report": report, "judge_inputs": judge.seen, "evidence_kind": "synthetic"}


def invalid_calibration_observation():
    judge = SyntheticJudge()
    samples = (JudgeSample("valid", QUERY, "answer", (), 1.0, "synthetic-reviewer"),
               JudgeSample("invalid", QUERY, "answer", (), 1.0, None))
    try:
        blinded_calibration(samples, judge, seed=1, min_reviewed=1)
    except ValueError as exc:
        return {"error": str(exc), "judge_requests": len(judge.seen)}
    return {"error": None, "judge_requests": len(judge.seen)}


def filtered_pair():
    chunks, embedder = _fixture()
    store = MemoryStore(3)
    try:
        vector = VectorRagPipeline(store, embedder, _harness(SyntheticEvidenceModel()), top_k=3, filters={"domain": "energy"})
        vector.ingest(chunks)
        lexical = LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel()), top_k=3, filters={"domain": "energy"})
        return {"vector": asdict(vector.run(QUERY)), "lexical": asdict(lexical.run(QUERY))}
    finally:
        store.close()


def filter_scalar_observation(value):
    documents = tuple(SourceDocument(name, "solar battery", "lab:" + name, {"flag": flag})
                      for name, flag in (("boolean", True), ("integer", 1), ("float", 1.0)))
    chunks = chunk_documents(documents, chunk_size=100, overlap=0)
    pipeline = LexicalRagPipeline(chunks, _harness(SyntheticEvidenceModel()), filters={"flag": value})
    return asdict(pipeline.run("solar"))


def tool_observation(requested_only=False):
    if requested_only:
        traces = (TraceEvent("tool_requested", {"name": "lookup"}), TraceEvent("tool_requested", {"name": "calculate"}))
    else:
        traces = (TraceEvent("tool_requested", {"name": "lookup"}), TraceEvent("tool_start", {"name": "lookup"}),
                  TraceEvent("tool_result", {"name": "lookup"}), TraceEvent("tool_start", {"name": "calculate"}))
    return asdict(tool_task_check(traces, expected_tools=("lookup", "calculate")))
