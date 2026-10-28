"""Portable RAG behavior; only detached actions and native assertions."""

import pytest
from test_support.actions import rag


def test_two_independent_retrievers_preserve_the_same_source_evidence():
    result = rag.compare_retrieval_pipelines()
    assert result["vector"]["evidence"][0]["source_id"] == "lab:solar"
    assert result["lexical"]["evidence"][0]["source_id"] == "lab:solar"
    assert result["vector"]["evidence"][0]["document_id"] == "solar"
    assert result["vector"]["evidence"][0]["chunk_id"] == "solar:0"
    assert "[source:lab:solar]" in result["lexical"]["answer"]
    assert result["vector"]["metadata"]["semantic_verdict"] == "not_evaluated"
    assert result["descriptions"][0]["embedder"]["evidence_kind"] == "synthetic"
    assert result["descriptions"][1]["retriever"]["adapter"] == "bm25"


def test_chunk_overlap_retains_exact_source_offsets():
    chunks = rag.split_source_with_overlap()
    assert [chunk["text"] for chunk in chunks] == ["abcdef", "efghij"]
    assert [(chunk["start"], chunk["end"]) for chunk in chunks] == [(0, 6), (4, 10)]
    assert [chunk["source_id"] for chunk in chunks] == ["lab:span", "lab:span"]


@pytest.mark.parametrize("kind", ["vector", "lexical"])
def test_empty_corpus_abstains_without_a_model_request(kind):
    observed = rag.ask_empty_corpus(kind)
    assert observed["result"]["evidence"] == ()
    assert observed["model_requests"] == 0
    assert observed["abstention"]["passed"] is True
    assert observed["result"]["usage"]["cost_usd"] == 0.0


def test_retrieval_metrics_use_the_declared_relevance_labels():
    metrics = rag.score_retrieval()
    assert [metric["name"] for metric in metrics] == ["recall_at_k", "ndcg_at_k"]
    assert [metric["value"] for metric in metrics] == [1.0, 1.0]
    assert all(metric["scope"] == "retrieval" for metric in metrics)
    assert all(metric["passed"] is None for metric in metrics)


def test_known_citation_is_structural_evidence_only():
    check = rag.inspect_citations()
    assert check["passed"] is True
    assert check["evidence"]["semantic_faithfulness"] == "not_evaluated"


def test_fabricated_citation_is_rejected():
    check = rag.inspect_citations(unknown=True)
    assert check["passed"] is False
    assert check["evidence"]["unknown_source_ids"] == ["missing"]


def test_truncated_generation_is_not_a_completed_rag_run():
    result = rag.generate_truncated_answer()
    assert result["metadata"]["status"] != "completed"
    assert result["metadata"]["semantic_verdict"] == "not_evaluated"


@pytest.mark.parametrize("duplicate,expected", [(False, True), (True, False)])
def test_lineage_rejects_duplicate_retrieved_chunks(duplicate, expected):
    observed = rag.inspect_lineage(duplicate)
    assert observed["passed"] is expected
    assert observed["evidence"]["duplicate_chunk_ids"] is duplicate


@pytest.mark.parametrize("case,message", [
    ("unknown_embedding", "no frozen vector"),
    ("invalid_chunker", "overlap"),
    ("bad_source_id", "citation delimiters"),
    ("duplicate_chunks", "chunk ids must be unique"),
    ("blank_query", "query must be a nonempty"),
    ("unsupported_ann", "exact search only"),
    ("missing_lineage", "missing source lineage"),
    ("invalid_rank", "scores or rank violate"),
    ("invalid_score", "scores or rank violate"),
    ("duplicate_hits", "document ids must be unique"),
])
def test_invalid_or_unsupported_behavior_is_explicit(case, message):
    with pytest.raises(ValueError, match=message):
        rag.request_invalid_behavior(case)


def test_judge_without_independent_review_remains_pending():
    observed = rag.inspect_blinded_calibration()
    assert observed["report"]["status"] == "pending_human_calibration"
    assert observed["report"]["reviewed_rows"] == 0
    assert observed["report"]["agreement_within_tolerance"] is None
    assert observed["report"]["semantic_acceptance"] == "pending_independent_review"


def test_calibration_hides_candidate_labels_scores_and_retrieval_metadata():
    observed = rag.inspect_blinded_calibration(reviewed=True)
    judge_input = observed["judge_inputs"][0]
    assert "secret-provider" not in judge_input["id"]
    assert "human_score" not in judge_input
    assert judge_input["evidence"][0]["metadata"] == {}
    assert judge_input["evidence"][0]["score"] == 0.0
    assert observed["report"]["status"] == "evaluated"
    assert observed["report"]["semantic_acceptance"] == "pending_independent_review"
    assert observed["evidence_kind"] == "synthetic"


def test_tool_check_counts_dispatch_once_and_keeps_task_semantics_pending():
    observed = rag.inspect_tool_dispatch()
    assert observed["passed"] is True
    assert observed["evidence"]["observed_tools"] == ["lookup", "calculate"]
    assert observed["evidence"]["task_completion"] == "not_evaluated"


def test_tool_request_without_handler_start_does_not_count_as_dispatch():
    observed = rag.inspect_tool_dispatch(requested_only=True)
    assert observed["passed"] is False
    assert observed["evidence"]["observed_tools"] == []


def test_invalid_human_labels_are_rejected_before_any_judge_request():
    observed = rag.reject_invalid_calibration_before_judging()
    assert "reviewer identifier" in observed["error"]
    assert observed["judge_requests"] == 0


def test_both_retrievers_respect_the_same_metadata_filter():
    observed = rag.compare_filtered_retrievers()
    assert {item["source_id"] for item in observed["vector"]["evidence"]} == {"lab:solar", "lab:wind"}
    assert {item["source_id"] for item in observed["lexical"]["evidence"]} == {"lab:solar", "lab:wind"}


@pytest.mark.parametrize("value,expected", [(True, {"boolean"}), (1, {"integer", "float"}), (1.0, {"integer", "float"})])
def test_lexical_filters_keep_booleans_separate_from_numbers(value, expected):
    observed = rag.search_with_scalar_filter(value)
    assert {item["document_id"] for item in observed["evidence"]} == expected
