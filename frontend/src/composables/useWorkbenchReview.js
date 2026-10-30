/** Hash-bound review workflow; consumes data and a report/review port, never files. */
import { onScopeDispose, reactive, readonly, ref, watch } from 'vue';

export function useWorkbenchReview({ execution }) {
  const reviewer = ref(''), reviewReason = ref(''), reviewVerdict = ref('failed'), reviewRows = ref('[]');
  const reviewHash = ref(''), loading = ref(false);
  let revision = 0, disposed = false;
  watch(() => execution.state.revision, () => {
    revision++; reviewHash.value = ''; reviewer.value = ''; reviewReason.value = ''; reviewRows.value = '[]';
  }, { flush: 'sync' });
  onScopeDispose(() => { disposed = true; revision++; });
  async function withReport(operation) {
    const id = execution.state.selectedRun?.id, epoch = revision;
    if (!id || disposed || execution.lifecycle.signal.aborted) return;
    loading.value = true; execution.actions.clearError();
    try {
      const artifact = await execution.actions.fetchReport(id);
      if (disposed || execution.lifecycle.signal.aborted || revision !== epoch || execution.state.selectedRun?.id !== id) return;
      await operation(id, artifact);
    } catch (failure) { if (revision === epoch) execution.actions.reportFailure(failure); }
    finally { loading.value = false; }
  }
  async function prepareReview() {
    await withReport((_id, artifact) => {
      reviewHash.value = artifact.report_sha256;
      reviewRows.value = JSON.stringify((artifact.review_contract?.rows || []).map(row => ({ row_sha256: row.row_sha256, verdict: '', reason: '' })), null, 2);
    });
  }
  async function review() {
    await withReport(async (id, artifact) => {
      const rows = JSON.parse(reviewRows.value);
      if (!Array.isArray(rows)) throw new TypeError('Case reviews must be a JSON array');
      await execution.actions.submitReview(id, { report_sha256: artifact.report_sha256, reviewer: reviewer.value.trim(), reason: reviewReason.value.trim(), verdict: reviewVerdict.value, rows });
    });
  }
  return {
    state: readonly(reactive({ reviewHash, loading })),
    form: reactive({ reviewer, reviewReason, reviewVerdict, reviewRows }),
    actions: { prepareReview, review },
  };
}
