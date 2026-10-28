// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { createI18n } from "vue-i18n";
import QaReleaseDecision from "../QaReleaseDecision.vue";
import en from "../../i18n/en.json";
import validationFixtures from "../../../e2e/observatory-validation-physical.cjs";
import liveFixtures from "../../../e2e/observatory-live-evaluation-physical.cjs";

const CURRENT = "a".repeat(40), mounted = [];
// Contract: read-only job/capabilities display; all source records come from the
// existing public API physical fixtures, and mounting cannot execute a QA run.
function openDecision({ kind = "offline_regression", state = "completed", failedModel = false, passedModel = false, fullBasic = false, ownerBasic = false } = {}) {
  const job = kind === "model_evaluation" ? { ...liveFixtures.jobBody("quick", state), source_sha: CURRENT } : { ...validationFixtures.jobBody("all", state, kind), source_sha: CURRENT };
  if (kind === "offline_regression" && state === "completed") job.steps.forEach((step) => { step.skipped = 0; });
  if (failedModel) { job.structural.passed -= 1; job.structural.failed += 1; }
  if (passedModel) job.structural = { passed: job.completed_cases, failed: 0 };
  const service = { ...validationFixtures.jobBody("all", "completed", "es_integration"), id: "service-observation", source_sha: CURRENT };
  const regression = { ...validationFixtures.jobBody("all", "completed", "offline_regression"), id: "regression-observation", source_sha: CURRENT };
  regression.steps.forEach((step) => { step.skipped = 0; });
  const validationObservation = ownerBasic ? { capabilities: { source_sha: CURRENT, recent: [regression, service] }, job: null, loading: false, error: "" } : null;
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: "en", messages: { en } });
  const wrapper = mount(QaReleaseDecision, { props: { job, sourceSha: CURRENT, kind, validationObservation, capabilities: { recent: fullBasic ? [service] : [] } }, global: { plugins: [i18n] } });
  mounted.push(wrapper);
  return {
    state: () => ["running", "blocked", "incomplete", "ready"].find((value) => wrapper.classes().includes("qa-release-decision-" + value)),
    verdict: () => wrapper.get('[data-testid="qa-release-decision-verdict"]').text(),
    blockers: () => wrapper.get('[data-testid="qa-release-blockers"]').text(),
    missing: () => wrapper.get('[data-testid="qa-release-missing"]').text(),
    text: () => wrapper.text(), headings: () => wrapper.findAll("h2, h3").map((heading) => heading.text()),
  };
}
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); });

describe("readable release decision", () => {
  it("places the release verdict before blockers and missing checks", () => {
    const view = openDecision();
    expect(view.state()).toBe("incomplete");
    expect(view.headings()).toEqual([en.qaRunFlow.states.incomplete, en.qaRunFlow.blockersTitle, en.qaRunFlow.missingTitle]);
    expect(view.missing()).toContain(en.qaRunFlow.missing.es_integration);
  });
  it("keeps the pending quality boundary visible when the basic release checks pass", () => {
    const view = openDecision({ fullBasic: true });
    expect(view.state()).toBe("ready");
    expect(view.verdict()).toBe(en.qaRunFlow.states.ready);
    expect(view.text()).toContain(en.qaRunFlow.basicScope);
    expect(view.missing()).toContain(en.qaRunFlow.missing.humanReview);
  });
  it("makes model failures actionable before detailed case evidence", () => {
    const view = openDecision({ kind: "model_evaluation", failedModel: true });
    expect(view.state()).toBe("blocked");
    expect(view.blockers()).toContain(en.qaRunFlow.tasks.model_evaluation);
    expect(view.missing()).toContain(en.qaRunFlow.missing.humanReview);
  });
  it("does not present an executing job as a final release verdict", () => {
    const view = openDecision({ state: "running" });
    expect(view.state()).toBe("running");
    expect(view.verdict()).toBe(en.qaRunFlow.states.running);
    expect(view.blockers()).toContain(en.qaRunFlow.pendingBlockers);
  });
  it("shows the remaining quality gap without claiming confirmed owner basic checks are missing", () => {
    const view = openDecision({ kind: "model_evaluation", passedModel: true, ownerBasic: true });
    expect(view.state()).toBe("incomplete");
    expect(view.missing()).not.toContain(en.qaRunFlow.missing.offline_regression);
    expect(view.missing()).not.toContain(en.qaRunFlow.missing.es_integration);
    expect(view.missing()).toContain(en.qaRunFlow.missing.humanReview);
  });
});
