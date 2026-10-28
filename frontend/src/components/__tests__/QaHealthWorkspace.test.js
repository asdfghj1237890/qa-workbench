// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createI18n } from 'vue-i18n';
import { Quasar } from 'quasar';
import fixtures from '../../../e2e/observatory-health-physical.cjs';
import QaHealthWorkspace from '../QaHealthWorkspace.vue';
import zhTW from '../../i18n/zh-TW.json';
import en from '../../i18n/en.json';

const transport = vi.hoisted(() => ({ request: null }));
vi.mock("../../lib/runtime.js", async original => { const actual = await original(); return ({ ...actual, get QA_EVIDENCE() { return actual.QA_EVIDENCE; }, get QA_REPOSITORY() { return actual.QA_REPOSITORY; }, get WORKBENCH_TASKS() { return actual.WORKBENCH_TASKS; },  AGENT: '/qa/api'  }); });
vi.mock('../../lib/qaSession.js', () => ({ apiFetch: (...args) => transport.request(...args) }));
const mounted = [];

// Contract: qaHealth.js validates the shared /qa/health v1 response; the real
// workspace/child components render it. This local physical owns transport,
// clock and jsdom's native-dialog replacement, never an external service.
async function openHealth({ scenario = 'normal', failed = false } = {}) {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
  vi.setSystemTime(new Date('2026-10-26T00:00:00Z'));
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  const requests = [];
  transport.request = vi.fn(async (url, options) => {
    requests.push({ url, method: options.method });
    if (url.includes('/history?')) { const query = new URL(url, 'http://fixture.invalid').searchParams; return { ok: true, status: 200, json: async () => fixtures.historyBody({ module: query.get('module'), window: query.get('window'), now: Date.now() }) }; }
    return { ok: !failed, status: failed ? 503 : 200, json: async () => fixtures.healthBody(scenario) };
  });
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: 'zh-TW', messages: { 'zh-TW': zhTW, en } });
  const host = document.createElement('div'); document.body.appendChild(host);
  const wrapper = mount(QaHealthWorkspace, { attachTo: host, props: { dark: true, preview: false }, global: { plugins: [i18n, Quasar] } });
  mounted.push({ wrapper, host });
  await flushPromises();
  const settle = async () => {
    await flushPromises();
    const node = wrapper.find('dialog');
    if (node.exists()) { node.element.showModal = () => node.element.setAttribute('open', ''); node.element.close = () => node.element.removeAttribute('open'); }
  };
  await settle();
  const control = (id) => wrapper.get('[data-testid="health-' + id + '"]');
  return {
    text: () => wrapper.text(),
    coverage: () => control('coverage').text(),
    requests: () => requests.filter((request) => !request.url.includes('/history?')).map((request) => ({ ...request })),
    historyRequests: () => requests.filter((request) => request.url.includes('/history?')).map((request) => ({ ...request })),
    module: (id) => control('module-' + id).text(),
    jobCounts: () => control('run-counts').text(),
    failureValues: () => control('run-counts').findAll('.has-failure').map((node) => node.text()),
    observedIssues: () => control('observed-issues').text(),
    missingObservations: () => control('unobserved-modules').text(),
    async choose(id) { await control('module-' + id).trigger('click'); await settle(); },
    async reload() { await (wrapper.find('[data-testid="health-refresh"]').exists() ? control('refresh') : control('retry')).trigger('click'); await settle(); },
    fail() { failed = true; },
    recover() { failed = false; scenario = 'recovered'; },
    async expire() { vi.setSystemTime(new Date('2026-10-26T00:02:01Z')); await vi.advanceTimersByTimeAsync(5000); await settle(); },
    async evidence() { await control('evidence').trigger('click'); await flushPromises(); await control('evidence-tab-raw').trigger('click'); await flushPromises(); return JSON.parse(wrapper.get('dialog pre').text()); },
  };
}
afterEach(() => { mounted.splice(0).forEach(({ wrapper, host }) => { wrapper.unmount(); host.remove(); }); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('authenticated health observations', () => {
  it('shows passive LLM counts, denominator and duration without treating successful counts as errors', async () => {
    const health = await openHealth({ scenario: 'llm-failed' }); await health.choose('llm');
    expect(health.coverage()).toContain('6/7');
    expect(health.jobCounts()).toContain('可分類完成數3');
    expect(health.jobCounts()).toContain('成功數1');
    expect(health.jobCounts()).toContain('平均請求耗時120');
    expect(health.failureValues()).toEqual(['1', '1']);
    const evidence = await health.evidence();
    expect(evidence.observation.measurement.value).toBe(33.33);
    expect(evidence.observation.details.cancelled_count).toBe(1);
    expect(evidence.observation.details.completed_count).toBe(3);
    expect(evidence.quality_review).toBe('unmeasured'); expect(evidence.score).toBeNull();
    expect(health.requests()).toHaveLength(1);
  });
  it.each(['llm-no-traffic', 'llm-cancelled', 'llm-unavailable'])('keeps missing or inconclusive model evidence unknown (%s)', async (scenario) => {
    const health = await openHealth({ scenario }); await health.choose('llm');
    expect(health.coverage()).toContain('5/7');
    const evidence = await health.evidence();
    expect(evidence.observation.measurement.value).toBeNull();
    expect(evidence.view_state.status).toBe('unknown');
    if (scenario === 'llm-no-traffic') { expect(health.jobCounts()).toBe('觀測請求數0'); expect(health.text()).toContain('沒有可用的已完成模型請求紀錄'); }
    expect(evidence.score).toBeNull(); expect(health.requests()).toHaveLength(1);
  });
  it('rejects a fabricated LLM percentage at the public page boundary', async () => {
    const health = await openHealth({ scenario: 'llm-invalid-rate' });
    expect(health.text()).toContain('健康觀測格式無效');
  });
  it('renders scoped observations and a hard job failure without synthetic backlog values', async () => {
    const health = await openHealth();
    expect(health.text()).toContain('QA 觀測資料');
    expect(health.text()).toContain('目前 QA 實例');
    expect(health.text()).toContain('回答品質未量測');
    expect(health.text()).not.toContain('最舊積壓 38 分鐘');
    expect(health.text()).not.toContain('設計示意');
    expect(health.coverage()).toContain('異常 1');
    expect(health.coverage()).toContain('5/7');
    expect(health.jobCounts()).toContain('待重試文件數3');
    const evidence = await health.evidence();
    expect(evidence.module).toBe('indexer');
    expect(evidence.observation.details.retry_pending).toBe(3);
    expect(evidence.score).toBeNull();
  });
  it('has no success or demo fallback when the first read fails', async () => {
    const health = await openHealth({ failed: true });
    expect(health.text()).toContain('目前無法讀取健康觀測');
    expect(health.text()).not.toContain('服務正常');
    expect(health.text()).not.toContain('38');
  });
  it.each(['invalid', 'missing', 'future-success', 'future-observation', 'frontend-invalid-status', 'frontend-invalid-revision'])('rejects an unsupported or partial response (%s)', async (scenario) => {
    const health = await openHealth({ scenario });
    expect(health.text()).toContain('健康觀測格式無效');
    expect(health.text()).not.toContain('服務正常');
  });
  it('retains observed failures but expires positive observations without making another request', async () => {
    const health = await openHealth(); await health.expire();
    expect(health.text()).toContain('觀測已超過有效期');
    expect(health.coverage()).toContain('0/7');
    expect(health.coverage()).toContain('異常 1');
    expect(health.requests()).toHaveLength(1);
    expect(health.historyRequests()).toHaveLength(1);
  });
  it('does not restore old healthy observations while a failed refresh is unresolved', async () => {
    const health = await openHealth(); health.fail(); await health.reload();
    expect(health.coverage()).toContain('0/7');
    expect(health.text()).toContain('保留上次數值');
    health.recover(); await health.reload();
    expect(health.coverage()).toContain('5/7');
    expect(health.requests().map((request) => request.method)).toEqual(['GET', 'GET', 'GET']);
  });
  it('exports only allowlisted observation fields and keeps review unmeasured', async () => {
    const health = await openHealth({ scenario: 'private' });
    const evidence = await health.evidence();
    expect(evidence.kind).toBe('observed_health');
    expect(evidence.live).toBe(true);
    expect(evidence.quality_review).toBe('unmeasured');
    expect(JSON.stringify(evidence)).not.toContain(fixtures.PRIVATE_HEALTH_DETAIL);
  });
  it('separates measured failures from missing probes and renders successful frontend evidence', async () => {
    const health = await openHealth({ scenario: 'frontend-ok' });
    expect(health.coverage()).toContain('6/7');
    expect(health.observedIssues()).toContain('(1)'); expect(health.missingObservations()).toContain('(1)');
    await health.choose('frontend');
    expect(health.jobCounts()).toContain('HTTP 狀態碼200'); expect(health.jobCounts()).toContain('入口版本ffffffffffff');
    const evidence = await health.evidence();
    expect(evidence.observation.details).toEqual({ http_status: 200, frontend_revision: 'f'.repeat(40) });
    expect(evidence.score).toBeNull();
  });
});
