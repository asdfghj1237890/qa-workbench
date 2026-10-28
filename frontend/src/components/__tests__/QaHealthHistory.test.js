// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createI18n } from 'vue-i18n';
import fixtures from '../../../e2e/observatory-health-physical.cjs';
import QaHealthHistory from '../QaHealthHistory.vue';
import en from '../../i18n/en.json';
import zhTW from '../../i18n/zh-TW.json';

const physical = vi.hoisted(() => ({ request: null }));
vi.mock("../../lib/runtime.js", async original => { const actual = await original(); return ({ ...actual, get QA_EVIDENCE() { return actual.QA_EVIDENCE; }, get QA_REPOSITORY() { return actual.QA_REPOSITORY; }, get WORKBENCH_TASKS() { return actual.WORKBENCH_TASKS; },  AGENT: '/qa/api'  }); });
vi.mock('../../lib/qaSession.js', () => ({ apiFetch: (...args) => physical.request(...args) }));
const mounted = [];

// Contract: /qa/health/history v1 shared fixture; this local physical owns
// deferred HTTP completion, abort observations and the real Vue component.
async function openHistory({ scenario = 'trend', delayed = false, moduleId = 'indexer', currentReason } = {}) {
  const requests = [], pending = [];
  physical.request = vi.fn((url, options) => {
    const query = new URL(url, 'http://fixture.invalid').searchParams;
    const entry = { module: query.get('module'), window: query.get('window'), method: options.method, signal: options.signal }; requests.push(entry);
    const response = () => ({ ok: scenario !== 'error', status: scenario === 'error' ? 503 : 200,
      json: async () => fixtures.historyBody({ ...entry, scenario }) });
    if (delayed && requests.length === 1) return new Promise((resolve) => pending.push(() => resolve(response())));
    return Promise.resolve(response());
  });
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: 'zh-TW', messages: { 'zh-TW': zhTW, en } });
  const wrapper = mount(QaHealthHistory, { props: { moduleId, currentReason, refreshKey: 'initial' }, global: { plugins: [i18n] } });
  mounted.push(wrapper); await flushPromises();
  return {
    text: () => wrapper.text(), chart: () => wrapper.find('[data-testid="history-chart"]').exists(),
    lines: () => wrapper.findAll('[data-testid="history-line"]').length,
    chartFrame: () => wrapper.get('[data-testid="history-chart"]').attributes('viewBox'),
    requests: () => requests.map((p) => ({ module: p.module, window: p.window, method: p.method, aborted: p.signal.aborted })),
    async chooseWindow(value) { await wrapper.get('[data-testid="history-window-' + value + '"]').trigger('click'); await flushPromises(); },
    async chooseModule(value) { await wrapper.setProps({ moduleId: value }); await flushPromises(); },
    async finishOldRequest() { pending.splice(0).forEach((complete) => complete()); await flushPromises(); },
    async values() { wrapper.get('details').element.open = true; await wrapper.get('details').trigger('toggle'); await flushPromises(); return wrapper.text(); },
  };
}
afterEach(() => mounted.splice(0).forEach((w) => w.unmount()));

describe('history on the live health page', () => {
  it.each([['sampling-lock', '上一輪因作業鎖忙碌而略過'], ['sampling-failed', '上一輪採樣失敗'], ['sampling-delayed', '601 秒']])('separates scheduler outcomes and delays from measured component history (%s)', async (scenario, message) => {
    const page = await openHistory({ scenario });
    expect(page.text()).toContain('最後成功採樣'); expect(page.text()).toContain(message);
    expect(page.text()).toContain('不回填數值'); expect(page.chart()).toBe(true);
  });
  it('rejects unknown scheduler status without inventing a successful sample', async () => {
    const page = await openHistory({ scenario: 'sampling-invalid' });
    expect(page.text()).toContain('歷史觀測目前無法讀取'); expect(page.chart()).toBe(false);
  });
  it('explains passive model data instead of waiting for a synthetic provider probe', async () => {
    const page = await openHistory({ moduleId: 'llm', currentReason: 'llm_no_recent_requests' });
    expect(page.text()).toContain('只在實際請求發生後記錄'); expect(page.chart()).toBe(false);
  });
  it('plots classified model success rate as percent and preserves unmeasured states', async () => {
    const page = await openHistory({ moduleId: 'llm', currentReason: 'llm_requests_failed', scenario: 'llm' });
    expect(page.chart()).toBe(true);
    const values = await page.values(); expect(values).toContain('50'); expect(values).toContain('未量測');
  });
  it('shows measured values, explicit gaps and a separate sampled-status strip', async () => {
    const page = await openHistory();
    expect(page.chart()).toBe(true); expect(page.lines()).toBe(1);
    expect(page.text()).toContain('共 5 筆'); expect(page.text()).toContain('缺失、過期');
    expect(page.requests()).toEqual([{ module: 'indexer', window: '24h', method: 'GET', aborted: false }]);
    const values = await page.values(); expect(values).toContain('aaaaaaaaaaaa'); expect(values).toContain('bbbbbbbbbbbb'); expect(values).toContain('資料過期');
  });
  it('switches bounded windows and cancels the superseded request', async () => {
    const page = await openHistory(); await page.chooseWindow('7d');
    expect(page.requests()).toEqual([{ module: 'indexer', window: '24h', method: 'GET', aborted: true }, { module: 'indexer', window: '7d', method: 'GET', aborted: false }]);
    expect(page.chart()).toBe(true);
  });
  it('does not overwrite a different module with a late response', async () => {
    const page = await openHistory({ delayed: true }); await page.chooseModule('frontend'); await page.finishOldRequest();
    expect(page.text()).toContain('沒有有效量測'); expect(page.lines()).toBe(0);
    expect(page.chart()).toBe(false);
    expect(page.requests()[0].aborted).toBe(true);
  });
  it('shows accumulation explicitly without a fabricated chart', async () => {
    const page = await openHistory({ scenario: 'empty' });
    expect(page.text()).toContain('尚未累積歷史觀測'); expect(page.chart()).toBe(false);
  });
  it.each(['error', 'invalid'])('does not replace unavailable history with synthetic samples (%s)', async (scenario) => {
    const page = await openHistory({ scenario }); expect(page.text()).toContain('歷史觀測目前無法讀取'); expect(page.chart()).toBe(false);
  });
  it('explains an unconnected source instead of suggesting that waiting creates a curve', async () => {
    const page = await openHistory({ moduleId: 'llm', currentReason: 'not_connected' });
    expect(page.chart()).toBe(false);
    expect(page.text()).toContain('尚未接入探測來源');
    expect(page.text()).toContain('繼續等待不會產生數值曲線');
    expect(await page.values()).toContain('未量測');
  });
  it('keeps pre-connection states while waiting for the first scheduled frontend measurement', async () => {
    const page = await openHistory({ moduleId: 'frontend', currentReason: 'frontend_entry_ok' });
    expect(page.chart()).toBe(false);
    expect(page.text()).toContain('等待歷史排程記錄');
    expect(await page.values()).toContain('未量測');
  });
  it('plots actual frontend timings and keeps target revisions separate from the sampler revision', async () => {
    const page = await openHistory({ moduleId: 'frontend', currentReason: 'frontend_entry_ok', scenario: 'frontend' });
    expect(page.chart()).toBe(true); expect(page.lines()).toBe(1);
    const text = await page.values();
    expect(text).toContain('入口版本'); expect(text).toContain('ffffffffffff'); expect(text).toContain('eeeeeeeeeeee');
    expect(text).toContain('異常'); expect(text).toContain('未量測');
    expect(text).not.toContain('aaaaaaaaaaaa');
  });
});
