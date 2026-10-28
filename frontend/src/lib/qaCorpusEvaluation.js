// Contract: app/qa_corpus.py bank and review schemas, qa_corpus_evaluations.py
// owner-scoped public jobs. Retrieval and semantic quality remain separate.
const DIMENSIONS = ["intent", "grounding", "completeness", "language"];
const HARNESS = "application_harness_real_es";
const STANDARD_RATES = { input: 2, cache_write: 2.5, cached_input: 0.1, output: 10, embedding: 0.02 };
const EXCLUDED = ["firebase_identity", "turnstile", "http_api_owner_controls", "http_sse_delivery", "chat_persistence", "usage_log_persistence", "production_deployment"];
const STATES = new Set(["queued", "running", "completed", "incomplete", "failed", "cancelled", "timed_out", "stale"]);
const count = (value, max = 50) => Number.isSafeInteger(value) && value >= 0 && value <= max;
const text = (value, max = 4096) => typeof value === "string" && value.trim().length > 0 && value.length <= max;
const hash = (value) => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const sha = (value) => typeof value === "string" && /^[a-f0-9]{40}$/.test(value);
const id = (value) => typeof value === "string" && /^[a-zA-Z0-9-]{1,64}$/.test(value);
const caseId = (value) => typeof value === "string" && /^real-\d{3}$/.test(value);
const timestamp = (value) => text(value, 64) && /^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const finite = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
const boundedArray = (value, maximum = 50) => Array.isArray(value) && value.length <= maximum;
const mapCounts = (value) => value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length <= 100 && Object.entries(value).every(([key, n]) => text(key) && count(n, 100));
const unique = (values) => new Set(values).size === values.length;
const strings = (value, max = 50) => boundedArray(value, max) && value.every((entry) => text(entry));
const equalRate = (a, b) => Math.abs(a - b) < 1e-9;
const expectedRecall = (expected, found) => expected.filter((item) => found.includes(item)).length / expected.length;
const firstRank = (expected, found) => { const position = found.findIndex((item) => expected.includes(item)); return position < 0 ? 0 : 1 / (position + 1); };
export const corpusActive = (job) => ["queued", "running"].includes(job?.status);
export const corpusCasePassed = (row) => !!row?.scores && DIMENSIONS.every((name) => row.scores[name] === true);
export const corpusHarness = (job) => job?.engine === HARNESS;

export function validCorpusBank(bank) {
  const provenance = bank?.provenance, coverage = bank?.coverage;
  return !!bank && text(bank.id, 80) && text(bank.version, 100) && hash(bank.sha256) && hash(bank.source_sha256)
    && timestamp(bank.created_at) && count(bank.case_count) && bank.case_count > 0 && count(bank.document_count) && bank.document_count > 0
    && coverage && [coverage.splits, coverage.categories, coverage.task_types, coverage.sources].every(mapCounts)
    && Object.keys(coverage.splits).every((split) => ["dev", "holdout"].includes(split))
    && Object.values(coverage.splits).reduce((sum, n) => sum + n, 0) === bank.case_count
    && text(coverage.date_window?.start) && text(coverage.date_window?.end)
    && provenance?.kind === "elasticsearch" && provenance.alias === "news_read" && timestamp(provenance.captured_at)
    && boundedArray(provenance.indices, 32) && provenance.indices.length > 0 && provenance.indices.every((entry) => text(entry.name, 255) && text(entry.uuid, 255))
    && unique(provenance.indices.map((entry) => entry.name)) && hash(provenance.mapping_sha256) && text(provenance.embed_model)
    && count(provenance.embed_dim, 65536) && provenance.embed_dim > 0;
}
function validRetrieval(value) {
  return value && value.metric_scope === "actual_tool_rankings" && value.aggregation === "union_recall_mean_call_rr"
    && strings(value.expected) && value.expected.length > 0 && unique(value.expected) && strings(value.found, 2500) && unique(value.found)
    && finite(value.recall) && value.recall <= 1 && finite(value.mrr) && value.mrr <= 1 && typeof value.passed === "boolean"
    && boundedArray(value.calls, 1000) && value.calls.every((call) => count(call.turn, 2) && call.turn > 0 && text(call.tool, 256)
      && (call.call_id === null || text(call.call_id, 256)) && strings(call.article_ids, 1000) && count(call.returned_k, 1000) && call.returned_k === call.article_ids.length
      && finite(call.recall) && equalRate(call.recall, expectedRecall(value.expected, call.article_ids))
      && finite(call.reciprocal_rank) && equalRate(call.reciprocal_rank, firstRank(value.expected, call.article_ids)))
    && equalRate(value.recall, expectedRecall(value.expected, value.found))
    && equalRate(value.mrr, value.calls.length ? value.calls.reduce((sum, call) => sum + call.reciprocal_rank, 0) / value.calls.length : 0)
    && JSON.stringify(value.found) === JSON.stringify([...new Set(value.calls.flatMap((call) => call.article_ids))])
    && (!value.passed || (value.calls.length > 0 && value.expected.every((item) => value.found.includes(item))));
}
function validCoverage(value) { return value && strings(value.expected) && value.expected.length > 0 && unique(value.expected) && strings(value.found, 1000) && unique(value.found) && finite(value.recall) && equalRate(value.recall, expectedRecall(value.expected, value.found)); }
function validCase(row, harness = false) {
  return row && caseId(row.case_id) && ["dev", "holdout"].includes(row.split) && text(row.category) && text(row.task_type)
    && strings(row.questions, 2) && row.questions.length === 2 && hash(row.row_sha) && (row.error === null || text(row.error))
    && boundedArray(row.expected_facts) && row.expected_facts.length > 0 && row.expected_facts.every((fact) => text(fact.article_id, 256) && text(fact.quote, 12000) && text(fact.claim, 12000))
    && boundedArray(row.expected_sources) && row.expected_sources.length > 0 && row.expected_sources.every((source) => text(source.article_id, 256) && text(source.title) && hash(source.content_sha256))
    && boundedArray(row.answers, 2) && row.answers.every((answer) => count(answer.turn, 2) && answer.turn > 0 && text(answer.question)
      && typeof answer.answer_md === "string" && answer.answer_md.length <= 2 * 1024 * 1024 && boundedArray(answer.items, 500) && boundedArray(answer.citations, 500)
      && (harness ? ["completed", "failed", "cancelled"].includes(answer.status) && typeof answer.raw_model_answer === "string"
        && answer.context_snapshot && boundedArray(answer.context_snapshot.items, 500)
        && answer.context_snapshot.full_texts && typeof answer.context_snapshot.full_texts === "object" && !Array.isArray(answer.context_snapshot.full_texts)
        && answer.context_snapshot.refs && typeof answer.context_snapshot.refs === "object" && !Array.isArray(answer.context_snapshot.refs)
        : boundedArray(answer.tool_trace, 1000)))
    && boundedArray(row.tool_trace, 1000) && typeof row.tool_trace_truncated === "boolean"
    && validRetrieval(row.retrieval) && validCoverage(row.final_source_coverage)
    && JSON.stringify(row.final_source_coverage.expected) === JSON.stringify(row.retrieval.expected)
    && JSON.stringify(row.final_source_coverage.found) === JSON.stringify([...new Set(row.answers.flatMap((answer) => answer.items.map((item) => item.article_id)).filter((item) => typeof item === "string"))])
    && (!row.retrieval.passed || (row.answers.length === 2 && row.tool_trace.length > 0 && !row.tool_trace_truncated))
    && (!harness || (row.engine === HARNESS && ["completed", "failed", "cancelled"].includes(row.status)));
}
function verifiedAfter(job) {
  if (corpusHarness(job)) return job.index_observation?.scope === "dynamic_index_fixed_question_bank"
    && job.index_observation.verified_before_run === true && job.index_observation.verified_after_run === true
    && job.index_observation.verified_documents === job.bank?.document_count;
  const evidence = job.index_observation?.verified_after_run, provenance = job.bank?.provenance;
  return evidence && evidence.alias === provenance?.alias && evidence.mapping_sha256 === provenance.mapping_sha256
    && evidence.embed_model === provenance.embed_model && evidence.embed_dim === provenance.embed_dim
    && evidence.verified_documents === job.bank.document_count && Array.isArray(evidence.indices)
    && evidence.indices.length === provenance.indices.length
    && evidence.indices.every((index) => provenance.indices.some((entry) => entry.name === index.name && entry.uuid === index.uuid));
}
function validReviewRow(row) {
  return row && caseId(row.case_id) && hash(row.row_sha) && text(row.reason, 12000) && row.scores
    && Object.keys(row.scores).length === DIMENSIONS.length && DIMENSIONS.every((name) => typeof row.scores[name] === "boolean");
}
export function corpusReview(job, { summary = job?.cases === undefined } = {}) {
  if (corpusHarness(job)) return harnessReview(job, { summary });
  const review = job?.semantic_review;
  if (!job || job.semantic_status !== "reviewed" || corpusActive(job) || !STATES.has(job.status) || !job.report_available || !hash(job.report_sha256)
    || !review || !["ai", "human"].includes(review.reviewer_kind) || !text(review.reviewer) || !timestamp(review.reviewed_at)
    || review.report_sha256 !== job.report_sha256 || !count(job.completed_cases) || !job.completed_cases || !count(job.total_cases)
    || review.reviewed_cases !== job.completed_cases || !count(review.passed) || !count(review.failed) || review.passed + review.failed !== review.reviewed_cases
    || !boundedArray(review.cases) || review.cases.length !== review.reviewed_cases || !review.cases.every(validReviewRow)
    || !unique(review.cases.map((row) => row.case_id)) || !unique(review.cases.map((row) => row.row_sha)) || review.cases.filter(corpusCasePassed).length !== review.passed) return null;
  const traceComplete = Array.isArray(job.cases) && job.cases.every((row) => Array.isArray(row.tool_trace) && row.tool_trace.length > 0 && row.tool_trace_truncated === false);
  const passed = job.status === "completed" && job.completed_cases === job.total_cases && job.retrieval?.failed === 0 && review.failed === 0 && !job.error && !!verifiedAfter(job) && traceComplete;
  if (job.quality_passed !== passed) return null;
  if (job.cases === undefined) return summary ? review : null;
  if (!boundedArray(job.cases) || job.cases.length !== job.completed_cases || job.cases.some((row) => !review.cases.some((entry) => entry.case_id === row.case_id && entry.row_sha === row.row_sha))) return null;
  return review;
}
export const corpusCaseReview = (job, row) => corpusReview(job)?.cases.find((entry) => entry.case_id === row?.case_id && entry.row_sha === row?.row_sha) || null;

function harnessReview(job, { summary }) {
  const review = job.semantic_review;
  if (job.semantic_status !== "reviewed" || corpusActive(job) || !STATES.has(job.status) || job.report_available !== true
    || !hash(job.report_sha256) || !review || review.status !== "completed" || !["ai", "human"].includes(review.reviewer_kind)
    || !text(review.reviewer) || !timestamp(review.reviewed_at) || review.report_sha256 !== job.report_sha256
    || !count(job.completed_cases) || job.completed_cases === 0 || !count(job.total_cases)
    || review.reviewed_cases !== job.completed_cases || ![review.passed, review.failed, review.not_assessable].every((n) => count(n))
    || review.passed + review.failed + review.not_assessable !== review.reviewed_cases
    || !boundedArray(review.cases) || review.cases.length !== review.reviewed_cases
    || !unique(review.cases.map((row) => row.case_id)) || !unique(review.cases.map((row) => row.row_sha))) return null;
  for (const row of review.cases) {
    if (!caseId(row?.case_id) || !hash(row.row_sha) || !text(row.reason, 12000)) return null;
    if (row.assessment_status === "not_assessable") { if (row.scores !== null) return null; }
    else if (row.assessment_status !== "assessed" || !validReviewRow(row)) return null;
  }
  const assessed = review.cases.filter((row) => row.assessment_status === "assessed");
  if (assessed.filter(corpusCasePassed).length !== review.passed || assessed.length - review.passed !== review.failed
    || review.cases.filter((row) => row.assessment_status === "not_assessable").length !== review.not_assessable) return null;
  if (!Array.isArray(job.cases)) return summary && job.quality_passed === false ? review : null;
  if (job.cases.length !== job.completed_cases || job.cases.some((row) => {
    const attached = review.cases.find((entry) => entry.case_id === row.case_id && entry.row_sha === row.row_sha);
    if (!attached) return true;
    if (attached.assessment_status === "not_assessable") return row.tool_trace_truncated === false && row.tool_trace?.length > 0
      && row.answers?.length === 2 && row.answers.every((answer) => answer.status === "completed" && text(answer.answer_md, 2 * 1024 * 1024));
    return !row.answers?.some((answer) => text(answer.answer_md, 2 * 1024 * 1024));
  })) return null;
  const passed = job.status === "completed" && job.completed_cases === job.total_cases && job.retrieval?.failed === 0
    && review.failed === 0 && review.not_assessable === 0 && !job.error && verifiedAfter(job)
    && validHarnessLedger(job.provider_budget) && !job.provider_budget.halted
    && job.provider_budget.retained_unknown_micro_usd === 0 && job.provider_budget.inflight_reserved_micro_usd === 0
    && job.cases.every((row) => row.status === "completed" && row.tool_trace?.length > 0 && row.tool_trace_truncated === false
      && row.answers.length === 2 && row.answers.every((answer) => answer.status === "completed"));
  return job.quality_passed === passed ? review : null;
}

export function validCorpusJob(job, { summary = false } = {}) {
  if (corpusHarness(job)) return validHarnessJob(job, { summary });
  if (job?.engine !== undefined) return false;
  return !!job && job.mode === "real_corpus_quality" && id(job.id) && STATES.has(job.status) && (job.source_sha === null || sha(job.source_sha))
    && validCorpusBank(job.bank) && ["all", "dev", "holdout"].includes(job.split)
    && boundedArray(job.selected_case_ids) && job.selected_case_ids.length > 0 && job.selected_case_ids.every(caseId) && unique(job.selected_case_ids)
    && job.total_cases === job.selected_case_ids.length && job.total_cases <= (job.split === "all" ? job.bank.case_count : job.bank.coverage.splits[job.split] || 0) && count(job.completed_cases, job.total_cases)
    && timestamp(job.started_at) && (corpusActive(job) ? job.finished_at === null : timestamp(job.finished_at)) && validPricing(job.pricing)
    && count(job.retrieval?.passed, job.completed_cases) && count(job.retrieval?.failed, job.completed_cases)
    && job.retrieval.passed + job.retrieval.failed === job.completed_cases
    && typeof job.report_available === "boolean" && (job.report_available ? hash(job.report_sha256) : job.report_sha256 === null)
    && (job.error === null || text(job.error)) && typeof job.quality_passed === "boolean"
    && (job.status !== "completed" || job.completed_cases === job.total_cases)
    && ((job.semantic_status === "pending_review" && job.semantic_review === null && job.quality_passed === false) || !!corpusReview(job, { summary }))
    && ((summary && job.cases === undefined) || (boundedArray(job.cases) && job.cases.length === job.completed_cases && job.cases.every((row) => validCase(row))
      && unique(job.cases.map((row) => row.case_id)) && job.cases.every((row) => job.selected_case_ids.includes(row.case_id) && (job.split === "all" || row.split === job.split) && (job.status !== "completed" || row.answers.length === 2)) && job.cases.filter((row) => row.retrieval.passed).length === job.retrieval.passed));
}
function micro(value) { return Number.isSafeInteger(value) && value >= 0 && value <= 10000000; }
function validHarnessLedger(ledger) {
  if (!ledger || typeof ledger.halted !== "boolean" || !(ledger.halted ? text(ledger.halt_reason, 256) : ledger.halt_reason === null)
    || ![ledger.max_micro_usd, ledger.committed_upper_micro_usd, ledger.retained_unknown_micro_usd, ledger.inflight_reserved_micro_usd, ledger.available_micro_usd].every(micro)
    || ledger.max_micro_usd <= 0 || !boundedArray(ledger.requests, 5000)) return false;
  let committed = 0, unknown = 0, inflight = 0;
  for (const [index, request] of ledger.requests.entries()) {
    if (!request || request.request_index !== index + 1 || !["main", "judge", "embedding"].includes(request.kind)
      || request.model !== (request.kind === "embedding" ? "text-embedding-3-small" : "gpt-6.1-sol")
      || !["settled", "unknown", "reserved"].includes(request.outcome) || !micro(request.reservation_micro_usd)
      || request.reservation_micro_usd === 0) return false;
    if (request.outcome === "settled") {
      const usage = request.usage;
      if (!micro(request.cost_upper_micro_usd) || request.cost_upper_micro_usd > request.reservation_micro_usd
        || !usage || ![usage.input_tokens, usage.output_tokens, usage.total_tokens].every((value) => Number.isSafeInteger(value) && value >= 0)
        || usage.input_tokens + usage.output_tokens !== usage.total_tokens) return false;
      committed += request.cost_upper_micro_usd;
    } else {
      if (request.cost_upper_micro_usd !== null || request.usage !== null) return false;
      if (request.outcome === "unknown") unknown += request.reservation_micro_usd;
      else inflight += request.reservation_micro_usd;
    }
  }
  return committed === ledger.committed_upper_micro_usd && unknown === ledger.retained_unknown_micro_usd
    && inflight === ledger.inflight_reserved_micro_usd && committed + unknown + inflight + ledger.available_micro_usd === ledger.max_micro_usd
    && (unknown === 0 || ledger.halted);
}
function validCombinedBudget(job) {
  const combined = job.combined_budget;
  if (combined === undefined) return true;
  if (combined?.version === 2) {
    const keys = ["version", "original_cap_micro_usd", "prior_committed_micro_usd", "prior_retained_unknown_micro_usd", "new_run_cap_micro_usd", "policy", "prior_runs"];
    if (!exactKeys(combined, keys) || combined.original_cap_micro_usd !== 10000000
      || !micro(combined.prior_committed_micro_usd) || !micro(combined.prior_retained_unknown_micro_usd)
      || !micro(combined.new_run_cap_micro_usd) || combined.new_run_cap_micro_usd <= 0
      || combined.new_run_cap_micro_usd !== job.provider_budget?.max_micro_usd
      || combined.policy !== "retain_all_prior_upper_and_unknown_no_refund"
      || !boundedArray(combined.prior_runs, 100) || combined.prior_runs.length === 0
      || combined.prior_committed_micro_usd + combined.prior_retained_unknown_micro_usd + combined.new_run_cap_micro_usd !== combined.original_cap_micro_usd) return false;
    let committed = 0, unknown = 0;
    for (const prior of combined.prior_runs) {
      if (!exactKeys(prior, ["run_id", "committed_upper_micro_usd", "retained_unknown_micro_usd", "inflight_reserved_micro_usd", "report_file_sha256", "checkpoint_sha256"])
        || !runId(prior.run_id) || prior.run_id === job.id || !micro(prior.committed_upper_micro_usd)
        || !micro(prior.retained_unknown_micro_usd) || prior.inflight_reserved_micro_usd !== 0
        || !hash(prior.report_file_sha256) || !hash(prior.checkpoint_sha256)) return false;
      committed += prior.committed_upper_micro_usd; unknown += prior.retained_unknown_micro_usd;
    }
    return unique(combined.prior_runs.map((prior) => prior.run_id)) && committed === combined.prior_committed_micro_usd
      && unknown === combined.prior_retained_unknown_micro_usd;
  }
  const keys = ["original_cap_micro_usd", "prior_run_id", "prior_retained_micro_usd", "new_run_cap_micro_usd", "policy", "prior_report_file_sha256", "prior_checkpoint_sha256"];
  return !!combined && typeof combined === "object" && !Array.isArray(combined)
    && Object.keys(combined).length === keys.length && keys.every((key) => Object.hasOwn(combined, key))
    && combined.original_cap_micro_usd === 10000000 && micro(combined.prior_retained_micro_usd) && combined.prior_retained_micro_usd > 0
    && micro(combined.new_run_cap_micro_usd) && combined.new_run_cap_micro_usd > 0
    && combined.prior_retained_micro_usd + combined.new_run_cap_micro_usd === combined.original_cap_micro_usd
    && combined.new_run_cap_micro_usd === job.provider_budget?.max_micro_usd
    && typeof combined.prior_run_id === "string" && /^[a-f0-9]{32}$/.test(combined.prior_run_id) && combined.prior_run_id !== job.id
    && combined.policy === "retain_prior_full_unknown_reservation_no_refund"
    && hash(combined.prior_report_file_sha256) && hash(combined.prior_checkpoint_sha256);
}
function exactKeys(value, keys) {
  return !!value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}
const runId = (value) => typeof value === "string" && /^[a-f0-9]{32}$/.test(value);
function validHarnessJob(job, { summary = false } = {}) {
  return job.mode === "real_corpus_quality" && id(job.id) && STATES.has(job.status) && !corpusActive(job)
    && sha(job.source_sha) && hash(job.source_files_sha256) && job.source_revision_scope === "local_dirty_application_source_not_deployed_revision"
    && job.model === "gpt-6.1-sol" && job.judge_model === job.model && job.reasoning_effort === "medium"
    && job.durability_policy === "single_dispatch_checkpoint_no_resume_unknown_allocation_retained"
    && Array.isArray(job.excluded_checks) && JSON.stringify(job.excluded_checks) === JSON.stringify(EXCLUDED)
    && validCorpusBank(job.bank) && job.split === "all" && strings(job.selected_case_ids) && job.selected_case_ids.length > 0
    && job.selected_case_ids.every(caseId) && unique(job.selected_case_ids) && job.total_cases === job.selected_case_ids.length
    && job.total_cases <= job.bank.case_count && count(job.completed_cases, job.total_cases)
    && timestamp(job.started_at) && timestamp(job.finished_at) && job.report_available === true && hash(job.report_sha256)
    && job.pricing === null && finite(job.max_usd) && job.max_usd > 0 && job.max_usd <= 10
    && validHarnessLedger(job.provider_budget) && job.provider_budget.max_micro_usd === Math.round(job.max_usd * 1000000)
    && validCombinedBudget(job)
    && (job.cost_observation === undefined || corpusCostObservation(job) !== null)
    && count(job.retrieval?.passed, job.completed_cases) && count(job.retrieval?.failed, job.completed_cases)
    && job.retrieval.passed + job.retrieval.failed === job.completed_cases
    && (job.error === null || text(job.error)) && typeof job.quality_passed === "boolean"
    && (job.status !== "completed" || (job.completed_cases === job.total_cases && verifiedAfter(job) && !job.provider_budget.halted
      && job.provider_budget.inflight_reserved_micro_usd === 0 && job.provider_budget.retained_unknown_micro_usd === 0))
    && ((job.semantic_status === "pending_review" && job.semantic_review === null && job.quality_passed === false) || !!corpusReview(job, { summary }))
    && ((summary && job.cases === undefined) || (boundedArray(job.cases) && job.cases.length === job.completed_cases
      && job.cases.every((row) => validCase(row, true)) && unique(job.cases.map((row) => row.case_id))
      && job.cases.every((row) => job.selected_case_ids.includes(row.case_id))
      && job.cases.filter((row) => row.retrieval.passed).length === job.retrieval.passed));
}
export function corpusLedger(job) {
  if (!corpusHarness(job) || !validHarnessLedger(job.provider_budget)) return null;
  const ledger = job.provider_budget;
  return { cap: ledger.max_micro_usd / 1000000, committed: ledger.committed_upper_micro_usd / 1000000,
    unknown: ledger.retained_unknown_micro_usd / 1000000, inflight: ledger.inflight_reserved_micro_usd / 1000000,
    available: ledger.available_micro_usd / 1000000, requests: ledger.requests.length, halted: ledger.halted, haltReason: ledger.halt_reason };
}
export function corpusCombinedBudget(job) {
  if (!corpusHarness(job) || !job.combined_budget || !validHarnessLedger(job.provider_budget) || !validCombinedBudget(job)) return null;
  const combined = job.combined_budget;
  if (combined.version === 2) return { version: 2, originalCap: combined.original_cap_micro_usd / 1000000,
    priorCommitted: combined.prior_committed_micro_usd / 1000000, priorUnknown: combined.prior_retained_unknown_micro_usd / 1000000,
    runCap: combined.new_run_cap_micro_usd / 1000000, remaining: job.provider_budget.available_micro_usd / 1000000,
    totalAllocation: (combined.prior_committed_micro_usd + combined.prior_retained_unknown_micro_usd
      + job.provider_budget.committed_upper_micro_usd + job.provider_budget.retained_unknown_micro_usd + job.provider_budget.inflight_reserved_micro_usd) / 1000000,
    totalAllocationAll: (combined.prior_committed_micro_usd + combined.prior_retained_unknown_micro_usd
      + job.provider_budget.committed_upper_micro_usd + job.provider_budget.retained_unknown_micro_usd + job.provider_budget.inflight_reserved_micro_usd) / 1000000,
    totalAllocationAll: (combined.prior_committed_micro_usd + combined.prior_retained_unknown_micro_usd
      + job.provider_budget.committed_upper_micro_usd + job.provider_budget.retained_unknown_micro_usd + job.provider_budget.inflight_reserved_micro_usd) / 1000000,
    priorRuns: combined.prior_runs.map((prior) => ({ runId: prior.run_id, reportHash: prior.report_file_sha256,
      checkpointHash: prior.checkpoint_sha256, committed: prior.committed_upper_micro_usd / 1000000, unknown: prior.retained_unknown_micro_usd / 1000000 })) };
  return { originalCap: combined.original_cap_micro_usd / 1000000, priorRetained: combined.prior_retained_micro_usd / 1000000,
    runCap: combined.new_run_cap_micro_usd / 1000000, remaining: job.provider_budget.available_micro_usd / 1000000,
    totalAllocation: (job.provider_budget.committed_upper_micro_usd + job.provider_budget.retained_unknown_micro_usd
      + job.provider_budget.inflight_reserved_micro_usd + combined.prior_retained_micro_usd) / 1000000,
    priorRunId: combined.prior_run_id, priorReport: combined.prior_report_file_sha256, priorCheckpoint: combined.prior_checkpoint_sha256 };
}
export function corpusCostObservation(job) {
  const observation = job?.cost_observation, ledger = job?.provider_budget, combined = job?.combined_budget;
  if (!corpusHarness(job) || !observation || typeof observation !== "object" || Array.isArray(observation)
    || !validHarnessLedger(ledger) || !combined || !validCombinedBudget(job)
    || ledger.retained_unknown_micro_usd !== 0 || ledger.inflight_reserved_micro_usd !== 0
    || !hash(observation.report_sha256) || observation.report_sha256 !== job.report_sha256
    || !exactKeys(observation.rates, Object.keys(STANDARD_RATES))
    || Object.entries(STANDARD_RATES).some(([key, rate]) => observation.rates[key] !== rate)) return null;
  let priorNano = 0n, priorObservations;
  if (observation.version === 2) {
    if (combined.version !== 2 || !exactKeys(observation, ["version", "report_sha256", "rates", "prior_observations"])
      || !boundedArray(observation.prior_observations, 100) || observation.prior_observations.length !== combined.prior_runs.length
      || !unique(observation.prior_observations.map((prior) => prior?.run_id))) return null;
    priorObservations = [];
    for (const prior of observation.prior_observations) {
      if (!exactKeys(prior, ["run_id", "kind", "amount_nano_usd", "report_file_sha256", "evidence_file_sha256"])
        || !runId(prior.run_id) || !["gateway_estimate", "standard_rate_token_estimate"].includes(prior.kind)
        || !Number.isSafeInteger(prior.amount_nano_usd) || prior.amount_nano_usd < 0 || !hash(prior.evidence_file_sha256)) return null;
      const bound = combined.prior_runs.find((run) => run.run_id === prior.run_id);
      if (!bound || prior.report_file_sha256 !== bound.report_file_sha256
        || BigInt(prior.amount_nano_usd) > BigInt(bound.committed_upper_micro_usd + bound.retained_unknown_micro_usd) * 1000n) return null;
      priorNano += BigInt(prior.amount_nano_usd);
      priorObservations.push({ runId: prior.run_id, kind: prior.kind, amount: prior.amount_nano_usd / 1000000000,
        amountNanoUsd: prior.amount_nano_usd, reportHash: prior.report_file_sha256, evidenceHash: prior.evidence_file_sha256 });
    }
  } else {
    if (combined.version !== undefined || !exactKeys(observation, ["report_sha256", "prior_run_id", "prior_gateway_micro_usd", "prior_diagnosis_sha256", "rates"])
      || observation.prior_run_id !== combined.prior_run_id || !hash(observation.prior_diagnosis_sha256)
      || !micro(observation.prior_gateway_micro_usd) || observation.prior_gateway_micro_usd > combined.prior_retained_micro_usd) return null;
    priorNano = BigInt(observation.prior_gateway_micro_usd) * 1000n;
  }
  let currentNano = 0n;
  for (const request of ledger.requests) {
    if (request.outcome !== "settled") return null;
    const usage = request.usage;
    if (request.kind === "embedding") {
      if (usage.output_tokens !== 0) return null;
      currentNano += BigInt(usage.input_tokens) * 20n;
    } else {
      const details = usage.input_tokens_details;
      if (!details || typeof details !== "object" || Array.isArray(details)
        || !Number.isSafeInteger(details.cached_tokens) || details.cached_tokens < 0
        || !Number.isSafeInteger(details.cache_write_tokens) || details.cache_write_tokens < 0
        || details.cached_tokens > usage.input_tokens || details.cache_write_tokens > usage.input_tokens - details.cached_tokens
        || (Object.hasOwn(details, "audio_tokens") && details.audio_tokens !== 0)
        || Object.keys(details).some((key) => !["cached_tokens", "cache_write_tokens", "audio_tokens"].includes(key))) return null;
      currentNano += BigInt(usage.input_tokens - details.cached_tokens - details.cache_write_tokens) * 2000n
        + BigInt(details.cache_write_tokens) * 2500n + BigInt(details.cached_tokens) * 100n + BigInt(usage.output_tokens) * 10000n;
    }
  }
  if (currentNano > BigInt(ledger.committed_upper_micro_usd) * 1000n) return null;
  return { version: observation.version || 1, current: Number(currentNano) / 1000000000, prior: Number(priorNano) / 1000000000,
    total: Number(currentNano + priorNano) / 1000000000, currentNanoUsd: Number(currentNano), totalNanoUsd: Number(currentNano + priorNano),
    reportHash: observation.report_sha256, diagnosisHash: observation.prior_diagnosis_sha256, priorObservations };
}
export function corpusAnswerEvidence(row, answer) {
  if (corpusHarness(row)) return { raw_model_answer: answer.raw_model_answer, items: answer.items, citations: answer.citations,
    context_snapshot: answer.context_snapshot, tool_events: (row.tool_trace || []).filter((event) => event.turn === answer.turn),
    usage: answer.usage, judge_usage: answer.judge_usage, guard: answer.guard, status: answer.status, error: answer.error };
  return { items: answer.items, citations: answer.citations, sources: answer.sources, tool_events: answer.tool_trace,
    usage: answer.usage, witness: answer.witness, guard: answer.guard };
}
function validPricing(pricing) {
  return !!pricing && [pricing.model, pricing.judge_model, pricing.embedding_model].every((name) => text(name, 256))
    && [pricing.main, pricing.judge].every((entry) => finite(entry?.input_per_million) && finite(entry?.output_per_million))
    && finite(pricing.embedding?.input_per_million) && finite(pricing.reserved_estimated_usd) && finite(pricing.per_case_reserved_estimated_usd);
}
export function validCorpusCapabilities(value) {
  return !!value && typeof value.available === "boolean" && (value.reason === null || text(value.reason)) && (value.source_sha === null || sha(value.source_sha))
    && (value.bank === null || validCorpusBank(value.bank)) && (value.pricing === null || validPricing(value.pricing))
    && (!value.available || (value.bank !== null && validPricing(value.pricing) && value.pricing.per_case_reserved_estimated_usd <= value.limits?.max_budget_usd))
    && finite(value.limits?.max_budget_usd) && value.limits.max_budget_usd <= 50 && value.limits.max_budget_usd >= 0.01 && finite(value.limits.deadline_seconds)
    && typeof value.busy === "boolean" && (value.active_job_id === null || id(value.active_job_id)) && typeof value.turnstile_required === "boolean"
    && boundedArray(value.recent, 5) && value.recent.every((job) => validCorpusJob(job, { summary: true }));
}
export function corpusResult(job) {
  const result = (status, reason) => ({ status, reason, counts: null });
  if (!job) return result("NOT RUN", "not_run");
  if (corpusActive(job)) return result("RUNNING", "running");
  if (job.status === "stale") return result("STALE", "corpus_drift");
  if (!validCorpusJob(job, { summary: true })) return result("UNKNOWN", "unmeasured");
  const review = corpusReview(job);
  if (corpusHarness(job) && (job.status !== "completed" || job.provider_budget.halted
    || job.provider_budget.retained_unknown_micro_usd > 0 || job.provider_budget.inflight_reserved_micro_usd > 0
    || review?.not_assessable > 0)) return result("INCOMPLETE", "incomplete");
  if (["failed", "timed_out"].includes(job.status) || job.retrieval.failed || review?.failed) return result("FAIL", "failed_checks");
  if (job.status !== "completed" || job.completed_cases !== job.total_cases || !review) return result("INCOMPLETE", "incomplete");
  return job.quality_passed ? result("PASS", "passed") : result("INCOMPLETE", "incomplete");
}
