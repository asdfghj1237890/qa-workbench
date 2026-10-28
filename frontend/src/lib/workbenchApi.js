/** Contract: qa_workbench.api; adapters supply transport and project tasks. */
export function startPayload(task, { options = {}, acknowledgeCost = false, maxUsd } = {}) {
  if (!task || typeof task.id !== 'string' || !task.id) throw new TypeError('Select a task');
  if (!options || Array.isArray(options) || typeof options !== 'object') throw new TypeError('Options must be a JSON object');
  const body = { task_id: task.id, options };
  if (task.paid) {
    if (acknowledgeCost !== true || !Number.isFinite(maxUsd) || maxUsd <= 0) throw new TypeError('Paid tasks require explicit consent and a positive USD budget');
    body.acknowledge_cost = true;
    body.max_usd = maxUsd;
  }
  return body;
}

export function createWorkbenchClient({ apiBase = '/api', request = (...args) => fetch(...args) } = {}) {
  const base = apiBase.replace(/\/$/, '');
  async function call(path, options = {}) {
    const response = await request(base + path, { cache: 'no-store', ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
    if (!response.ok) {
      let detail;
      try { detail = (await response.json()).detail; } catch { /* An HTML proxy error still has a meaningful HTTP status. */ }
      const error = new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }
  const runPath = id => '/runs/' + encodeURIComponent(id);
  const mutate = (path, body, signal) => call(path, { method: 'POST', body: JSON.stringify(body), signal });
  return {
    capabilities: signal => call('/capabilities', { signal }),
    history: signal => call('/runs', { signal }),
    health: signal => call('/health', { signal }),
    start: (task, form, signal) => mutate('/runs', startPayload(task, form), signal),
    run: (id, signal) => call(runPath(id), { signal }),
    cancel: (id, signal) => mutate(runPath(id) + '/cancel', {}, signal),
    logs: (id, offset = 0, signal) => call(runPath(id) + '/logs?offset=' + offset + '&limit=32768', { signal }),
    report: (id, signal) => call(runPath(id) + '/report', { signal }),
    review: (id, review, signal) => mutate(runPath(id) + '/review', review, signal),
    importRun: (artifact, signal) => mutate('/runs/import', artifact, signal),
  };
}

export const activeRun = run => ['queued', 'running'].includes(run?.status);
export function runEvidence(run, currentSha) {
  if (!run) return { structural: 'not_run', semantic: 'pending_review', quality: 'not_evaluated', revision: 'unknown' };
  return {
    structural: run.structural_status || 'not_run',
    semantic: run.semantic_status || 'pending_review',
    quality: run.quality_passed === true ? 'passed' : run.semantic_status === 'reviewed' && run.review?.verdict === 'failed' ? 'failed' : 'not_passed',
    revision: !currentSha || !run.source_sha ? 'unknown' : currentSha === run.source_sha ? 'current' : 'historical',
  };
}
