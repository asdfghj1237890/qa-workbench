// Presentation only. Verdicts and counts come from buildWorkbenchModel; this
// module never runs work or fills missing measurements with fixture values.
export { WORKBENCH_TASKS } from './runtime.js';
const ACTIVE = new Set(['RUNNING', 'QUEUED']);
const STATUSES = new Set(['PASS', 'FAIL', 'ERROR', 'SKIP', 'RUNNING', 'QUEUED', 'NOT RUN', 'UNKNOWN', 'STALE', 'INCOMPLETE']);
export const validWorkbenchSha = value => typeof value === 'string' && /^[a-f0-9]{40}$/i.test(value) ? value : null;

export function workbenchTaskEntry(model = {}, mode) {
  const history = (model.history || []).filter(entry => entry.mode === mode);
  const entry = history.find(item => ACTIVE.has(item.status)) || history[0];
  const row = (model.rows || []).find(item => item.mode === mode) || (model.optional || []).find(item => item.mode === mode);
  const observed = entry || row || {};
  let status = STATUSES.has(observed.status) ? observed.status : model.loading || model.errors?.length ? 'UNKNOWN' : 'NOT RUN';
  const job = observed.job || null;
  const partial = Boolean(job && mode === 'offline_regression' && job.suite && job.suite !== 'all');
  if (status === 'PASS' && (!validWorkbenchSha(model.sourceSha) || !validWorkbenchSha(job?.source_sha || observed.sourceSha) || model.sourceSha !== (job?.source_sha || observed.sourceSha))) status = 'STALE';
  if (status === 'PASS' && partial) status = 'PARTIAL';
  // A contract/model run can pass its checks while answer quality is unreviewed.
  if (status === 'PASS' && ['model_evaluation', 'real_es_llm_e2e'].includes(mode)) status = 'STRUCTURAL';
  return { ...observed, mode, job, partial, status, counts: observed.counts || null };
}

export function workbenchStatusTone(status) {
  if (['FAIL', 'ERROR'].includes(status)) return 'danger';
  if (['PASS', 'STRUCTURAL'].includes(status)) return 'success';
  if (ACTIVE.has(status)) return 'active';
  if (['STALE', 'INCOMPLETE', 'PARTIAL', 'UNKNOWN'].includes(status)) return 'warning';
  return 'neutral';
}
