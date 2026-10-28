// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createI18n } from "vue-i18n";
import QaExecutionLog from "../QaExecutionLog.vue";
import zhTW from "../../i18n/zh-TW.json";
import en from "../../i18n/en.json";

const transport = vi.hoisted(() => ({ fetch: null }));
vi.mock("../../lib/runtime.js", async original => { const actual = await original(); return ({ ...actual, get QA_EVIDENCE() { return actual.QA_EVIDENCE; }, get QA_REPOSITORY() { return actual.QA_REPOSITORY; }, get WORKBENCH_TASKS() { return actual.WORKBENCH_TASKS; },  AGENT: "/qa/api"  }); });
vi.mock("../../lib/qaSession.js", () => ({ apiFetch: (...args) => transport.fetch(...args) }));
const mounted = [];

// Contract: owner-scoped qa_validation/qa_evaluations GET /{id}/logs byte
// pages and /logs/download. Transport is a local browser physical; no test,
// provider, real model or backend is executed by these component journeys.
async function openLog({ running = false, legacy = false, truncated = false, content = "FIRST\n中文\nLAST\n", family = "validations", conclusion = false } = {}) {
  const calls = [], downloads = [], encoder = new TextEncoder(), decoder = new TextDecoder();
  let bytes = encoder.encode(content), fail = null, pending = null, nextPageSize = null;
  let downloadFlags = { complete: !running, truncated, legacy }, downloadHeaderOverride;
  vi.stubGlobal("URL", { createObjectURL: vi.fn((blob) => { downloads.push(blob); return "blob:log-" + downloads.length; }), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  transport.fetch = vi.fn(async (url, init = {}) => {
    const parsed = new URLForTest(url, "https://fixture.invalid");
    calls.push({ path: parsed.pathname, offset: Number(parsed.searchParams.get("offset")), step: parsed.searchParams.get("step"), signal: init.signal });
    if (fail) { const status = fail; fail = null; return { ok: false, status }; }
    if (parsed.pathname.endsWith("/download")) return { ok: true,
      headers: new Headers(downloadHeaderOverride ?? {
        "X-Log-Complete": String(downloadFlags.complete), "X-Log-Truncated": String(downloadFlags.truncated), "X-Log-Legacy": String(downloadFlags.legacy),
      }), blob: async () => new Blob([bytes], { type: "text/plain" }) };
    const offset = Number(parsed.searchParams.get("offset")), limit = Math.min(Number(parsed.searchParams.get("limit")), nextPageSize ?? Infinity);
    nextPageSize = null;
    let end = Math.min(bytes.length, offset + limit);
    while (end > offset && (bytes[end] & 0xc0) === 0x80) end--;
    const page = { text: decoder.decode(bytes.slice(offset, end)), next_offset: end, total_bytes: bytes.length, has_more: end < bytes.length, complete: !running, legacy, truncated };
    if (conclusion && !running) {
      const marker = decoder.decode(bytes).indexOf("TEST RESULT CONCLUSION");
      page.conclusion_offset = marker < 0 ? null : encoder.encode(decoder.decode(bytes).slice(0, marker)).length;
    }
    if (pending) { const control = pending; pending = null; await new Promise((resolve) => { control.resolve = resolve; }); }
    return { ok: true, json: async () => page };
  });
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: "zh-TW", messages: { "zh-TW": zhTW, en } });
  const wrapper = mount(QaExecutionLog, { props: { jobId: "owned-first", family, running, steps: family === "validations" ? ["indexer", "retrieval"] : [] }, global: { plugins: [i18n] } });
  mounted.push(wrapper); await flushPromises();
  const control = (name) => wrapper.get('[data-testid="qa-full-log-' + name + '"]');
  return {
    text: () => wrapper.text(), output: () => control("output").text(), calls: () => calls,
    requestsFor: (id) => calls.filter((call) => call.path.includes("/" + id + "/")),
    revoked: () => URL.revokeObjectURL.mock.calls.map(([value]) => value), downloads: () => downloads,
    async reveal() { await control("open").trigger("click"); await flushPromises(); },
    async more() { const more = wrapper.find('[data-testid="qa-full-log-more"]'); await (more.exists() ? more : control("refresh")).trigger("click"); await flushPromises(); },
    async earlier() { await control("earlier").trigger("click"); await flushPromises(); },
    async retry() { await control("retry").trigger("click"); await flushPromises(); },
    async download() { await control("download").trigger("click"); await flushPromises(); },
    async conclusion() { await control("conclusion").trigger("click"); await flushPromises(); },
    conclusionPresent: () => wrapper.find('[data-testid="qa-full-log-conclusion"]').exists(),
    downloadStatus: () => { const status = wrapper.find('[data-testid="qa-full-log-download-integrity"]'); return status.exists() ? status.text() : null; },
    downloadFlags(value) { downloadFlags = { ...downloadFlags, ...value }; },
    untrustedDownloadFlags(mode) { downloadHeaderOverride = mode === "missing" ? {} : { "X-Log-Complete": "true", "X-Log-Truncated": "unknown", "X-Log-Legacy": "false" }; },
    retryDownload: () => { const link = wrapper.find('[data-testid="qa-full-log-download-again"]'); return link.exists() ? link.attributes("href") : null; },
    async scope(value) { await control("scope").setValue(value); await flushPromises(); },
    scopePresent: () => wrapper.find('[data-testid="qa-full-log-scope"]').exists(),
    async follow() { await control("follow").setValue(true); await flushPromises(); },
    async finish() { running = false; await wrapper.setProps({ running: false }); await flushPromises(); },
    async tick() { await vi.advanceTimersByTimeAsync(1000); await flushPromises(); },
    append(value) { bytes = encoder.encode(decoder.decode(bytes) + value); },
    pageSize(value) { nextPageSize = value; }, failNext(status = 503) { fail = status; },
    deferNext() { const control = {}; pending = control; return control; },
    async release(control) { control.resolve(); await flushPromises(); },
    async changeJob(value) { await wrapper.setProps({ jobId: value }); await flushPromises(); },
    scroll(value) { control("output").element.scrollTop = value; },
    scrollTop: () => control("output").element.scrollTop,
    close() { mounted.splice(mounted.indexOf(wrapper), 1); wrapper.unmount(); },
  };
}
const URLForTest = URL;
beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }));
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("complete QA execution output", () => {
  it("loads output on demand and preserves the first and last bytes across pages", async () => {
    const log = await openLog({ content: "FIRST\n" + "x".repeat(70000) + "\nLAST\n" });
    expect(log.calls()).toEqual([]);
    await log.reveal(); expect(log.output()).toContain("FIRST"); expect(log.output()).not.toContain("LAST");
    await log.more(); expect(log.output()).toContain("FIRST"); expect(log.output()).toContain("LAST");
    expect(log.calls().map((call) => call.offset)).toEqual([0, 65536]);
  });
  it("keeps the reader scroll position and appends each running byte once", async () => {
    const log = await openLog({ running: true }); await log.reveal(); log.scroll(42);
    await log.tick(); expect(log.calls()).toHaveLength(1);
    log.append("NEXT\n"); await log.more(); expect(log.scrollTop()).toBe(42);
    expect(log.output().match(/NEXT/g)).toHaveLength(1);
    await log.follow(); await log.tick(); expect(log.output().match(/NEXT/g)).toHaveLength(1);
    log.append("FINAL\n"); await log.finish(); expect(log.output()).toContain("FINAL");
    const count = log.calls().length; await log.tick(); expect(log.calls()).toHaveLength(count);
  });
  it("opens the final conclusion directly after a large UTF-8 log and can return to raw output", async () => {
    const prefix = "FIRST\n" + "界".repeat(120000) + "\n";
    const conclusion = "TEST RESULT CONCLUSION\n本次測試結果：PASS\n";
    const log = await openLog({ content: prefix + conclusion, conclusion: true });
    await log.reveal();
    expect(log.output()).not.toContain("TEST RESULT CONCLUSION");
    expect(log.conclusionPresent()).toBe(true);
    await log.conclusion();
    expect(log.output()).toBe(conclusion.trim());
    expect(log.calls().at(-1).offset).toBe(360007);
    await log.earlier();
    expect(log.output()).toContain("FIRST");
  });
  it("offers the conclusion only after execution ends and the server provides it", async () => {
    const log = await openLog({ running: true, conclusion: true });
    await log.reveal();
    expect(log.conclusionPresent()).toBe(false);
    log.append("TEST RESULT CONCLUSION\n本次測試結果：CANCELLED\n");
    await log.finish();
    expect(log.conclusionPresent()).toBe(true);
    await log.conclusion();
    expect(log.output()).toContain("本次測試結果：CANCELLED");
  });
  it("uses a separate step cursor and does not mix step and entire-run output", async () => {
    const log = await openLog(); await log.reveal(); await log.scope("retrieval");
    expect(log.calls().map((call) => [call.offset, call.step])).toEqual([[0, null], [0, "retrieval"]]);
    expect(log.output().match(/FIRST/g)).toHaveLength(1);
  });
  it("retains the last readable output on failure and retries the same cursor", async () => {
    const log = await openLog(); await log.reveal(); log.failNext(); await log.more();
    expect(log.text()).toContain("無法讀取執行 log"); expect(log.output()).toContain("FIRST");
    await log.retry(); expect(log.text()).not.toContain("無法讀取執行 log");
    expect(log.calls().slice(-2).map((call) => call.offset)).toEqual([18, 18]);
  });
  it("uses UTF-8 byte cursors without losing or replacing Chinese characters", async () => {
    const content = "FIRST\n" + "界".repeat(30000) + "\nLAST\n";
    const log = await openLog({ content }); await log.reveal(); await log.more();
    expect(log.output()).toBe(content.trim());
    expect(log.calls().map((call) => call.offset)).toEqual([0, 65535]);
  });
  it("does not relabel a legacy tail or capped capture as complete output", async () => {
    const log = await openLog({ legacy: true, truncated: true }); await log.reveal();
    expect(log.text()).toContain("舊紀錄僅保留摘要，較早輸出無法還原");
    expect(log.text()).toContain("部分輸出未保留");
    expect(log.text()).not.toContain("輸出已完整保留");
  });
  it("discards stale pages and downloads when the selected historical run changes", async () => {
    const log = await openLog(); await log.reveal(); await log.download();
    expect(log.downloadStatus()).not.toBe(null);
    const old = log.retryDownload(), deferred = log.deferNext(); await log.more();
    await log.changeJob("owned-second"); await log.release(deferred);
    expect(log.revoked()).toContain(old); expect(log.retryDownload()).toBe(null); expect(log.downloadStatus()).toBe(null);
    expect(log.output().match(/FIRST/g)).toHaveLength(1);
    expect(log.requestsFor("owned-second").map((call) => call.offset)).toEqual([0]);
  });
  it("downloads the authenticated log separately from the JSON report", async () => {
    const log = await openLog(); await log.reveal(); await log.scope("indexer"); await log.download();
    expect(log.calls().at(-1).path).toBe("/qa/api/qa/validations/owned-first/logs/download");
    expect(log.calls().at(-1).step).toBe("indexer"); expect(log.downloads()).toHaveLength(1);
    expect(log.downloadStatus()).toContain("這份 TXT 的輸出已停止新增");
    expect(log.retryDownload()).toBe("blob:log-1"); log.close(); expect(log.revoked()).toContain("blob:log-1");
  });
  it("labels a newer capped download independently of an older running log page", async () => {
    const log = await openLog({ running: true }); await log.reveal();
    log.downloadFlags({ truncated: true }); await log.download();
    expect(log.downloadStatus()).toContain("這份 TXT 不完整");
    expect(log.downloadStatus()).toContain("下載時仍在收集輸出");
    log.downloadFlags({ complete: true }); await log.download();
    expect(log.downloadStatus()).toContain("這份 TXT 不完整");
    expect(log.downloadStatus()).not.toContain("下載時仍在收集輸出");
    await log.more();
    expect(log.downloadStatus()).toContain("這份 TXT 不完整");
    expect(log.downloadStatus()).not.toContain("下載時仍在收集輸出");
  });
  it("labels legacy download evidence even when the visible page was not legacy", async () => {
    const log = await openLog(); await log.reveal();
    log.downloadFlags({ legacy: true, truncated: true }); await log.download();
    expect(log.downloadStatus()).toContain("這份 TXT 僅保留舊紀錄摘要，較早輸出無法還原");
    await log.more();
    expect(log.downloadStatus()).toContain("這份 TXT 僅保留舊紀錄摘要，較早輸出無法還原");
  });
  for (const mode of ["missing", "invalid"]) {
    it("keeps " + mode + " download integrity flags unknown", async () => {
      const log = await openLog(); await log.reveal(); log.untrustedDownloadFlags(mode); await log.download();
      expect(log.downloadStatus()).toContain("這份 TXT 的完整性狀態未知");
      expect(log.downloadStatus()).not.toContain("這份 TXT 的輸出已停止新增");
    });
  }
  it("does not offer an unsupported model step filter or run another evaluation", async () => {
    const log = await openLog({ family: "evaluations" }); await log.reveal();
    expect(log.scopePresent()).toBe(false); expect(log.calls()[0].path).toBe("/qa/api/qa/evaluations/owned-first/logs");
  });
  it("keeps a failed TXT download retryable without downloading an error body", async () => {
    const log = await openLog(); await log.reveal(); log.failNext(500); await log.download();
    expect(log.downloads()).toEqual([]); expect(log.retryDownload()).toBe(null);
    expect(log.text()).toContain("無法下載執行 log");
    await log.download(); expect(log.downloads()).toHaveLength(1); expect(log.retryDownload()).toBe("blob:log-1");
  });
  it("bounds the displayed window and permits loading earlier output after following", async () => {
    const log = await openLog({ content: "FIRST\n" + "x".repeat(360000) + "\nLAST\n" }); await log.reveal();
    for (let page = 0; page < 5; page++) await log.more();
    expect(log.output().length).toBeLessThanOrEqual(262144); expect(log.output()).toContain("LAST");
    await log.earlier(); expect(log.output().length).toBeLessThanOrEqual(262144);
    expect(log.calls().at(-1).offset).toBeLessThan(log.calls().at(-2).offset);
  });
  it("rewinds large Chinese output to a known UTF-8 cursor rather than a partial character", async () => {
    const log = await openLog({ content: "界".repeat(120000) }); await log.reveal();
    for (let page = 0; page < 5; page++) await log.more();
    await log.earlier();
    expect(log.text()).not.toContain("無法讀取執行 log");
    expect(log.calls().at(-1).offset).toBe(65535);
  });
  it("aborts reads and follow timers on teardown without appending a late page", async () => {
    const log = await openLog({ running: true }); await log.reveal(); await log.follow();
    const deferred = log.deferNext(); await log.more(); const pending = log.calls().at(-1);
    log.close(); expect(pending.signal.aborted).toBe(true); await log.release(deferred);
    const count = log.calls().length; await log.tick(); expect(log.calls()).toHaveLength(count);
  });
});
