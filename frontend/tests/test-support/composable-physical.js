/** Contract: headless execution and review cores and the
 * workbenchApi, qaValidation and qaLiveEvaluation request/observation contracts.
 * A Vue effect scope runs the cores in Node, with no DOM, i18n or host adapter.
 * Existing frozen panel fixtures remain the source for validation/model records.
 */
import { effectScope, isReadonly, nextTick, toRefs } from 'vue';
import { vi } from 'vitest';
import { useWorkbenchExecution } from '../../src/composables/useWorkbenchExecution.js';
import { useWorkbenchReview } from '../../src/composables/useWorkbenchReview.js';
import { useValidationExecution } from '../../src/composables/useValidationExecution.js';
import { useLiveExecution } from '../../src/composables/useLiveExecution.js';
import { createWorkbenchClient } from '../../src/lib/workbenchApi.js';
import { executionRequest } from './contracts/composable-api.js';
import validationFixtures from '../../e2e/observatory-validation-physical.cjs';
import liveFixtures from '../../e2e/observatory-live-evaluation-physical.cjs';
import { observeReviewedJob, reviewImportBody } from '../../src/lib/__tests__/qa/semantic-review-physical.js';

const mounted = [];
let clockStarted = false;
const detached = value => JSON.parse(JSON.stringify(value));

export function disposeExecutionFlows() {
  mounted.splice(0).forEach(driver => driver.stop());
  if (clockStarted) vi.useRealTimers();
  clockStarted = false;
}

export async function mountExecutionFlow(kind) {
  if (!clockStarted) {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
    vi.setSystemTime(new Date('2026-10-30T00:00:00Z'));
    clockStarted = true;
  }
  let model, execution, pendingOperation, holdMutation = false, holdReport = false;
  let job = null, held = null, holdNext = false, failNext = false, heldReadAborted = false, closed = false;
  const calls = [], events = [], protocolErrors = [];
  const tasks = [{ id: 'inventory', paid: false }, { id: 'quality', paid: true }];
  const base = kind === 'workbench' ? '/unit/api' : kind === 'validation' ? '/api/qa/validations' : '/api/qa/evaluations';
  const freshJob = status => kind === 'workbench'
    ? { id: 'unit-run', task_id: 'quality', status, source_sha: 'a'.repeat(40), structural_status: 'passed',
      semantic_status: 'pending_review', quality_passed: false, evidence_kind: 'synthetic', report_available: status === 'completed' }
    : kind === 'validation' ? validationFixtures.jobBody('all', status, 'real_es_llm_e2e') : liveFixtures.jobBody('quick', status, 0.25);
  const reply = value => ({ ok: true, json: async () => detached(value), blob: async () => new Blob([JSON.stringify(value)], { type: 'application/json' }) });
  function delayed(value) {
    const snapshot = detached(value);
    return new Promise(resolve => { held = { resolve: () => { held = null; resolve(reply(snapshot)); } }; });
  }
  const expectedReview = () => reviewImportBody(observeReviewedJob({}, value => { value.id = job.id; }));

  async function request(url, options = {}) {
    const parsed = new URL(url, 'https://controller.test'), path = parsed.pathname;
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : undefined;
    calls.push({ path, method, ...(body ? { body } : {}) });
    let route;
    try { route = executionRequest({ kind, base, path, method, body, query: parsed.search }); }
    catch (failure) { protocolErrors.push(failure.message); throw failure; }
    const { operation, id } = route;
    if (id && (!job || id !== job.id)) return { ok: false, status: 404, json: async () => ({ detail: 'missing' }) };
    if (method === 'POST') {
      if (operation === 'cancel') job = freshJob('cancelled');
      else if (operation === 'review') {
        if (kind === 'live') job = observeReviewedJob({}, value => { value.id = job.id; });
        else job = { ...job, semantic_status: 'reviewed', review: { verdict: body.verdict } };
      } else if (operation === 'import') job = { ...body.job, quality_passed: false, ...(kind === 'workbench' ? { historical_import: true } : { archive_imported: true }) };
      else if (operation === 'start') job = freshJob('queued');
      else throw new TypeError('Unhandled mutation: ' + operation);
      if (operation === 'start' && holdMutation) { holdMutation = false; return delayed({ job }); }
      return reply({ job });
    }
    if (operation === 'history') return reply({ runs: job ? [job] : [] });
    if (operation === 'logs') return reply({ text: '', next_offset: 0, truncated: false });
    if (operation === 'report') {
      const artifact = { report_sha256: 'b'.repeat(64), review_contract: { rows: [{ row_sha256: 'd'.repeat(64) }] } };
      if (holdReport) { holdReport = false; return delayed(artifact); }
      return reply(artifact);
    }
    if (operation === 'review') return reply(expectedReview());
    if (operation === 'detail' && job && id === job.id) {
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
    if (operation === 'health') return reply({ status: 'unknown', observations: [] });
    if (operation !== 'capabilities') return { ok: false, status: 404 };
    if (kind === 'workbench') return reply({ project: { id: 'fixture' }, source_sha: 'a'.repeat(40), tasks });
    if (kind === 'validation') return reply(validationFixtures.capabilitiesBody({ available: true, realAvailable: true, job, busy: ['queued', 'running'].includes(job?.status) }));
    return reply(liveFixtures.capabilitiesBody({ job, busy: ['queued', 'running'].includes(job?.status) }));
  }

  const scope = effectScope();
  const emit = (name, value) => events.push({ name, value: detached(value) });
  scope.run(() => {
    execution = kind === 'workbench' ? useWorkbenchExecution({ client: createWorkbenchClient({ apiBase: base, request }) })
      : kind === 'validation' ? useValidationExecution({ request, base, onObservation: value => emit('observation-change', value), onStatus: value => emit('status-change', value) })
      : useLiveExecution({ request, base, onObservation: value => emit('observation-change', value), onStatus: value => emit('status-change', value) });
    const review = kind === 'workbench' ? useWorkbenchReview({ execution }) : null;
    model = { ...toRefs(execution.state), ...toRefs(execution.form), ...execution.actions,
      ...(review ? { ...toRefs(review.state), ...toRefs(review.form), ...review.actions } : {}),
      importReview: value => execution.actions.importEvidence(value),
    };
  });
  mounted.push(scope);
  await (execution.actions.initialize || execution.actions.refresh)();
  const flush = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick(); };
  await flush();
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
    async holdNextStart() { holdMutation = true; },
    async beginStart() { pendingOperation = model.start(kind === 'validation' ? 'all' : undefined); await flush(); },
    async holdNextReport() { holdReport = true; },
    async beginReviewPreparation() { pendingOperation = model.prepareReview(); await flush(); },
    async releaseOperation() { held.resolve(); await pendingOperation; await flush(); },
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
        await model.importReview(expectedReview());
      }
      await flush();
    },
    async restoreEvidence() {
      const archivedJob = kind === 'workbench' ? freshJob('completed') : observeReviewedJob();
      const bundle = kind === 'workbench' ? { job: archivedJob, report: {}, report_sha256: 'b'.repeat(64), review: null }
        : { version: 1, job: archivedJob, report: {}, review: reviewImportBody(archivedJob) };
      if (kind === 'workbench') await execution.actions.importArtifact(bundle);
      else await execution.actions.importEvidence(bundle, true);
      await flush();
    },
    async challengeProtocol(name) {
      const root = kind === 'workbench' ? '/runs' : '';
      const good = kind === 'workbench' ? { task_id: 'quality', options: {}, acknowledge_cost: true, max_usd: 1 }
        : kind === 'validation' ? { mode: 'real_es_llm_e2e', suite: 'all', acknowledge_cost: true, max_usd: 1 }
        : { profile: 'quick', acknowledge_cost: true, max_usd: 1 };
      const challenges = {
        unknownPost: [base + root + '/not/a/route', { method: 'POST', body: '{}' }],
        unknownGet: [base + root + '/not/a/route', {}],
        wrongBase: [base + '-other' + root, { method: 'POST', body: JSON.stringify(good) }],
        wrongMethod: [base + root, { method: 'DELETE' }],
        missingConsent: [base + root, { method: 'POST', body: JSON.stringify({ ...good, acknowledge_cost: false }) }],
        invalidBudget: [base + root, { method: 'POST', body: JSON.stringify({ ...good, max_usd: '1' }) }],
        extraField: [base + root, { method: 'POST', body: JSON.stringify({ ...good, misspelled_option: true }) }],
        invalidCancel: [base + root + '/unit-run/cancel', { method: 'POST', body: JSON.stringify({ unexpected: true }) }],
      };
      try { await request(...challenges[name]); return { accepted: true }; }
      catch (failure) { return { accepted: false, error: failure.message }; }
    },
    observation() {
      const observed = kind === 'workbench' ? model.selectedRun.value : model.job.value;
      return detached({ job: observed, acknowledged: (model.acknowledgeCost || model.acknowledged).value,
        calls, protocolErrors, headless: { readonlyState: isReadonly(execution.state), groups: Object.keys(execution) }, mutations: calls.filter(call => call.method === 'POST'), events, error: model.error.value,
        detailReads: calls.filter(call => call.method === 'GET' && call.path.endsWith('/' + observed?.id)).length,
        cancelPath: base + (kind === 'workbench' ? '/runs/' : '/') + observed?.id + '/cancel',
        pendingReads: held ? 1 : 0, heldReadAborted, reviewSaved: model.reviewSaved?.value,
        reviewHash: model.reviewHash?.value, reviewRows: model.reviewRows ? JSON.parse(model.reviewRows.value) : null, expectedReview: job && kind === 'live' ? expectedReview() : null });
    },
    async close() { if (!closed) scope.stop(); closed = true; await flush(); },
  };
}
