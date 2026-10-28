import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import validationFixtures from "../../../e2e/observatory-validation-physical.cjs";
import liveFixtures from "../../../e2e/observatory-live-evaluation-physical.cjs";
import { buildReleaseDecision } from "../qaReleaseDecision.js";
import { allPassingReviewedJob, observeReviewedJob } from "./qa/semantic-review-physical.js";

const CURRENT = "a".repeat(40), PREVIOUS = "b".repeat(40);
// Contract: public ValidationService and LiveEvaluationService records. Existing
// physical fixture factories remain the single source for API record shapes.
function validation({ kind = "offline_regression", state = "completed", source = CURRENT, suite = "all", id = kind, at = "2026-10-22T10:00:00Z", skipped = false, unmeasured = false } = {}) {
  const job = { ...validationFixtures.jobBody(suite, state, kind), id, source_sha: source, started_at: at };
  if (kind === "offline_regression" && state === "completed") job.steps.forEach((step) => { step.skipped = 0; });
  if (skipped) job.steps[0].skipped = 1;
  if (unmeasured) job.steps[0].tests = null;
  return job;
}
function decision({ job = validation(), current = CURRENT, recent = [], kind = job.mode, validationObservation = null, syncIssue = false } = {}) {
  return buildReleaseDecision({ job, sourceSha: current, kind, syncIssue, validationObservation, capabilities: { ...validationFixtures.capabilitiesBody(), source_sha: current, recent } });
}
const basicPasses = () => [validation(), validation({ kind: "es_integration" })];
function validationObservation({ source = CURRENT, job = null, error = "", recent = basicPasses() } = {}) {
  return { capabilities: { ...validationFixtures.capabilitiesBody(), source_sha: source, recent }, job, loading: false, error };
}
function model({ failed = false } = {}) {
  const job = { ...liveFixtures.jobBody("quick", "completed"), source_sha: CURRENT };
  // Exercise summary verdict boundaries; the frozen browser baseline has 7/8,
  // while this deterministic observation explicitly covers an all-PASS summary.
  job.structural = { passed: job.completed_cases - Number(failed), failed: Number(failed) };
  return job;
}

describe("result-first release decision", () => {
  it("resolves only the selected model run's review boundary and keeps semantic failures visible alongside other blockers", () => {
    const job = observeReviewedJob({}, (value) => { value.source_sha = PREVIOUS; });
    const result = decision({ job, kind: "model_evaluation" });
    expect(result.state).toBe("blocked");
    expect(result.missing.map((entry) => entry.id)).not.toContain("human_semantic_review_pending");
    expect(result.missing.map((entry) => entry.id)).toEqual(expect.arrayContaining(["offline_regression", "es_integration", "es_integration_not_executed"]));
    expect(result.blockers.map((entry) => entry.reason)).toEqual(expect.arrayContaining(["semantic_failed", "failed_checks", "version_mismatch"]));
    expect(result.blockers).toContainEqual({ mode: "model_evaluation", reason: "semantic_failed", i18nKey: "qaSemanticReview.failedReview" });
  });
  it("keeps real ES and other quality boundaries after a completed passing semantic review", () => {
    const job = allPassingReviewedJob({ incomplete: true });
    const result = decision({ job, kind: "model_evaluation" });
    expect(result.state).toBe("incomplete");
    expect(result.missing.map((entry) => entry.id)).not.toContain("human_semantic_review_pending");
    expect(result.missing.map((entry) => entry.id)).toContain("es_integration_not_executed");
    expect(result.blockers.map((entry) => entry.reason)).toContain("incomplete");
    expect(result.blockers.map((entry) => entry.reason)).not.toContain("semantic_failed");
  });
  it("keeps RAG pending and refuses a review with altered report evidence", () => {
    const rag = decision({ job: validation({ kind: "real_es_llm_e2e" }) });
    expect(rag.missing.map((entry) => entry.id)).toContain("human_semantic_review_pending");
    const altered = observeReviewedJob({}, (job) => { job.semantic_review.cases[0].row_sha = "b".repeat(64); });
    const result = decision({ job: altered, kind: "model_evaluation" });
    expect(result.missing.map((entry) => entry.id)).toContain("human_semantic_review_pending");
    expect(result.blockers.map((entry) => entry.reason)).not.toContain("semantic_failed");
  });
  it("keeps a single successful regression incomplete until same-revision full service evidence exists", () => {
    const result = decision();
    expect(result.state).toBe("incomplete");
    expect(result.selected.status).toBe("PASS");
    expect(result.missing.map((entry) => entry.id)).toContain("es_integration");
  });
  it("allows basic readiness only when both complete measured gates pass at the current full SHA", () => {
    const result = decision({ recent: basicPasses() });
    expect(result.state).toBe("ready");
    expect(result.scope).toBe("basic");
    expect(result.blockers).toEqual([]);
    expect(result.missing.map((entry) => entry.id)).toContain("human_semantic_review_pending");
  });
  it("retains a selected failed historical run even when newer complete evidence passed", () => {
    const result = decision({ job: validation({ state: "failed", id: "failed-history", at: "2026-10-22T09:00:00Z" }), recent: basicPasses() });
    expect(result.state).toBe("blocked");
    expect(result.blockers).toContainEqual(expect.objectContaining({ mode: "offline_regression", reason: "failed_checks" }));
  });
  it("blocks when a more recent service run failed instead of borrowing its older PASS", () => {
    const result = decision({ recent: [...basicPasses(), validation({ kind: "es_integration", state: "failed", id: "failed-new", at: "2026-10-22T11:00:00Z" })] });
    expect(result.state).toBe("blocked");
    expect(result.blockers).toContainEqual(expect.objectContaining({ mode: "es_integration", reason: "failed_checks" }));
  });
  it("rejects skipped or missing measurements instead of upgrading completed to release PASS", () => {
    const skipped = decision({ job: validation({ skipped: true }), recent: [basicPasses()[1]] });
    expect(skipped.state).toBe("incomplete");
    expect(skipped.blockers.map((entry) => entry.reason)).toContain("skipped_checks");
    const unmeasured = decision({ job: validation({ unmeasured: true }), recent: [basicPasses()[1]] });
    expect(unmeasured.state).toBe("incomplete");
    expect(unmeasured.blockers.map((entry) => entry.reason)).toContain("unmeasured");
  });
  it("rejects a previous or unknown selected revision even if current capabilities contain both passing gates", () => {
    for (const source of [PREVIOUS, null, CURRENT.slice(0, 12)]) {
      const result = decision({ job: validation({ source, id: "historical", at: "2026-10-22T09:00:00Z" }), recent: basicPasses() });
      expect(result.state).toBe("incomplete");
      expect(result.blockers.map((entry) => entry.reason)).toContain(source === PREVIOUS ? "version_mismatch" : "version_unknown");
    }
    expect(decision({ current: null, recent: basicPasses() }).state).toBe("incomplete");
  });
  it("keeps a partial suite incomplete even when other full passing records exist", () => {
    const result = decision({ job: validation({ suite: "ingestion", id: "partial" }), recent: basicPasses() });
    expect(result.state).toBe("incomplete");
    expect(result.blockers.map((entry) => entry.reason)).toContain("partial_scope");
  });
  it("withholds a final verdict while running and reports lost observation as incomplete", () => {
    const running = validation({ state: "running" });
    expect(decision({ job: running }).state).toBe("running");
    const lost = decision({ job: running, syncIssue: true });
    expect(lost.state).toBe("incomplete");
    expect(lost.blockers.map((entry) => entry.reason)).toContain("sync_error");
  });
  it("does not turn structural model success into a quality or basic release pass", () => {
    const job = model();
    const result = decision({ job, kind: "model_evaluation" });
    expect(result.state).toBe("incomplete");
    expect(result.scope).toBe("quality");
    expect(result.missing.map((entry) => entry.id)).toEqual(expect.arrayContaining(["offline_regression", "es_integration", "human_semantic_review_pending"]));
    const withBasic = decision({ job, kind: "model_evaluation", recent: basicPasses() });
    expect(withBasic.basicReady).toBe(true);
    expect(withBasic.state).toBe("incomplete");
  });
  it("reports structural model failures as blockers independently of a completed job process", () => {
    const job = model({ failed: true });
    const result = decision({ job, kind: "model_evaluation" });
    expect(result.state).toBe("blocked");
    expect(result.blockers.map((entry) => entry.reason)).toContain("failed_checks");
  });
  it("uses separate owner validation evidence without listing already confirmed basic checks as missing", () => {
    const result = decision({ job: model(), kind: "model_evaluation", validationObservation: validationObservation() });
    expect(result.basicReady).toBe(true);
    expect(result.state).toBe("incomplete");
    expect(result.missing.map((entry) => entry.id)).not.toContain("offline_regression");
    expect(result.missing.map((entry) => entry.id)).not.toContain("es_integration");
    expect(result.missing.map((entry) => entry.id)).not.toContain("es_integration_not_executed");
    expect(result.missing.map((entry) => entry.id)).toContain("human_semantic_review_pending");
  });
  it("does not combine owner validation and model evidence from conflicting current capability revisions", () => {
    const result = decision({ job: model(), kind: "model_evaluation", validationObservation: validationObservation({ source: PREVIOUS }) });
    expect(result.basicReady).toBe(false);
    expect(result.currentSha).toBe(null);
    expect(result.state).toBe("incomplete");
    expect(result.blockers.map((entry) => entry.reason)).toContain("version_unknown");
    expect(result.missing.map((entry) => entry.id)).toEqual(expect.arrayContaining(["offline_regression", "es_integration"]));
  });
  it("prefers the latest owner validation detail over a passing capability snapshot with the same ID", () => {
    const latest = validation({ state: "failed" });
    const result = decision({ job: model(), kind: "model_evaluation", validationObservation: validationObservation({ job: latest }) });
    expect(result.state).toBe("blocked");
    expect(result.basicReady).toBe(false);
    expect(result.rows[0]).toMatchObject({ status: "FAIL", job: { id: latest.id, status: "failed" } });
    expect(result.blockers).toContainEqual(expect.objectContaining({ mode: "offline_regression", reason: "failed_checks" }));
  });
  it("keeps failed validation observation unknown instead of treating previous PASS or an unread history as confirmed", () => {
    for (const observation of [validationObservation({ error: "request" }), { capabilities: null, job: null, loading: false, error: "request" }]) {
      const result = decision({ job: model(), kind: "model_evaluation", validationObservation: observation });
      expect(result.basicReady).toBe(false);
      expect(result.state).toBe("incomplete");
      expect(result.blockers.map((entry) => entry.reason)).toContain("sync_error");
      expect(result.missing.map((entry) => entry.id)).toEqual(expect.arrayContaining(["offline_regression", "es_integration"]));
    }
  });
});
