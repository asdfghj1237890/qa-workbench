"""Public RAG evaluation actions; assertions stay in the script layer."""

from test_support.observed import observed
from test_support.physical import rag as physical


@observed
def compare_retrieval_pipelines():
    return physical.run_pair()


@observed
def split_source_with_overlap():
    return physical.chunk_observation()


@observed
def ask_empty_corpus(kind):
    return physical.empty_result(kind)


@observed
def score_retrieval():
    return physical.retrieval_evaluation()


@observed
def inspect_citations(unknown=False):
    return physical.citation_observation(unknown)


@observed
def generate_truncated_answer():
    return physical.failure_status()


@observed
def inspect_lineage(duplicate=False):
    return physical.lineage_observation(duplicate)


@observed
def request_invalid_behavior(case):
    return physical.reject_invalid(case)


@observed
def inspect_blinded_calibration(reviewed=False):
    return physical.calibration_observation(reviewed)


@observed
def inspect_tool_dispatch(requested_only=False):
    return physical.tool_observation(requested_only)


@observed
def reject_invalid_calibration_before_judging():
    return physical.invalid_calibration_observation()


@observed
def compare_filtered_retrievers():
    return physical.filtered_pair()


@observed
def search_with_scalar_filter(value):
    return physical.filter_scalar_observation(value)
