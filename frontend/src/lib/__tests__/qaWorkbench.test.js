import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import validationFixtures from "../../../e2e/observatory-validation-physical.cjs";
import liveFixtures from "../../../e2e/observatory-live-evaluation-physical.cjs";
import { buildWorkbenchModel } from "../qaWorkbench.js";
import { corpusCapabilities, corpusJob } from "./qa/corpus-evaluation-physical.js";

const CURRENT = "a".repeat(40), PREVIOUS = "b".repeat(40);
// Contract: ValidationService.capabilities/start and LiveEvaluationService.capabilities/start;
// source_sha is the packaged backend revision captured at creation, never inferred from time.
function regression({ id = "regression", mode = "offline_regression", suite = "all", state = "completed", sha = CURRENT, at = "2026-10-21T10:00:00Z" } = {}) {
  const job = { ...validationFixtures.jobBody(suite, state, mode), id, source_sha: sha, started_at: at };
  if (mode === "offline_regression" && state === "completed") job.steps.forEach((step) => { step.skipped = 0; });
  return job;
}
function scenario({ jobs = [], selected = null, live = [], selectedLive = null, source = CURRENT, error = "", loading = false, patch = {} } = {}) {
  const capabilities = { ...validationFixtures.capabilitiesBody(), source_sha: source, recent: jobs, ...patch };
  return buildWorkbenchModel({ validation: { capabilities, job: selected, loading, error }, evaluation: { capabilities: { ...liveFixtures.capabilitiesBody(), source_sha: source, recent: live }, job: selectedLive, loading: false, error: "" } });
}
const passedBasicChecks = () => [regression(), regression({ id: "service", mode: "es_integration", at: "2026-10-21T10:01:00Z" })];

describe("verification workbench evidence", () => {
  it("keeps real corpus quality separate from structural test counts and synthetic observations", () => {
    const job = corpusJob({ reviewed: true, failed: true });
    const model = buildWorkbenchModel({ validation: { capabilities: { recent: passedBasicChecks(), source_sha: CURRENT } }, corpus: { capabilities: corpusCapabilities({ job }), job } });
    expect(model.rows.map((row) => row.status)).toEqual(["PASS", "PASS"]);
    expect(model.readiness).toBe("ready");
    expect(model.history.find((entry) => entry.id === job.id)).toMatchObject({ family: "corpus-evaluations", mode: "real_corpus_quality", status: "FAIL", counts: null });
    expect(model.optional.find((entry) => entry.mode === "real_corpus_quality").status).toBe("FAIL");
  });
  it("cannot treat an earlier bank or source revision as a current corpus pass", () => {
    for (const oldSource of [true, false]) {
      const job = corpusJob({ reviewed: true }), capabilities = corpusCapabilities({ job });
      if (oldSource) job.source_sha = PREVIOUS;
      else capabilities.bank.sha256 = "0".repeat(64);
      const model = buildWorkbenchModel({ validation: { capabilities: { recent: passedBasicChecks(), source_sha: CURRENT } }, corpus: { capabilities, job } });
      expect(model.optional.find((entry) => entry.mode === "real_corpus_quality").status).toBe("STALE");
      expect(model.readiness).toBe("ready");
      expect(job.quality_passed).toBe(true);
    }
  });
  it("allows basic readiness only from both full measured checks bound to the current full revision", () => {
    const model = scenario({ jobs: passedBasicChecks() });
    expect(model.sourceSha).toBe(CURRENT);
    expect(model.rows.map((row) => row.status)).toEqual(["PASS", "PASS"]);
    expect(model.readiness).toBe("ready");
    expect(model.optional.map((row) => row.status)).toEqual(["NOT RUN", "NOT RUN"]);
    expect(model.latest.mode).toBe("es_integration");
  });
  it("never binds a legacy or previous-revision PASS to the revision observed now", () => {
    const legacy = regression(); delete legacy.source_sha;
    for (const job of [legacy, regression({ sha: PREVIOUS }), regression({ sha: CURRENT.slice(0, 12) })]) {
      const model = scenario({ jobs: [job, passedBasicChecks()[1]] });
      expect(model.rows[0].status).toBe("STALE");
      expect(model.readiness).toBe("unknown");
      expect(model.rows[0].job.status).toBe("completed");
      expect(model.nextAction).toMatchObject({ kind: "start", mode: "offline_regression" });
    }
  });
  it("rejects a partial suite, skipped checks, or unmeasured completed steps as full regression evidence", () => {
    const partial = scenario({ jobs: [regression({ suite: "ingestion" }), passedBasicChecks()[1]] });
    expect(partial.rows[0]).toMatchObject({ status: "NOT RUN", reason: "partial_scope" });
    expect(partial.readiness).toBe("blocked");
    const skipped = regression(); skipped.steps[0].skipped = 1;
    expect(scenario({ jobs: [skipped, passedBasicChecks()[1]] }).rows[0]).toMatchObject({ status: "INCOMPLETE", reason: "skipped_checks" });
    const unmeasured = regression(); unmeasured.steps[0].tests = null;
    expect(scenario({ jobs: [unmeasured, passedBasicChecks()[1]] }).rows[0]).toMatchObject({ status: "UNKNOWN", reason: "unmeasured" });
  });
  it("keeps a newer failure visible instead of reusing an older PASS", () => {
    const model = scenario({ jobs: [...passedBasicChecks(), regression({ id: "new-failure", state: "failed", at: "2026-10-21T11:00:00Z" })] });
    expect(model.rows[0].status).toBe("FAIL");
    expect(model.rows[0].job.id).toBe("new-failure");
    expect(model.readiness).toBe("blocked");
    expect(model.nextAction).toMatchObject({ kind: "details", id: "new-failure" });
  });
  it("preserves the newer selected observation when a capabilities snapshot still reports RUNNING", () => {
    const completed = regression(); const old = { ...completed, status: "running" };
    const model = scenario({ jobs: [old, passedBasicChecks()[1]], selected: completed });
    expect(model.rows[0].status).toBe("PASS");
    expect(model.history.filter((entry) => entry.id === completed.id)).toHaveLength(1);
  });
  it("keeps family IDs distinct and includes live detail without making optional model quality required", () => {
    const live = { ...liveFixtures.jobBody("quick", "completed"), id: "regression", source_sha: CURRENT, started_at: "2026-10-21T12:00:00Z" };
    const model = scenario({ jobs: passedBasicChecks(), live: [live], selectedLive: live });
    expect(model.history.filter((entry) => entry.id === "regression")).toHaveLength(2);
    expect(model.latest).toMatchObject({ family: "evaluations", mode: "model_evaluation" });
    expect(model.latest.job.semantic_status).toBe("pending");
    expect(model.readiness).toBe("ready");
  });
  it("resumes active work and does not offer a new free start while busy or cooling down", () => {
    const running = regression({ state: "running" });
    expect(scenario({ jobs: [running] }).nextAction).toMatchObject({ kind: "resume", id: running.id, disabled: false });
    const busy = scenario({ patch: { busy: true } });
    expect(busy.nextAction).toMatchObject({ kind: "start", disabled: true, reason: "busy" });
    const cooldown = scenario({ patch: { retry_after_seconds: 18 } });
    expect(cooldown.nextAction).toMatchObject({ disabled: true, reason: "cooldown" });
    expect(cooldown.retryAfterSeconds).toBe(18);
  });
  it("distinguishes an initial read or failed sync from successfully observed NOT RUN", () => {
    const initial = buildWorkbenchModel({ validation: { capabilities: null, loading: true, error: "" }, evaluation: {} });
    expect(initial.readiness).toBe("loading");
    const failed = scenario({ jobs: passedBasicChecks(), error: "request" });
    expect(failed.readiness).toBe("unknown");
    expect(failed.nextAction).toMatchObject({ kind: "reload", reason: "sync_error" });
    expect(failed.errors).toEqual([{ family: "validations", error: "request" }]);
    expect(scenario().rows.map((row) => row.status)).toEqual(["NOT RUN", "NOT RUN"]);
  });
  it("refuses inconsistent current backend revisions from the two observed services", () => {
    const jobs = passedBasicChecks();
    const model = buildWorkbenchModel({ validation: { capabilities: { ...validationFixtures.capabilitiesBody(), source_sha: CURRENT, recent: jobs } }, evaluation: { capabilities: { ...liveFixtures.capabilitiesBody(), source_sha: PREVIOUS, recent: [] } } });
    expect(model.sourceSha).toBe(null);
    expect(model.readiness).toBe("unknown");
    expect(model.rows.every((row) => row.status === "STALE")).toBe(true);
  });
  it("does not use an older optional capability SHA to replace an explicitly unknown validation service revision", () => {
    const model = buildWorkbenchModel({ validation: { capabilities: { ...validationFixtures.capabilitiesBody(), source_sha: null, recent: passedBasicChecks() } }, evaluation: { capabilities: { ...liveFixtures.capabilitiesBody(), source_sha: CURRENT, recent: [] } } });
    expect(model.sourceSha).toBe(null);
    expect(model.readiness).toBe("unknown");
    expect(model.rows.every((row) => row.status === "STALE")).toBe(true);
  });
  it("keeps a missing active validation as unknown last-known evidence instead of suggesting it is still running", () => {
    const job = regression({ state: "running" });
    const model = scenario({ jobs: [job], selected: job, error: "missing" });
    expect(model.readiness).toBe("unknown");
    expect(model.rows[0]).toMatchObject({ status: "UNKNOWN", reason: "sync_error", job: { status: "running" } });
    expect(model.nextAction.kind).toBe("reload");
    expect(model.history[0].status).toBe("UNKNOWN");
  });
  it("does not let a missing last-known model run lock free checks after capabilities confirm the service is idle", () => {
    const lost = { ...liveFixtures.jobBody("quick", "running"), source_sha: CURRENT };
    const model = buildWorkbenchModel({ validation: { capabilities: { ...validationFixtures.capabilitiesBody(), source_sha: CURRENT } }, evaluation: { capabilities: { ...liveFixtures.capabilitiesBody(), source_sha: CURRENT }, job: lost, error: "missing" } });
    expect(model.history[0]).toMatchObject({ status: "UNKNOWN", job: { status: "running" } });
    expect(model.busy).toBe(false);
    expect(model.nextAction).toMatchObject({ kind: "start", mode: "offline_regression", disabled: false });
  });
});
