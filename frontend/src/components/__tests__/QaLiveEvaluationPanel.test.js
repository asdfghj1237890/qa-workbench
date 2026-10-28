// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createI18n } from "vue-i18n";
import { Quasar } from "quasar";
import QaLiveEvaluationPanel from "../QaLiveEvaluationPanel.vue";
import QaSemanticReviewPanel from "../QaSemanticReviewPanel.vue";
import fixtures from "../../../e2e/observatory-live-evaluation-physical.cjs";
import { observeReviewedJob } from "../../lib/__tests__/qa/semantic-review-physical.js";
import zhTW from "../../i18n/zh-TW.json";
import en from "../../i18n/en.json";

const transport = vi.hoisted(() => ({ fetch: null }));
vi.mock("../../lib/runtime.js", async original => { const actual = await original(); return ({ ...actual, get QA_EVIDENCE() { return actual.QA_EVIDENCE; }, get QA_REPOSITORY() { return actual.QA_REPOSITORY; }, get WORKBENCH_TASKS() { return actual.WORKBENCH_TASKS; },  AGENT: "/qa/api"  }); });
vi.mock("../../lib/qaSession.js", () => ({ apiFetch: (...args) => transport.fetch(...args) }));
const mounted = [];
// Contract: qa_evaluations.py POST /{id}/review and /import accept only the raw
// sidecar review fields. Public semantic_review rows additionally carry case_id.
function reviewImportBody(job = observeReviewedJob()) {
  const review = job.semantic_review;
  return { report_sha256: review.report_sha256, reviewer_kind: review.reviewer_kind, reviewer: review.reviewer,
    reviewed_at: review.reviewed_at, reviews: review.cases.map((row) => ({ key: row.key, row_sha: row.row_sha,
      reviewer: row.reviewer, scores: row.scores, reason: row.reason })) };
}
const uploadFile = (value, malformed = false) => ({ name: "offline-review.json", size: 1024,
  text: async () => malformed ? "{invalid JSON" : JSON.stringify(value) });
function archiveImportBody() {
  const job = observeReviewedJob({ archived: true, incomplete: true }, (value) => { value.id = "archive-browser-run"; });
  return { version: 1, job: { id: job.id, profile: job.profile, started_at: job.started_at,
    finished_at: job.finished_at, status: job.status, source_sha: job.source_sha },
  report: fixtures.reportBody(job), review: reviewImportBody(job) };
}

// Local action/physical boundary. Reuses the contract-anchored browser HTTP fixture
// shape. No model, regression command, or paid provider request is executed here.
async function openPanel({ available = true, busy = false, rejection = null, reviewRejection = null, resume = false, resumeStatus = "partial", retryAfter = 0, malformed = false, configuredPricing = false, manyFailures = false, workbench = false, maxBudget = 5 } = {}) {
  let run = resume ? fixtures.jobBody("quick", resumeStatus) : null;
  if (manyFailures && run) {
    run.cases[0].failures = Array.from({ length: 33 }, (_, index) => index ? "Fixture tool violation " + index : "x".repeat(2049));
    run.cases[0].structural_pass = false; run.structural = { passed: 0, failed: 1 };
  }
  let corrupted = false, nextPollFailure = null, nextReportFailure = null, hungReadAborted = false;
  const deferredPolls = [];
  const calls = [], downloads = [];
  vi.stubGlobal("URL", { createObjectURL: vi.fn((blob) => { downloads.push(blob); return "blob:offline-fixture-" + downloads.length; }), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  transport.fetch = vi.fn(async (url, init = {}) => {
    calls.push({ url, method: init.method || "GET", body: init.body ? JSON.parse(init.body) : undefined, signal: init.signal });
    if (url.includes("/logs")) {
      const text = "Captured model events for " + run.id;
      const total = new TextEncoder().encode(text).length, offset = Number(new URLSearchParams(url.split("?")[1]).get("offset"));
      return { ok: true, json: async () => ({ text: offset ? "" : text, next_offset: total, total_bytes: total, has_more: false, complete: !["queued", "running"].includes(run.status), truncated: false, legacy: false }) };
    }
    if (url.endsWith("/report")) {
      if (nextReportFailure) { const status = nextReportFailure; nextReportFailure = null; return { ok: false, status, headers: new Headers() }; }
      return { ok: true, blob: async () => new Blob([JSON.stringify(fixtures.reportBody(run))], { type: "application/json" }) };
    }
    if (url.endsWith("/import") && init.method === "POST") {
      if (reviewRejection) return { ok: false, status: reviewRejection };
      const body = JSON.parse(init.body);
      run = observeReviewedJob({ archived: true, incomplete: true }, (value) => Object.assign(value, body.job));
      run.pricing.source = "historical_report"; delete run.pricing.verified_at;
      return { ok: true, json: async () => ({ job: structuredClone(run) }) };
    }
    if (url.endsWith("/review")) {
      if (init.method === "POST") {
        if (reviewRejection) return { ok: false, status: reviewRejection };
        const id = run.id;
        run = observeReviewedJob({}, (value) => { value.id = id; });
        return { ok: true, json: async () => ({ job: structuredClone(run) }) };
      }
      return { ok: true, blob: async () => new Blob([JSON.stringify(reviewImportBody(run))], { type: "application/json" }) };
    }
    if (init.method === "POST" && !url.endsWith("/cancel")) {
      if (rejection) return { ok: false, status: rejection, headers: new Headers({ "Retry-After": "2" }) };
      const body = JSON.parse(init.body); run = fixtures.jobBody(body.profile, "queued", body.max_usd);
      return { ok: true, json: async () => ({ job: structuredClone(run) }) };
    }
    if (url.endsWith("/cancel")) { run = fixtures.jobBody(run.profile, "cancelled", run.max_usd); return { ok: true, json: async () => ({ job: structuredClone(run) }) }; }
    if (run && url.endsWith("/" + run.id)) {
      if (nextPollFailure) {
        const status = nextPollFailure; nextPollFailure = null;
        if (status === "hang") return new Promise((_, reject) => init.signal.addEventListener("abort", () => { hungReadAborted = true; reject(new DOMException("Cancelled", "AbortError")); }, { once: true }));
        if (status === "defer") { const value = structuredClone(run); await new Promise((resolve) => { deferredPolls.push(resolve); }); return { ok: true, json: async () => ({ job: value }) }; }
        return { ok: false, status, headers: new Headers() };
      }
      const value = structuredClone(run); if (corrupted) value.quality_passed = true;
      return { ok: true, json: async () => ({ job: value }) };
    }
    return { ok: true, json: async () => {
      const value = fixtures.capabilitiesBody({ available, busy, job: run, retryAfter });
      value.max_budget_usd = maxBudget; value.default_budget_usd = Math.min(value.default_budget_usd, maxBudget);
      if (configuredPricing) value.pricing = { ...value.pricing, source: "server_configuration", verified_at: "server_configuration" };
      return malformed ? { available: true } : value;
    } };
  });
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: "zh-TW", messages: { "zh-TW": zhTW, en } });
  const wrapper = mount(QaLiveEvaluationPanel, { props: { workbench }, global: { plugins: [i18n, Quasar] } });
  mounted.push(wrapper); await flushPromises();
  const control = (id) => wrapper.get('[data-testid="qa-live-' + id + '"]');
  return {
    text: () => wrapper.text(), calls: () => calls, downloads: () => downloads,
    heading: () => wrapper.get("#qa-live-title").element.tagName,
    stateTitle: () => wrapper.get('[data-testid="qa-live-state-title"]').text(),
    oldStepper: () => wrapper.find(".qa-flow-steps").exists(),
    resultOrder: () => {
      const result = control("result"), decision = result.get('[data-testid="qa-release-decision"]').element;
      return [".qa-live-cases", ".qa-execution-log"].map((selector) => Boolean(decision.compareDocumentPosition(result.get(selector).element) & Node.DOCUMENT_POSITION_FOLLOWING));
    },
    releaseBlocked: () => wrapper.find(".qa-release-decision-blocked").exists(),
    showsReleaseDecision: () => wrapper.find('[data-testid="qa-release-decision"]').exists(),
    showsPendingDecision: () => wrapper.find('[data-testid="qa-live-pending-decision"]').exists(),
    logBeforeCases: () => Boolean(wrapper.get(".qa-execution-log").element.compareDocumentPosition(wrapper.get(".qa-live-cases").element) & Node.DOCUMENT_POSITION_FOLLOWING),
    summary: () => wrapper.emitted("status-change")?.at(-1)?.[0],
    observation: () => wrapper.emitted("observation-change")?.at(-1)?.[0],
    prepareExternally: () => wrapper.vm.prepareRun(),
    showExternally: (id, options) => wrapper.vm.showJob(id, options),
    startFree: (mode) => wrapper.vm.startFree(mode),
    phase: () => wrapper.emitted("phase-change")?.at(-1)?.[0],
    history: () => { const history = wrapper.find('[data-testid="qa-live-history"]'); return history.exists() ? history.text() : null; },
    async selectHistory() { await wrapper.get('[data-testid="qa-live-history"] button').trigger("click"); await flushPromises(); },
    async fullLog() { await wrapper.get('[data-testid="qa-full-log-open"]').trigger("click"); await flushPromises(); },
    fullLogOutput: () => wrapper.get('[data-testid="qa-full-log-output"]').text(),
    resourceExpanded: () => wrapper.get(".qa-live-resource-toggle").attributes("aria-expanded") === "true",
    resourceInsideForm: () => wrapper.get("#qa-live-resource-details").element.closest("form") !== null,
    model: () => ({ value: control("model").text(), tag: control("model").element.tagName }),
    settingsLocked: () => ["profile", "budget", "ack"].every((id) => control(id).attributes("disabled") !== undefined),
    startInForm: () => control("start").element.closest("form")?.id === "qa-live-config-form",
    startCount: () => wrapper.findAll('[data-testid="qa-live-start"]').length,
    startReason: () => control("start-reason").text(),
    budgetCeiling: () => control("budget").attributes("max"),
    compactEmpty: () => ({ exists: wrapper.find('[data-testid="qa-live-empty"]').exists(), legacyResult: wrapper.find(".qa-live-empty").exists() }),
    displayedView: () => wrapper.find(".qa-live-left").element.style.display === "none" ? "evidence" : "settings",
    navigation: () => wrapper.emitted("navigate") || [],
    hide() { wrapper.element.style.display = "none"; },
    failNextPoll(status) { nextPollFailure = status; },
    statusReads: () => calls.filter((call) => call.method === "GET" && run && call.url.endsWith("/" + run.id)).length,
    hungReadAborted: () => hungReadAborted,
    async releaseDeferredPoll() { deferredPolls.shift()(); await flushPromises(); },
    captureFailure(reason) { run.status = "failed"; run.error = reason; },
    failNextReport(status) { nextReportFailure = status; },
    reportDisabled: () => control("report").attributes("disabled") !== undefined,
    retryLink: () => { const link = wrapper.find('[data-testid="qa-live-report-retry"]'); return link.exists() ? { href: link.attributes("href"), download: link.attributes("download"), tag: link.element.tagName } : null; },
    disabled: () => control("start").attributes("disabled") !== undefined,
    progress: () => { const progress = wrapper.find("progress"); return progress.exists() ? { value: Number(progress.attributes("value")), max: Number(progress.attributes("max")) } : null; },
    async acknowledge() { await control("ack").setValue(true); },
    async budget(value) { await control("budget").setValue(value); },
    async profile(value) { await control("profile").setValue(value); },
    async start() { await control("start").trigger(workbench ? "click" : "submit"); await flushPromises(); },
    async cancel() { await control("cancel").trigger("click"); await flushPromises(); },
    async settings() { await control("show-settings").trigger("click"); await flushPromises(); },
    async prepare() { await control("new-run").trigger("click"); await flushPromises(); },
    async backToWorkbench() { await control("back-workbench").trigger("click"); await flushPromises(); },
    async openHistory() { await wrapper.vm.showHistory(); await flushPromises(); },
    async toggleResourceLimits() { await wrapper.get(".qa-live-resource-toggle").trigger("click"); },
    async refresh() { await wrapper.findAll("button").find((button) => button.text() === zhTW.qaLive.refresh).trigger("click"); await flushPromises(); },
    async download() { await control("report").trigger("click"); await flushPromises(); },
    async uploadReview({ malformedFile = false } = {}) {
      wrapper.findComponent(QaSemanticReviewPanel).vm.$emit("import", uploadFile(reviewImportBody(), malformedFile));
      await flushPromises();
    },
    async uploadArchive() {
      const input = wrapper.get('.qa-live-archive-import input[type="file"]');
      Object.defineProperty(input.element, "files", { configurable: true, value: [uploadFile(archiveImportBody())] });
      await input.trigger("change"); await flushPromises();
    },
    async downloadReview() { await wrapper.get('[data-testid="qa-semantic-download"]').trigger("click"); await flushPromises(); },
    reviewStatus: () => control("semantic").text(),
    reviewRequests: () => calls.filter((call) => call.url.endsWith("/review")),
    importedRequests: () => calls.filter((call) => call.url.endsWith("/import")),
    paidStartRequests: () => calls.filter((call) => call.method === "POST" && call.url === "/qa/api/qa/evaluations"),
    advance(status) { run = fixtures.jobBody(run.profile, status, run.max_usd); },
    corruptQuality() { corrupted = true; },
    async tick(seconds = 1) { await vi.advanceTimersByTimeAsync(seconds * 1000); await flushPromises(); },
    close() { mounted.splice(mounted.indexOf(wrapper), 1); wrapper.unmount(); },
  };
}
beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] }));
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("manual live LLM evaluation", () => {
  it("fills the selected run's AI semantic review without another paid start and retains its failed reasons", async () => {
    const panel = await openPanel({ workbench: true, resume: true, resumeStatus: "completed" });
    expect(panel.reviewStatus()).toContain("人工語意審核待完成");
    await panel.uploadReview();
    expect(panel.reviewStatus()).toContain("AI 語意審核已完成");
    expect(panel.text()).toContain("The source does not support the numeric claim.");
    expect(panel.text()).toContain("7 通過 · 1 未通過");
    expect(panel.observation().job.semantic_status).toBe("reviewed");
    expect(panel.reviewRequests()).toHaveLength(1);
    expect(panel.reviewRequests()[0]).toMatchObject({ method: "POST", body: reviewImportBody() });
    expect(panel.importedRequests()).toHaveLength(0);
    expect(panel.paidStartRequests()).toHaveLength(0);
  });
  for (const status of [409, 503]) {
    it("preserves the pending evidence when review backfill is rejected with HTTP " + status, async () => {
      const panel = await openPanel({ resume: true, resumeStatus: "completed", reviewRejection: status });
      await panel.uploadReview();
      expect(panel.reviewStatus()).toContain("人工語意審核待完成");
      expect(panel.observation().job.semantic_status).toBe("pending");
      expect(panel.text()).toContain(status === 503 ? zhTW.qaSemanticReview.storageError : zhTW.qaSemanticReview.importError);
      expect(panel.text()).toContain("Fixture: required source reference missing");
      expect(panel.reviewRequests()).toHaveLength(1);
      expect(panel.paidStartRequests()).toHaveLength(0);
    });
  }
  it("rejects a malformed review file before sending any backfill or paid request", async () => {
    const panel = await openPanel({ resume: true, resumeStatus: "completed" });
    await panel.uploadReview({ malformedFile: true });
    expect(panel.reviewStatus()).toContain("人工語意審核待完成");
    expect(panel.observation().job.semantic_status).toBe("pending");
    expect(panel.text()).toContain(zhTW.qaSemanticReview.fileError);
    expect(panel.reviewRequests()).toHaveLength(0);
    expect(panel.paidStartRequests()).toHaveLength(0);
  });
  it("restores an archived reviewed run without a paid start and retains the incomplete planned coverage", async () => {
    const panel = await openPanel({ workbench: true });
    await panel.uploadArchive();
    expect(panel.reviewStatus()).toContain("AI 語意審核已完成");
    expect(panel.text()).toContain("匯入的歷史執行紀錄");
    expect(panel.text()).toContain("原定 49 題；41 題尚未執行");
    expect(panel.observation().job).toMatchObject({ id: "archive-browser-run", archive_imported: true,
      status: "incomplete", quality_passed: false });
    expect(panel.importedRequests()).toHaveLength(1);
    expect(panel.importedRequests()[0]).toMatchObject({ method: "POST", body: archiveImportBody() });
    expect(panel.paidStartRequests()).toHaveLength(0);
  });
  it("downloads the validated review through its authenticated GET endpoint without a paid start", async () => {
    const panel = await openPanel({ resume: true, resumeStatus: "completed" });
    await panel.uploadReview(); await panel.downloadReview();
    expect(panel.reviewRequests().map((call) => call.method)).toEqual(["POST", "GET"]);
    expect(panel.downloads()).toHaveLength(1);
    expect(panel.downloads()[0].type).toBe("application/json");
    expect(panel.retryLink()?.download).toBe("newscout-semantic-review-live-browser-quick.json");
    expect(panel.paidStartRequests()).toHaveLength(0);
  });
  it("marks a missing running job UNKNOWN, preserves last known evidence and stops automatic status reads", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    panel.failNextPoll(404); await panel.tick();
    expect(panel.summary()).toMatchObject({ active: false, error: "missing" });
    expect(panel.text()).toContain("UNKNOWN");
    expect(panel.observation().job.status).toBe("running");
    const reads = panel.statusReads(); await panel.tick(10);
    expect(panel.statusReads()).toBe(reads);
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("lets an explicit resume detail finish when an earlier poll returns during that read", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    panel.failNextPoll("defer"); await panel.tick();
    panel.failNextPoll("defer");
    const opening = panel.showExternally("live-browser-quick"); await flushPromises();
    await panel.releaseDeferredPoll(); await panel.releaseDeferredPoll();
    expect(await opening).toBe(true);
    expect(panel.observation().job.status).toBe("running");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("automatically recovers a hidden running evaluation after a transient status failure without another paid start", async () => {
    const panel = await openPanel({ workbench: true }); await panel.acknowledge(); await panel.start();
    panel.advance("partial"); await panel.tick(); panel.hide();
    panel.failNextPoll(503); await panel.tick();
    expect(panel.observation()).toMatchObject({ error: "unavailable", job: { status: "running" } });
    const failedReads = panel.statusReads();
    await panel.tick();
    expect(panel.statusReads()).toBe(failedReads + 1);
    expect(panel.observation()).toMatchObject({ error: "", job: { status: "running" } });
    panel.advance("completed"); await panel.tick();
    expect(panel.observation().job.status).toBe("completed");
    const finalReads = panel.statusReads(); await panel.tick(10);
    expect(panel.statusReads()).toBe(finalReads);
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("times out an unresponsive status GET and recovers on the bounded retry without resending a paid start", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    panel.failNextPoll("hang"); await panel.tick(); panel.advance("completed");
    await panel.tick(15);
    expect(panel.hungReadAborted()).toBe(true);
    expect(panel.observation().error).toBe("request");
    await panel.tick();
    expect(panel.observation()).toMatchObject({ error: "", job: { status: "completed" } });
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("keeps a manually refreshed terminal result when an earlier running poll arrives late", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    panel.failNextPoll("defer"); await panel.tick();
    panel.advance("completed"); await panel.refresh();
    expect(panel.observation().job.status).toBe("completed");
    await panel.releaseDeferredPoll();
    expect(panel.observation().job.status).toBe("completed");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("prepares paid settings with consent cleared and never implements a free model start", async () => {
    const panel = await openPanel({ workbench: true, resume: true, resumeStatus: "completed" });
    expect(panel.observation()).toMatchObject({ loading: false, error: "", job: { id: "live-browser-quick" } });
    expect(await panel.prepareExternally()).toBe(true); await flushPromises();
    expect(panel.displayedView()).toBe("settings");
    expect(panel.disabled()).toBe(true);
    expect(await panel.startFree("model_evaluation")).toBe(false);
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("loads the exact historical model detail then opens its full log without another paid start", async () => {
    const panel = await openPanel({ workbench: true, resume: true, resumeStatus: "completed" });
    expect(await panel.showExternally("live-browser-quick", { logs: true })).toBe(true);
    await flushPromises();
    expect(panel.fullLogOutput()).toContain("live-browser-quick");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("does not stop the active model poll when another historical record is selected", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    expect(await panel.showExternally("older-model-run", { logs: true })).toBe(false);
    expect(await panel.prepareExternally()).toBe(false); panel.hide();
    panel.advance("completed"); await panel.tick();
    expect(panel.observation().job.status).toBe("completed");
    expect(panel.calls().some((call) => call.url.endsWith("/older-model-run"))).toBe(false);
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("explains incomplete model evidence when log storage fails", async () => {
    const panel = await openPanel({ resume: true });
    panel.captureFailure("log_storage_error"); await panel.tick();
    expect(panel.text()).toContain("日誌儲存失敗，證據不完整");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("opens model event output for a historical run without another paid start", async () => {
    const panel = await openPanel({ workbench: true, resume: true, resumeStatus: "completed" });
    await panel.openHistory(); await panel.selectHistory(); await panel.fullLog();
    expect(panel.fullLogOutput()).toContain("live-browser-quick");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("reports the displayed settings, execution and evidence phase without starting a second run", async () => {
    const panel = await openPanel({ workbench: true });
    expect(panel.phase()).toBe("settings");
    expect(panel.stateTitle()).toBe("設定與開始");
    expect(panel.oldStepper()).toBe(false);
    await panel.acknowledge(); await panel.start();
    expect(panel.phase()).toBe("execution");
    expect(panel.stateTitle()).toBe("執行中");
    expect(panel.showsPendingDecision()).toBe(true);
    expect(panel.showsReleaseDecision()).toBe(false);
    panel.advance("partial"); await panel.tick();
    expect(panel.logBeforeCases()).toBe(true);
    panel.advance("completed"); await panel.tick();
    expect(panel.phase()).toBe("evidence");
    expect(panel.stateTitle()).toBe("測試結果");
    expect(panel.showsReleaseDecision()).toBe(true);
    await panel.prepare();
    expect(panel.phase()).toBe("settings");
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("opens the actual owned execution history through the sidebar action without another request", async () => {
    const panel = await openPanel({ workbench: true, resume: true, resumeStatus: "completed" });
    expect(panel.history()).toBe(null);
    const requests = panel.calls().length;
    await panel.openHistory();
    expect(panel.history()).toContain("快速檢查");
    expect(panel.history()).toContain("評測執行完成");
    expect(panel.calls()).toHaveLength(requests);
  });
  it("opens an empty history and resource limits without enabling or submitting a paid run", async () => {
    const panel = await openPanel({ workbench: true });
    await panel.openHistory();
    expect(panel.history()).toContain("尚無評測執行紀錄。");
    expect(panel.resourceInsideForm()).toBe(false);
    expect(panel.resourceExpanded()).toBe(false);
    await panel.toggleResourceLimits();
    expect(panel.resourceExpanded()).toBe(true);
    expect(panel.disabled()).toBe(true);
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  it("places one paid start beside its consent and explains the guard without a blank evidence panel", async () => {
    const panel = await openPanel({ workbench: true });
    expect(panel.startInForm()).toBe(true);
    expect(panel.startCount()).toBe(1);
    expect(panel.startReason()).toBe("勾選上方費用同意後即可開始。");
    expect(panel.compactEmpty()).toEqual({ exists: true, legacyResult: false });
    expect(panel.text()).toContain("NOT RUN");
    expect(panel.text()).toContain("這次會取得什麼");
    await panel.acknowledge();
    expect(panel.startReason()).toContain("執行將呼叫設定的模型");
    expect(panel.stateTitle()).toBe("設定與開始");
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(0);
  });
  it("reflects a lower service budget ceiling and keeps an invalid budget blocked beside the form", async () => {
    const panel = await openPanel({ workbench: true, maxBudget: 0.5 });
    expect(panel.budgetCeiling()).toBe("0.5");
    await panel.acknowledge(); await panel.budget("0.51");
    expect(panel.disabled()).toBe(true);
    expect(panel.startReason()).toBe("請輸入 USD 0.01 至 0.5 的預算。");
    await panel.start();
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(0);
  });
  it("opens observed execution after explicit start and keeps it polling when returning to locked settings", async () => {
    const panel = await openPanel({ workbench: true });
    expect(panel.displayedView()).toBe("settings");
    await panel.acknowledge(); await panel.start();
    expect(panel.displayedView()).toBe("evidence");
    await panel.settings();
    expect(panel.displayedView()).toBe("settings");
    expect(panel.settingsLocked()).toBe(true);
    panel.advance("partial"); await panel.tick();
    expect(panel.displayedView()).toBe("settings");
    expect(panel.summary().tests).toBe(1);
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("returns to task selection and clears consent for a new configuration without automatically starting another paid run", async () => {
    const panel = await openPanel({ workbench: true, resume: true, resumeStatus: "completed" });
    expect(panel.displayedView()).toBe("evidence");
    expect(panel.text()).toContain("人工語意審核待完成");
    await panel.backToWorkbench();
    expect(panel.navigation()).toEqual([["verification"]]);
    await panel.prepare();
    expect(panel.displayedView()).toBe("settings");
    expect(panel.disabled()).toBe(true);
    expect(panel.startReason()).toBe("勾選上方費用同意後即可開始。");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("places release judgment and missing verification before model cases and full logs", async () => {
    const panel = await openPanel({ workbench: true, resume: true, resumeStatus: "completed" });
    expect(panel.stateTitle()).toBe("測試結果");
    expect(panel.oldStepper()).toBe(false);
    expect(panel.resultOrder()).toEqual([true, true]);
    expect(panel.releaseBlocked()).toBe(true);
    expect(panel.text()).toContain("人工語意審核待完成");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("requires paid consent in the workbench and keeps the server-selected model read-only", async () => {
    const panel = await openPanel({ workbench: true });
    expect(panel.heading()).toBe("H1");
    expect(panel.model()).toEqual({ value: "gpt-5-mini", tag: "OUTPUT" });
    expect(panel.disabled()).toBe(true);
    expect(panel.summary()).toEqual({ status: "not_run", tests: null, active: false, available: true, error: null });
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
    await panel.acknowledge(); await panel.start();
    expect(panel.settingsLocked()).toBe(true);
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("keeps a hidden workbench updating progress without interpreting completion as semantic approval", async () => {
    const panel = await openPanel({ workbench: true }); await panel.acknowledge(); await panel.start(); panel.hide();
    panel.advance("partial"); await panel.tick();
    expect(panel.summary()).toEqual({ status: "running", tests: 1, active: true, available: true, error: null });
    panel.advance("completed"); await panel.tick();
    expect(panel.summary()).toEqual({ status: "completed", tests: 8, active: false, available: true, error: null });
    expect(panel.text()).toContain("人工語意審核待完成 · 模型品質尚未判定");
    expect(panel.text()).toContain("7 PASS · 1 FAIL");
    expect(panel.text()).not.toContain("品質通過");
    expect(panel.settingsLocked()).toBe(false);
    expect(panel.disabled()).toBe(true);
  });
  it("exports a hidden service failure with the last observed progress until a successful manual refresh", async () => {
    const panel = await openPanel({ workbench: true }); await panel.acknowledge(); await panel.start(); panel.advance("partial"); await panel.tick(); panel.hide();
    panel.failNextPoll(503); await panel.tick();
    expect(panel.summary()).toEqual({ status: "running", tests: 1, active: true, available: true, error: "unavailable" });
    await panel.refresh();
    expect(panel.summary()).toEqual({ status: "running", tests: 1, active: true, available: true, error: null });
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("only reads capabilities on mount and requires explicit cost acknowledgement", async () => {
    const panel = await openPanel();
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
    expect(panel.disabled()).toBe(true);
    expect(panel.text()).toContain("合成檢索資料");
    expect(panel.text()).toContain("並非供應商帳單的硬性上限");
    await panel.acknowledge(); expect(panel.disabled()).toBe(false);
    expect(panel.calls().filter((call) => call.method === "POST")).toEqual([]);
  });
  it("enforces budget limits before submitting only a fixed profile and acknowledged budget", async () => {
    const panel = await openPanel(); await panel.acknowledge();
    for (const invalid of ["0", "0.001", "5.01", ""]) { await panel.budget(invalid); expect(panel.disabled()).toBe(true); }
    await panel.budget("0.25"); await panel.profile("holdout"); await panel.start();
    expect(panel.calls().filter((call) => call.method === "POST").map((call) => call.body)).toEqual([{ profile: "holdout", max_usd: 0.25, acknowledge_cost: true }]);
    expect(panel.progress()).toEqual({ value: 0, max: 15 });
    expect(panel.disabled()).toBe(true);
  });
  it("labels explicit server-configured rates without presenting them as a verification date", async () => {
    const panel = await openPanel({ configuredPricing: true });
    expect(panel.text()).toContain("伺服器設定費率");
    expect(panel.text()).not.toContain("server_configuration");
    expect(panel.text()).not.toContain("費率核對日期");
    await panel.acknowledge(); expect(panel.disabled()).toBe(false);
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("shows observed model/tool progress, measured usage, and mixed structural results without a semantic pass", async () => {
    const panel = await openPanel(); await panel.acknowledge(); await panel.start();
    panel.advance("tool"); await panel.tick();
    expect(panel.text()).toContain("工具 RUNNING · fixture-case-1 · search_news");
    panel.advance("partial"); await panel.tick();
    expect(panel.progress()).toEqual({ value: 1, max: 8 });
    expect(panel.text()).toContain("輸入 1,200 · 輸出 300");
    panel.advance("completed"); await panel.tick();
    expect(panel.progress()).toEqual({ value: 8, max: 8 });
    expect(panel.text()).toContain("評測執行完成");
    expect(panel.text()).toContain("7 PASS · 1 FAIL");
    expect(panel.text()).toContain("人工語意審核待完成 · 模型品質尚未判定");
    expect(panel.text()).toContain("Fixture: required source reference missing");
    expect(panel.text()).not.toContain("離線回歸 PASS");
    expect(panel.text()).not.toContain("品質通過");
  });
  it("resumes an owned active run by GET without another paid start", async () => {
    const panel = await openPanel({ resume: true });
    expect(panel.progress()).toEqual({ value: 1, max: 8 });
    expect(panel.calls().map((call) => call.method)).toEqual(["GET", "GET"]);
    await panel.tick(); expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("keeps model rule violations visible when a legal report has many long failures", async () => {
    const panel = await openPanel({ resume: true, manyFailures: true });
    expect(panel.progress()).toEqual({ value: 1, max: 8 });
    expect(panel.text()).toContain("0 PASS · 1 FAIL");
    expect(panel.text()).toContain("Fixture tool violation 32");
    expect(panel.text()).toContain("x".repeat(2049));
    expect(panel.text()).not.toContain("無法讀取評測狀態或報告");
  });
  it("preserves completed evidence after cancellation and stops job polling", async () => {
    const panel = await openPanel(); await panel.acknowledge(); await panel.start();
    panel.advance("partial"); await panel.tick(); await panel.cancel();
    expect(panel.text()).toContain("評測已取消");
    expect(panel.progress()).toEqual({ value: 1, max: 8 });
    expect(panel.text()).toContain("[OFFLINE BROWSER FIXTURE]");
    const requests = panel.calls().length; await panel.tick(); expect(panel.calls()).toHaveLength(requests);
  });
  it("downloads the owned report through the authenticated API before creating a local blob link", async () => {
    const panel = await openPanel({ resume: true }); await panel.download();
    expect(panel.calls().at(-1).url).toBe("/qa/api/qa/evaluations/live-browser-quick/report");
    expect(panel.calls().at(-1).method).toBe("GET");
    expect(panel.downloads()).toHaveLength(1);
    expect(panel.downloads()[0].type).toBe("application/json");
    expect(panel.retryLink()).toEqual({ href: "blob:offline-fixture-1", download: "newscout-live-evaluation-live-browser-quick.json", tag: "A" });
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });
  it("keeps one retryable report URL and revokes it when replaced or the panel closes", async () => {
    const panel = await openPanel({ resume: true });
    await panel.download(); await panel.download();
    expect(URL.revokeObjectURL.mock.calls).toEqual([["blob:offline-fixture-1"]]);
    expect(panel.retryLink().href).toBe("blob:offline-fixture-2");
    panel.close();
    expect(URL.revokeObjectURL.mock.calls).toEqual([["blob:offline-fixture-1"], ["blob:offline-fixture-2"]]);
  });
  it("removes the previous report link as soon as a different evaluation is selected", async () => {
    const panel = await openPanel({ resume: true });
    await panel.cancel(); await panel.download();
    await panel.profile("dev"); await panel.acknowledge(); await panel.start();
    expect(panel.retryLink()).toBe(null);
    expect(URL.revokeObjectURL.mock.calls).toEqual([["blob:offline-fixture-1"]]);
  });
  for (const [status, message] of [[404, "找不到這次評測"], [503, "真 LLM 評測服務尚未就緒"], [500, "無法讀取評測狀態或報告"]]) {
    it("keeps report HTTP " + status + " visible without downloading an error body and permits retry", async () => {
      const panel = await openPanel({ resume: true });
      panel.failNextReport(status); await panel.download();
      expect(panel.text()).toContain(message);
      expect(panel.downloads()).toHaveLength(0);
      expect(URL.createObjectURL).not.toHaveBeenCalled();
      expect(panel.retryLink()).toBe(null);
      expect(panel.reportDisabled()).toBe(false);
      await panel.download();
      expect(panel.downloads()).toHaveLength(1);
      expect(panel.summary().error).toBe(null);
    });
  }
  it("clears a previously retained report if a fresh report request fails", async () => {
    const panel = await openPanel({ resume: true }); await panel.download();
    panel.failNextReport(500); await panel.download();
    expect(panel.retryLink()).toBe(null);
    expect(panel.downloads()).toHaveLength(1);
    expect(URL.revokeObjectURL.mock.calls).toEqual([["blob:offline-fixture-1"]]);
  });
  for (const [status, message] of [[409, "目前已有真 LLM 評測執行中"], [429, "請等候冷卻時間"], [503, "真 LLM 評測服務尚未就緒"]]) {
    it("reports start rejection " + status + " without fabricated execution results", async () => {
      const panel = await openPanel({ rejection: status }); await panel.acknowledge(); await panel.start();
      expect(panel.text()).toContain(message); expect(panel.progress()).toBe(null);
      if (status === 429) expect(panel.disabled()).toBe(true);
    });
  }
  it("keeps unavailable, malformed and busy capabilities from enabling paid starts", async () => {
    for (const options of [{ available: false }, { busy: true }, { malformed: true }]) {
      const panel = await openPanel(options); await panel.acknowledge();
      expect(panel.disabled()).toBe(true); expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
      panel.close();
    }
  });
  it("rejects a response that invents semantic success", async () => {
    const panel = await openPanel(); await panel.acknowledge(); await panel.start();
    panel.advance("completed"); panel.corruptQuality(); await panel.tick();
    expect(panel.text()).toContain("無法讀取評測狀態或報告");
    expect(panel.text()).not.toContain("評測執行完成");
  });
  it("aborts in-flight requests and timers when the protected component unmounts", async () => {
    const panel = await openPanel(); await panel.acknowledge(); await panel.start(); panel.close(); await panel.tick();
    expect(panel.calls().every((call) => call.signal.aborted)).toBe(true);
    expect(panel.calls()).toHaveLength(2);
  });
});
