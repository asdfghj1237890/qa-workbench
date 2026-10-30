/** Owns the panel lifecycle, requests and execution evidence; views keep the public component contract. */
import { qaChallenge } from '../lib/runtime.js';
import { qaDownloadPrefix } from '../lib/runtime.js';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { AGENT, TS_SITEKEY } from "../lib/runtime.js";
import { createCfToken } from "../lib/cfToken.js";
import { apiFetch as defaultApiFetch } from "../lib/qaSession.js";
import { QA_EVIDENCE, QA_REPOSITORY } from "../lib/qa.js";
import { validValidationCapabilities, validValidationJob, validValidationPricing, validationModes } from "../lib/qaValidation.js";
import { logCaptureErrorKey } from "../lib/qaLogs.js";
import { getEvidenceStep } from "../lib/qaEvidence.js";

export function useValidationRun(props, emit, { request: apiFetch = defaultApiFetch } = {}) {
  const { locale, t } = useI18n();
  const evidence = QA_EVIDENCE, repository = QA_REPOSITORY;
  const busy = ref(false), loading = ref(false), cancelling = ref(false), downloading = ref(false);
  const modes = ref(validationModes()), mode = ref("offline_regression"), budget = ref(null), acknowledged = ref(false), reportDownload = ref(null);
  const workspacePhase = ref("settings"), selectedSuite = ref("all");
  const expandedSteps = ref(new Set()), historyDetails = ref(null), historyRequested = ref(false);
  const executionLog = ref(null);
  watch(workspacePhase, (phase) => emit("phase-change", phase), { immediate: true });
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

  const tsBox = ref(null), tsSitekey = TS_SITEKEY, cfToken = createCfToken({ enabled: !!TS_SITEKEY });
  let tsWidgetId = null;
  const selectedMode = computed(() => modes.value.find((entry) => entry.id === mode.value));
  const available = computed(() => selectedMode.value.available);
  const isOffline = computed(() => mode.value === "offline_regression");
  const costRequired = computed(() => mode.value === "real_es_llm_e2e" || selectedMode.value.cost_required);
  const turnstileRequired = computed(() => mode.value === "real_es_llm_e2e" && selectedMode.value.turnstile_required === true);
  const budgetCeiling = computed(() => Number(selectedMode.value.limits.max_budget_usd) || 0);
  const money = (value) => typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(locale.value, { maximumFractionDigits: 6 }).format(value) : "—";
  const budgetValid = computed(() => typeof budget.value === "number" && Number.isFinite(budget.value) && budget.value >= 0.01
    && budget.value <= budgetCeiling.value && validValidationPricing(selectedMode.value.pricing)
    && budget.value >= selectedMode.value.pricing.reserved_estimated_usd);
  const modeStages = computed(() => mode.value === "es_integration" ? ["isolatedEs", "api", "storage"] : ["isolatedEs", "realChain", "guard"]);
  const statusLabel = (status, executionMode) => t('qaValidation.' + (executionMode === "offline_regression" ? "status." : "realStatus.") + status);
  const evidenceText = (value) => JSON.stringify(value, null, 2);
  const capabilities = ref(null), recent = ref([]), job = ref(null), error = ref(""), retryAfter = ref(0), syncIssue = ref(false), missingJob = ref(false);
  const base = `${AGENT}/qa/validations`;
  const isActive = (value) => value && ["queued", "running"].includes(value.status);
  const runningJob = computed(() => Boolean(isActive(job.value)) && !missingJob.value);
  const executionStatus = computed(() => ({ queued: 'QUEUED', running: 'RUNNING', completed: 'COMPLETED', failed: 'FAILED', cancelled: 'CANCELLED', timed_out: 'TIMED OUT', incomplete: 'INCOMPLETE' })[job.value?.status] || 'UNKNOWN');
  const cannotStart = computed(() => !available.value || loading.value || busy.value || runningJob.value || retryAfter.value > 0 || (turnstileRequired.value && !tsSitekey)
    || (costRequired.value && (!budgetValid.value || !acknowledged.value)));
  const modeHistory = computed(() => recent.value.filter((entry) => entry.mode === mode.value));
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
  const finishedSteps = computed(() => job.value?.steps.filter((step) => ["completed", "failed", "timed_out"].includes(step.status)).length || 0);
  const number = (value) => new Intl.NumberFormat(locale.value).format(value || 0);
  const hasCounts = (step) => [step.tests, step.failed, step.errors, step.skipped].every((value) => Number.isSafeInteger(value) && value >= 0);
  const countsFor = (value) => {
    const measured = value?.steps.filter(hasCounts) || [];
    return measured.length ? measured.reduce((sum, step) => ({ tests: sum.tests + step.tests, failed: sum.failed + step.failed + step.errors, skipped: sum.skipped + step.skipped }), { tests: 0, failed: 0, skipped: 0 }) : null;
  };
  const measuredCounts = computed(() => countsFor(job.value));
  const outcomeCounts = computed(() => {
    if (!job.value) return null;
    if (isOffline.value) {
      const measured = job.value.steps.filter(hasCounts);
      return measured.length ? measured.reduce((sum, step) => ({ passed: sum.passed + Math.max(0, step.tests - step.failed - step.errors - step.skipped), failed: sum.failed + step.failed, errors: sum.errors + step.errors, skipped: sum.skipped + step.skipped }), { passed: 0, failed: 0, errors: 0, skipped: 0 }) : null;
    }
    const checks = job.value.steps.flatMap((step) => step.checks || []);
    return checks.length ? { passed: checks.filter((check) => check.status === "passed").length, failed: checks.filter((check) => check.status === "failed").length, errors: 0, skipped: 0 } : null;
  });
  const progressPercent = computed(() => job.value?.total_steps ? Math.round(finishedSteps.value / job.value.total_steps * 100) : 0);
  const summaryJob = computed(() => {
    if (isActive(job.value)) return job.value;
    const active = recent.value.find(isActive);
    if (active && active.id !== job.value?.id) return active;
    return recent.value[0]?.id === job.value?.id ? job.value : recent.value[0] || job.value;
  });
  watch(() => ({ status: summaryJob.value?.status || "not_run", mode: summaryJob.value?.mode || mode.value, tests: countsFor(summaryJob.value)?.tests ?? null, active: Boolean(isActive(summaryJob.value)) && !(missingJob.value && summaryJob.value?.id === job.value?.id), available: available.value, error: error.value || null }), (value) => emit("status-change", value), { immediate: true });
  watch(() => ({ capabilities: capabilities.value ? { ...capabilities.value, recent: recent.value, busy: busy.value, retry_after_seconds: retryAfter.value } : null, job: job.value, loading: loading.value, error: error.value }), (value) => emit("observation-change", JSON.parse(JSON.stringify(value))), { immediate: true, deep: true });
  const timestamp = (value) => new Intl.DateTimeFormat(locale.value, { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(value));
  const resultTimestamp = (value) => new Intl.DateTimeFormat(locale.value, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "Asia/Taipei" }).format(new Date(value));
  const latestFor = (suite) => isActive(job.value) && job.value.mode === mode.value && [suite, "all"].includes(job.value.suite) ? job.value : recent.value.find((entry) => entry.mode === mode.value && (entry.suite === suite || entry.suite === "all"));
  let controller = new AbortController(), pollTimer, cooldownTimer, refreshNeeded = false, observationRevision = 0;
  function clearReportDownload() { if (reportDownload.value) URL.revokeObjectURL(reportDownload.value.url); reportDownload.value = null; }
  function clearSecurityWidget() { if (qaChallenge.widget && tsWidgetId !== null) qaChallenge.widget.remove?.(tsWidgetId); tsWidgetId = null; cfToken.clear(); }
  watch(() => job.value?.id, () => { clearReportDownload(); expandedSteps.value = new Set(); });
  function selectMode(id) {
    if (loading.value) return;
    if (!modes.value.some((entry) => entry.id === id) || runningJob.value) { emit("mode-change", mode.value); return; }
    workspacePhase.value = "settings";
    if (mode.value === id) { emit("mode-change", mode.value); return; }
    clearSecurityWidget(); mode.value = id; acknowledged.value = false; error.value = ""; syncIssue.value = false; missingJob.value = false; clearReportDownload();
    selectedSuite.value = "all";
    job.value = recent.value.find((entry) => entry.mode === id) || null;
    if (costRequired.value) budget.value = selectedMode.value.limits.default_budget_usd ?? null;
  }
  function prepareRun(id = mode.value) {
    if (loading.value || runningJob.value || !modes.value.some((entry) => entry.id === id)) return false;
    selectMode(id);
    acknowledged.value = false; selectedSuite.value = "all"; clearSecurityWidget(); workspacePhase.value = "settings";
    return mode.value === id;
  }
  async function startFree(id) {
    if (!["offline_regression", "es_integration"].includes(id) || !prepareRun(id)) return false;
    return start("all");
  }
  async function openLogs() {
    if (!job.value) return false;
    workspacePhase.value = runningJob.value ? "execution" : "evidence";
    await nextTick();
    if (!executionLog.value) return false;
    await executionLog.value.openStep(""); return true;
  }
  async function showJob(id, { logs = false } = {}) {
    if (loading.value || !/^[a-zA-Z0-9-]{1,64}$/.test(id) || (runningJob.value && job.value.id !== id)) return false;
    const revision = observationRevision;
    loading.value = true;
    try {
      const value = await request("/" + encodeURIComponent(id));
      if (controller.signal.aborted || revision !== observationRevision) return false;
      if (!validValidationJob(value.job) || value.job.id !== id) throw new Error("schema");
      if (runningJob.value && job.value.id !== id) return false;
      clearTimeout(pollTimer); clearSecurityWidget(); acknowledged.value = false;
      mode.value = value.job.mode; remember(value.job); error.value = ""; syncIssue.value = false;
      workspacePhase.value = isActive(value.job) ? "execution" : "evidence"; schedule();
      if (logs) await openLogs();
      return true;
    } catch (failure) { failed(failure); return false; }
    finally { loading.value = false; }
  }
  watch([() => props.requestedMode, loading], ([value]) => { if (value && value !== mode.value) selectMode(value); }, { immediate: true });
  watch(mode, (value) => emit("mode-change", value), { immediate: true });
  watch(() => selectedMode.value.suites, (suites) => { if (!suites.includes(selectedSuite.value)) selectedSuite.value = suites.includes("all") ? "all" : suites[0]; }, { immediate: true });
  watch(() => job.value?.status, (status, previous) => {
    if (["queued", "running"].includes(status)) workspacePhase.value = "execution";
    else if (["queued", "running"].includes(previous)) workspacePhase.value = "evidence";
  });
  async function securityToken() {
    if (!turnstileRequired.value) return undefined;
    await nextTick();
    if (!TS_SITEKEY || !tsBox.value) throw new Error("turnstile");
    cfToken.clear();
    await qaChallenge.load(controller.signal);
    if (tsWidgetId !== null) qaChallenge.widget.reset(tsWidgetId);
    else tsWidgetId = qaChallenge.widget.render(tsBox.value, { sitekey: TS_SITEKEY, size: "compact", callback: (token) => cfToken.set(token), "expired-callback": () => cfToken.clear() });
    const token = await cfToken.get();
    if (!token || controller.signal.aborted) throw new Error("turnstile");
    return token;
  }
  function schedule() {
    clearTimeout(pollTimer);
    if (controller.signal.aborted) return;
    if (runningJob.value) pollTimer = setTimeout(poll, 1000);
    else if (busy.value || refreshNeeded) pollTimer = setTimeout(load, 2000);
  }
  function setCooldown(seconds) {
    clearInterval(cooldownTimer); retryAfter.value = Math.max(0, Math.ceil(Number(seconds) || 0));
    if (retryAfter.value) cooldownTimer = setInterval(() => { retryAfter.value = Math.max(0, retryAfter.value - 1); if (!retryAfter.value) { clearInterval(cooldownTimer); load(); } }, 1000);
  }
  async function responseFor(path = "", init = {}) {
    const response = await apiFetch(base + path, { ...init, cache: "no-store", signal: init.signal || controller.signal });
    if (!response.ok) {
      if (response.status === 429) setCooldown(response.headers?.get("Retry-After") || 60);
      throw new Error(response.status === 409 ? "busy" : response.status === 429 ? "cooldown" : response.status === 503 ? "unavailable" : response.status === 404 ? "missing" : "request");
    }
    return response;
  }
  async function request(path = "", init = {}) {
    if (controller.signal.aborted) throw new DOMException("Cancelled", "AbortError");
    if (init.method && init.method !== "GET") return (await responseFor(path, init)).json();
    const readController = new AbortController();
    const abort = () => readController.abort();
    controller.signal.addEventListener("abort", abort, { once: true });
    let timer;
    try {
      return await Promise.race([
        (async () => (await responseFor(path, { ...init, signal: readController.signal })).json())(),
        new Promise((_, reject) => { timer = setTimeout(() => { readController.abort(); reject(new Error("request")); }, 15000); }),
      ]);
    } finally { clearTimeout(timer); controller.signal.removeEventListener("abort", abort); readController.abort(); }
  }
  function failed(failure) { if (!controller.signal.aborted) error.value = ["busy", "cooldown", "unavailable", "missing", "turnstile"].includes(failure.message) ? failure.message : "request"; }
  function remember(value) {
    if (job.value?.id === value.id && !isActive(job.value) && isActive(value)) return false;
    observationRevision += 1; job.value = value; missingJob.value = false;
    recent.value = [value, ...recent.value.filter((entry) => entry.id !== value.id)].slice(0, 20);
    return true;
  }
  async function load() {
    clearTimeout(pollTimer); loading.value = true;
    const revision = observationRevision;
    try {
      const value = await request();
      if (controller.signal.aborted || revision !== observationRevision) return;
      if (!validValidationCapabilities(value)) throw new Error("schema");
      const observed = value.recent.filter(validValidationJob).map((entry) => entry.id === job.value?.id && !isActive(job.value) && isActive(entry) ? job.value : entry).slice(0, 20);
      if (value.active_job_id && value.recent.some((entry) => entry.id === value.active_job_id) && !observed.some((entry) => entry.id === value.active_job_id)) throw new Error("schema");
      if (job.value && value.recent.some((entry) => entry.id === job.value.id) && !observed.some((entry) => entry.id === job.value.id)) throw new Error("schema");
      capabilities.value = value; modes.value = validationModes(value); busy.value = value.busy === true;
      if (costRequired.value && budget.value === null) budget.value = selectedMode.value.limits.default_budget_usd ?? null;
      recent.value = observed; refreshNeeded = false; error.value = ""; syncIssue.value = false; missingJob.value = false;
      observationRevision += 1;
      setCooldown(value.retry_after_seconds);
      const active = recent.value.find((entry) => entry.id === value.active_job_id && isActive(entry));
      if (active) { mode.value = active.mode; job.value = active; if (costRequired.value && budget.value === null) budget.value = selectedMode.value.limits.default_budget_usd ?? null; }
      else {
        const current = recent.value.find((entry) => entry.id === job.value?.id);
        if (current) job.value = current;
        else if (isActive(job.value)) { missingJob.value = true; syncIssue.value = true; error.value = "missing"; }
        else if (!job.value && modeHistory.value.length) { job.value = modeHistory.value[0]; workspacePhase.value = "evidence"; }
      }
      schedule();
    } catch (failure) { if (revision === observationRevision) { failed(failure); syncIssue.value = Boolean(runningJob.value); refreshNeeded = true; schedule(); } } finally { loading.value = false; }
  }
  async function start(suite) {
    if (cannotStart.value || !selectedMode.value.suites.includes(suite)) return false;
    loading.value = true; error.value = "";
    let submitted = false;
    try {
      const payload = { mode: mode.value, suite, ...(costRequired.value ? { max_usd: budget.value, acknowledge_cost: true } : {}) };
      const token = await securityToken();
      if (controller.signal.aborted) return;
      if (token) payload.cf_token = token;
      submitted = true;
      const value = await request("", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!validValidationJob(value.job) || value.job.mode !== mode.value) throw new Error("schema");
      remember(value.job); busy.value = Boolean(isActive(value.job)); syncIssue.value = false; acknowledged.value = false; schedule(); return true;
    } catch (failure) { failed(failure); if (submitted) { refreshNeeded = true; schedule(); } return false; } finally { loading.value = false; }
  }
  async function poll() {
    if (!runningJob.value) return;
    const jobId = job.value.id;
    const revision = observationRevision;
    try {
      const value = await request("/" + encodeURIComponent(jobId));
      if (controller.signal.aborted || job.value?.id !== jobId || revision !== observationRevision) return;
      if (!validValidationJob(value.job)) throw new Error("schema");
      if (value.job.id !== jobId) throw new Error("schema");
      if (!remember(value.job)) { refreshNeeded = true; schedule(); return; }
      busy.value = Boolean(isActive(value.job)); error.value = ""; syncIssue.value = false;
      if (!isActive(job.value)) await load();
      else schedule();
    } catch (failure) { if (revision === observationRevision) { failed(failure); syncIssue.value = Boolean(runningJob.value); schedule(); } }
  }
  async function cancel() {
    if (!job.value || cancelling.value) return;
    cancelling.value = true; error.value = ""; observationRevision += 1;
    try {
      const value = await request("/" + encodeURIComponent(job.value.id) + "/cancel", { method: "POST" });
      if (!validValidationJob(value.job)) throw new Error("schema");
      remember(value.job); busy.value = Boolean(isActive(value.job)); syncIssue.value = false; if (isActive(job.value)) schedule(); else await load();
    } catch (failure) { failed(failure); syncIssue.value = Boolean(isActive(job.value)); schedule(); } finally { cancelling.value = false; }
  }
  function show(entry) { clearTimeout(pollTimer); job.value = entry; workspacePhase.value = isActive(entry) ? "execution" : "evidence"; schedule(); }
  async function download() {
    if (!job.value?.report_available || downloading.value) return;
    const jobId = job.value.id; downloading.value = true; error.value = ""; clearReportDownload();
    try {
      const response = await responseFor("/" + encodeURIComponent(jobId) + "/report");
      const blob = await response.blob();
      if (controller.signal.aborted || job.value?.id !== jobId) return;
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = qaDownloadPrefix() + "-validation-" + jobId + ".json";
      reportDownload.value = { url, filename: link.download }; document.body.append(link);
      try { link.click(); } finally { link.remove(); }
    } catch (failure) { clearReportDownload(); failed(failure); } finally { downloading.value = false; }
  }
  onMounted(load);
  onBeforeUnmount(() => { controller.abort(); cfToken.set(""); clearSecurityWidget(); clearTimeout(pollTimer); clearInterval(cooldownTimer); clearReportDownload(); });

  return {
    acknowledged, available, budget, budgetCeiling, budgetValid,
    busy, cancel, cancelling, cannotStart, capabilities,
    costRequired, download, downloading, error, evidence,
    evidenceText, executionLog, executionStatus, expandedSteps, finishedSteps,
    hasCounts, historyDetails, historyRequested, isOffline, job,
    latestFor, load, loading, logCaptureErrorKey, measuredCounts,
    missingJob, mode, modeHistory, modeStages, modes,
    money, number, openLogs, outcomeCounts, prepareRun,
    progressPercent, recent, reportDownload, repository, resultTimestamp,
    retryAfter, runningJob, selectMode, selectedEvidence, selectedMode,
    selectedSuite, show, showHistory, showJob, start,
    startFree, startReason, statusLabel, stepDescription, stepResultDescription,
    stepStatusLabel, stepTitle, syncIssue, timestamp, toggleStep,
    tsBox, tsSitekey, turnstileRequired, unavailableReason, workspacePhase
  };
}
