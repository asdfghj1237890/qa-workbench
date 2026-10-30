/** Model-evaluation presentation. Execution and file ports stay independent. */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, toRefs, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { AGENT, qaDownloadPrefix } from '../lib/runtime.js';
import { apiFetch } from '../lib/qaSession.js';
import { logCaptureErrorKey } from '../lib/qaLogs.js';
import { getCaseSemanticReview, getSemanticReview, semanticReviewKey } from '../lib/qaSemanticReview.js';
import { useLiveExecution } from './useLiveExecution.js';
import { useArtifactFiles } from './useArtifactFiles.js';
import { usePanelDownload } from './usePanelDownload.js';

export function useLivePanel(emit, options = {}) {
  const { locale, t } = useI18n();
  const execution = useLiveExecution({ request: options.request || apiFetch, base: options.base || AGENT + '/qa/evaluations', onStatus: value => emit('status-change', value), onObservation: value => emit('observation-change', value) });
  const { capabilities, job, retryAfter, loading, profiles, ceiling, selectedProfile, budgetValid } = toRefs(execution.state);
  const { isLiveActive } = execution.state;
  const { acknowledged } = toRefs(execution.form);
  const reviewImportError = computed(() => ({ file: 'qaSemanticReview.fileError', storage: 'qaSemanticReview.storageError', import: 'qaSemanticReview.importError' })[execution.state.reviewError] || '');
  const files = useArtifactFiles(options.fileIO);
  const downloads = usePanelDownload({ execution, files, filename: (id, kind) => qaDownloadPrefix() + (kind === 'review' ? '-semantic-review-' : '-live-evaluation-') + id + '.json' });
  const { downloading, reportDownload } = downloads;
  const clearReportDownload = downloads.clear;
  const archiveInput = ref(null);
  const semanticReview = computed(() => getSemanticReview(job.value));
  const caseReview = (entry) => getCaseSemanticReview(job.value, entry);
  const caseReviewPassed = (entry) => Object.values(caseReview(entry)?.scores || {}).every(Boolean);
  const workspaceView = ref("settings");
  const historyOpen = ref(false);
  const historyElement = ref(null);
  const resourceOpen = ref(false);
  const executionLog = ref(null);
  const profileCounts = computed(() => profiles.value.filter((entry) => entry.id !== "quick").map((entry) => t(entry.id === "all" ? "qaFaithfulLive.allProfiles" : "qaLive.profiles." + entry.id) + " " + entry.case_count).join(" / "));
  const workspacePhase = computed(() => workspaceView.value === "settings" || !job.value ? "settings" : isLiveActive(job.value) ? "execution" : "evidence");
  const stateTitleKey = computed(() => workspacePhase.value === "settings" ? "qaRunFlow.settings" : workspacePhase.value === "execution" ? "qaRunFlow.running" : "qaRunFlow.results");
  watch(workspacePhase, (value) => emit("phase-change", value), { immediate: true });
  const startReason = computed(() => {
    if (loading.value) return t("qaFlowLive.loading");
    if (isLiveActive(job.value)) return t("qaLive.settingsLocked");
    if (capabilities.value?.busy) return t("qaLive.busy");
    if (retryAfter.value > 0) return t("qaLive.cooldown", { n: retryAfter.value });
    if (!capabilities.value?.available) return t("qaLive.unavailable");
    if (!selectedProfile.value) return t("qaFlowLive.chooseProfile");
    if (!budgetValid.value) return t("qaFlowLive.invalidBudget", { n: ceiling.value });
    return t(acknowledged.value ? "qaFlowLive.ready" : "qaFlowLive.consentRequired");
  });
  const evidenceGuide = [
    { id: "answers", icon: "chat_bubble_outline" },
    { id: "traces", icon: "account_tree" },
    { id: "rules", icon: "fact_check" },
    { id: "usage", icon: "bar_chart" },
  ];
  const number = (value) => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 2 }).format(value);
  const money = (value) => new Intl.NumberFormat(locale.value, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(value);
  const resourceLimits = computed(() => capabilities.value ? t("qaLive.limits", { model: capabilities.value.model, cases: selectedProfile.value?.case_count || 0, requests: selectedProfile.value?.max_requests || 0, tokens: number(capabilities.value.max_output_tokens), minutes: number(capabilities.value.deadline_seconds / 60) }) : "");
  const resourcePricing = computed(() => capabilities.value?.pricing ? t(capabilities.value.pricing.source === "server_configuration" ? "qaLive.pricingConfigured" : "qaLive.pricing", { input: money(capabilities.value.pricing.input_per_million), output: money(capabilities.value.pricing.output_per_million), date: capabilities.value.pricing.verified_at }) : "");
  const timestamp = (value) => new Intl.DateTimeFormat(locale.value, { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(value));
  watch(() => job.value?.id, clearReportDownload);
  async function openLogs() {
    if (!job.value) return false;
    workspaceView.value = "evidence"; await nextTick();
    if (!executionLog.value) return false;
    await executionLog.value.openStep(""); return true;
  }
  async function showHistory() {
    historyOpen.value = true;
    await nextTick();
    historyElement.value?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    historyElement.value?.focus({ preventScroll: true });
  }
  watch(() => execution.state.selection, value => { if (value) workspaceView.value = value.reason === 'configure' ? 'settings' : 'evidence'; }, { immediate: true });
  async function importReview(file) { if (file) await execution.actions.importEvidence(() => files.readJson(file, { maxBytes: 20 * 1024 * 1024, errorCode: 'file' })); }
  async function selectArchive(event) { const file = files.takeFile(event); if (file) await execution.actions.importEvidence(() => files.readJson(file, { maxBytes: 20 * 1024 * 1024, errorCode: 'file' }), true); }
  async function showJob(id, { logs = false } = {}) { const accepted = await execution.actions.showJob(id); if (accepted && logs) await openLogs(); return accepted; }
  const load = execution.actions.refresh, start = execution.actions.start, cancel = execution.actions.cancel, show = execution.actions.show, prepareRun = execution.actions.prepareRun, startFree = execution.actions.startFree;
  const download = downloads.download, downloadReview = () => download('review');
  onMounted(load); onBeforeUnmount(execution.lifecycle.dispose);
  return {
    state: execution.state, form: execution.form,
    ui: reactive({ semanticReview, caseReview, caseReviewPassed, workspaceView, historyOpen, resourceOpen, profileCounts, workspacePhase, stateTitleKey, startReason, evidenceGuide, number, money, resourceLimits, resourcePricing, timestamp, reviewImportError, downloading, reportDownload, logCaptureErrorKey, semanticReviewKey }),
    dom: { archiveInput, historyElement, executionLog },
    actions: { importReview, selectArchive, openLogs, showHistory, showJob, load, start, cancel, show, prepareRun, startFree, download, downloadReview },
  };
}
