// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createI18n } from 'vue-i18n';
import { Quasar } from 'quasar';
import QaHealthPanel from '../QaHealthPanel.vue';
import zhTW from '../../i18n/zh-TW.json';
import en from '../../i18n/en.json';
import { buildHealthOverview } from '../../lib/qaHealthView.js';
import { HEALTH_PREVIEW } from '../../lib/qaHealthPreview.js';

const mounted = [];
// Contract: QaHealthPanel renders qaHealthPreview.js frozen visual observations.
// Local mount/actions own DOM, dialog and download plumbing. No API is mocked:
// any attempted network request fails, so the design cannot run a real probe.
async function openHealth({ mobile = false } = {}) {
  const network = vi.fn(() => { throw new Error('Health design must stay offline'); });
  vi.stubGlobal('fetch', network);
  vi.stubGlobal('matchMedia', () => ({ matches: mobile }));
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: 'zh-TW', messages: { 'zh-TW': zhTW, en } });
  const host = document.createElement('div'); host.className = 'qa-workspace'; document.body.appendChild(host);
  const wrapper = mount(QaHealthPanel, { attachTo: host, props: { dark: true, preview: true, model: HEALTH_PREVIEW }, global: { plugins: [Quasar, i18n] } });
  // jsdom has no native modal lifecycle; model open/close on this owned dialog
  // so focus tests exercise the same visible DOM state as a browser showModal.
  const dialog = wrapper.get('dialog').element;
  dialog.showModal = () => dialog.setAttribute('open', '');
  dialog.close = () => dialog.removeAttribute('open');
  mounted.push({ wrapper, host }); await flushPromises();
  const control = (id) => wrapper.get('[data-testid="health-' + id + '"]');
  return {
    text: () => wrapper.text(),
    detail: () => control('detail').text(),
    score: () => control('score').text(),
    evidence: () => JSON.parse(wrapper.get('dialog pre').text()),
    evidenceOpen: () => wrapper.find('dialog > div').exists(),
    summary: () => control('evidence-summary').text(),
    rawVisible: () => wrapper.find('dialog pre').exists() && wrapper.find('dialog pre').isVisible(),
    coverage: () => control('coverage').text(),
    observationNote: () => control('observation-note').text(),
    thresholdRatio: () => control('threshold-ratio').text(),
    serviceSummary: () => control('summary-service').text(),
    requests: () => network.mock.calls.length,
    async choose(id) { await control('module-' + id).trigger('click'); await flushPromises(); },
    async allModules() { await control('filter-all').trigger('click'); },
    modules: () => wrapper.findAll('[data-testid^="health-module-"]').map((row) => row.attributes('data-testid').replace('health-module-', '')),
    async showEvidence() { await control('evidence').trigger('click'); await flushPromises(); },
    async rawEvidence() { await control('evidence-tab-raw').trigger('click'); await flushPromises(); },
    async summaryEvidence() { await control('evidence-tab-summary').trigger('click'); await flushPromises(); },
    async moveEvidenceTab(key) { await control('evidence-tab-summary').trigger('keydown', { key }); await flushPromises(); },
    focusedEvidenceTab: () => document.activeElement?.getAttribute('data-testid'),
    canReturn: () => wrapper.find('[data-testid="health-back-to-issues"]').exists(),
    async returnToIssues() { await control('back-to-issues').trigger('click'); await flushPromises(); },
    scrollIssuesTo(value) { host.scrollTop = value; },
    issueScroll: () => host.scrollTop,
    allFilterSelected: () => control('filter-all').attributes('aria-pressed') === 'true',
    focusedModule: () => document.activeElement?.getAttribute('data-testid'),
    async closeEvidence() { await control('close-evidence').trigger('click'); },
    async refresh() { await control('refresh').trigger('click'); },
    async english() { i18n.global.locale.value = 'en'; await flushPromises(); },
  };
}
afterEach(() => { mounted.splice(0).forEach(({ wrapper, host }) => { wrapper.unmount(); host.remove(); }); vi.unstubAllGlobals(); });

// Independent supplied-observation scenarios exercise presentation of a stale or
// missing dependency. They do not simulate network clients or produce verdicts.
function observeCoverage(scenario) {
  let observations = ['frontend', 'agent', 'es', 'llm', 'crawler', 'indexer', 'collector'].map((id) => ({ id, status: id === 'indexer' ? 'warning' : id === 'collector' ? 'stale' : 'healthy', observedAt: id === 'es' ? '14:32:03' : '14:32:10' }));
  if (scenario === 'expired-service') observations.find((item) => item.id === 'agent').status = 'stale';
  if (scenario === 'missing-service') observations = observations.filter((item) => item.id !== 'es');
  if (scenario === 'no-observations') observations = [];
  return buildHealthOverview(observations);
}

describe('health design preview', () => {
  it('identifies synthetic observations and opens the actionable backlog issue', async () => {
    const health = await openHealth();
    expect(health.text()).toContain('設計示意・非即時資料');
    expect(health.detail()).toContain('最新新聞向量更新延遲');
    expect(health.detail()).toContain('既有新聞與關鍵字搜尋仍可使用');
    expect(health.detail()).toContain('尚無足夠證據確認根因');
    expect(health.text()).toContain('尚無已審查的品質證據');
    expect(health.score()).toBe('—');
    expect(health.thresholdRatio()).toContain('1.9');
  });
  it('never assigns a healthy score to stale collector observations', async () => {
    const health = await openHealth();
    await health.choose('collector');
    expect(health.score()).toBe('—');
    expect(health.detail()).toContain('資料過期');
    expect(health.detail()).toContain('不沿用先前健康判定');
    await health.showEvidence();
    expect(health.summary()).toContain('無法確認目前狀態');
    await health.rawEvidence();
    expect(health.evidence()).toMatchObject({ live: false, module: 'collector', status: 'stale', score: null, root_cause: null });
  });
  it('keeps evidence bound to the selected module and closes its viewer', async () => {
    const health = await openHealth();
    await health.showEvidence();
    expect(health.rawVisible()).toBe(false);
    expect(health.summary()).toContain('超過 20 分鐘');
    await health.rawEvidence();
    expect(health.evidence()).toMatchObject({ kind: 'synthetic_design_preview', module: 'indexer', measurements: { value: 38, threshold: 20, pending_articles: 126 } });
    await health.closeEvidence();
    expect(health.evidenceOpen()).toBe(false);
    await health.choose('es'); await health.showEvidence();
    expect(health.rawVisible()).toBe(false);
    expect(health.summary()).toContain('42 ms');
    await health.rawEvidence();
    expect(health.evidence()).toMatchObject({ module: 'es', measurements: { value: 42, unit: 'milliseconds' } });
  });
  it('lets all module rows open their own observation details', async () => {
    const health = await openHealth();
    await health.allModules();
    expect(health.modules()).toEqual(['indexer', 'collector', 'frontend', 'agent', 'es', 'crawler', 'llm']);
    await health.choose('agent');
    expect(health.detail()).toContain('完整回應成功率');
    expect(health.detail()).toContain('回答內容與來源品質仍需獨立審查');
  });
  it('refreshes only frozen preview data without advancing observations or calling a service', async () => {
    const health = await openHealth();
    await health.refresh(); await health.showEvidence(); await health.rawEvidence();
    expect(health.text()).toContain('未執行真實健康檢查');
    expect(health.evidence().observed_at).toBe('2026-10-26T14:32:10+08:00');
    expect(health.requests()).toBe(0);
  });
  it('translates the selected issue and continues to mark quality review as pending', async () => {
    const health = await openHealth();
    await health.english();
    expect(health.text()).toContain('Design preview · Not live data');
    expect(health.detail()).toContain('Latest-news embeddings are delayed');
    expect(health.text()).toContain('No reviewed quality evidence yet');
    expect(health.text()).toContain('Indexer falling behind');
    expect(health.text()).toContain('Health collector stale data');
    expect(health.text()).not.toContain('qaHealth.');
  });
  it('shows observation coverage, stale-data context and the oldest service observation', async () => {
    const health = await openHealth();
    expect(health.coverage()).toContain('正常 5');
    expect(health.coverage()).toContain('需關注 1');
    expect(health.coverage()).toContain('待確認 1');
    expect(health.coverage()).toContain('6/7');
    expect(health.coverage()).toContain('86%');
    expect(health.serviceSummary()).toContain('4/4');
    expect(health.serviceSummary()).toContain('14:32:03');
    expect(health.observationNote()).toContain('健康資料收集器');
  });
  it('does not call a group healthy when a required service observation expires', () => {
    const observed = observeCoverage('expired-service');
    expect(observed.counts).toEqual({ healthy: 4, warning: 1, critical: 0, unknown: 2 });
    expect(observed.groups.find((group) => group.id === 'service')).toMatchObject({ tone: 'stale', observed: 3, total: 4 });
    expect(observed.groups.find((group) => group.id === 'data')).toMatchObject({ tone: 'warning', warning: 1 });
  });
  it('keeps missing services and empty measurements inconclusive rather than healthy', () => {
    const missing = observeCoverage('missing-service'), empty = observeCoverage('no-observations');
    expect(missing.groups.find((group) => group.id === 'service')).toMatchObject({ tone: 'stale', observed: 3, total: 4 });
    expect(missing).toMatchObject({ observed: 5, total: 7, counts: { healthy: 4, warning: 1, unknown: 2 } });
    expect(missing.coverage).toBe(5 / 7);
    expect(empty.coverage).toBeNull();
    expect(empty.groups.map((group) => group.tone)).toEqual(['stale', 'stale']);
  });
  it('supports keyboard switching between evidence summary and raw data', async () => {
    const health = await openHealth(); await health.showEvidence();
    await health.moveEvidenceTab('ArrowRight');
    expect(health.rawVisible()).toBe(true);
    expect(health.focusedEvidenceTab()).toBe('health-evidence-tab-raw');
    await health.summaryEvidence();
    expect(health.rawVisible()).toBe(false);
    expect(health.summary()).toContain('126');
  });
  it('returns mobile users to the selected module without losing their filter or position', async () => {
    const health = await openHealth({ mobile: true });
    expect(health.canReturn()).toBe(false);
    await health.allModules(); health.scrollIssuesTo(180); await health.choose('collector');
    expect(health.canReturn()).toBe(true);
    expect(health.detail()).toContain('健康觀測資料停止更新');
    expect(health.issueScroll()).toBe(0);
    await health.returnToIssues();
    expect(health.canReturn()).toBe(false);
    expect(health.allFilterSelected()).toBe(true);
    expect(health.focusedModule()).toBe('health-module-collector');
    expect(health.issueScroll()).toBe(180);
  });
});
