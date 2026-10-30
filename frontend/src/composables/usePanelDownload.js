/** Presentation-owned download state, backed by an injected artifact reader. */
import { onScopeDispose, ref, watch } from 'vue';

export function usePanelDownload({ execution, files, filename }) {
  const downloading = ref(false), reportDownload = ref(null);
  function clear() {
    if (reportDownload.value) files.revoke(reportDownload.value);
    reportDownload.value = null;
  }
  watch(() => execution.state.job?.id, clear);
  onScopeDispose(clear);
  async function download(kind = 'report') {
    const job = execution.state.job;
    if (!job?.report_available || downloading.value || execution.lifecycle.signal.aborted) return;
    downloading.value = true; execution.actions.clearError(); clear();
    try {
      const report = await execution.actions.fetchArtifact(job.id, kind);
      if (execution.lifecycle.signal.aborted || execution.state.job?.id !== job.id) return;
      reportDownload.value = files.saveBlob(report, filename(job.id, kind));
    } catch (failure) { clear(); execution.actions.reportFailure(failure); }
    finally { downloading.value = false; }
  }
  return { downloading, reportDownload, download, clear };
}
