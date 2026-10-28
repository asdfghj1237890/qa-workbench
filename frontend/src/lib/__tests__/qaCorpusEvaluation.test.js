import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import { corpusCapabilities, corpusJob, observeCorpus } from "./qa/corpus-evaluation-physical.js";
import { corpusReview, corpusCaseReview, corpusResult, validCorpusCapabilities, validCorpusJob } from "../qaCorpusEvaluation.js";

describe("independent real corpus quality evidence", () => {
  it("accepts an unavailable missing bank without fabricating executed quality", () => {
    expect(validCorpusCapabilities(corpusCapabilities({ available: false, missing: true }))).toBe(true);
    expect(corpusResult(null)).toEqual({ status: "NOT RUN", reason: "not_run", counts: null });
  });
  it("keeps completed retrieval distinct from pending semantic quality", () => {
    const job = corpusJob();
    expect(validCorpusJob(job)).toBe(true); expect(corpusReview(job)).toBeNull();
    expect(corpusResult(job).status).toBe("INCOMPLETE"); expect(corpusResult(job).counts).toBeNull();
  });
  it("validates exact report and case binding before reporting an AI review", () => {
    const job = corpusJob({ reviewed: true, failed: true });
    expect(validCorpusJob(job)).toBe(true); expect(corpusReview(job)).toMatchObject({ passed: 1, failed: 1 });
    expect(corpusCaseReview(job, job.cases[1]).reason).toContain("無法支持"); expect(corpusResult(job).status).toBe("FAIL");
  });
  it("rejects changed hashes, partial or duplicate reviews, and invented passing totals", () => {
    for (const change of [
      (job) => { job.semantic_review.report_sha256 = "0".repeat(64); },
      (job) => { job.semantic_review.cases[0].row_sha = "0".repeat(64); },
      (job) => { job.semantic_review.cases.pop(); },
      (job) => { job.semantic_review.cases[1] = job.semantic_review.cases[0]; },
      (job) => { job.semantic_review.passed = 2; job.semantic_review.failed = 0; },
      (job) => { job.quality_passed = true; },
    ]) expect(validCorpusJob(observeCorpus(change, { reviewed: true, failed: true }))).toBe(false);
  });
  it("does not let missing executions become a complete quality pass", () => {
    const job = observeCorpus((value) => { value.total_cases = 3; value.bank.case_count = 3; }, { reviewed: true });
    expect(validCorpusJob(job)).toBe(false);
  });
  it("allows a clearly selected subset without claiming that the entire bank ran", () => {
    const job = observeCorpus((value) => { value.bank.case_count = 4; value.bank.coverage.splits = { dev: 2, holdout: 2 }; }, { reviewed: true });
    expect(validCorpusJob(job)).toBe(true); expect(job.total_cases).toBe(2); expect(job.bank.case_count).toBe(4);
  });
  it("requires source verification and complete model-visible tool evidence for a quality pass", () => {
    for (const change of [(job) => { job.index_observation = {}; }, (job) => { job.cases[0].tool_trace_truncated = true; }, (job) => { job.cases[0].tool_trace = []; }]) {
      expect(validCorpusJob(observeCorpus(change, { reviewed: true }))).toBe(false);
    }
  });
  it("checks actual retrieval call ranks separately from final answer source coverage", () => {
    const job = observeCorpus((value) => { const row = value.cases[0]; row.retrieval.calls[0].article_ids.unshift("unrelated"); row.retrieval.calls[0].returned_k = 2; row.retrieval.calls[0].reciprocal_rank = 0.5; row.retrieval.found.unshift("unrelated"); row.retrieval.mrr = 0.5; });
    expect(validCorpusJob(job)).toBe(true); expect(job.cases[0].final_source_coverage.found).toEqual(["article-1"]);
    job.cases[0].retrieval.mrr = 1;
    expect(validCorpusJob(job)).toBe(false);
  });
  it("preserves drift as stale evidence and never includes retrieval scores in measured test counts", () => {
    const job = corpusJob({ status: "stale" });
    expect(validCorpusJob(job)).toBe(true); expect(corpusResult(job)).toMatchObject({ status: "STALE", counts: null });
  });
});
