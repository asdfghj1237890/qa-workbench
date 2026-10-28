import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import { corpusAnswerEvidence, corpusCombinedBudget, corpusCostObservation, corpusHarness, corpusLedger, corpusResult, corpusReview, validCorpusCapabilities, validCorpusJob } from "../qaCorpusEvaluation.js";
import { accumulatedHarnessJob, combinedHarnessJob, harnessCapabilities, harnessJob, observedCostHarnessJob, readHarnessArtifact, readHarnessRun } from "./qa/corpus-harness-physical.js";
import { corpusJob } from "./qa/corpus-evaluation-physical.js";

describe("offline standalone application-harness report projection", () => {
  it("accepts immutable direct-harness rows without manufacturing native API or persistence evidence", () => {
    const job = harnessJob();
    expect(corpusHarness(job)).toBe(true); expect(validCorpusJob(job)).toBe(true);
    expect(validCorpusCapabilities(harnessCapabilities())).toBe(true);
    expect(job.pricing).toBeNull(); expect(job.cases[0].answers[0].tool_trace).toBeUndefined();
    expect(corpusReview(job)).toBeNull(); expect(corpusResult(job).status).toBe("INCOMPLETE");
  });
  it("derives this turn's actual tool events without changing raw rows or their hashes", () => {
    const row = harnessJob().cases[0], original = structuredClone(row);
    const evidence = corpusAnswerEvidence(row, row.answers[1]);
    expect(evidence.tool_events.map((event) => event.turn)).toEqual([2]);
    expect(evidence.raw_model_answer).toBe("Synthetic raw answer");
    expect(evidence.witness).toBeUndefined(); expect(evidence.raw_sse).toBeUndefined();
    expect(row).toEqual(original);
  });
  it("shows an AI review only with the exact original report and row bindings", () => {
    const job = harnessJob({ reviewed: true, failed: true });
    expect(validCorpusJob(job)).toBe(true); expect(corpusReview(job)).toMatchObject({ reviewer_kind: "ai", passed: 1, failed: 1 });
    expect(corpusResult(job).status).toBe("FAIL");
    job.semantic_review.cases[0].row_sha = "0".repeat(64); expect(validCorpusJob(job)).toBe(false);
  });
  it("allows a fully observed reviewed harness quality result without implying excluded checks passed", () => {
    const job = harnessJob({ reviewed: true });
    expect(validCorpusJob(job)).toBe(true); expect(corpusResult(job).status).toBe("PASS");
    expect(job.excluded_checks).toContain("firebase_identity"); expect(job.excluded_checks).toContain("chat_persistence");
  });
  it("validates the conservative aggregate ledger instead of inventing per-case reservations", () => {
    const job = harnessJob();
    expect(corpusLedger(job)).toMatchObject({ cap: 10, committed: 0.000266, unknown: 0, inflight: 0, requests: 6 });
    for (const change of [
      (value) => { value.provider_budget.available_micro_usd++; },
      (value) => { value.provider_budget.requests[0].usage.total_tokens++; },
      (value) => { value.provider_budget.requests[0].cost_upper_micro_usd++; },
      (value) => { value.provider_budget.requests[0].model = "unapproved"; },
      (value) => { value.provider_budget.requests[0].request_index = 2; },
      (value) => { value.max_usd = 11; },
    ]) { const invalid = harnessJob(); change(invalid); expect(validCorpusJob(invalid)).toBe(false); }
  });
  it("retains unknown allocations and all unexecuted cases without a quality pass", () => {
    const job = harnessJob({ unknown: true, reviewed: true });
    expect(validCorpusJob(job)).toBe(true); expect(job.total_cases - job.completed_cases).toBe(1);
    expect(corpusLedger(job)).toMatchObject({ committed: 0.000265, unknown: 0.001, halted: true });
    expect(corpusReview(job)).not.toBeNull(); expect(corpusResult(job).status).toBe("INCOMPLETE");
    job.quality_passed = true; expect(validCorpusJob(job)).toBe(false);
  });
  it("rejects false source verification, incomplete exclusions and a hidden ledger halt", () => {
    for (const change of [
      (job) => { job.index_observation.verified_after_run = false; },
      (job) => { job.excluded_checks.pop(); },
      (job) => { job.provider_budget.halted = true; job.provider_budget.halt_reason = "run_halted"; },
      (job) => { job.source_files_sha256 = "missing"; },
    ]) { const invalid = harnessJob({ reviewed: true }); change(invalid); expect(validCorpusJob(invalid)).toBe(false); }
  });
  it("keeps native report validation strict", () => {
    const job = corpusJob(); delete job.cases[0].answers[0].tool_trace;
    expect(validCorpusJob(job)).toBe(false);
    const ordinary = corpusJob(); ordinary.engine = "unrecognized_engine"; expect(validCorpusJob(ordinary)).toBe(false);
  });
  it("marks an unobserved answer as not assessable without fabricating four failed semantic scores", () => {
    const job = harnessJob({ reviewed: true, noAnswer: true });
    expect(validCorpusJob(job)).toBe(true); expect(corpusReview(job)).toMatchObject({ reviewed_cases: 1, passed: 0, failed: 0, not_assessable: 1 });
    expect(corpusReview(job).cases[0].scores).toBeNull();
    expect(corpusLedger(job)).toMatchObject({ committed: 0, unknown: 0.226759, requests: 1 });
    expect(corpusResult(job).status).toBe("INCOMPLETE");
    job.semantic_review.cases[0].assessment_status = "assessed";
    job.semantic_review.cases[0].scores = { intent: false, grounding: false, completeness: false, language: false };
    job.semantic_review.not_assessable = 0; job.semantic_review.failed = 1;
    expect(validCorpusJob(job)).toBe(false);
  });
  it("keeps the prior unknown reservation inside the original ten-dollar authorization without changing immutable rows", () => {
    const original = harnessJob(), job = combinedHarnessJob();
    expect(validCorpusJob(job)).toBe(true); expect(validCorpusCapabilities(harnessCapabilities({ combined: true }))).toBe(true);
    expect(corpusCombinedBudget(job)).toMatchObject({ originalCap: 10, priorRetained: 0.226759, runCap: 9.773241, remaining: 9.772975, totalAllocation: 0.227025 });
    expect(corpusLedger(job)).toMatchObject({ cap: 9.773241, committed: 0.000266 });
    expect(job.cases).toEqual(original.cases); expect(job.report_sha256).toBe(original.report_sha256);
    expect(corpusCombinedBudget(original)).toBeNull(); expect(corpusCombinedBudget(corpusJob())).toBeNull();
  });
  it("rejects unbound or inconsistent combined-budget context", () => {
    for (const change of [
      (job) => { job.combined_budget.prior_retained_micro_usd = 0; },
      (job) => { job.combined_budget.prior_retained_micro_usd++; },
      (job) => { job.combined_budget.new_run_cap_micro_usd++; },
      (job) => { job.combined_budget.original_cap_micro_usd = 20000000; },
      (job) => { job.combined_budget.new_run_cap_micro_usd = 9773241.5; },
      (job) => { job.combined_budget.prior_run_id = job.id; },
      (job) => { job.combined_budget.prior_report_file_sha256 = "missing"; },
      (job) => { delete job.combined_budget.prior_checkpoint_sha256; },
      (job) => { job.combined_budget.refund = true; },
      (job) => { job.combined_budget.policy = "refund_prior"; },
    ]) { const invalid = combinedHarnessJob(); change(invalid); expect(validCorpusJob(invalid)).toBe(false); expect(corpusCombinedBudget(invalid)).toBeNull(); }
  });
  it("includes current unknown and in-flight reservations in the combined allocation upper bound", () => {
    const unknown = combinedHarnessJob({ unknown: true });
    expect(validCorpusJob(unknown)).toBe(true); expect(corpusCombinedBudget(unknown).totalAllocation).toBe(0.228024);
    const inflight = combinedHarnessJob({ incomplete: true }), ledger = inflight.provider_budget;
    ledger.requests[0] = { ...ledger.requests[0], outcome: "reserved", cost_upper_micro_usd: null, usage: null };
    ledger.committed_upper_micro_usd -= 66; ledger.inflight_reserved_micro_usd = 1000; ledger.available_micro_usd -= 934;
    expect(validCorpusJob(inflight)).toBe(true); expect(corpusCombinedBudget(inflight).totalAllocation).toBe(0.227959);
  });
  it("derives standard-rate estimates with integer nano-USD and disjoint cache categories", () => {
    const job = observedCostHarnessJob();
    expect(validCorpusJob(job)).toBe(true);
    expect(corpusCostObservation(job)).toMatchObject({ current: 0.000136, prior: 0.008056, total: 0.008192,
      currentNanoUsd: 136000, totalNanoUsd: 8192000 });
    expect(corpusCombinedBudget(job).totalAllocation).toBe(0.227025);
    expect(corpusCostObservation(harnessJob())).toBeNull(); expect(corpusCostObservation(corpusJob())).toBeNull();
  });
  it("retains multiple prior confirmed and unknown amounts separately within the original authorization", () => {
    const job = accumulatedHarnessJob(), original = structuredClone(job.cases);
    expect(validCorpusJob(job)).toBe(true); expect(validCorpusCapabilities(harnessCapabilities({ cumulative: true }))).toBe(true);
    expect(corpusCombinedBudget(job)).toMatchObject({ version: 2, originalCap: 10, priorCommitted: 3.95268, priorUnknown: 0.226759,
      runCap: 5.820561, remaining: 5.820295, totalAllocation: 4.179705 });
    expect(corpusCombinedBudget(job).priorRuns).toHaveLength(2); expect(job.cases).toEqual(original);
    expect(corpusCombinedBudget(accumulatedHarnessJob({ unknown: true })).totalAllocation).toBe(4.180704);
  });
  it("rejects malformed, duplicate, active, unbound or arithmetically inconsistent v2 prior runs", () => {
    for (const change of [
      (job) => { job.combined_budget.version = 3; },
      (job) => { job.combined_budget.prior_committed_micro_usd++; },
      (job) => { job.combined_budget.prior_retained_unknown_micro_usd++; },
      (job) => { job.combined_budget.new_run_cap_micro_usd++; },
      (job) => { job.combined_budget.original_cap_micro_usd++; },
      (job) => { job.combined_budget.prior_committed_micro_usd = 3952680.5; },
      (job) => { job.combined_budget.prior_runs[0].committed_upper_micro_usd = -1; },
      (job) => { job.combined_budget.prior_runs[0].retained_unknown_micro_usd++; },
      (job) => { job.combined_budget.prior_runs[0].inflight_reserved_micro_usd = 1; },
      (job) => { job.combined_budget.prior_runs[0].run_id = job.id; },
      (job) => { job.combined_budget.prior_runs[0].run_id = "invalid"; },
      (job) => { job.combined_budget.prior_runs[1].run_id = job.combined_budget.prior_runs[0].run_id; },
      (job) => { job.combined_budget.prior_runs[0].report_file_sha256 = "missing"; },
      (job) => { job.combined_budget.prior_runs[0].checkpoint_sha256 = "missing"; },
      (job) => { job.combined_budget.prior_runs[0].refund = true; },
      (job) => { delete job.combined_budget.prior_runs[0].checkpoint_sha256; },
      (job) => { job.combined_budget.prior_runs.pop(); },
      (job) => { job.combined_budget.prior_runs = []; },
      (job) => { job.combined_budget.policy = "refund"; },
      (job) => { job.combined_budget.refund = true; },
      (job) => { job.provider_budget.max_micro_usd--; job.provider_budget.available_micro_usd--; job.max_usd -= 0.000001; },
    ]) { const invalid = accumulatedHarnessJob(); change(invalid); expect(validCorpusJob(invalid)).toBe(false); expect(corpusCombinedBudget(invalid)).toBeNull(); }
  });
  it("adds typed prior Gateway and token estimates with BigInt without releasing conservative reservations", () => {
    const job = accumulatedHarnessJob({ costObservation: true });
    expect(validCorpusJob(job)).toBe(true);
    expect(corpusCostObservation(job)).toMatchObject({ version: 2, current: 0.000136, prior: 1.05651024,
      total: 1.05664624, currentNanoUsd: 136000, totalNanoUsd: 1056646240 });
    expect(corpusCostObservation(job).priorObservations.map((prior) => prior.kind)).toEqual(["gateway_estimate", "standard_rate_token_estimate"]);
    expect(corpusCombinedBudget(job).totalAllocation).toBe(4.179705);
  });
  it("requires exact v2 estimate keys, unique complete prior coverage and bounded report/evidence bindings", () => {
    for (const change of [
      (job) => { job.cost_observation.version = 1; },
      (job) => { job.cost_observation.extra = true; },
      (job) => { delete job.cost_observation.rates; },
      (job) => { job.cost_observation.rates.output = 9; },
      (job) => { job.cost_observation.rates.extra = 0; },
      (job) => { job.cost_observation.report_sha256 = "0".repeat(64); },
      (job) => { job.cost_observation.prior_observations.pop(); },
      (job) => { job.cost_observation.prior_observations.push(structuredClone(job.cost_observation.prior_observations[0])); },
      (job) => { job.cost_observation.prior_observations[1].run_id = job.cost_observation.prior_observations[0].run_id; },
      (job) => { job.cost_observation.prior_observations[0].run_id = "9".repeat(32); },
      (job) => { job.cost_observation.prior_observations[0].kind = "invoice"; },
      (job) => { job.cost_observation.prior_observations[0].amount_nano_usd = -1; },
      (job) => { job.cost_observation.prior_observations[0].amount_nano_usd = 1.5; },
      (job) => { job.cost_observation.prior_observations[0].amount_nano_usd = 226759001; },
      (job) => { job.cost_observation.prior_observations[1].amount_nano_usd = 3952680001; },
      (job) => { job.cost_observation.prior_observations[0].report_file_sha256 = "4".repeat(64); },
      (job) => { job.cost_observation.prior_observations[0].evidence_file_sha256 = "missing"; },
      (job) => { job.cost_observation.prior_observations[0].invoice = true; },
      (job) => { delete job.cost_observation.prior_observations[0].kind; },
      (job) => { delete job.provider_budget.requests[0].usage.input_tokens_details; },
    ]) { const invalid = accumulatedHarnessJob({ costObservation: true }); change(invalid); expect(validCorpusJob(invalid)).toBe(false); expect(corpusCostObservation(invalid)).toBeNull(); }
    expect(validCorpusJob(accumulatedHarnessJob({ costObservation: true, unknown: true }))).toBe(false);
  });
  it("rejects supplied standard-rate observations with missing usage, bad bindings, prices or cache arithmetic", () => {
    for (const change of [
      (job) => { delete job.provider_budget.requests[0].usage.input_tokens_details; },
      (job) => { delete job.provider_budget.requests[0].usage.input_tokens_details.cache_write_tokens; },
      (job) => { job.provider_budget.requests[0].usage.input_tokens_details.cached_tokens = 8; },
      (job) => { job.provider_budget.requests[0].usage.input_tokens_details.cache_write_tokens = 1.5; },
      (job) => { job.provider_budget.requests[0].usage.input_tokens_details.audio_tokens = 1; },
      (job) => { job.cost_observation.report_sha256 = "0".repeat(64); },
      (job) => { job.cost_observation.prior_run_id = "0".repeat(32); },
      (job) => { job.cost_observation.prior_diagnosis_sha256 = "missing"; },
      (job) => { job.cost_observation.prior_gateway_micro_usd = 226760; },
      (job) => { job.cost_observation.rates.cache_write = 2; },
      (job) => { job.cost_observation.rates.extra = 0; },
      (job) => { job.cost_observation.invoice = true; },
    ]) { const invalid = observedCostHarnessJob(); change(invalid); expect(validCorpusJob(invalid)).toBe(false); expect(corpusCostObservation(invalid)).toBeNull(); }
    const unknown = observedCostHarnessJob({ unknown: true });
    expect(validCorpusJob(unknown)).toBe(false); expect(corpusCostObservation(unknown)).toBeNull();
  });
  it.skipIf(!process.env.QA_CORPUS_HARNESS_ARTIFACT)("validates an explicitly supplied local private artifact without modifying raw rows", async () => {
    const { job, capabilities } = await readHarnessArtifact(process.env.QA_CORPUS_HARNESS_ARTIFACT);
    expect(validCorpusJob(job)).toBe(true); expect(validCorpusCapabilities(capabilities)).toBe(true);
    expect(corpusReview(job)).toMatchObject({ passed: 0, failed: 0, not_assessable: 1 });
    expect(corpusResult(job).status).toBe("INCOMPLETE");
    expect(corpusLedger(job)).toMatchObject({ committed: 0, unknown: 0.226759, requests: 1 });
    expect(job.total_cases).toBe(24); expect(job.completed_cases).toBe(1);
  });
  it.skipIf(!process.env.QA_CORPUS_HARNESS_RUN)("preserves every answer, citation and turn trace in an explicitly supplied completed private run", async () => {
    const { report, combinedBudget } = await readHarnessRun(process.env.QA_CORPUS_HARNESS_RUN);
    const originalCases = JSON.stringify(report.cases);
    expect(report.status).toBe("completed"); expect(report.cases).toHaveLength(24);
    expect(report.cases.reduce((sum, row) => sum + row.answers.length, 0)).toBe(48);
    for (const row of report.cases) for (const answer of row.answers) {
      const evidence = corpusAnswerEvidence(row, answer);
      expect(typeof answer.answer_md).toBe("string"); expect(Array.isArray(answer.items)).toBe(true); expect(Array.isArray(answer.citations)).toBe(true);
      expect(JSON.stringify(evidence.items) === JSON.stringify(answer.items)).toBe(true);
      expect(JSON.stringify(evidence.citations) === JSON.stringify(answer.citations)).toBe(true);
      expect(JSON.stringify(evidence.guard) === JSON.stringify(answer.guard)).toBe(true);
      expect(evidence.raw_model_answer === answer.raw_model_answer).toBe(true);
      expect(evidence.tool_events.every((event) => event.turn === answer.turn)).toBe(true);
      expect(evidence.tool_events.length).toBe(row.tool_trace.filter((event) => event.turn === answer.turn).length);
    }
    const total = corpusCombinedBudget({ ...report, id: report.run_id, combined_budget: combinedBudget });
    expect(total).toMatchObject({ originalCap: 10, priorRetained: 0.226759, totalAllocation: 4.179439 });
    expect(total.totalAllocation + total.remaining).toBe(10);
    expect(JSON.stringify(report.cases) === originalCases).toBe(true);
  });
  it.skipIf(!process.env.QA_CORPUS_HARNESS_CURRENT_ARTIFACT)("validates the completed private run's full AI review and bound cost estimates", async () => {
    const { job, capabilities } = await readHarnessArtifact(process.env.QA_CORPUS_HARNESS_CURRENT_ARTIFACT);
    const { report } = await readHarnessRun(process.env.QA_CORPUS_HARNESS_CURRENT_ARTIFACT);
    expect(JSON.stringify(job.cases) === JSON.stringify(report.cases)).toBe(true);
    expect(validCorpusJob(job)).toBe(true); expect(validCorpusCapabilities(capabilities)).toBe(true);
    expect(corpusReview(job)).toMatchObject({ reviewed_cases: 24, passed: 22, failed: 2, not_assessable: 0 });
    const reviews = corpusReview(job).cases;
    expect(reviews.find((row) => row.case_id === "real-006").scores.grounding).toBe(false);
    expect(reviews.find((row) => row.case_id === "real-022").scores).toMatchObject({ intent: false, completeness: false });
    expect(reviews.every((row) => row.reason.trim().length > 0)).toBe(true);
    expect(corpusResult(job).status).toBe("FAIL");
    expect(corpusCostObservation(job)).toMatchObject({ current: 1.04845424, prior: 0.008056, total: 1.05651024,
      currentNanoUsd: 1048454240, totalNanoUsd: 1056510240 });
    expect(corpusCombinedBudget(job)).toMatchObject({ totalAllocation: 4.179439, remaining: 5.820561 });
  });
});
