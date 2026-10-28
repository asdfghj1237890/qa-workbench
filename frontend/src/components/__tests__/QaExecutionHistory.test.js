// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { createI18n } from "vue-i18n";
import { Quasar } from "quasar";
import fixtures from "../../../e2e/observatory-validation-physical.cjs";
import liveFixtures from "../../../e2e/observatory-live-evaluation-physical.cjs";
import zhTW from "../../i18n/zh-TW.json";
import en from "../../i18n/en.json";
import { buildWorkbenchModel } from "../../lib/qaWorkbench.js";
import QaExecutionHistory from "../QaExecutionHistory.vue";
import { corpusCapabilities, corpusJob } from "../../lib/__tests__/qa/corpus-evaluation-physical.js";

// Contract: owner-scoped recent records from qa_validation.py / qa_evaluations.py;
// the component receives the normalized real API observations from qaWorkbench.js.
function openHistory({ empty = false, loading = false, error = "", corpus = false } = {}) {
  const offline = { ...fixtures.jobBody("all", "completed"), source_sha: "a".repeat(40) };
  const model = { ...liveFixtures.jobBody("quick", "completed"), source_sha: null };
  const entries = empty ? [] : buildWorkbenchModel({ validation: { capabilities: { recent: [offline] } }, evaluation: { capabilities: { recent: [model] } }, ...(corpus ? { corpus: { capabilities: corpusCapabilities({ job: corpusJob({ reviewed: true, failed: true }) }) } } : {}) }).history;
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: "zh-TW", messages: { "zh-TW": zhTW, en } });
  const wrapper = mount(QaExecutionHistory, { props: { entries, loading, error }, global: { plugins: [i18n, Quasar] } });
  const control = (name) => wrapper.get('[data-testid="qa-history-' + name + '"]');
  return {
    text: () => wrapper.text(),
    ids: () => wrapper.findAll('[data-testid="qa-history-row"]').map((entry) => entry.attributes("data-job-id")),
    selected: () => wrapper.emitted("select")?.at(-1)?.[0],
    logs: () => wrapper.emitted("logs")?.at(-1)?.[0],
    refreshes: () => wrapper.emitted("refresh")?.length || 0,
    logButtons: () => wrapper.findAll('[data-testid="qa-history-logs"]').length,
    async filterMode(value) { await control("mode").setValue(value); },
    async filterStatus(value) { await control("status").setValue(value); },
    async search(value) { await control("search").setValue(value); },
    async details() { await wrapper.findAll('[data-testid="qa-history-details"]')[0].trigger("click"); },
    async openLogs() { await wrapper.findAll('[data-testid="qa-history-logs"]')[0].trigger("click"); },
    async refresh() { await control("refresh").trigger("click"); },
    close() { wrapper.unmount(); },
  };
}

describe("global execution history", () => {
  it("keeps real corpus failures and review attribution distinct without a nonexistent log action", async () => {
    const history = openHistory({ corpus: true });
    await history.filterMode("real_corpus_quality");
    expect(history.ids()).toEqual(["offline-corpus-job"]);
    expect(history.text()).toContain("AI 語意審核已完成");
    expect(history.text()).toContain("不與結構測試合計");
    expect(history.logButtons()).toBe(0);
    await history.details(); expect(history.selected().family).toBe("corpus-evaluations"); history.close();
  });
  it("keeps model and validation records together and emits the actual selected record", async () => {
    const history = openHistory();
    expect(history.ids()).toHaveLength(2);
    await history.filterMode("model_evaluation");
    expect(history.ids()).toEqual(["live-browser-quick"]);
    await history.details(); await history.openLogs();
    expect(history.selected()).toMatchObject({ family: "evaluations", id: "live-browser-quick" });
    expect(history.logs()).toMatchObject({ family: "evaluations", id: "live-browser-quick" });
    expect(history.text()).toContain("模型語意品質尚待審核"); history.close();
  });
  it("filters known statuses and searches IDs or full revisions without inventing records", async () => {
    const history = openHistory();
    await history.filterStatus("FAIL"); expect(history.ids()).toEqual(["live-browser-quick"]);
    await history.filterStatus(""); await history.search("a".repeat(40));
    expect(history.ids()).toEqual(["offline-browser-all"]);
    await history.search("unknown-run"); expect(history.ids()).toEqual([]);
    expect(history.text()).toContain("沒有符合篩選條件的紀錄。"); history.close();
  });
  it("distinguishes retained-history emptiness, loading and failed reads", () => {
    const empty = openHistory({ empty: true }); expect(empty.text()).toContain("尚無保留中的執行紀錄。"); empty.close();
    const loading = openHistory({ empty: true, loading: true }); expect(loading.text()).toContain("正在讀取執行紀錄"); loading.close();
    const failed = openHistory({ error: "request" }); expect(failed.text()).toContain("部分紀錄無法更新"); expect(failed.ids()).toHaveLength(2); failed.close();
  });
  it("does not emit a history selection or log request while retained records are refreshing", async () => {
    const history = openHistory({ loading: true });
    await history.details(); await history.openLogs();
    expect(history.selected()).toBe(undefined);
    expect(history.logs()).toBe(undefined); history.close();
  });
  it("offers a visible refresh action for failed reads and blocks duplicate refresh while loading", async () => {
    const failed = openHistory({ error: "request" }); await failed.refresh();
    expect(failed.refreshes()).toBe(1); failed.close();
    const loading = openHistory({ loading: true }); await loading.refresh();
    expect(loading.refreshes()).toBe(0); loading.close();
  });
});
