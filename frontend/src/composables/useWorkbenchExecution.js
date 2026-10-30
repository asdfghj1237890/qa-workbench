/** Headless workbench lifecycle. The caller supplies the workbench client port. */
import { computed, onScopeDispose, reactive, readonly, ref } from 'vue';
import { activeRun, runEvidence } from '../lib/workbenchApi.js';

export function useWorkbenchExecution({ client }) {
  const project = ref({}), tasks = ref([]), history = ref([]), sourceSha = ref(null);
  const selectedTaskId = ref(''), selectedRun = ref(null), health = ref(null);
  const maxUsd = ref(1), acknowledgeCost = ref(false), error = ref(''), loading = ref(false);
  const logText = ref(''), logOffset = ref(0), logTruncated = ref(false), revision = ref(0);
  const controller = new AbortController();
  let timer, cancelling = false;
  const selectedTask = computed(() => tasks.value.find(task => task.id === selectedTaskId.value));
  const busy = computed(() => history.value.some(activeRun));
  const evidence = computed(() => runEvidence(selectedRun.value, sourceSha.value));
  const jobOf = value => value?.job || value;
  const current = (id, epoch) => !controller.signal.aborted && revision.value === epoch && selectedRun.value?.id === id;

  function fail(failure) {
    if (!controller.signal.aborted && failure?.name !== 'AbortError') error.value = failure.message || 'Request failed';
  }
  function clearError() { error.value = ''; }
  function resetLogs() { logText.value = ''; logOffset.value = 0; logTruncated.value = false; }
  async function refresh() {
    if (controller.signal.aborted) return;
    loading.value = true; clearError();
    try {
      const [capabilities, runs] = await Promise.all([client.capabilities(controller.signal), client.history(controller.signal)]);
      if (controller.signal.aborted) return;
      project.value = capabilities.project || {};
      sourceSha.value = capabilities.source_sha || project.value.source_sha || null;
      tasks.value = capabilities.tasks || []; history.value = runs.runs || [];
      if (!selectedTaskId.value) selectedTaskId.value = tasks.value[0]?.id || '';
    } catch (failure) { fail(failure); }
    finally { loading.value = false; }
  }
  function chooseTask(task) {
    revision.value++; selectedTaskId.value = task.id; selectedRun.value = null;
    acknowledgeCost.value = false; resetLogs(); clearError();
  }
  async function loadRun(id) {
    if (controller.signal.aborted) return;
    const epoch = revision.value;
    try {
      const result = jobOf(await client.run(id, controller.signal));
      if (!current(id, epoch)) return;
      selectedRun.value = result;
      const logs = await client.logs(id, logOffset.value, controller.signal);
      if (!current(id, epoch)) return;
      logText.value += logs.text || ''; logOffset.value = logs.next_offset ?? logOffset.value;
      logTruncated.value = logs.truncated === true;
    } catch (failure) { if (current(id, epoch)) fail(failure); }
  }
  async function selectRun(run) {
    revision.value++; selectedTaskId.value = run.task_id; selectedRun.value = run;
    acknowledgeCost.value = false; resetLogs(); await loadRun(run.id);
  }
  async function start(options = {}) {
    if (controller.signal.aborted || !selectedTask.value || loading.value || busy.value) return;
    loading.value = true; clearError();
    const epoch = ++revision.value;
    try {
      const result = jobOf(await client.start(selectedTask.value, { options, acknowledgeCost: acknowledgeCost.value, maxUsd: maxUsd.value }, controller.signal));
      acknowledgeCost.value = false;
      if (epoch !== revision.value || controller.signal.aborted) return;
      selectedRun.value = result; resetLogs(); await refresh(); await loadRun(result.id);
    } catch (failure) { if (epoch === revision.value) fail(failure); }
    finally { loading.value = false; }
  }
  async function cancel() {
    if (controller.signal.aborted || cancelling || !activeRun(selectedRun.value)) return;
    const id = selectedRun.value.id, epoch = ++revision.value;
    cancelling = true;
    try {
      const result = jobOf(await client.cancel(id, controller.signal));
      if (!current(id, epoch)) return;
      selectedRun.value = result; await refresh();
    } catch (failure) { if (current(id, epoch)) fail(failure); }
    finally { cancelling = false; }
  }
  async function fetchReport(id) { return client.report(id, controller.signal); }
  async function submitReview(id, value) {
    const epoch = revision.value;
    await client.review(id, value, controller.signal);
    if (!current(id, epoch)) return;
    await loadRun(id); await refresh();
  }
  async function importArtifact(readArtifact) {
    if (controller.signal.aborted) return;
    clearError(); loading.value = true;
    try {
      const artifact = typeof readArtifact === 'function' ? await readArtifact() : readArtifact;
      if (controller.signal.aborted) return;
      const result = jobOf(await client.importRun(artifact, controller.signal));
      if (controller.signal.aborted) return;
      await refresh(); if (result?.id) await selectRun(result);
    } catch (failure) { fail(failure); }
    finally { loading.value = false; }
  }
  async function loadHealth() {
    if (controller.signal.aborted) return;
    clearError();
    try { const observed = await client.health(controller.signal); if (!controller.signal.aborted) health.value = observed; }
    catch (failure) { fail(failure); }
  }
  async function poll() {
    if (controller.signal.aborted) return;
    if (!loading.value && activeRun(selectedRun.value)) {
      await loadRun(selectedRun.value.id);
      if (controller.signal.aborted) return;
      await refresh();
    }
    if (!controller.signal.aborted) timer = setTimeout(poll, 2000);
  }
  async function initialize() {
    await refresh();
    if (!controller.signal.aborted) { clearTimeout(timer); timer = setTimeout(poll, 2000); }
  }
  function dispose() { controller.abort(); clearTimeout(timer); }
  onScopeDispose(dispose);
  return {
    state: readonly(reactive({ project, tasks, history, sourceSha, selectedTaskId, selectedRun, selectedTask, health, loading, error, busy, evidence, logText, logTruncated, revision })),
    form: reactive({ maxUsd, acknowledgeCost }),
    actions: { initialize, refresh, chooseTask, loadRun, selectRun, start, cancel, fetchReport, submitReview, importArtifact, loadHealth, clearError, reportFailure: fail },
    lifecycle: Object.freeze({ signal: controller.signal, dispose }),
  };
}
