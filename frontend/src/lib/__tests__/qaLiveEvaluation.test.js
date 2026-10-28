import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import fixtures from "../../../e2e/observatory-live-evaluation-physical.cjs";
import { validLiveBudget, validLiveCapabilities, validLiveEvaluationJob } from "../qaLiveEvaluation.js";
import { allPassingReviewedJob, expandedLivePackObservation, historicalPricingObservation, invalidHistoricalPricingObservations, observeReviewedJob, observedReviewSummary } from "./qa/semantic-review-physical.js";

// Contract observations come from the shared browser physical fixture, never a
// reimplementation of backend execution or model scoring.
const observedJob = (change = () => {}) => { const job = fixtures.jobBody("quick", "completed"); change(job); return job; };
describe("live evaluation public records", () => {
  it("supports the 51-case current pack while preserving historical 49-case records and rejecting larger packs", () => {
    const { job, capabilities } = expandedLivePackObservation();
    expect(validLiveEvaluationJob(job)).toBe(true); expect(validLiveCapabilities(capabilities)).toBe(true);
    expect(capabilities.profiles.map((profile) => profile.case_count)).toEqual([8, 36, 15, 51]);
    expect(validLiveEvaluationJob(fixtures.jobBody("all", "incomplete"))).toBe(true);
    expect(fixtures.capabilitiesBody().profiles.find((profile) => profile.id === "all").case_count).toBe(49);
    job.total_cases = 52; expect(validLiveEvaluationJob(job)).toBe(false);
    capabilities.profiles.find((profile) => profile.id === "all").case_count = 52;
    expect(validLiveCapabilities(capabilities)).toBe(false);
  });
  it("accepts finite historical report rates only on imported archives and keeps start pricing provenance strict", () => {
    const archived = historicalPricingObservation();
    expect(validLiveEvaluationJob(archived)).toBe(true);
    expect(validLiveCapabilities(fixtures.capabilitiesBody({ job: archived }))).toBe(true);
    const capabilities = fixtures.capabilitiesBody();
    capabilities.pricing = archived.pricing;
    expect(validLiveCapabilities(capabilities)).toBe(false);
    for (const { name, job } of invalidHistoricalPricingObservations()) expect(validLiveEvaluationJob(job), name).toBe(false);
  });
  it("accepts completed AI review without turning semantic failures or an incomplete run into quality PASS", () => {
    expect(validLiveEvaluationJob(observeReviewedJob())).toBe(true);
    expect(validLiveEvaluationJob(observeReviewedJob({ incomplete: true }))).toBe(true);
    expect(validLiveEvaluationJob(allPassingReviewedJob())).toBe(true);
  });
  it("accepts internally consistent reviewed history summaries but requires row evidence on job details", () => {
    const summary = observedReviewSummary();
    expect(validLiveEvaluationJob(summary, { summary: true })).toBe(true);
    expect(validLiveEvaluationJob(summary)).toBe(false);
    expect(validLiveCapabilities(fixtures.capabilitiesBody({ job: observeReviewedJob() }))).toBe(true);
  });
  it("accepts bounded real-execution records while semantic review remains pending", () => {
    expect(validLiveCapabilities(fixtures.capabilitiesBody())).toBe(true);
    expect(validLiveEvaluationJob(observedJob())).toBe(true);
    expect(validLiveEvaluationJob(fixtures.jobBody("all", "incomplete"))).toBe(true);
    expect(validLiveEvaluationJob(observedJob((job) => { job.semantic_review = null; }))).toBe(true);
  });
  it("accepts missing pricing only when the service is unavailable", () => {
    const value = fixtures.capabilitiesBody({ available: false }); value.pricing = null;
    expect(validLiveCapabilities(value)).toBe(true);
    value.available = true;
    expect(validLiveCapabilities(value)).toBe(false);
  });
  it("accepts the exact server pricing provenance pair while rejecting mixed or unknown provenance", () => {
    const value = fixtures.capabilitiesBody();
    value.pricing.source = "server_configuration"; value.pricing.verified_at = "server_configuration";
    expect(validLiveCapabilities(value)).toBe(true);
    value.pricing.verified_at = "2026-10-19";
    expect(validLiveCapabilities(value)).toBe(false);
    value.pricing.source = "https://developers.openai.com/api/docs/models/gpt-5-mini";
    value.pricing.verified_at = "server_configuration";
    expect(validLiveCapabilities(value)).toBe(false);
    value.pricing.source = "unknown"; value.pricing.verified_at = "unknown";
    expect(validLiveCapabilities(value)).toBe(false);
  });
  it("allows omitted case detail only for capability history summaries", () => {
    const summary = fixtures.capabilitiesBody({ job: observedJob() }).recent[0];
    expect(validLiveEvaluationJob(summary, { summary: true })).toBe(true);
    expect(validLiveEvaluationJob(summary)).toBe(false);
  });
  it("retains legitimate model failures and long answers within the backend report limits", () => {
    const value = observedJob((job) => {
      job.cases[1].failures = Array.from({ length: 33 }, (_, index) => index ? "tool violation " + index : "x".repeat(2049));
      job.cases[1].hard_failures = Array.from({ length: 200 }, () => "missing source");
      job.cases[1].answer = "a".repeat(262145);
    });
    expect(validLiveEvaluationJob(value)).toBe(true);
    value.cases[1].hard_failures.push("too many");
    expect(validLiveEvaluationJob(value)).toBe(false);
  });
  it("rejects fabricated semantic approval, malformed usage and unmeasured fields", () => {
    for (const change of [
      (job) => { job.quality_passed = true; },
      (job) => { job.semantic_status = "passed"; },
      (job) => { job.usage.input_tokens = null; },
      (job) => { job.usage.measured_estimated_usd = NaN; },
      (job) => { job.completed_cases = 50; },
      (job) => { job.completed_cases = 1; job.cases = job.cases.slice(0, 1); job.structural = { passed: 1, failed: 0 }; },
      (job) => { job.cases[0].row_sha = "unverified"; },
      (job) => { job.semantic_review = {}; },
      (job) => { job.archive_imported = "true"; },
      (job) => { job.report_sha256 = "unverified"; },
      (job) => { job.report_sha256 = null; },
    ]) expect(validLiveEvaluationJob(observedJob(change))).toBe(false);
  });
  it("accepts finite acknowledged budget range only", () => {
    for (const invalid of [null, "1", NaN, Infinity, -1, 0, 0.009, 5.01]) expect(validLiveBudget(invalid)).toBe(false);
    expect(validLiveBudget(0.01)).toBe(true); expect(validLiveBudget(5)).toBe(true);
    expect(validLiveBudget(2, 1)).toBe(false);
  });
});
