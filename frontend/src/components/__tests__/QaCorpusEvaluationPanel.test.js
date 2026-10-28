// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createI18n } from "vue-i18n";
import { Quasar } from "quasar";
import QaCorpusEvaluationPanel from "../QaCorpusEvaluationPanel.vue";
import { corpusCapabilities, corpusJob } from "../../lib/__tests__/qa/corpus-evaluation-physical.js";
import zhTW from "../../i18n/zh-TW.json";
import en from "../../i18n/en.json";
const transport = vi.hoisted(() => ({ fetch: null }));
vi.mock("../../lib/runtime.js", async original => { const actual = await original(); return ({ ...actual, get QA_EVIDENCE() { return actual.QA_EVIDENCE; }, get QA_REPOSITORY() { return actual.QA_REPOSITORY; }, get WORKBENCH_TASKS() { return actual.WORKBENCH_TASKS; },  AGENT: "/qa/api", TS_SITEKEY: ""  }); });
vi.mock("../../lib/qaSession.js", () => ({ apiFetch: (...args) => transport.fetch(...args) }));
const mounted = [];
// Contract: CorpusEvaluationService routes. Every mutation has an explicit route;
// this offline physical cannot call a provider or ES, or treat any POST as a run.
async function openCorpus({ missing = false, reviewed = false, failed = false, drift = false, resume = false, reviewRejected = false, readableCoverage = false, locale = "zh-TW" } = {}) {
  let job = reviewed || resume || drift ? corpusJob({ reviewed, failed, status: drift ? "stale" : resume ? "running" : "completed" }) : null;
  const capabilities = corpusCapabilities({ available: !missing, missing, job });
  if (readableCoverage) {
    // Contract: bank_summary coverage counts cases for categories/task types/splits,
    // but counts source documents for publishers; those totals may differ.
    const bank = capabilities.bank;
    bank.case_count = 24; bank.document_count = 12;
    bank.coverage = { ...bank.coverage, categories: { 政治: 16, 社會: 8 }, sources: { "Fixture daily": 9, "Fixture wire": 3 }, splits: { dev: 16, holdout: 8 }, task_types: { incident_sequence: 6, investigation_sequence_and_status: 6, comparison_of_local_impacts: 6, "<img src=x onerror=alert(1)>": 6 } };
    if (job) { job.bank = structuredClone(bank); job.index_observation.verified_after_run.verified_documents = bank.document_count; job.cases[0].task_type = "incident_sequence"; job.cases[1].task_type = "<img src=x onerror=alert(1)>"; }
    capabilities.recent = job ? [job] : [];
  }
  const calls = [], json = (value, status = 200) => ({ ok: status < 400, status, json: async () => structuredClone(value) });
  transport.fetch = async (url, init = {}) => { const method = init.method || "GET", body = init.body ? JSON.parse(init.body) : null; calls.push({ url, method, body });
    const base = "/qa/api/qa/corpus-evaluations";
    if (url === base && method === "GET") { const current = corpusCapabilities({ available: !missing, missing, job }); if (readableCoverage) current.bank = capabilities.bank; return json(current); }
    if (url === base && method === "POST") { job = corpusJob({ status: "queued" }); return json({ job }, 202); }
    if (url === base + "/offline-corpus-job/cancel" && method === "POST") { job = corpusJob({ status: "cancelled" }); return json({ job }); }
    if (url === base + "/offline-corpus-job/review" && method === "POST") { if (reviewRejected) return json({ detail: "corpus_review_hash_mismatch" }, 409); const reviewedJob = corpusJob({ reviewed: true, failed: true, status: job.status }); job = { ...job, semantic_status: "reviewed", semantic_review: reviewedJob.semantic_review, quality_passed: false }; return json({ job }); }
    if (url === base + "/offline-corpus-job" && method === "GET") return json({ job });
    throw new Error("Unexpected offline corpus route: " + method + " " + url);
  };
  const i18n = createI18n({ legacy: false, locale, globalInjection: true, messages: { "zh-TW": zhTW, en } });
  const wrapper = mount(QaCorpusEvaluationPanel, { global: { plugins: [Quasar, i18n] } }); mounted.push(wrapper); await flushPromises();
  const control = (id) => wrapper.get('[data-testid="qa-corpus-' + id + '"]');
  return { text: () => wrapper.text(), calls: () => structuredClone(calls), starts: () => calls.filter((call) => call.method === "POST" && call.url.endsWith("corpus-evaluations")),
    disabled: () => control("start").element.disabled,
    async consent() { await control("ack").setValue(true); }, async start() { await control("start").trigger("click"); await flushPromises(); },
    async cancel() { await control("cancel").trigger("click"); await flushPromises(); },
    coverage: (kind) => control("coverage-" + kind).text(),
    taskTypes: () => ({ open: control("task-types").element.open, summary: control("task-types").get("summary").text(), text: control("task-types").text(), injectedElements: control("task-types").findAll("img").length }),
    caseSummaries: () => wrapper.findAll('[data-testid="qa-corpus-case"]>summary').map((summary) => summary.text()),
    async expandTaskTypes() { control("task-types").get("summary").element.click(); await flushPromises(); },
    async review({ wrongHash = false } = {}) { const input = control("review-file"), reviewedJob = corpusJob({ reviewed: true, failed: true }); const file = { size: 100, text: async () => JSON.stringify({ report_sha256: (wrongHash ? "0" : "c").repeat(64), reviewer_kind: "ai", reviewer: "Offline fixture reviewer", reviewed_at: "2026-10-23T02:00:00+08:00", reviews: reviewedJob.semantic_review.cases }) }; Object.defineProperty(input.element, "files", { value: [file], configurable: true }); await input.trigger("change"); await flushPromises(); },
  };
}
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); vi.restoreAllMocks(); });
describe("real corpus quality workflow", () => {
  it("distinguishes case and news counts while keeping localized task details collapsed without changing the bank or starting a run", async () => {
    const panel = await openCorpus({ readableCoverage: true });
    expect(panel.text()).toContain("24 個兩輪案例 · 12 篇來源新聞");
    expect(panel.coverage("categories")).toContain("主題覆蓋（案例數）政治 16 · 社會 8");
    expect(panel.coverage("sources")).toContain("新聞來源覆蓋（篇數）Fixture daily 9 · Fixture wire 3");
    expect(panel.coverage("splits")).toContain("開發／保留集（案例數）開發集 16 · 保留集 8");
    expect(panel.taskTypes()).toMatchObject({ open: false, summary: "題型明細 · 4 種題型／24 個案例", injectedElements: 0 });
    await panel.expandTaskTypes();
    expect(panel.taskTypes().open).toBe(true);
    expect(panel.taskTypes().text).toContain("事件經過 6");
    expect(panel.taskTypes().text).toContain("調查經過與進度 6");
    expect(panel.taskTypes().text).toContain("各地影響比較 6");
    expect(panel.taskTypes().text).toContain("<img src=x onerror=alert(1)> 6");
    expect(panel.text()).toContain("c".repeat(64));
    expect(panel.text()).toContain("e".repeat(64));
    expect(panel.text()).toContain("尚未執行");
    expect(panel.disabled()).toBe(true);
    expect(panel.starts()).toEqual([]);
    const executed = await openCorpus({ readableCoverage: true, reviewed: true });
    expect(executed.caseSummaries()[0]).toContain("開發集 · 科技 · 事件經過");
    expect(executed.caseSummaries()[1]).toContain("保留集 · 科技 · <img src=x onerror=alert(1)>");
    expect(executed.starts()).toEqual([]);
    const english = await openCorpus({ readableCoverage: true, locale: "en" });
    expect(english.taskTypes().summary).toBe("Task details · 4 task types / 24 cases");
    expect(english.taskTypes().text).toContain("Sequence of events 6");
    expect(english.coverage("splits")).toContain("Development 16 · Holdout 8");
  });
  it("describes environment-local bank absence without denying private local evaluation history and disables paid execution", async () => {
    for (const [locale, expected, misleading] of [
      ["zh-TW", "此 QA 執行環境未提供真新聞題庫。若題庫與完整評測紀錄僅保存於本機，本頁不會顯示；無法由此判定是否曾執行或通過。", "尚未建立真新聞題庫"],
      ["en", "This QA environment has no real news bank available. A bank and complete evaluation records kept only locally are not shown here; their execution or quality status cannot be determined from this page.", "This evaluation has not run"],
    ]) {
      const panel = await openCorpus({ missing: true, locale });
      expect(panel.text()).toContain(expected);
      expect(panel.text()).not.toContain(misleading);
      expect(panel.disabled()).toBe(true);
      expect(panel.starts()).toEqual([]);
    }
  });
  it("shows a fixed bank with dynamic ES retrieval and requires explicit paid consent", async () => { const panel = await openCorpus(); expect(panel.text()).toContain("offline-contract-fixture"); expect(panel.text()).toContain("news_read"); expect(panel.disabled()).toBe(true); await panel.consent(); expect(panel.disabled()).toBe(false); expect(panel.starts()).toEqual([]); await panel.start(); expect(panel.starts()).toHaveLength(1); expect(panel.starts()[0].body).toMatchObject({ bank_sha256: "c".repeat(64), acknowledge_cost: true }); });
  it("renders reviewed case reasons independently of retrieval counts", async () => { const panel = await openCorpus({ reviewed: true, failed: true }); expect(panel.text()).toContain("AI 語意審核已完成"); expect(panel.text()).toContain("回答引用無法支持該事實。"); expect(panel.text()).toContain("預期事實"); expect(panel.text()).toContain("Recall"); expect(panel.starts()).toEqual([]); });
  it("preserves an ES drift result as stale and pending semantic review", async () => { const panel = await openCorpus({ drift: true }); expect(panel.text()).toContain("語料已變更"); expect(panel.text()).toContain("語意審核待完成"); expect(panel.starts()).toEqual([]); });
  it("allows cancellation without starting another paid run", async () => { const panel = await openCorpus({ resume: true }); await panel.cancel(); expect(panel.calls().filter((call) => call.url.endsWith("/cancel"))).toHaveLength(1); expect(panel.starts()).toEqual([]); });
  it("imports review evidence without changing original stale execution or issuing a model start request", async () => { const panel = await openCorpus({ drift: true }); await panel.review(); expect(panel.text()).toContain("AI 語意審核已完成"); expect(panel.text()).toContain("語料已變更"); expect(panel.starts()).toEqual([]); expect(panel.calls().filter((call) => call.method === "POST" && call.url.endsWith("/review"))).toHaveLength(1); });
  it("keeps a rejected review pending and exposes a visible retryable error", async () => { const panel = await openCorpus({ drift: true, reviewRejected: true }); await panel.review(); expect(panel.text()).toContain("語意審核待完成"); expect(panel.text()).toContain("此審核與現有紀錄不符"); expect(panel.text()).not.toContain("AI 語意審核已完成"); expect(panel.starts()).toEqual([]); });
  it("rejects a review for another report before making any review request", async () => { const panel = await openCorpus({ drift: true }); await panel.review({ wrongHash: true }); expect(panel.text()).toContain("逐題雜湊不符"); expect(panel.calls().filter((call) => call.method === "POST")).toHaveLength(0); });
});
