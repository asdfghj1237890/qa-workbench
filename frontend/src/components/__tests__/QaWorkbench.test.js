// @vitest-environment jsdom
import "../../../tests/test-support/panelAdapter.js";
import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createI18n } from 'vue-i18n';
import { Quasar } from 'quasar';
import QaWorkbench from '../QaWorkbench.vue';
import zhTW from '../../i18n/zh-TW.json';
import en from '../../i18n/en.json';

const CURRENT_SHA = 'a'.repeat(40), EARLIER_SHA = 'b'.repeat(40);
const mounted = [];
// Contract: qaWorkbench.js owns measured verdicts; this local browser adapter
// renders observations and records UI intents without API or model execution.
function measuredModel() {
  const latest = { family: 'validations', id: 'owned-regression', mode: 'offline_regression', status: 'PASS', startedAt: '2026-10-21T10:54:00Z', sourceSha: CURRENT_SHA, counts: { passed: 42, failed: 0, errors: 0, skipped: 0, total: 42 }, job: { id: 'owned-regression', source_sha: CURRENT_SHA, suite: 'all' } };
  return { sourceSha: CURRENT_SHA, loading: false, errors: [], readiness: 'blocked', rows: [{ ...latest }, { mode: 'es_integration', status: 'NOT RUN', reason: 'not_run', counts: null }], nextAction: { kind: 'start', mode: 'es_integration', family: 'validations', disabled: false }, latest, history: [latest], optional: [], busy: false, retryAfterSeconds: 0 };
}
async function openWorkbench({ model = measuredModel(), selected = 'es_integration', preview = false, detail = false } = {}) {
  const copy = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal('navigator', { clipboard: { writeText: copy }, userAgent: 'jsdom' });
  const i18n = createI18n({ legacy: false, globalInjection: true, locale: 'zh-TW', messages: { 'zh-TW': zhTW, en } });
  const wrapper = mount(QaWorkbench, { props: { model, selectedMode: selected, preview, detail }, slots: { default: '<div data-testid="controller-fixture">existing controller</div>' }, global: { plugins: [Quasar, i18n] } });
  mounted.push(wrapper); await flushPromises();
  const control = name => wrapper.get('[data-testid="wb-' + name + '"]');
  return {
    text: () => wrapper.text(),
    primary: () => wrapper.emitted('primary') || [], selected: () => wrapper.emitted('select') || [], optional: () => wrapper.emitted('optional') || [], evidence: () => wrapper.emitted('evidence') || [],
    copied: () => copy.mock.calls.map(([value]) => value),
    async next() { await control('primary').trigger('click'); await flushPromises(); },
    async choose(mode) { await control('task-' + mode).trigger('click'); await wrapper.setProps({ selectedMode: mode }); },
    async configure() { await control('configure').trigger('click'); },
    async evidenceOpen() { await control('evidence').trigger('click'); },
    async copyVersion() { const button = wrapper.find('[data-testid="wb-copy-version"]'); if (button.exists()) await button.trigger('click'); },
    async copyEvidenceVersion() { const button = wrapper.find('[data-testid="wb-copy-evidence-version"]'); if (button.exists()) await button.trigger('click'); },
    async change(value) { await wrapper.setProps({ model: value }); await flushPromises(); },
    async detail(value) { await wrapper.setProps({ detail: value }); },
    async toggleSummary() { await wrapper.get('.qt-summary-toggle').trigger('click'); },
    summaryExpanded: () => wrapper.get('.qt-summary-toggle').attributes('aria-expanded'),
    count: name => control('count-' + name).text(),
    nextDisabled: () => control('primary').element.disabled,
    configureDisabled: () => control('configure').element.disabled,
    hasEmptyEvidence: () => wrapper.find('[data-testid="wb-empty-evidence"]').exists(),
    hasCopyVersion: () => wrapper.find('[data-testid="wb-copy-version"]').exists(),
    evidenceName: () => control('evidence').attributes('aria-label'),
    environmentIsInteractive: () => wrapper.find('[data-testid="wb-environment"]').findAll('select,input,button').length > 0,
    hasStaleEvidenceNote: () => wrapper.find('[data-testid="wb-evidence-stale"]').exists(),
    controllerCount: () => wrapper.findAll('[data-testid="controller-fixture"]').length,
    readiness: () => control('readiness-title').text(),
  };
}
afterEach(() => { mounted.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('three-pane verification workbench', () => {
  it('selects a task without opening settings or starting work', async () => {
    const workbench = await openWorkbench();
    await workbench.choose('real_es_llm_e2e');
    expect(workbench.selected()).toEqual([['real_es_llm_e2e']]);
    expect(workbench.optional()).toEqual([]); expect(workbench.primary()).toEqual([]);
    expect(workbench.text()).toContain('只抽一篇新聞、跑兩輪對話');
  });
  it('opens free and paid settings only after the configure action', async () => {
    const workbench = await openWorkbench();
    await workbench.configure(); await workbench.choose('model_evaluation'); await workbench.configure();
    await workbench.choose('real_corpus_quality'); await workbench.configure();
    expect(workbench.optional()).toEqual([['es_integration'], ['model_evaluation'], ['real_corpus_quality']]);
    expect(workbench.primary()).toEqual([]);
  });
  it('passes one explicit suggested action to the page, which owns configuration', async () => {
    const model = measuredModel(), workbench = await openWorkbench({ model });
    expect(workbench.primary()).toEqual([]);
    await workbench.next(); expect(workbench.primary()).toEqual([[model.nextAction]]);
  });
  it('keeps missing measurements unknown rather than turning them into zero', async () => {
    const model = measuredModel(); model.history[0].counts = null;
    const workbench = await openWorkbench({ model, selected: 'offline_regression' });
    expect(['passed', 'failed', 'errors', 'skipped'].map(workbench.count)).toEqual(['—', '—', '—', '—']);
    expect(workbench.text()).toContain('尚無可計數的實測結果'); expect(workbench.text()).not.toContain('907');
  });
  it('keeps run and deployed revisions separate and only copies full valid SHAs', async () => {
    const model = measuredModel(); model.history[0].sourceSha = EARLIER_SHA; model.history[0].job.source_sha = EARLIER_SHA;
    const workbench = await openWorkbench({ model, selected: 'offline_regression' });
    expect(workbench.environmentIsInteractive()).toBe(false); expect(workbench.hasStaleEvidenceNote()).toBe(true);
    expect(workbench.text()).toContain('目前版本'); expect(workbench.text()).toContain('這次執行版本');
    await workbench.copyVersion(); await workbench.copyEvidenceVersion();
    expect(workbench.copied()).toEqual([CURRENT_SHA, EARLIER_SHA]);
    await workbench.change({ ...model, sourceSha: 'Bearer secret-with-spaces' }); await workbench.copyVersion();
    expect(workbench.hasCopyVersion()).toBe(false); expect(workbench.text()).not.toContain('secret-with-spaces');
    expect(workbench.copied()).toEqual([CURRENT_SHA, EARLIER_SHA]);
  });
  it('retains readable empty, loading and failed synchronization states', async () => {
    const workbench = await openWorkbench({ model: {} });
    expect(workbench.hasEmptyEvidence()).toBe(true); expect(workbench.nextDisabled()).toBe(true);
    expect(workbench.readiness()).toContain('目前無法判定發布證據');
    await workbench.change({ loading: true, readiness: 'ready', errors: [] });
    expect(workbench.readiness()).toContain('正在讀取驗證狀態');
    await workbench.change({ ...measuredModel(), readiness: 'unknown', errors: ['untrusted backend text'] });
    expect(workbench.text()).toContain('部分驗證狀態無法讀取'); expect(workbench.text()).not.toContain('untrusted backend text');
    await workbench.change(measuredModel()); await workbench.choose('offline_regression');
    expect(workbench.count('passed')).toBe('42');
  });
  it('opens the selected task evidence with full-log access in its accessible name', async () => {
    const model = measuredModel(), workbench = await openWorkbench({ model, selected: 'offline_regression' });
    await workbench.evidenceOpen();
    expect(workbench.evidence()[0][0].id).toBe(model.latest.id);
    expect(workbench.evidenceName()).toContain('完整 log');
  });
  it('refuses disabled, loading and unexpected paid actions on the free primary path', async () => {
    const model = measuredModel(); model.nextAction.disabled = true;
    const workbench = await openWorkbench({ model }); await workbench.next();
    expect(workbench.primary()).toEqual([]);
    await workbench.change({ ...model, nextAction: { kind: 'start', mode: 'real_es_llm_e2e', disabled: false } });
    expect(workbench.nextDisabled()).toBe(true); await workbench.next(); expect(workbench.primary()).toEqual([]);
    await workbench.change({ ...measuredModel(), loading: true });
    expect(workbench.nextDisabled()).toBe(true); expect(workbench.configureDisabled()).toBe(true);
  });
  it('prevents configuring another run while preserving mounted controllers', async () => {
    const workbench = await openWorkbench({ model: { ...measuredModel(), busy: true } });
    expect(workbench.configureDisabled()).toBe(true);
    await workbench.configure(); expect(workbench.optional()).toEqual([]);
    await workbench.detail(true); expect(workbench.controllerCount()).toBe(1);
    await workbench.detail(false); expect(workbench.controllerCount()).toBe(1);
  });
  it('marks partial results without changing their measured counts', async () => {
    const model = measuredModel(); model.history[0].job.suite = 'rag';
    const workbench = await openWorkbench({ model, selected: 'offline_regression' });
    expect(workbench.text()).toContain('部分範圍'); expect(workbench.text()).toContain('不能代替全部回歸通過');
    expect(workbench.count('passed')).toBe('42');
  });
  it('does not present a completed model contract as semantic quality acceptance', async () => {
    const model = measuredModel(); model.history.push({ ...model.latest, id: 'model-contract', mode: 'model_evaluation', family: 'evaluations', job: { source_sha: CURRENT_SHA } });
    const workbench = await openWorkbench({ model, selected: 'model_evaluation' });
    expect(workbench.text()).toContain('結構通過'); expect(workbench.text()).toContain('基礎通過與答案品質分開判定');
    expect(workbench.readiness()).toBe('發布證據尚未完整');
  });
  it('moves from completed foundation checks to quality setup without a paid start', async () => {
    const workbench = await openWorkbench({ model: { ...measuredModel(), readiness: 'ready' } });
    await workbench.next();
    expect(workbench.optional()).toEqual([['model_evaluation']]);
    expect(workbench.primary()).toEqual([]);
    expect(workbench.readiness()).toBe('發布證據尚未完整');
  });
  it('prioritizes existing failed model evidence after foundation checks are ready', async () => {
    const model = measuredModel(); model.readiness = 'ready'; model.history.push({ ...model.latest, id: 'failed-model', mode: 'model_evaluation', family: 'evaluations', status: 'FAIL' });
    const workbench = await openWorkbench({ model }); await workbench.next();
    expect(workbench.evidence()[0][0].id).toBe('failed-model');
    expect(workbench.optional()).toEqual([]); expect(workbench.primary()).toEqual([]);
  });
  it('shows fixture disclosure only for an explicit preview and expands mobile summary', async () => {
    const live = await openWorkbench(), preview = await openWorkbench({ preview: true });
    expect(live.text()).not.toContain('設計示意'); expect(preview.text()).toContain('設計示意 · 非即時數據');
    expect(live.summaryExpanded()).toBe('false'); await live.toggleSummary(); expect(live.summaryExpanded()).toBe('true');
  });
});
