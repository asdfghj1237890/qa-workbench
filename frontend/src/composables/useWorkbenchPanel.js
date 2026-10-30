/** Browser presentation for the generic workbench. */
import { computed, onMounted, reactive, ref, toRefs } from 'vue';
import { getQaAdapter } from '../lib/runtime.js';
import { createWorkbenchClient } from '../lib/workbenchApi.js';
import { useWorkbenchExecution } from './useWorkbenchExecution.js';
import { useWorkbenchReview } from './useWorkbenchReview.js';
import { useArtifactFiles } from './useArtifactFiles.js';

export function useWorkbenchPanel({ client: providedClient, fileIO } = {}) {
  const adapter = getQaAdapter(), files = useArtifactFiles(fileIO);
  const execution = useWorkbenchExecution({ client: providedClient || createWorkbenchClient({ apiBase: adapter.apiBase, request: adapter.fetch }) });
  const review = useWorkbenchReview({ execution });
  const view = ref('task'), optionsText = ref('{}'), showLogs = ref(true);
  const state = reactive({ ...toRefs(execution.state), loading: computed(() => execution.state.loading || review.state.loading), reviewHash: computed(() => review.state.reviewHash) });
  const form = reactive({ ...toRefs(execution.form), ...toRefs(review.form), optionsText });
  function chooseTask(task) { execution.actions.chooseTask(task); optionsText.value = JSON.stringify(task.default_options || {}, null, 2); view.value = 'task'; }
  async function selectRun(run) { view.value = 'task'; await execution.actions.selectRun(run); }
  async function start() {
    try { await execution.actions.start(JSON.parse(optionsText.value)); }
    catch (failure) { execution.actions.reportFailure(failure); }
  }
  async function downloadReport() {
    const id = execution.state.selectedRun?.id;
    if (!id) return;
    try {
      const report = await execution.actions.fetchReport(id);
      if (!execution.lifecycle.signal.aborted) files.saveJson(report, adapter.id + '-run-' + id.replace(/[^a-z0-9-]/gi, '') + '.json');
    } catch (failure) { execution.actions.reportFailure(failure); }
  }
  async function importEvidence(event) {
    const file = files.takeFile(event);
    if (!file) return;
    await execution.actions.importArtifact(() => files.readJson(file, { maxBytes: 8 * 1024 * 1024, requireSize: false }));
    if (execution.state.selectedRun) view.value = 'task';
  }
  async function openHealth() { view.value = 'health'; await execution.actions.loadHealth(); }
  onMounted(execution.actions.initialize);
  return {
    state, form, ui: reactive({ adapter, view, showLogs }),
    actions: { ...execution.actions, ...review.actions, chooseTask, selectRun, start, downloadReport, importEvidence, openHealth },
  };
}
