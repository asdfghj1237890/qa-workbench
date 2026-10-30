/** Generic execution lifecycle, cancellation and hash-bound review.
 * Each invocation owns its refs, selection revision and cancellation signal.
 * Call inside setup(); an injected client follows createWorkbenchClient's port.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { getQaAdapter } from '../lib/runtime.js';
import { activeRun, createWorkbenchClient, runEvidence } from '../lib/workbenchApi.js';

export function useWorkbench({ client: providedClient } = {}) {
  const adapter = getQaAdapter();
  const client = providedClient || createWorkbenchClient({ apiBase: adapter.apiBase, request: adapter.fetch });
  const project = ref({}), tasks = ref([]), history = ref([]), sourceSha = ref(null);
  const selectedTaskId = ref(''), selectedRun = ref(null), view = ref('task');
  const optionsText = ref('{}'), maxUsd = ref(1), acknowledgeCost = ref(false);
  const error = ref(''), loading = ref(false), health = ref(null);
  const logText = ref(''), logOffset = ref(0), logTruncated = ref(false), showLogs = ref(true);
  const reviewer = ref(''), reviewReason = ref(''), reviewVerdict = ref('failed');
  const reviewRows = ref('[]'), reviewHash = ref('');
  const lifecycle = new AbortController();
  let timer, selectionEpoch = 0;

  const selectedTask = computed(() => tasks.value.find(task => task.id === selectedTaskId.value));
  const busy = computed(() => history.value.some(activeRun));
  const evidence = computed(() => runEvidence(selectedRun.value, sourceSha.value));
  const json = value => JSON.stringify(value, null, 2);
  const jobOf = value => value?.job || value;

  function fail(failure) {
    if (!lifecycle.signal.aborted && failure?.name !== 'AbortError') {
      error.value = failure.message || 'Request failed';
    }
  }

  async function refresh() {
    if (lifecycle.signal.aborted) return;
    loading.value = true;
    error.value = '';
    try {
      const [capabilities, runs] = await Promise.all([
        client.capabilities(lifecycle.signal), client.history(lifecycle.signal),
      ]);
      if (lifecycle.signal.aborted) return;
      project.value = capabilities.project || {};
      sourceSha.value = capabilities.source_sha || project.value.source_sha || null;
      tasks.value = capabilities.tasks || [];
      history.value = runs.runs || [];
      if (!selectedTaskId.value) selectedTaskId.value = tasks.value[0]?.id || '';
    } catch (failure) {
      fail(failure);
    } finally {
      loading.value = false;
    }
  }

  function chooseTask(task) {
    selectionEpoch++;
    selectedTaskId.value = task.id;
    selectedRun.value = null;
    acknowledgeCost.value = false;
    optionsText.value = json(task.default_options || {});
    logText.value = '';
    logOffset.value = 0;
    view.value = 'task';
    error.value = '';
  }

  function resetLogs() {
    logText.value = '';
    logOffset.value = 0;
    logTruncated.value = false;
    reviewer.value = '';
    reviewReason.value = '';
    reviewRows.value = '[]';
    reviewHash.value = '';
  }

  async function loadRun(id) {
    if (lifecycle.signal.aborted) return;
    const epoch = selectionEpoch;
    try {
      const result = jobOf(await client.run(id, lifecycle.signal));
      if (lifecycle.signal.aborted || epoch !== selectionEpoch || selectedRun.value?.id !== id) return;
      selectedRun.value = result;
      const logs = await client.logs(id, logOffset.value, lifecycle.signal);
      if (lifecycle.signal.aborted || epoch !== selectionEpoch || selectedRun.value?.id !== id) return;
      logText.value += logs.text || '';
      logOffset.value = logs.next_offset ?? logOffset.value;
      logTruncated.value = logs.truncated === true;
    } catch (failure) {
      fail(failure);
    }
  }

  async function selectRun(run) {
    selectionEpoch++;
    selectedTaskId.value = run.task_id;
    selectedRun.value = run;
    acknowledgeCost.value = false;
    resetLogs();
    view.value = 'task';
    await loadRun(run.id);
  }

  async function start() {
    if (lifecycle.signal.aborted || !selectedTask.value || loading.value || busy.value) return;
    loading.value = true;
    error.value = '';
    const epoch = ++selectionEpoch;
    try {
      const options = JSON.parse(optionsText.value);
      const result = jobOf(await client.start(selectedTask.value, {
        options, acknowledgeCost: acknowledgeCost.value, maxUsd: maxUsd.value,
      }, lifecycle.signal));
      acknowledgeCost.value = false;
      if (epoch !== selectionEpoch || lifecycle.signal.aborted) return;
      selectedRun.value = result;
      resetLogs();
      await refresh();
      await loadRun(result.id);
    } catch (failure) {
      fail(failure);
    } finally {
      loading.value = false;
    }
  }

  async function cancel() {
    if (lifecycle.signal.aborted || !selectedRun.value || !activeRun(selectedRun.value)) return;
    try {
      const result = jobOf(await client.cancel(selectedRun.value.id, lifecycle.signal));
      if (lifecycle.signal.aborted) return;
      selectedRun.value = result;
      await refresh();
    } catch (failure) {
      fail(failure);
    }
  }

  function save(filename, value) {
    const url = URL.createObjectURL(new Blob([json(value)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function downloadReport() {
    const id = selectedRun.value?.id;
    if (!id) return;
    try {
      const report = await client.report(id, lifecycle.signal);
      if (lifecycle.signal.aborted) return;
      save(adapter.id + '-run-' + id.replace(/[^a-z0-9-]/gi, '') + '.json', report);
    } catch (failure) {
      fail(failure);
    }
  }

  async function prepareReview() {
    const id = selectedRun.value?.id;
    if (!id) return;
    loading.value = true;
    error.value = '';
    try {
      const artifact = await client.report(id, lifecycle.signal);
      if (lifecycle.signal.aborted || selectedRun.value?.id !== id) return;
      reviewHash.value = artifact.report_sha256;
      reviewRows.value = json((artifact.review_contract?.rows || []).map(row => ({
        row_sha256: row.row_sha256, verdict: '', reason: '',
      })));
    } catch (failure) {
      fail(failure);
    } finally {
      loading.value = false;
    }
  }

  async function review() {
    const id = selectedRun.value?.id;
    if (!id) return;
    loading.value = true;
    error.value = '';
    try {
      const artifact = await client.report(id, lifecycle.signal);
      if (lifecycle.signal.aborted || selectedRun.value?.id !== id) return;
      const rows = JSON.parse(reviewRows.value);
      if (!Array.isArray(rows)) throw new TypeError('Case reviews must be a JSON array');
      await client.review(id, {
        report_sha256: artifact.report_sha256, reviewer: reviewer.value.trim(),
        reason: reviewReason.value.trim(), verdict: reviewVerdict.value, rows,
      }, lifecycle.signal);
      await loadRun(id);
      await refresh();
    } catch (failure) {
      fail(failure);
    } finally {
      loading.value = false;
    }
  }

  async function importEvidence(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    error.value = '';
    loading.value = true;
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error('Import exceeds 8 MiB');
      const artifact = JSON.parse(await file.text());
      if (lifecycle.signal.aborted) return;
      const result = jobOf(await client.importRun(artifact, lifecycle.signal));
      if (lifecycle.signal.aborted) return;
      await refresh();
      if (result?.id) await selectRun(result);
    } catch (failure) {
      fail(failure);
    } finally {
      loading.value = false;
      event.target.value = '';
    }
  }

  async function openHealth() {
    if (lifecycle.signal.aborted) return;
    view.value = 'health';
    error.value = '';
    try {
      const observed = await client.health(lifecycle.signal);
      if (!lifecycle.signal.aborted) health.value = observed;
    } catch (failure) {
      fail(failure);
    }
  }

  async function poll() {
    if (lifecycle.signal.aborted) return;
    if (!loading.value && selectedRun.value && activeRun(selectedRun.value)) {
      await loadRun(selectedRun.value.id);
      if (lifecycle.signal.aborted) return;
      await refresh();
    }
    if (!lifecycle.signal.aborted) timer = setTimeout(poll, 2000);
  }

  onMounted(async () => {
    await refresh();
    if (!lifecycle.signal.aborted) timer = setTimeout(poll, 2000);
  });
  onBeforeUnmount(() => {
    lifecycle.abort();
    clearTimeout(timer);
  });

  return {
    adapter, project, sourceSha, loading, refresh, error, tasks, selectedTaskId, chooseTask,
    view, history, openHealth, importEvidence, optionsText, maxUsd, acknowledgeCost,
    selectedTask, selectedRun, busy, start, cancel, showLogs, reviewer, reviewReason,
    reviewVerdict, reviewRows, evidence, logText, logTruncated, reviewHash, loadRun,
    downloadReport, prepareReview, review, selectRun, health,
  };
}
