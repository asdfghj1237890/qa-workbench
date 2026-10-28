// Contract: qa_corpus_evaluations.py public bank/capabilities/job/review schemas.
// Deliberately synthetic offline fixture; this is never real corpus quality evidence.
const clone = (value) => structuredClone(value);
const HASH = "c".repeat(64), ROW = "d".repeat(64), SOURCE = "a".repeat(40);
export function corpusBank() {
  return { id: "offline-contract-fixture", version: "fixture-v1", sha256: HASH, source_sha256: "e".repeat(64), created_at: "2026-10-23T01:00:00Z", case_count: 2, document_count: 2,
    coverage: { splits: { dev: 1, holdout: 1 }, categories: { 科技: 2 }, task_types: { factual: 2 }, sources: { "Example fixture": 2 }, date_window: { start: "2026-10-20", end: "2026-10-21" } },
    provenance: { kind: "elasticsearch", alias: "news_read", captured_at: "2026-10-23T01:00:00Z", indices: [{ name: "offline-news", uuid: "fixture-uuid" }], mapping_sha256: "f".repeat(64), embed_model: "fixture-embedding", embed_dim: 3 } };
}
export function corpusJob({ status = "completed", reviewed = false, failed = false } = {}) {
  const cases = [1, 2].map((n) => ({ case_id: "real-00" + n, split: n === 1 ? "dev" : "holdout", category: "科技", task_type: "factual", questions: ["離線題庫問題 " + n, "離線追問 " + n], expected_facts: [{ article_id: "article-" + n, quote: "離線來源支持事實", claim: "預期事實" }], expected_sources: [{ article_id: "article-" + n, title: "離線新聞", source: { site: "Example fixture", url: "https://example.test/article-" + n }, posted_at: "2026-10-20", content_sha256: "e".repeat(64) }], answers: [{ turn: 1, question: "離線題庫問題 " + n, answer_md: "離線回答 " + n, items: [], citations: [], sources: [], tool_trace: [], raw_sse: "", usage: {}, witness: {}, guard: {} }], retrieval: { expected: ["article-" + n], found: failed && n === 2 ? [] : ["article-" + n], recall: failed && n === 2 ? 0 : 1, mrr: failed && n === 2 ? 0 : 1, passed: !(failed && n === 2), metric_scope: "observed_final_items" }, row_sha: n === 1 ? ROW : "b".repeat(64), error: null }));
  const terminal = !["queued", "running"].includes(status);
  for (const row of cases) {
    row.answers[0].items = row.retrieval.found.map((article_id) => ({ article_id }));
    row.answers.push({ ...clone(row.answers[0]), turn: 2, question: row.questions[1] }); row.tool_trace = [{ turn: 1, name: "search_news", status: "completed", arguments: { query: row.questions[0] }, output: { results: row.retrieval.found.map((article_id) => ({ article_id })) } }]; row.tool_trace_truncated = false;
    row.final_source_coverage = { expected: clone(row.retrieval.expected), found: clone(row.retrieval.found), recall: row.retrieval.recall };
    row.retrieval.metric_scope = "actual_tool_rankings"; row.retrieval.aggregation = "union_recall_mean_call_rr";
    row.retrieval.calls = [{ turn: 1, tool: "search_news", call_id: row.case_id + "-call-1", arguments: { query: row.questions[0] }, article_ids: clone(row.retrieval.found), returned_k: row.retrieval.found.length, recall: row.retrieval.recall, reciprocal_rank: row.retrieval.mrr }];
  }
  const job = { id: "offline-corpus-job", mode: "real_corpus_quality", split: "all", status, source_sha: SOURCE, bank: corpusBank(), model: "offline-model", started_at: "2026-10-23T01:01:00Z", finished_at: terminal ? "2026-10-23T01:02:00Z" : null,
    completed_cases: terminal ? cases.length : 0, total_cases: 2, cases: terminal ? cases : [], retrieval: { passed: terminal ? failed ? 1 : 2 : 0, failed: terminal && failed ? 1 : 0 }, semantic_status: "pending_review", semantic_review: null, report_available: terminal, report_sha256: terminal ? HASH : null, quality_passed: false, error: null, usage: { requests: 2, measured_estimated_usd: 0.01 } };
  if (reviewed) { job.semantic_status = "reviewed"; job.semantic_review = { reviewer_kind: "ai", reviewer: "Offline fixture reviewer", reviewed_at: "2026-10-23T02:00:00+08:00", report_sha256: HASH, reviewed_cases: cases.length, passed: failed ? 1 : 2, failed: failed ? 1 : 0, cases: cases.map((row, i) => ({ case_id: row.case_id, row_sha: row.row_sha, scores: { intent: true, grounding: !failed || i === 0, completeness: true, language: true }, reason: failed && i === 1 ? "回答引用無法支持該事實。" : "回答與來源相符。" })) }; job.quality_passed = !failed && status === "completed"; }
  job.selected_case_ids = cases.map((row) => row.case_id);
  job.index_observation = { verified_after_run: { ...clone(job.bank.provenance), verified_documents: job.bank.document_count } };
  job.pricing = { model: "offline-model", judge_model: "offline-judge", embedding_model: "offline-embedding", main: { input_per_million: 1, output_per_million: 2 }, judge: { input_per_million: 1, output_per_million: 2 }, embedding: { input_per_million: 1 }, reserved_estimated_usd: 0.4, per_case_reserved_estimated_usd: 0.2 };
  return clone(job);
}
export function corpusCapabilities({ available = true, job = null, missing = false } = {}) {
  return clone({ available, reason: available ? null : missing ? "bank_missing" : "pricing_required", source_sha: SOURCE, bank: missing ? null : corpusBank(), pricing: available ? { model: "offline-model", judge_model: "offline-judge", embedding_model: "offline-embedding", main: { input_per_million: 1, output_per_million: 2 }, judge: { input_per_million: 1, output_per_million: 2 }, embedding: { input_per_million: 1 }, reserved_estimated_usd: 0.4, per_case_reserved_estimated_usd: 0.2 } : null, busy: ["queued", "running"].includes(job?.status), active_job_id: ["queued", "running"].includes(job?.status) ? job.id : null, recent: job ? [job] : [], limits: { max_budget_usd: 50, deadline_seconds: 1800 }, turnstile_required: false });
}
export function observeCorpus(change = () => {}, options = {}) { const job = corpusJob(options); change(job); return job; }
