/** Contract: useWorkbench/useValidationRun/useLiveEvaluation lifecycle and the
 * workbenchApi, qaValidation and qaLiveEvaluation request/observation contracts.
 * A minimal Vue lifecycle host runs controllers without any workbench panel.
 * Existing frozen panel fixtures remain the source for validation/model records.
 */
import { defineComponent, h, reactive } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { vi } from 'vitest';
import { useWorkbench } from '../../src/composables/useWorkbench.js';
import { useValidationRun } from '../../src/composables/useValidationRun.js';
import { useLiveEvaluation } from '../../src/composables/useLiveEvaluation.js';
import { createWorkbenchClient } from '../../src/lib/workbenchApi.js';
import validationFixtures from '../../e2e/observatory-validation-physical.cjs';
import liveFixtures from '../../e2e/observatory-live-evaluation-physical.cjs';
import { observeReviewedJob, reviewImportBody } from '../../src/lib/__tests__/qa/semantic-review-physical.js';
import zhTW from '../../src/i18n/zh-TW.json';
import en from '../../src/i18n/en.json';

const mounted = [];
let clockStarted = false;
const detached = value => JSON.parse(JSON.stringify(value));

export function disposeExecutionFlows() {
  mounted.splice(0).forEach(driver => driver.unmount());
  if (clockStarted) vi.useRealTimers();
  clockStarted = false;
}

export async function mountExecutionFlow(kind) {
  if (!clockStarted) {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
    vi.setSystemTime(new Date('2026-10-30T00:00:00Z'));
    clockStarted = true;
  }
  let model, job = null, held = null, holdNext = false, failNext = false, heldReadAborted = false, closed = false;
  const calls = [], events = [];
  const tasks = [{ id: 'inventory', paid: false }, { id: 'quality', paid: true }];
  const base = kind === 'workbench' ? '/unit/api' : kind === 'validation' ? '/api/qa/validations' : '/api/qa/evaluations';
  const freshJob = status => kind === 'workbench'
    ? { id: 'unit-run', task_id: 'quality', status, source_sha: 'a'.repeat(40), structural_status: 'passed',
      semantic_status: 'pending_review', quality_passed: false, evidence_kind: 'synthetic', report_available: status === 'completed' }
    : kind === 'validation' ? validationFixtures.jobBody('all', status, 'real_es_llm_e2e') : liveFixtures.jobBody('quick', status, 0.25);
  const reply = value => ({ ok: true, json: async () => detached(value) });
  const expectedReview = () => reviewImportBody(observeReviewedJob({}, value => { value.id = job.id; }));

  async function request(url, options = {}) {
    const path = new URL(url, 'https://controller.test').pathname;
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : undefined;
    calls.push({ path, method, ...(body ? { body } : {}) });
    const suffix = path.slice(base.length);
    if (method === 'POST') {
      if (suffix.endsWith('/cancel')) job = freshJob('cancelled');
      else if (suffix.endsWith('/review')) {
        if (kind === 'live') job = observeReviewedJob({}, value => { value.id = job.id; });
        else job = { ...job, semantic_status: 'reviewed', review: { verdict: body.verdict } };
      } else job = freshJob('queued');
      return reply({ job });
    }
    if (suffix === '/runs') return reply({ runs: job ? [job] : [] });
    if (suffix.endsWith('/logs')) return reply({ text: '', next_offset: 0, truncated: false });
    if (suffix.endsWith('/report')) return reply({ report_sha256: 'b'.repeat(64), review_contract: { rows: [{ row_sha256: 'd'.repeat(64) }] } });
    if (job && suffix.endsWith('/' + job.id)) {
      if (failNext) { failNext = false; return { ok: false, status: 503 }; }
      const value = detached(job);
      if (holdNext) {
        holdNext = false;
        return new Promise((resolve, reject) => {
          held = { resolve: () => { held = null; resolve(reply({ job: value })); } };
          options.signal.addEventListener('abort', () => {
            heldReadAborted = true; held = null; reject(new DOMException('Disposed', 'AbortError'));
          }, { once: true });
        });
      }
      return reply({ job: value });
    }
    if (kind === 'workbench') return reply({ project: { id: 'fixture' }, source_sha: 'a'.repeat(40), tasks });
    if (kind === 'validation') return reply(validationFixtures.capabilitiesBody({ available: true, realAvailable: true, job, busy: ['queued', 'running'].includes(job?.status) }));
    return reply(liveFixtures.capabilitiesBody({ job, busy: ['queued', 'running'].includes(job?.status) }));
  }

  const props = reactive({ requestedMode: '', workbench: false });
  const emit = (name, value) => events.push({ name, value: detached(value) });
  const Host = defineComponent({
    setup() {
      model = kind === 'workbench' ? useWorkbench({ client: createWorkbenchClient({ apiBase: base, request }) })
        : kind === 'validation' ? useValidationRun(props, emit, { request }) : useLiveEvaluation(emit, { request });
      return () => h('div');
    },
  });
  const wrapper = mount(Host, { global: { plugins: [createI18n({ legacy: false, locale: 'zh-TW', messages: { 'zh-TW': zhTW, en } })] } });
  mounted.push(wrapper);
  await flushPromises();
  const flush = async () => { await flushPromises(); };
  return {
    async choosePaidTask() {
      if (kind === 'workbench') model.chooseTask(tasks[1]);
      else if (kind === 'validation') model.prepareRun('real_es_llm_e2e');
      else model.prepareRun();
      await flush();
    },
    async authorizeCost(amount) {
      if (kind === 'workbench') { model.maxUsd.value = amount; model.acknowledgeCost.value = true; }
      else { model.budget.value = amount; model.acknowledged.value = true; }
      await flush();
    },
    async startRun() { await model.start(kind === 'validation' ? 'all' : undefined); await flush(); },
    async cancelRun() { await model.cancel(); await flush(); },
    async advanceTime(milliseconds) { await vi.advanceTimersByTimeAsync(milliseconds); await flush(); },
    async holdNextPoll() { holdNext = true; },
    async releasePoll() { held.resolve(); await flush(); },
    async failNextPoll() { failNext = true; },
    async completeRun() { job = freshJob('completed'); },
    async prepareReview() { await model.prepareReview(); await flush(); },
    async submitReview() {
      if (kind === 'workbench') {
        model.reviewer.value = 'Synthetic fixture reviewer'; model.reviewReason.value = 'Compared the fixture row';
        model.reviewVerdict.value = 'failed'; model.reviewRows.value = JSON.stringify([{ row_sha256: 'd'.repeat(64), verdict: 'failed', reason: 'Fixture mismatch' }]);
        await model.review();
      } else {
        const body = expectedReview();
        await model.importReview({ size: 1024, text: async () => JSON.stringify(body) });
      }
      await flush();
    },
    observation() {
      const observed = kind === 'workbench' ? model.selectedRun.value : model.job.value;
      return detached({ job: observed, acknowledged: (model.acknowledgeCost || model.acknowledged).value,
        calls, mutations: calls.filter(call => call.method === 'POST'), events, error: model.error.value,
        detailReads: calls.filter(call => call.method === 'GET' && call.path.endsWith('/' + observed?.id)).length,
        cancelPath: base + (kind === 'workbench' ? '/runs/' : '/') + observed?.id + '/cancel',
        pendingReads: held ? 1 : 0, heldReadAborted, reviewSaved: model.reviewSaved?.value,
        reviewRows: model.reviewRows ? JSON.parse(model.reviewRows.value) : null, expectedReview: job && kind === 'live' ? expectedReview() : null });
    },
    async close() { if (!closed) wrapper.unmount(); closed = true; await flush(); },
  };
}
