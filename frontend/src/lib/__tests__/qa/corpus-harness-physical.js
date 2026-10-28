// Detached, synthetic application-harness observations. No provider/ES calls.
// Contract: qa/real_corpus_live_driver.py immutable rows and provider ledger,
// projected by a local read-only artifact bridge rather than a deployed API.
import { corpusCapabilities, corpusJob } from "./corpus-evaluation-physical.js";
const ENGINE = "application_harness_real_es";
export function harnessJob({ reviewed = false, failed = false, unknown = false, incomplete = false, noAnswer = false, actualCitations = false } = {}) {
  const job = corpusJob({ reviewed, failed: failed || unknown, status: unknown || incomplete ? "incomplete" : "completed" });
  Object.assign(job, { id: "offline-harness-fixture", engine: ENGINE, model: "gpt-6.1-sol", judge_model: "gpt-6.1-sol", reasoning_effort: "medium",
    source_files_sha256: "1".repeat(64), source_revision_scope: "local_dirty_application_source_not_deployed_revision", pricing: null, max_usd: 10,
    durability_policy: "single_dispatch_checkpoint_no_resume_unknown_allocation_retained",
    excluded_checks: ["firebase_identity", "turnstile", "http_api_owner_controls", "http_sse_delivery", "chat_persistence", "usage_log_persistence", "production_deployment"],
    index_observation: { scope: "dynamic_index_fixed_question_bank", verified_before_run: true, verified_after_run: true, verified_documents: 2 },
    error: unknown ? "provider_outcome_unknown" : incomplete ? "corpus_budget_exhausted" : null });
  job.bank.id = "offline-harness-contract-fixture";
  job.bank.provenance.embed_model = "text-embedding-3-small";
  for (const row of job.cases) {
    Object.assign(row, { engine: ENGINE, status: "completed" });
    row.tool_trace = [1, 2].map((turn) => ({ turn, name: "search_news", status: "completed", call_id: row.case_id + "-call-" + turn,
      arguments: { query: row.questions[turn - 1] }, result: JSON.stringify({ type: "untrusted_data", schema_version: 1, kind: "search_results", payload: { results: row.retrieval.found.map((article_id) => ({ article_id })) } }) }));
    row.retrieval.calls.push({ ...structuredClone(row.retrieval.calls[0]), turn: 2, call_id: row.case_id + "-call-2", arguments: { query: row.questions[1] } });
    for (const answer of row.answers) {
      delete answer.tool_trace; delete answer.raw_sse; delete answer.witness;
      Object.assign(answer, { status: "completed", raw_model_answer: "Synthetic raw answer", judge_usage: { input_tokens: 10, output_tokens: 2 },
        context_snapshot: { items: structuredClone(answer.items), refs: { ["article-" + answer.turn]: answer.turn }, full_texts: { synthetic: "Synthetic truncated model-visible article text" } } });
      if (actualCitations) answer.citations = [{ id: 7, title: "Synthetic actual cited source", url: "https://actual-source.example.test/news" },
        { id: 8, title: "Synthetic unsafe citation URL", url: "javascript:alert(1)" }];
    }
  }
  const requests = Array.from({ length: 6 }, (_, index) => {
    const kind = ["main", "judge", "embedding"][index % 3], embedding = kind === "embedding";
    return { request_index: index + 1, kind, model: embedding ? "text-embedding-3-small" : "gpt-6.1-sol", outcome: "settled", reservation_micro_usd: 1000,
      cost_upper_micro_usd: embedding ? 1 : 66, usage: { input_tokens: 10, output_tokens: embedding ? 0 : 2, total_tokens: embedding ? 10 : 12 } };
  });
  if (unknown) { requests[5] = { ...requests[5], outcome: "unknown", cost_upper_micro_usd: null, usage: null }; job.cases[1].status = "failed"; job.cases[1].answers[1].status = "failed"; }
  const committed = requests.filter((row) => row.outcome === "settled").reduce((sum, row) => sum + row.cost_upper_micro_usd, 0);
  job.provider_budget = { halted: unknown || incomplete, halt_reason: unknown ? "provider_outcome_unknown" : incomplete ? "budget_exhausted" : null,
    max_micro_usd: 10000000, committed_upper_micro_usd: committed, retained_unknown_micro_usd: unknown ? 1000 : 0, inflight_reserved_micro_usd: 0,
    available_micro_usd: 10000000 - committed - (unknown ? 1000 : 0), requests };
  if (incomplete || unknown) {
    job.bank.case_count = 3; job.bank.coverage.splits = { dev: 2, holdout: 1 }; job.bank.coverage.categories = { 科技: 3 }; job.bank.coverage.task_types = { factual: 3 };
    job.total_cases = 3; job.selected_case_ids.push("real-003"); job.quality_passed = false;
  }
  if (reviewed) { job.semantic_review.status = "completed"; job.semantic_review.not_assessable = 0; job.semantic_review.cases.forEach((row) => { row.assessment_status = "assessed"; }); }
  if (noAnswer) {
    const row = job.cases[0], answer = row.answers[0];
    Object.assign(row, { status: "failed", tool_trace: [], error: "live_driver_failure" });
    row.retrieval = { ...row.retrieval, found: [], recall: 0, mrr: 0, passed: false, calls: [] };
    row.final_source_coverage = { expected: ["article-1"], found: [], recall: 0 };
    Object.assign(answer, { status: "failed", answer_md: "", raw_model_answer: "", items: [], citations: [], usage: {}, guard: {}, context_snapshot: { items: [], full_texts: {}, refs: {} } });
    row.answers = [answer]; job.cases = [row];
    Object.assign(job, { status: "incomplete", error: "provider_outcome_unknown", total_cases: 24, completed_cases: 1,
      retrieval: { passed: 0, failed: 1 }, quality_passed: false,
      selected_case_ids: Array.from({ length: 24 }, (_, index) => "real-" + String(index + 1).padStart(3, "0")) });
    Object.assign(job.bank, { case_count: 24, document_count: 12 });
    job.bank.coverage = { ...job.bank.coverage, splits: { dev: 12, holdout: 12 }, categories: { 科技: 24 }, task_types: { factual: 24 }, sources: { "Example fixture": 12 } };
    job.index_observation.verified_documents = 12;
    job.provider_budget = { halted: true, halt_reason: "provider_outcome_unknown", max_micro_usd: 10000000, committed_upper_micro_usd: 0,
      retained_unknown_micro_usd: 226759, inflight_reserved_micro_usd: 0, available_micro_usd: 9773241,
      requests: [{ request_index: 1, kind: "main", model: "gpt-6.1-sol", outcome: "unknown", reservation_micro_usd: 226759, cost_upper_micro_usd: null, usage: null }] };
    if (reviewed) Object.assign(job.semantic_review, { reviewed_cases: 1, passed: 0, failed: 0, not_assessable: 1,
      cases: [{ case_id: row.case_id, row_sha: row.row_sha, assessment_status: "not_assessable", scores: null, reason: "沒有可評判回答；僅完成執行紀錄檢視，模型品質尚未判定。" }] });
  }
  return structuredClone(job);
}
export function harnessCapabilities(options = {}) {
  const job = options.cumulative ? accumulatedHarnessJob(options) : options.costObservation ? observedCostHarnessJob(options) : options.combined ? combinedHarnessJob(options) : harnessJob(options), capabilities = corpusCapabilities({ available: false, job });
  capabilities.bank = structuredClone(job.bank); capabilities.reason = "local_read_only";
  capabilities.limits.max_budget_usd = 10;
  return capabilities;
}
export function combinedHarnessJob(options = {}) {
  const job = harnessJob(options);
  job.max_usd = 9.773241;
  job.provider_budget.max_micro_usd = 9773241;
  job.provider_budget.available_micro_usd -= 226759;
  job.combined_budget = { original_cap_micro_usd: 10000000, prior_run_id: "7".repeat(32), prior_retained_micro_usd: 226759,
    new_run_cap_micro_usd: 9773241, policy: "retain_prior_full_unknown_reservation_no_refund",
    prior_report_file_sha256: "2".repeat(64), prior_checkpoint_sha256: "3".repeat(64) };
  return job;
}
export function observedCostHarnessJob(options = {}) {
  const job = combinedHarnessJob(options);
  for (const request of job.provider_budget.requests) if (request.kind !== "embedding" && request.outcome === "settled") {
    request.usage.input_tokens_details = { cached_tokens: 4, cache_write_tokens: 3 };
  }
  job.cost_observation = { report_sha256: job.report_sha256, prior_run_id: job.combined_budget.prior_run_id,
    prior_gateway_micro_usd: 8056, prior_diagnosis_sha256: "4".repeat(64),
    rates: { input: 2, cache_write: 2.5, cached_input: 0.1, output: 10, embedding: 0.02 } };
  return job;
}
// Contract: the local launcher retains both prior ledger upper bounds and binds
// each typed estimate to its original report/evidence; these remain offline rows.
export function accumulatedHarnessJob(options = {}) {
  const job = observedCostHarnessJob(options);
  job.max_usd = 5.820561;
  job.provider_budget.max_micro_usd = 5820561;
  job.provider_budget.available_micro_usd -= 3952680;
  job.combined_budget = { version: 2, original_cap_micro_usd: 10000000, prior_committed_micro_usd: 3952680,
    prior_retained_unknown_micro_usd: 226759, new_run_cap_micro_usd: 5820561, policy: "retain_all_prior_upper_and_unknown_no_refund",
    prior_runs: [
      { run_id: "7".repeat(32), committed_upper_micro_usd: 0, retained_unknown_micro_usd: 226759, inflight_reserved_micro_usd: 0,
        report_file_sha256: "2".repeat(64), checkpoint_sha256: "3".repeat(64) },
      { run_id: "8".repeat(32), committed_upper_micro_usd: 3952680, retained_unknown_micro_usd: 0, inflight_reserved_micro_usd: 0,
        report_file_sha256: "4".repeat(64), checkpoint_sha256: "5".repeat(64) },
    ] };
  if (options.costObservation) job.cost_observation = { version: 2, report_sha256: job.report_sha256,
    rates: { input: 2, cache_write: 2.5, cached_input: 0.1, output: 10, embedding: 0.02 }, prior_observations: [
      { run_id: "7".repeat(32), kind: "gateway_estimate", amount_nano_usd: 8056000, report_file_sha256: "2".repeat(64), evidence_file_sha256: "6".repeat(64) },
      { run_id: "8".repeat(32), kind: "standard_rate_token_estimate", amount_nano_usd: 1048454240, report_file_sha256: "4".repeat(64), evidence_file_sha256: "9".repeat(64) },
    ] };
  else delete job.cost_observation;
  return job;
}
export async function readHarnessArtifact(directory) {
  const { readFile } = await import("node:fs/promises");
  const { join } = await import("node:path");
  return { job: JSON.parse(await readFile(join(directory, "ui-job.json"), "utf8")),
    capabilities: JSON.parse(await readFile(join(directory, "ui-capabilities.json"), "utf8")) };
}
export async function readHarnessRun(directory) {
  const { readFile } = await import("node:fs/promises");
  const { join } = await import("node:path");
  return { report: JSON.parse(await readFile(join(directory, "report.json"), "utf8")),
    combinedBudget: JSON.parse(await readFile(join(directory, "combined-budget.json"), "utf8")) };
}
