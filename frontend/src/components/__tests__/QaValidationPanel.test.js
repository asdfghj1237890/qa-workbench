// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createI18n } from "vue-i18n";
import { Quasar } from "quasar";
import QaValidationPanel from "../QaValidationPanel.vue";
import zhTW from "../../i18n/zh-TW.json";
import en from "../../i18n/en.json";
import fixtures from "../../../e2e/observatory-validation-physical.cjs";

const transport = vi.hoisted(() => ({ fetch: null, sitekey: "" }));
vi.mock("../../lib/runtime.js", async original => { const actual = await original(); return ({ ...actual, get QA_EVIDENCE() { return actual.QA_EVIDENCE; }, get QA_REPOSITORY() { return actual.QA_REPOSITORY; }, get WORKBENCH_TASKS() { return actual.WORKBENCH_TASKS; },  AGENT: "/qa/api", get TS_SITEKEY() { return transport.sitekey; }  }); });
vi.mock("../../lib/qaSession.js", () => ({ apiFetch: (...args) => transport.fetch(...args) }));
const mounted = [];

// Contract: app/qa_validation.py owner-scoped API and app/qa_runner.py JUnit observations.
// Local mount/transport factory owns the physical fixture; tests express UI journeys.
async function openPanel({ enabled = true, busy = false, denied = false, workbench = false, resume = false, resumeMode = "offline_regression", realAvailable = true, turnstileRequired = false, sitekey = "", proof = "fixture-proof", requestedMode = "", missingPricing = false, stepName = "Retrieval contracts" } = {}) {
  const calls = [], downloads = [], challenges = [];
  transport.sitekey = sitekey;
  let widgetCallback;
  vi.stubGlobal("turnstile", { render: vi.fn((_element, options) => { challenges.push(options.sitekey); widgetCallback = options.callback; if (proof) widgetCallback(proof); return "fixture-widget"; }), reset: vi.fn(() => { if (proof) widgetCallback(proof); }), remove: vi.fn() });
  vi.stubGlobal("URL", { createObjectURL: vi.fn((blob) => { downloads.push(blob); return "blob:validation-fixture-" + downloads.length; }), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const step = { name: stepName, suite: "rag", status: "completed", exit_code: 0,
    tests: 11, failed: 0, errors: 0, skipped: 2, duration_seconds: 1, log: "9 passed, 2 skipped", log_truncated: false };
  const metadata = { mode: "offline_regression", semantic_status: "pending", quality_passed: null, covered: [], gaps: [], report_available: false };
  let run = resume ? { ...metadata, id: "owned-run", suite: "rag", status: "completed", started_at: null, finished_at: null, total_steps: 1, steps: [{ ...step }] } : null;
  if (resume && resumeMode !== "offline_regression") {
    const completed = fixtures.jobBody("all", "completed", resumeMode);
    run = { ...completed, total_steps: 1, steps: [{ ...completed.steps[0], name: stepName }] };
  }
  let nextPollFailure = null, nextRefreshFailure = null, deferredReply = null, loseStartReply = false;
  transport.fetch = vi.fn(async (url, init = {}) => {
    calls.push({ url, method: init.method || "GET", body: init.body, signal: init.signal });
    if (url.includes("/logs")) {
      const query = new URLSearchParams(url.split("?")[1]), scope = query.get("step");
      const text = "Captured output for " + run.id + (scope ? " / " + scope : " / entire run");
      const total = new TextEncoder().encode(text).length, offset = Number(query.get("offset"));
      if (url.includes("/logs/download")) return { ok: true, blob: async () => new Blob([text], { type: "text/plain" }) };
      return { ok: true, json: async () => ({ text: offset ? "" : text, next_offset: total, total_bytes: total, has_more: false, complete: !["queued", "running"].includes(run.status), truncated: false, legacy: false }) };
    }
    if (url.endsWith("/report")) return { ok: true, blob: async () => new Blob([JSON.stringify({ job_id: run.id, mode: run.mode, quality_passed: null, semantic_status: "pending", steps: run.steps })], { type: "application/json" }) };
    if (init.method === "POST" && !url.endsWith("/cancel")) {
      if (denied) return { ok: false, status: 409, headers: new Headers() };
      const payload = JSON.parse(init.body);
      run = payload.mode !== "offline_regression" ? fixtures.jobBody(payload.suite, "queued", payload.mode)
        : { ...metadata, id: "owned-run", suite: payload.suite, status: "queued", started_at: null,
        finished_at: null, total_steps: 1, steps: [] };
      if (loseStartReply) { loseStartReply = false; throw new Error("reply_lost_after_acceptance"); }
      return { ok: true, json: async () => ({ job: structuredClone(run) }) };
    }
    if (url.endsWith("/cancel")) { run.status = "cancelled"; return { ok: true, json: async () => ({ job: structuredClone(run) }) }; }
    if (run && url.endsWith("/" + run.id)) {
      if (nextPollFailure) {
        const status = nextPollFailure; nextPollFailure = null;
        if (status === "defer") { const body = { job: structuredClone(run) }; await new Promise((resolve) => { deferredReply = resolve; }); return { ok: true, json: async () => body }; }
        if (status === "hang") return new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("Cancelled", "AbortError")), { once: true }));
        if (status === "schema") return { ok: true, json: async () => ({ job: { ...structuredClone(run), status: "completed", steps: [] } }) };
        return { ok: false, status, headers: new Headers() };
      }
      return { ok: true, json: async () => ({ job: structuredClone(run) }) };
    }
    const capabilities = fixtures.capabilitiesBody({ available: enabled, realAvailable, turnstileRequired, job: run ? structuredClone(run) : null,
      busy: busy || ["queued", "running"].includes(run?.status) });
    if (missingPricing) Object.assign(capabilities.modes.find((entry) => entry.id === "real_es_llm_e2e"), { available: false, reason: "complete_chain_pricing_required", pricing: null });
    if (nextRefreshFailure) {
      const status = nextRefreshFailure; nextRefreshFailure = null;
      if (status === "defer") { await new Promise((resolve) => { deferredReply = resolve; }); return { ok: true, json: async () => capabilities }; }
      return { ok: false, status, headers: new Headers() };
    }
    return { ok: true, json: async () => capabilities };
  });
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: "zh-TW", messages: { "zh-TW": zhTW, en } });
  const wrapper = mount(QaValidationPanel, { props: { workbench, requestedMode }, global: { plugins: [i18n, Quasar] } });
  mounted.push(wrapper); await flushPromises();
  return {
    text: () => wrapper.text(), calls: () => calls,
    challenges: () => challenges, downloads: () => downloads,
    heading: () => wrapper.get("#qa-testing-title").element.tagName,
    stateTitle: () => wrapper.get("#qa-testing-title").text(),
    summary: () => wrapper.emitted("status-change")?.at(-1)?.[0],
    observation: () => wrapper.emitted("observation-change")?.at(-1)?.[0],
    prepareExternally: (mode) => wrapper.vm.prepareRun(mode),
    startFree: (mode) => wrapper.vm.startFree(mode),
    showExternally: (id, options) => wrapper.vm.showJob(id, options),
    openLogsExternally: () => wrapper.vm.openLogs(),
    modeChanges: () => wrapper.emitted("mode-change")?.map(([value]) => value) || [],
    navigations: () => wrapper.emitted("navigate")?.map(([value]) => value) || [],
    startControls: () => wrapper.findAll('[data-testid="qa-run-all"]').length,
    outcomes: () => wrapper.findAll(".qa-guided-outcomes > div").map((entry) => entry.text()),
    stepTitles: () => wrapper.findAll(".qa-guided-step-row > th").map((entry) => entry.text()),
    stepEvidenceNames: () => wrapper.findAll(".qa-guided-step-details .qa-guided-raw-step code").map((entry) => entry.text()),
    technicalDetailsOpen: () => wrapper.get(".qa-evidence-technical").element.open,
    phase: () => wrapper.get(".qa-guided-form").attributes("style")?.includes("display: none") ? "evidence" : "settings",
    hide() { wrapper.element.style.display = "none"; },
    failNextPoll(status) { nextPollFailure = status; },
    captureFailure(reason) { run.status = "failed"; run.error = reason; },
    failNextRefresh(status) { nextRefreshFailure = status; },
    loseStartReply() { loseStartReply = true; },
    async releaseDeferredRead() { deferredReply(); deferredReply = null; await flushPromises(); },
    forgetRun() { run = null; },
    progress: () => { const progress = wrapper.find("progress"); const metadata = wrapper.find(".qa-faithful-run-metadata"); return progress.exists() ? { value: progress.element.value, max: progress.element.max } : { value: Number(metadata.attributes("data-completed")), max: Number(metadata.attributes("data-total")) }; },
    resultHeading: () => wrapper.get(".qa-faithful-result-title").text(),
    executionStatus: () => wrapper.get('[data-testid="qa-validation-execution-status"] strong').text(),
    workflowStrips: () => wrapper.findAll(".qa-flow-steps").length,
    resultOrder: () => { const result = wrapper.get('[data-testid="qa-validation-result"]').element; return [...result.children].map((element) => element.dataset.testid || element.className); },
    evidenceHeaders: () => wrapper.findAll(".qa-faithful-evidence-table thead th").map((entry) => entry.text()),
    completedProgressBars: () => wrapper.findAll("progress").length,
    resultWorkspaceTabs: () => wrapper.findAll(".qa-guided-tabs").length,
    phases: () => wrapper.emitted("phase-change")?.map(([value]) => value) || [],
    logExpanded: () => wrapper.get(".qa-faithful-log-button").attributes("aria-expanded"),
    async toggleLog() { await wrapper.get(".qa-faithful-log-button").trigger("click"); },
    async fullLog() { await wrapper.get('[data-testid="qa-full-log-open"]').trigger("click"); await flushPromises(); },
    async fullStepLog() { await wrapper.get(".qa-faithful-log-button").trigger("click"); await wrapper.get('[data-testid="qa-step-full-log"]').trigger("click"); await flushPromises(); },
    fullLogOutput: () => wrapper.get('[data-testid="qa-full-log-output"]').text(),
    logRequests: () => calls.filter((call) => call.url.includes("/logs")).map((call) => ({ step: new URLSearchParams(call.url.split("?")[1]).get("step"), offset: Number(new URLSearchParams(call.url.split("?")[1]).get("offset")) })),
    async history() { await wrapper.vm.showHistory(); },
    async selectHistory() { await wrapper.find(".qa-validation-history button").trigger("click"); await flushPromises(); },
    historyOpen: () => wrapper.get(".qa-guided-history").element.open,
    historyVisible: () => wrapper.get(".qa-guided-history").isVisible(),
    historyText: () => wrapper.get(".qa-guided-history").text(),
    resultBusy: () => wrapper.get('[data-testid="qa-validation-result"]').attributes("aria-busy"),
    disabled: () => wrapper.get('[data-testid="qa-run-all"]').attributes("disabled") !== undefined,
    async runAll() { await wrapper.get(workbench ? ".qa-guided-form" : '[data-testid="qa-run-all"]').trigger(workbench ? "submit" : "click"); await flushPromises(); },
    async doubleStart() { if (workbench) await Promise.all([wrapper.get(".qa-guided-form").trigger("submit"), wrapper.get(".qa-guided-form").trigger("submit")]); else { const button = wrapper.get('[data-testid="qa-run-all"]').element; button.click(); button.click(); } await flushPromises(); },
    async runRag() { await wrapper.get('[data-testid="qa-run-rag"]').trigger("click"); await flushPromises(); },
    async mode(value) { if (workbench) await wrapper.setProps({ requestedMode: value }); else await wrapper.get('[data-mode="' + value + '"]').trigger("click"); await flushPromises(); },
    async scope(value) { await wrapper.get('[data-testid="qa-validation-suite"]').setValue(value); await flushPromises(); },
    async settings() { await wrapper.get('[data-testid="qa-validation-settings"]').trigger("click"); await flushPromises(); },
    async latest() { const latest = wrapper.find('[data-testid="qa-validation-latest"]'); if (latest.exists()) await latest.trigger("click"); await flushPromises(); },
    async workbench() { await wrapper.get('[data-testid="qa-validation-workbench"]').trigger("click"); await flushPromises(); },
    async budget(value) { await wrapper.get('[data-testid="qa-validation-budget"]').setValue(value); await flushPromises(); },
    async acknowledge() { await wrapper.get('[data-testid="qa-validation-ack"]').setValue(true); await flushPromises(); },
    async download() { await wrapper.get('[data-testid="qa-validation-report"]').trigger("click"); await flushPromises(); },
    async expireSecurity() { await vi.advanceTimersByTimeAsync(8100); await flushPromises(); },
    async cancel() { await wrapper.get('[data-testid="qa-cancel-validation"]').trigger("click"); await flushPromises(); },
    async doubleCancel() { const button = wrapper.get('[data-testid="qa-cancel-validation"]').element; button.click(); button.click(); await flushPromises(); },
    async refresh() { await wrapper.findAll("button").find((button) => button.text() === zhTW.qaValidation.refresh).trigger("click"); await flushPromises(); },
    finish(failed = false) { if (run.mode !== "offline_regression") { run = fixtures.jobBody("all", failed ? "failed" : "completed", run.mode); return; } run.status = failed ? "failed" : "completed"; run.steps = [{ ...step, status: run.status, failed: failed ? 1 : 0, exit_code: failed ? 1 : 0 }]; },
    running() { run.status = "running"; run.steps = [{ ...step, status: "running", tests: null, failed: null, errors: null, skipped: null }]; },
    planned(status = "queued") { run = { ...fixtures.jobBody("all", status), id: run.id }; },
    cancelledPlan() { run = { ...fixtures.jobBody("all", "queued"), id: run.id, status: "cancelled" }; run.steps = run.steps.map((step) => ({ ...step, status: "cancelled" })); },
    liveProgress(progress) { run.status = "running"; run.steps[0].status = "running"; run.steps[0].progress = progress; },
    async tick() { await vi.advanceTimersByTimeAsync(1000); await flushPromises(); },
    close() { mounted.splice(mounted.indexOf(wrapper), 1); wrapper.unmount(); },
  };
}

beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] }));
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("manual QA validation", () => {
  it("exposes complete public observation and configures the same mode again without starting work", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    expect(panel.observation()).toMatchObject({ loading: false, error: "", job: { id: "owned-run" }, capabilities: { recent: [{ id: "owned-run" }] } });
    expect(await panel.prepareExternally("offline_regression")).toBe(true);
    await flushPromises(); expect(panel.phase()).toBe("settings");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("starts a full free suite once and refuses paid or duplicate bridge starts", async () => {
    const panel = await openPanel({ workbench: true });
    expect(await panel.startFree("real_es_llm_e2e")).toBe(false);
    await Promise.all([panel.startFree("es_integration"), panel.startFree("es_integration")]);
    await flushPromises();
    expect(panel.calls().filter((call) => call.method === "POST").map((call) => JSON.parse(call.body))).toEqual([{ mode: "es_integration", suite: "all" }]);
    expect(panel.observation().job).toMatchObject({ mode: "es_integration", suite: "all" });
  });
  it("opens an owned historical detail with GET before opening that run's complete log", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    expect(await panel.showExternally("owned-run", { logs: true })).toBe(true);
    await flushPromises();
    expect(panel.calls().some((call) => call.url.endsWith("/owned-run") && call.method === "GET")).toBe(true);
    expect(panel.fullLogOutput()).toContain("owned-run / entire run");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("refuses replacing an active run with history and retains its polling across hidden screens", async () => {
    const panel = await openPanel({ workbench: true });
    await panel.startFree("offline_regression"); panel.hide();
    expect(await panel.showExternally("another-history")).toBe(false);
    expect(await panel.prepareExternally("es_integration")).toBe(false);
    panel.running(); await panel.tick();
    expect(panel.observation().job).toMatchObject({ id: "owned-run", status: "running" });
    expect(panel.calls().some((call) => call.url.endsWith("/another-history"))).toBe(false);
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("explains log retention failure even when every measured test passed", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    await panel.settings(); panel.captureFailure("log_size_limit"); await panel.refresh(); await panel.latest();
    expect(panel.text()).toContain("執行輸出超過保存上限，證據不完整");
    expect(panel.outcomes()).toEqual(["9PASS", "0FAIL", "0ERROR", "2SKIP"]);
  });
  it("opens complete output for a selected history record without starting another run", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    expect(panel.logRequests()).toEqual([]);
    await panel.history(); await panel.selectHistory(); await panel.fullLog();
    expect(panel.fullLogOutput()).toContain("owned-run / entire run");
    expect(panel.logRequests()).toEqual([{ step: null, offset: 0 }]);
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("opens a single step log from the summary without downloading or rerunning tests", async () => {
    const panel = await openPanel({ workbench: true, resume: true, stepName: "retrieval" });
    await panel.fullStepLog();
    expect(panel.fullLogOutput()).toContain("owned-run / retrieval");
    expect(panel.text()).toContain("最近輸出（摘要）");
    expect(panel.logRequests()).toEqual([{ step: "retrieval", offset: 0 }]);
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("opens a visible empty history without starting a validation", async () => {
    const panel = await openPanel({ workbench: true });
    await panel.history();
    expect(panel.historyOpen()).toBe(true);
    expect(panel.historyVisible()).toBe(true);
    expect(panel.historyText()).toContain("尚未產生執行紀錄");
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  it("presents completed regression evidence as a five-column report with only observed counters", async () => {
    const panel = await openPanel({ workbench: true, resume: true, stepName: "retrieval" });
    expect(panel.resultHeading()).toBe("測試結果");
    expect(panel.evidenceHeaders()).toEqual(["#", "檢查了什麼", "結果", "測試數", "詳細說明"]);
    expect(panel.outcomes()).toEqual(["9PASS", "0FAIL", "0ERROR", "2SKIP"]);
    expect(panel.completedProgressBars()).toBe(0);
    expect(panel.resultWorkspaceTabs()).toBe(0);
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  it("explains a fixed conversation storage check without promoting it to a model-quality result", async () => {
    const panel = await openPanel({ workbench: true, requestedMode: "es_integration", resume: true, resumeMode: "es_integration", stepName: "seeded_two_turn_storage_api" });
    expect(panel.stepTitles()).toEqual(["固定對話的儲存與讀回"]);
    await panel.toggleLog();
    expect(panel.text()).toContain("這是儲存測試，不會呼叫模型產生答案");
    expect(panel.text()).toContain("模型答案品質仍需另外審核");
    expect(panel.technicalDetailsOpen()).toBe(false);
    expect(panel.stepEvidenceNames()).toEqual(["seeded_two_turn_storage_api"]);
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("opens rerun settings and exposes history without starting another execution", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    expect(panel.phases()).toEqual(["settings", "evidence"]);
    await panel.toggleLog(); expect(panel.logExpanded()).toBe("true");
    expect(panel.stepEvidenceNames()).toEqual(["Retrieval contracts"]);
    expect(panel.text()).toContain("9 passed, 2 skipped");
    await panel.history(); expect(panel.historyOpen()).toBe(true);
    await panel.settings(); expect(panel.phase()).toBe("settings");
    expect(panel.phases()).toEqual(["settings", "evidence", "settings"]);
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  for (const { stepName, expected } of [
    { stepName: "retrieval", expected: "檢索與回答" },
    { stepName: "[OFFLINE FIXTURE] retrieval", expected: "檢索與回答" },
    { stepName: "[OFFLINE FIXTURE] custom-retriever", expected: "[OFFLINE FIXTURE] custom-retriever" },
  ]) it(`presents ${stepName} with an exact known title and preserves its original evidence name`, async () => {
    const panel = await openPanel({ workbench: true, resume: true, stepName });
    expect(panel.stepTitles()).toEqual([expected]);
    expect(panel.stepEvidenceNames()).toEqual([stepName]);
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  it("keeps a requested task queued during a status refresh instead of reverting the navigation", async () => {
    const panel = await openPanel({ workbench: true });
    panel.failNextRefresh("defer"); await panel.refresh();
    await panel.mode("es_integration");
    expect(panel.modeChanges()).toEqual(["offline_regression"]);
    await panel.releaseDeferredRead();
    expect(panel.summary().mode).toBe("es_integration");
    expect(panel.modeChanges().at(-1)).toBe("es_integration");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("does not turn cancelled unexecuted steps into completed progress", async () => {
    const panel = await openPanel({ workbench: true });
    await panel.runAll(); panel.planned(); await panel.tick();
    panel.cancelledPlan(); await panel.tick();
    expect(panel.progress().value).toBe(0);
    expect(panel.progress().max).toBeGreaterThan(0);
    expect(panel.outcomes()).toEqual([]);
    expect(panel.text()).not.toContain("100%");
  });
  it("honors an initial task deep link without emitting a default offline selection or starting it", async () => {
    const panel = await openPanel({ workbench: true, requestedMode: "es_integration" });
    expect(panel.modeChanges()).toEqual(["es_integration"]);
    expect(panel.summary().mode).toBe("es_integration");
    expect(panel.phase()).toBe("settings");
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  it("runs only the chosen scope through the single workspace start control", async () => {
    const panel = await openPanel({ workbench: true }); await panel.scope("rag");
    expect(panel.startControls()).toBe(1);
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
    await panel.runAll(); panel.finish(true); await panel.tick();
    expect(JSON.parse(panel.calls().find((call) => call.method === "POST").body)).toEqual({ mode: "offline_regression", suite: "rag" });
    expect(panel.outcomes()).toEqual(["8PASS", "1FAIL", "0ERROR", "2SKIP"]);
    expect(panel.phase()).toBe("evidence");
    expect(panel.text()).not.toContain("整批狀態");
  });
  it("returns to task selection after reviewing results instead of forcing a next validation", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    await panel.latest(); expect(panel.phase()).toBe("evidence");
    await panel.settings(); expect(panel.phase()).toBe("settings");
    await panel.latest(); await panel.workbench();
    expect(panel.navigations()).toEqual(["verification"]);
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  it("shows actual setup, execution and results without a decorative progress strip", async () => {
    const panel = await openPanel({ workbench: true });
    expect(panel.text()).toContain("設定與開始");
    expect(panel.stateTitle()).toBe("設定與開始");
    expect(panel.workflowStrips()).toBe(0);
    await panel.runAll();
    expect(panel.resultHeading()).toBe("執行中");
    expect(panel.executionStatus()).toBe("QUEUED");
    expect(panel.text()).toContain("執行操作");
    expect(panel.text()).not.toContain(zhTW.qaRunFlow.selectMissing);
    expect(panel.workflowStrips()).toBe(0);
    panel.finish(); await panel.tick();
    expect(panel.resultHeading()).toBe("測試結果");
    expect(panel.executionStatus()).toBe("COMPLETED");
    expect(panel.workflowStrips()).toBe(0);
    const order = panel.resultOrder();
    expect(order.indexOf("qa-release-decision")).toBeGreaterThan(-1);
    expect(order.indexOf("qa-release-decision")).toBeLessThan(order.indexOf("qa-guided-evidence-title"));
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("keeps the opened full log available when execution becomes a result", async () => {
    const panel = await openPanel({ workbench: true });
    await panel.runAll(); panel.running(); await panel.tick();
    await panel.fullLog();
    expect(panel.fullLogOutput()).toContain("Captured output for owned-run");
    panel.finish(); await panel.tick();
    expect(panel.resultHeading()).toBe("測試結果");
    expect(panel.fullLogOutput()).toContain("Captured output for owned-run");
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("rejects an externally requested task switch while an existing run is active", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); await panel.mode("es_integration");
    expect(panel.modeChanges().at(-1)).toBe("offline_regression");
    expect(panel.summary().mode).toBe("offline_regression");
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("explains missing full-chain pricing and keeps execution blocked after consent and budget edits", async () => {
    const panel = await openPanel({ workbench: true, requestedMode: "real_es_llm_e2e", missingPricing: true });
    await panel.budget(1); await panel.acknowledge(); await panel.runAll();
    expect(panel.disabled()).toBe(true);
    expect(panel.text()).toContain("完整鏈路費率尚未設定");
    expect(panel.text()).toContain("complete_chain_pricing_required");
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  it("loads the server default budget for an initial paid task and still requires consent", async () => {
    const panel = await openPanel({ workbench: true, requestedMode: "real_es_llm_e2e" });
    expect(panel.disabled()).toBe(true);
    await panel.acknowledge(); await panel.runAll();
    expect(JSON.parse(panel.calls().find((call) => call.method === "POST").body)).toEqual({ mode: "real_es_llm_e2e", suite: "all", max_usd: 1, acknowledge_cost: true });
  });
  for (const operation of ["poll", "refresh"]) it(`does not let a delayed ${operation} revert a cancellation to running`, async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.running(); await panel.tick();
    if (operation === "poll") { panel.failNextPoll("defer"); await panel.tick(); }
    else { panel.failNextRefresh("defer"); await panel.refresh(); }
    await panel.cancel();
    expect(panel.text()).toContain("已取消");
    await panel.releaseDeferredRead();
    expect(panel.resultBusy()).toBe("false");
    expect(panel.summary().status).toBe("cancelled");
    expect(panel.disabled()).toBe(false);
    const calls = panel.calls().length; await panel.tick(); await panel.tick();
    expect(panel.calls()).toHaveLength(calls);
  });
  it("recovers an accepted start with a lost response by reading capabilities without repeating the POST", async () => {
    const panel = await openPanel({ workbench: true }); panel.loseStartReply(); await panel.runAll();
    expect(panel.text()).toContain("無法讀取驗證狀態");
    await panel.tick(); await panel.tick();
    expect(panel.text()).toContain("已排隊");
    expect(panel.disabled()).toBe(true);
    panel.finish(); await panel.tick();
    expect(panel.text()).toContain("離線回歸 PASS");
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("shows the complete pending plan and measured pytest progress without treating collection as a result", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.planned(); await panel.tick();
    expect(panel.progress()).toEqual({ value: 0, max: 7 });
    expect(panel.text().match(/NOT RUN；沒有測試結果/g)).toHaveLength(7);
    panel.liveProgress({ phase: "collecting", collected: null, completed: 0, passed: 0, failed: 0, errors: 0, skipped: 0, current_test: null }); await panel.tick();
    expect(panel.text()).toContain("正在收集測試");
    expect(panel.text()).not.toContain("測試進度 0／0");
    panel.liveProgress({ phase: "running", collected: 11, completed: 3, passed: 2, failed: 0, errors: 0, skipped: 1, current_test: "tests/test_fixture.py::test_current_fixture" }); await panel.tick();
    expect(panel.text()).toContain("測試進度 3／11");
    expect(panel.text()).toContain("目前測試：tests/test_fixture.py::test_current_fixture");
    expect(panel.text()).toContain("已觀測：PASS 2 · FAIL 0 · ERROR 0 · SKIP 1");
    expect(panel.text()).toContain("尚未取得測試報告");
    expect(panel.progress()).toEqual({ value: 0, max: 7 });
    panel.liveProgress({ phase: "finished", collected: 0, completed: 0, passed: 0, failed: 0, errors: 0, skipped: 0, collection_errors: 1, current_test: null }); await panel.tick();
    expect(panel.text()).toContain("測試收集錯誤：1");
    expect(panel.text()).not.toContain("離線回歸 PASS");
    panel.planned("failed"); await panel.tick();
    expect(panel.text()).toContain("回歸 FAIL");
    expect(panel.progress()).toEqual({ value: 1, max: 7 });
    expect(panel.text().match(/NOT RUN；沒有測試結果/g)).toHaveLength(6);
    expect(panel.disabled()).toBe(false);
  });
  it("bounds a stuck status read, preserves the unknown outcome and resumes polling", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.running(); await panel.tick();
    panel.failNextPoll("hang"); await panel.tick();
    for (let second = 0; second < 15; second++) await panel.tick();
    expect(panel.text()).toContain("進度更新中斷");
    expect(panel.text()).toContain("尚未確認執行結果");
    expect(panel.resultBusy()).toBe("false");
    panel.finish(); await panel.tick();
    expect(panel.text()).toContain("離線回歸 PASS");
    expect(panel.disabled()).toBe(false);
  });
  it("rejects a malformed terminal response without inventing a pass and recovers on the next valid poll", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.running(); await panel.tick();
    panel.failNextPoll("schema"); await panel.tick();
    expect(panel.text()).toContain("進度更新中斷");
    expect(panel.text()).not.toContain("離線回歸 PASS");
    panel.finish(true); await panel.tick();
    expect(panel.text()).toContain("回歸 FAIL");
    expect(panel.disabled()).toBe(false);
  });
  it("preserves the unknown result after a service restart without locking a confirmed idle service", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.running(); await panel.tick();
    panel.forgetRun(); await panel.refresh();
    expect(panel.text()).toContain("執行結果未知");
    expect(panel.text()).not.toContain("離線回歸 PASS");
    expect(panel.resultBusy()).toBe("false");
    expect(panel.disabled()).toBe(false);
    const calls = panel.calls().length; await panel.tick(); await panel.tick();
    expect(panel.calls()).toHaveLength(calls);
    await panel.runAll();
    expect(panel.text()).toContain("已排隊");
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(2);
  });
  it("recovers polling after a transient error and displays the observed terminal result", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.running(); await panel.tick();
    panel.failNextPoll(503); await panel.tick();
    expect(panel.text()).toContain("進度更新中斷");
    expect(panel.resultBusy()).toBe("false");
    panel.finish(); await panel.tick();
    expect(panel.text()).toContain("離線回歸 PASS");
    expect(panel.text()).not.toContain("進度更新中斷");
    expect(panel.disabled()).toBe(false);
    expect(panel.summary().active).toBe(false);
  });
  it("manual refresh replaces the same running job with its observed terminal history record", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.running(); await panel.tick();
    panel.finish(); await panel.refresh();
    expect(panel.text()).toContain("離線回歸 PASS");
    expect(panel.resultBusy()).toBe("false");
    expect(panel.disabled()).toBe(false);
    const calls = panel.calls().length; await panel.tick();
    expect(panel.calls()).toHaveLength(calls);
  });
  it("releases a completed job even when the following capabilities refresh fails and retries that refresh", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.finish(); panel.failNextRefresh(503); await panel.tick();
    expect(panel.text()).toContain("離線回歸 PASS");
    expect(panel.resultBusy()).toBe("false");
    expect(panel.disabled()).toBe(false);
    await panel.tick(); await panel.tick();
    expect(panel.summary().error).toBe(null);
    expect(panel.calls().filter((call) => call.url === "/qa/api/qa/validations" && call.method === "GET")).toHaveLength(3);
  });
  it("selects real integration without borrowing an offline pass or starting work on selection", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    await panel.mode("es_integration");
    expect(panel.text()).not.toContain("離線回歸 PASS");
    expect(panel.text()).toContain("服務整合");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
    await panel.runAll(); panel.finish(); await panel.tick();
    expect(JSON.parse(panel.calls().find((call) => call.method === "POST").body)).toEqual({ mode: "es_integration", suite: "all" });
    expect(panel.text()).toContain("實測流程已完成");
    expect(panel.text()).toContain("Observed isolated fixture check");
    expect(panel.text()).not.toContain("11 個測試");
    expect(panel.text()).toContain("人工語意審核待完成");
  });
  it("requires explicit E2E cost consent and a sufficient bounded budget", async () => {
    const panel = await openPanel({ workbench: true }); await panel.mode("real_es_llm_e2e");
    await panel.runAll();
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
    await panel.acknowledge(); await panel.budget(0.01);
    expect(panel.disabled()).toBe(true);
    await panel.budget(1); await panel.runAll();
    expect(JSON.parse(panel.calls().find((call) => call.method === "POST").body)).toEqual({ mode: "real_es_llm_e2e", suite: "all", max_usd: 1, acknowledge_cost: true });
  });
  it("submits one paid start and one cancellation when each control is clicked twice", async () => {
    const panel = await openPanel({ workbench: true, turnstileRequired: true, sitekey: "fixture-sitekey" });
    await panel.mode("real_es_llm_e2e"); await panel.acknowledge(); await panel.doubleStart();
    expect(panel.challenges()).toEqual(["fixture-sitekey"]);
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
    await panel.doubleCancel();
    expect(panel.calls().filter((call) => call.method === "POST" && call.url.endsWith("/cancel"))).toHaveLength(1);
    expect(panel.text()).toContain("已取消");
  });
  it("shows unavailable real-mode reasons without enabling execution", async () => {
    const panel = await openPanel({ workbench: true, realAvailable: false }); await panel.mode("es_integration");
    expect(panel.disabled()).toBe(true);
    expect(panel.text()).toContain("mode_unavailable");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("obtains a required Turnstile proof only after explicit cost consent and start", async () => {
    const panel = await openPanel({ workbench: true, turnstileRequired: true, sitekey: "fixture-sitekey" });
    await panel.mode("real_es_llm_e2e");
    expect(panel.challenges()).toEqual([]);
    await panel.runAll();
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
    await panel.acknowledge(); await panel.runAll();
    expect(panel.challenges()).toEqual(["fixture-sitekey"]);
    expect(JSON.parse(panel.calls().find((call) => call.method === "POST").body)).toEqual({ mode: "real_es_llm_e2e", suite: "all", max_usd: 1, acknowledge_cost: true, cf_token: "fixture-proof" });
  });
  it("does not submit E2E when a required proof is missing or times out", async () => {
    const panel = await openPanel({ workbench: true, turnstileRequired: true, sitekey: "fixture-sitekey", proof: "" });
    await panel.mode("real_es_llm_e2e"); await panel.acknowledge(); await panel.runAll(); await panel.expireSecurity();
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
    expect(panel.text()).toContain("安全驗證未完成");
    panel.close();
    const missing = await openPanel({ workbench: true, turnstileRequired: true }); await missing.mode("real_es_llm_e2e"); await missing.acknowledge();
    expect(missing.disabled()).toBe(true);
    expect(missing.text()).toContain("安全驗證尚未設定");
  });
  it("downloads measured real-mode evidence through the authenticated owner endpoint", async () => {
    const panel = await openPanel({ workbench: true }); await panel.mode("es_integration"); await panel.runAll(); panel.finish(); await panel.tick(); await panel.download();
    expect(panel.calls().at(-1).url).toBe("/qa/api/qa/validations/offline-browser-all/report");
    expect(panel.calls().at(-1).method).toBe("GET");
    expect(panel.downloads()).toHaveLength(1);
    expect(panel.text()).toContain("人工語意審核待完成");
  });
  it("opens the workbench with the latest observed report and exports measured counts", async () => {
    const panel = await openPanel({ workbench: true, resume: true });
    expect(panel.heading()).toBe("H1");
    expect(panel.text()).toContain("11 個測試");
    expect(panel.summary()).toEqual({ mode: "offline_regression", status: "completed", tests: 11, active: false, available: true, error: null });
    expect(panel.calls().map((call) => call.method)).toEqual(["GET"]);
  });
  it("keeps a hidden workbench polling and never exports unknown running counts as zero", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.hide();
    panel.running(); await panel.tick();
    expect(panel.summary()).toEqual({ mode: "offline_regression", status: "running", tests: null, active: true, available: true, error: null });
    panel.finish(); await panel.tick();
    expect(panel.summary()).toEqual({ mode: "offline_regression", status: "completed", tests: 11, active: false, available: true, error: null });
    expect(panel.text()).toContain("不能當作線上品質通過證據");
  });
  it("exports a hidden polling failure with the last observed status until a successful manual refresh", async () => {
    const panel = await openPanel({ workbench: true }); await panel.runAll(); panel.running(); await panel.tick(); panel.hide();
    panel.failNextPoll(404); await panel.tick();
    expect(panel.summary()).toEqual({ mode: "offline_regression", status: "running", tests: null, active: true, available: true, error: "missing" });
    await panel.refresh();
    expect(panel.summary()).toEqual({ mode: "offline_regression", status: "running", tests: null, active: true, available: true, error: null });
    expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(1);
  });
  it("reads capabilities without automatically starting tests or claiming live quality", async () => {
    const panel = await openPanel();
    expect(panel.calls()).toHaveLength(1);
    expect(panel.calls()[0].method).toBe("GET");
    expect(panel.text()).toContain("不呼叫付費模型");
    expect(panel.text()).toContain("NOT RUN");
  });
  it("runs all layers only after a click and shows measured progress and counts", async () => {
    const panel = await openPanel();
    await panel.runAll();
    expect(panel.calls().filter((call) => call.method === "POST").map((call) => JSON.parse(call.body))).toEqual([{ mode: "offline_regression", suite: "all" }]);
    expect(panel.disabled()).toBe(true);
    expect(panel.text()).toContain("已排隊");
    panel.finish(); await panel.tick();
    expect(panel.text()).toContain("離線回歸 PASS");
    expect(panel.text()).toContain("11 個測試 · FAIL／ERROR 0 · SKIP 2");
    expect(panel.text()).toContain("不能當作線上品質通過證據");
  });
  it("selects the requested layer and reports a failing execution", async () => {
    const panel = await openPanel(); await panel.runRag(); panel.finish(true); await panel.tick();
    expect(JSON.parse(panel.calls().find((call) => call.method === "POST").body)).toEqual({ mode: "offline_regression", suite: "rag" });
    expect(panel.text()).toContain("回歸 FAIL");
    expect(panel.text()).toContain("FAIL／ERROR 1");
  });
  it("labels a mixed all-layer failure as the whole run instead of each layer failing", async () => {
    const panel = await openPanel(); await panel.runAll(); panel.finish(true); await panel.tick();
    expect(panel.text().match(/整批狀態：回歸 FAIL/g)).toHaveLength(3);
  });
  it("continues polling unmeasured running steps instead of claiming zero tests", async () => {
    const panel = await openPanel(); await panel.runAll(); panel.running(); await panel.tick();
    expect(panel.text()).toContain("尚未取得測試報告");
    expect(panel.text()).not.toContain("0 個測試");
    panel.finish(); await panel.tick();
    expect(panel.text()).toContain("11 個測試");
    expect(panel.text()).toContain("離線回歸 PASS");
  });
  it("cancels the owned job and stops polling it", async () => {
    const panel = await openPanel(); await panel.runAll(); await panel.cancel();
    expect(panel.text()).toContain("已取消");
    const calls = panel.calls().length; await panel.tick();
    expect(panel.calls()).toHaveLength(calls);
    expect(panel.calls().some((call) => call.url.endsWith("/owned-run/cancel") && call.method === "POST")).toBe(true);
  });
  it("keeps controls unavailable if the runner is not packaged", async () => {
    const panel = await openPanel({ enabled: false });
    expect(panel.disabled()).toBe(true); expect(panel.text()).toContain("尚未就緒");
    expect(panel.calls().every((call) => call.method === "GET")).toBe(true);
  });
  it("surfaces a concurrent start rejection without creating a fake successful job", async () => {
    const panel = await openPanel({ denied: true }); await panel.runAll();
    expect(panel.text()).toContain("目前已有驗證工作執行中");
    expect(panel.text()).not.toContain("離線回歸 PASS");
  });
  it("aborts pending API work and polling when the page is closed", async () => {
    const panel = await openPanel(); await panel.runAll(); panel.close(); await panel.tick();
    expect(panel.calls().every((call) => call.signal.aborted)).toBe(true);
    expect(panel.calls()).toHaveLength(2);
  });
});
