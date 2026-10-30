/** Validation presentation and component event compatibility. */
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, toRefs, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { AGENT, TS_SITEKEY, qaChallenge, qaDownloadPrefix } from '../lib/runtime.js';
import { QA_EVIDENCE, QA_REPOSITORY } from '../lib/qa.js';
import { apiFetch } from '../lib/qaSession.js';
import { logCaptureErrorKey } from '../lib/qaLogs.js';
import { getEvidenceStep } from '../lib/qaEvidence.js';
import { useValidationExecution } from './useValidationExecution.js';
import { useValidationChallenge } from './useValidationChallenge.js';
import { useArtifactFiles } from './useArtifactFiles.js';
import { usePanelDownload } from './usePanelDownload.js';

export function useValidationPanel(props, emit, options = {}) {
  const { locale, t } = useI18n();
  const workspacePhase = ref('settings');
  watch(workspacePhase, phase => emit('phase-change', phase), { immediate: true });
  const challenge = useValidationChallenge({ sitekey: TS_SITEKEY, provider: qaChallenge });
  const execution = useValidationExecution({ request: options.request || apiFetch, base: options.base || AGENT + '/qa/validations', requestedMode: () => props.requestedMode, security: challenge,
  onModeChange: value => emit('mode-change', value), onStatus: value => emit('status-change', value), onObservation: value => emit('observation-change', value) });
  const { job, selectedMode, available, costRequired, turnstileRequired, budgetValid, runningJob, busy, loading, retryAfter } = toRefs(execution.state);
  const { mode, acknowledged, selectedSuite } = toRefs(execution.form);
  const files = useArtifactFiles(options.fileIO);
  const downloads = usePanelDownload({ execution, files, filename: id => qaDownloadPrefix() + '-validation-' + id + '.json' });
  const { downloading, reportDownload } = downloads;
  const clearReportDownload = downloads.clear, tsBox = challenge.element, tsSitekey = TS_SITEKEY;
  const evidence = QA_EVIDENCE;
  const repository = QA_REPOSITORY;
  const expandedSteps = ref(new Set());
  const historyDetails = ref(null);
  const historyRequested = ref(false);
  const executionLog = ref(null);
  function toggleStep(index) {
    const expanded = new Set(expandedSteps.value);
    if (expanded.has(index)) expanded.delete(index); else expanded.add(index);
    expandedSteps.value = expanded;
  }
  async function showHistory() {
    historyRequested.value = true;
    await nextTick();
    if (!historyDetails.value) return;
    historyDetails.value.open = true;
    historyDetails.value.focus({ preventScroll: true });
    historyDetails.value.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }
  const money = (value) => typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(locale.value, { maximumFractionDigits: 6 }).format(value) : "—";
  const modeStages = computed(() => mode.value === "es_integration" ? ["isolatedEs", "api", "storage"] : ["isolatedEs", "realChain", "guard"]);
  const statusLabel = (status, executionMode) => t('qaValidation.' + (executionMode === "offline_regression" ? "status." : "realStatus.") + status);
  const evidenceText = (value) => JSON.stringify(value, null, 2);
  const executionStatus = computed(() => ({ queued: 'QUEUED', running: 'RUNNING', completed: 'COMPLETED', failed: 'FAILED', cancelled: 'CANCELLED', timed_out: 'TIMED OUT', incomplete: 'INCOMPLETE' })[job.value?.status] || 'UNKNOWN');
  const selectedEvidence = computed(() => evidence.filter((entry) => selectedSuite.value === "all" || entry.id === selectedSuite.value));
  const unavailableReason = computed(() => t(selectedMode.value.reason === "complete_chain_pricing_required" ? "qaFlowValidation.pricingRequired" : "qaFlowValidation.modeUnavailable"));
  const startReason = computed(() => {
    if (loading.value) return t("qaFlowValidation.loading");
    if (runningJob.value) return t("qaFlowValidation.activeRun");
    if (!available.value) return unavailableReason.value;
    if (busy.value) return t("qaValidation.busy");
    if (retryAfter.value > 0) return t("qaValidation.cooldown", { n: retryAfter.value });
    if (turnstileRequired.value && !tsSitekey) return t("qaValidation.turnstileUnavailable");
    if (costRequired.value && !budgetValid.value) return t("qaFlowValidation.budgetRequired");
    if (costRequired.value && !acknowledged.value) return t("qaFlowValidation.consentRequired");
    return "";
  });
  const stepStatusLabel = (status) => ({ completed: "PASS", failed: "FAIL", pending: "NOT RUN", running: "RUNNING" })[status] || statusLabel(status, mode.value);
  function evidenceStep(name) {
    // The explicit local fixture prefix is presentation-only; preserve the raw
    // backend value in technical details and step-scoped log requests.
    const fixturePrefix = "[OFFLINE FIXTURE] ";
    return getEvidenceStep(name.startsWith(fixturePrefix) ? name.slice(fixturePrefix.length) : name);
  }
  function stepTitle(name) {
    const step = evidenceStep(name);
    return step ? t("qaEvidence.stages." + step.key + ".title") : name;
  }
  function stepDescription(name) {
    const step = evidenceStep(name);
    return t(step ? "qaEvidence.stages." + step.key + ".description" : "qaEvidence.unknownStepDescription");
  }
  function stepResultDescription(status) {
    const key = { completed: "resultCompleted", failed: "resultFailed", running: "resultRunning", pending: "resultPending", queued: "resultPending", cancelled: "resultCancelled", timed_out: "resultTimedOut" }[status] || "resultIncomplete";
    return t("qaEvidence." + key);
  }
  const number = (value) => new Intl.NumberFormat(locale.value).format(value || 0);
  const timestamp = (value) => new Intl.DateTimeFormat(locale.value, { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(value));
  const resultTimestamp = (value) => new Intl.DateTimeFormat(locale.value, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "Asia/Taipei" }).format(new Date(value));
  watch(() => job.value?.id, () => { clearReportDownload(); expandedSteps.value = new Set(); });
  async function openLogs() {
    if (!job.value) return false;
    workspacePhase.value = runningJob.value ? "execution" : "evidence";
    await nextTick();
    if (!executionLog.value) return false;
    await executionLog.value.openStep(""); return true;
  }
  watch(() => job.value?.status, (status, previous) => {
    if (["queued", "running"].includes(status)) workspacePhase.value = "execution";
    else if (["queued", "running"].includes(previous)) workspacePhase.value = "evidence";
  });
  watch(() => execution.state.selection, value => { if (value) workspacePhase.value = value.reason === 'configure' ? 'settings' : runningJob.value ? 'execution' : 'evidence'; }, { immediate: true });
  function selectMode(id) { execution.actions.selectMode(id); if (!loading.value && mode.value === id && !runningJob.value) { workspacePhase.value = 'settings'; clearReportDownload(); } }
  function prepareRun(id) { const accepted = execution.actions.prepareRun(id); if (accepted) { workspacePhase.value = 'settings'; clearReportDownload(); } return accepted; }
  async function showJob(id, { logs = false } = {}) { const accepted = await execution.actions.showJob(id); if (accepted && logs) await openLogs(); return accepted; }
  const load = execution.actions.refresh, cancel = execution.actions.cancel, start = execution.actions.start, startFree = execution.actions.startFree, show = execution.actions.show;
  onMounted(load); onBeforeUnmount(execution.lifecycle.dispose);
  return {
    state: execution.state, form: execution.form,
    ui: reactive({ workspacePhase, downloading, reportDownload, evidence, repository, expandedSteps, historyRequested, money, modeStages, statusLabel, evidenceText, executionStatus, selectedEvidence, unavailableReason, startReason, stepStatusLabel, number, timestamp, resultTimestamp, stepTitle, stepDescription, stepResultDescription, logCaptureErrorKey, tsSitekey }),
    dom: { historyDetails, executionLog, tsBox },
    actions: { load, cancel, start, startFree, show, selectMode, prepareRun, showJob, showHistory, openLogs, toggleStep, download: downloads.download },
  };
}
