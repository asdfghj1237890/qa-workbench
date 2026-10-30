/** Owns the panel lifecycle, requests and execution evidence; views keep the public component contract. */
import { qaDownloadPrefix } from '../lib/runtime.js';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { logCaptureErrorKey } from "../lib/qaLogs.js";
import { AGENT } from "../lib/runtime.js";
import { apiFetch as defaultApiFetch } from "../lib/qaSession.js";
import { isLiveActive as isRawLiveActive, validLiveBudget, validLiveCapabilities, validLiveEvaluationJob } from "../lib/qaLiveEvaluation.js";
import { getCaseSemanticReview, getSemanticReview, semanticReviewKey } from "../lib/qaSemanticReview.js";

export function useLiveEvaluation(emit, { request: apiFetch = defaultApiFetch } = {}) {
  const { locale, t } = useI18n();
  const capabilities = ref(null), job = ref(null), error = ref(""), retryAfter = ref(0);
  const archiveInput = ref(null), importing = ref(false), reviewImportError = ref(""), reviewSaved = ref(false);
  const semanticReview = computed(() => getSemanticReview(job.value));
  const caseReview = (entry) => getCaseSemanticReview(job.value, entry);
  const caseReviewPassed = (entry) => Object.values(caseReview(entry)?.scores || {}).every(Boolean);
  const missingJob = ref(false);
  function isLiveActive(value) { return isRawLiveActive(value) && !(missingJob.value && value?.id === job.value?.id); }
  const workspaceView = ref("settings");
  const historyOpen = ref(false), historyElement = ref(null), resourceOpen = ref(false);
  const executionLog = ref(null);
  const profile = ref("quick"), budget = ref(1), acknowledged = ref(false);
  const loading = ref(false), cancelling = ref(false), downloading = ref(false);
  const reportDownload = ref(null);
  const profiles = computed(() => capabilities.value?.profiles || []);
  const recent = computed(() => capabilities.value?.recent || []);
  const ceiling = computed(() => Math.min(5, capabilities.value?.max_budget_usd || 5));
  const selectedProfile = computed(() => profiles.value.find((entry) => entry.id === profile.value));
  const profileCounts = computed(() => profiles.value.filter((entry) => entry.id !== "quick").map((entry) => t(entry.id === "all" ? "qaFaithfulLive.allProfiles" : "qaLive.profiles." + entry.id) + " " + entry.case_count).join(" / "));
  const budgetValid = computed(() => validLiveBudget(budget.value, ceiling.value));
  const cannotStart = computed(() => !capabilities.value?.available || !selectedProfile.value || !budgetValid.value || !acknowledged.value || loading.value || capabilities.value.busy || isLiveActive(job.value) || retryAfter.value > 0);
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
  const summaryJob = computed(() => {
    if (isLiveActive(job.value)) return job.value;
    const active = recent.value.find(isLiveActive);
    if (active && active.id !== job.value?.id) return active;
    return recent.value[0]?.id === job.value?.id ? job.value : recent.value[0] || job.value;
  });
  watch(() => ({ status: summaryJob.value?.status || "not_run", tests: summaryJob.value?.completed_cases ?? null, active: isLiveActive(summaryJob.value), available: capabilities.value?.available === true, error: error.value || null }), (value) => emit("status-change", value), { immediate: true });
  watch(() => ({ capabilities: capabilities.value, job: job.value, loading: loading.value, error: error.value }), (value) => emit("observation-change", JSON.parse(JSON.stringify(value))), { immediate: true, deep: true });
  const number = (value) => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 2 }).format(value);
  const money = (value) => new Intl.NumberFormat(locale.value, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(value);
  const resourceLimits = computed(() => capabilities.value ? t("qaLive.limits", { model: capabilities.value.model, cases: selectedProfile.value?.case_count || 0, requests: selectedProfile.value?.max_requests || 0, tokens: number(capabilities.value.max_output_tokens), minutes: number(capabilities.value.deadline_seconds / 60) }) : "");
  const resourcePricing = computed(() => capabilities.value?.pricing ? t(capabilities.value.pricing.source === "server_configuration" ? "qaLive.pricingConfigured" : "qaLive.pricing", { input: money(capabilities.value.pricing.input_per_million), output: money(capabilities.value.pricing.output_per_million), date: capabilities.value.pricing.verified_at }) : "");
  const timestamp = (value) => new Intl.DateTimeFormat(locale.value, { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(value));
  const base = `${AGENT}/qa/evaluations`, controller = new AbortController();
  async function importEvidence(file, archive = false) {
    if (!file || loading.value || importing.value || capabilities.value?.busy || isLiveActive(job.value)) return;
    importing.value = true; loading.value = true; reviewImportError.value = ""; reviewSaved.value = false;
    const revision = ++observationRevision;
    let accepted = false;
    try {
      if (!Number.isFinite(file.size) || file.size > 20 * 1024 * 1024) throw new Error("file");
      let value;
      try { value = JSON.parse(await file.text()); } catch (_) { throw new Error("file"); }
      const source = value.review || value;
      const review = { report_sha256: source.report_sha256, reviewer_kind: source.reviewer_kind, reviewer: source.reviewer, reviewed_at: source.reviewed_at, reviews: source.reviews };
      if (archive && (value.version !== 1 || !value.job?.id || !value.report || !value.review)) throw new Error("file");
      const expectedId = archive ? value.job.id : job.value?.id;
      if (!expectedId) throw new Error("file");
      const result = await apiFetch(base + (archive ? "/import" : "/" + encodeURIComponent(expectedId) + "/review"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(archive ? { version: 1, job: value.job, report: value.report, review } : review), cache: "no-store", signal: controller.signal });
      if (!result.ok) throw new Error(result.status === 503 ? "storage" : "import");
      const body = await result.json();
      if (controller.signal.aborted || revision !== observationRevision) return;
      if (!validLiveEvaluationJob(body.job) || body.job.id !== expectedId || !getSemanticReview(body.job)) throw new Error("import");
      job.value = body.job; missingJob.value = false; observationRevision += 1;
      workspaceView.value = "evidence"; acknowledged.value = false; statusReadFailures = 0;
      reviewSaved.value = true; accepted = true;
    } catch (failure) {
      if (!controller.signal.aborted) reviewImportError.value = failure.message === "file" ? "qaSemanticReview.fileError" : failure.message === "storage" ? "qaSemanticReview.storageError" : "qaSemanticReview.importError";
    } finally { importing.value = false; loading.value = false; }
    if (accepted) await load();
  }
  async function importReview(file) { await importEvidence(file); }
  async function selectArchive(event) {
    const file = event.target.files?.[0]; event.target.value = "";
    await importEvidence(file, true);
  }
  let pollTimer, cooldownTimer, initialized = false, statusReadFailures = 0, observationRevision = 0;
  function clearReportDownload() {
    if (reportDownload.value) URL.revokeObjectURL(reportDownload.value.url);
    reportDownload.value = null;
  }
  watch(() => job.value?.id, clearReportDownload);
  function cooldown(seconds) {
    clearInterval(cooldownTimer); retryAfter.value = Math.max(0, Math.ceil(Number(seconds) || 0));
    if (retryAfter.value) cooldownTimer = setInterval(() => { retryAfter.value = Math.max(0, retryAfter.value - 1); if (!retryAfter.value) { clearInterval(cooldownTimer); load(); } }, 1000);
  }
  function schedule() {
    clearTimeout(pollTimer);
    if (controller.signal.aborted || missingJob.value) return;
    const retryDelay = Math.min(8000, 1000 * 2 ** Math.max(0, Math.min(statusReadFailures - 1, 3)));
    if (isLiveActive(job.value)) pollTimer = setTimeout(poll, retryDelay);
    else if (capabilities.value?.busy) pollTimer = setTimeout(load, 2000);
  }
  async function response(path = "", init = {}) {
    const result = await apiFetch(base + path, { ...init, cache: "no-store", signal: init.signal || controller.signal });
    if (!result.ok) {
      if (result.status === 429) cooldown(result.headers?.get("Retry-After") || 300);
      throw new Error(result.status === 409 ? "busy" : result.status === 429 ? "cooldown" : result.status === 503 ? "unavailable" : result.status === 404 ? "missing" : "request");
    }
    return result;
  }
  async function read(path = "") {
    if (controller.signal.aborted) throw new DOMException("Cancelled", "AbortError");
    const readController = new AbortController(), abort = () => readController.abort();
    controller.signal.addEventListener("abort", abort, { once: true });
    let timer;
    try {
      return await Promise.race([
        (async () => (await response(path, { signal: readController.signal })).json())(),
        new Promise((_, reject) => { timer = setTimeout(() => { readController.abort(); reject(new Error("request")); }, 15000); }),
      ]);
    } finally { clearTimeout(timer); controller.signal.removeEventListener("abort", abort); readController.abort(); }
  }
  function failed(failure) { if (!controller.signal.aborted) error.value = ["busy", "cooldown", "unavailable", "missing"].includes(failure.message) ? failure.message : "request"; }
  async function detail(id) {
    const revision = observationRevision;
    const value = await read("/" + encodeURIComponent(id));
    if (controller.signal.aborted || revision !== observationRevision) return false;
    if (!validLiveEvaluationJob(value.job) || value.job.id !== id) throw new Error("schema");
    if (job.value?.id === id && !isRawLiveActive(job.value) && isRawLiveActive(value.job)) return false;
    if (!job.value || job.value.id !== value.job.id) workspaceView.value = "evidence";
    job.value = value.job; missingJob.value = false; observationRevision += 1;
    return true;
  }
  async function load() {
    if (loading.value) return;
    const revision = observationRevision;
    loading.value = true; error.value = "";
    try {
      const value = await read();
      if (controller.signal.aborted || revision !== observationRevision) return;
      if (!validLiveCapabilities(value)) throw new Error("schema");
      capabilities.value = value; cooldown(value.retry_after_seconds);
      if (!initialized) { budget.value = value.default_budget_usd; if (!value.profiles.some((entry) => entry.id === profile.value)) profile.value = value.profiles[0].id; initialized = true; }
      const active = value.recent.find((entry) => entry.id === value.active_job_id && isLiveActive(entry));
      if (active) { if (!await detail(active.id)) { schedule(); return; } }
      else if (job.value && value.recent.some((entry) => entry.id === job.value.id)) { if (!await detail(job.value.id)) { schedule(); return; } }
      else if (!job.value && value.recent.length) { if (!await detail(value.recent[0].id)) return; }
      else if (missingJob.value) throw new Error("missing");
      statusReadFailures = 0; error.value = "";
      schedule();
    } catch (failure) { if (revision === observationRevision) { failed(failure); statusReadFailures += 1; schedule(); } } finally { loading.value = false; }
  }
  async function start() {
    if (cannotStart.value) return;
    loading.value = true; error.value = "";
    try {
      const value = await (await response("", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: profile.value, max_usd: budget.value, acknowledge_cost: true }) })).json();
      if (!validLiveEvaluationJob(value.job)) throw new Error("schema");
      job.value = value.job; missingJob.value = false; observationRevision += 1; statusReadFailures = 0; workspaceView.value = "evidence"; capabilities.value.busy = true; acknowledged.value = false; schedule();
    } catch (failure) { failed(failure); } finally { loading.value = false; }
  }
  async function poll() {
    if (!isLiveActive(job.value)) return;
    if (loading.value) { schedule(); return; }
    const revision = observationRevision;
    try {
      if (!await detail(job.value.id)) { schedule(); return; }
      statusReadFailures = 0; error.value = "";
      if (isLiveActive(job.value)) schedule(); else await load();
    } catch (failure) { if (revision === observationRevision) { failed(failure); if (failure.message === "missing") missingJob.value = true; statusReadFailures += 1; schedule(); } }
  }
  async function cancel() {
    if (!isLiveActive(job.value) || cancelling.value) return;
    cancelling.value = true; error.value = ""; observationRevision += 1;
    try {
      const value = await (await response("/" + encodeURIComponent(job.value.id) + "/cancel", { method: "POST" })).json();
      if (!validLiveEvaluationJob(value.job)) throw new Error("schema");
      job.value = value.job; observationRevision += 1; statusReadFailures = 0; if (isLiveActive(job.value)) schedule(); else await load();
    } catch (failure) { failed(failure); } finally { cancelling.value = false; }
  }
  async function show(id) {
    return showJob(id);
  }
  function prepareRun() {
    if (loading.value || isLiveActive(job.value)) return false;
    acknowledged.value = false;
    workspaceView.value = "settings";
    return true;
  }
  function startFree() { return false; }
  async function openLogs() {
    if (!job.value) return false;
    workspaceView.value = "evidence"; await nextTick();
    if (!executionLog.value) return false;
    await executionLog.value.openStep(""); return true;
  }
  async function showJob(id, { logs = false } = {}) {
    if (loading.value || !/^[a-zA-Z0-9-]{1,64}$/.test(id) || (isLiveActive(job.value) && job.value.id !== id)) return false;
    observationRevision += 1; loading.value = true; error.value = "";
    try {
      if (!await detail(id)) return false;
      clearTimeout(pollTimer); statusReadFailures = 0; workspaceView.value = "evidence"; acknowledged.value = false; schedule();
      if (logs) await openLogs();
      return true;
    } catch (failure) { failed(failure); if (failure.message === "missing" && job.value?.id === id) missingJob.value = true; return false; }
    finally { loading.value = false; }
  }
  async function showHistory() {
    historyOpen.value = true;
    await nextTick();
    historyElement.value?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    historyElement.value?.focus({ preventScroll: true });
  }

  async function downloadReview() { await download("review"); }
  async function download(kind = "report") {
    // Click handlers pass a MouseEvent; only the explicit review action selects a sidecar.
    const review = kind === "review";
    if (!job.value?.report_available || downloading.value) return;
    const jobId = job.value.id;
    downloading.value = true; error.value = "";
    clearReportDownload();
    try {
      const result = await response("/" + encodeURIComponent(jobId) + (review ? "/review" : "/report"));
      const report = await result.blob();
      if (controller.signal.aborted || job.value?.id !== jobId) return;
      const url = URL.createObjectURL(report), link = document.createElement("a");
      link.href = url; link.download = (review ? qaDownloadPrefix() + "-semantic-review-" : qaDownloadPrefix() + "-live-evaluation-") + jobId + ".json";
      reportDownload.value = { url, filename: link.download };
      document.body.append(link);
      try { link.click(); } finally { link.remove(); }
    } catch (failure) { clearReportDownload(); failed(failure); } finally { downloading.value = false; }
  }
  onMounted(load);
  onBeforeUnmount(() => { controller.abort(); clearTimeout(pollTimer); clearInterval(cooldownTimer); clearReportDownload(); });

  return {
    acknowledged, archiveInput, budget, budgetValid, cancel,
    cancelling, cannotStart, capabilities, caseReview, caseReviewPassed,
    ceiling, download, downloadReview, downloading, error,
    evidenceGuide, executionLog, historyElement, historyOpen, importReview,
    importing, isLiveActive, job, load, loading,
    logCaptureErrorKey, missingJob, money, number, openLogs,
    prepareRun, profile, profileCounts, profiles, recent,
    reportDownload, resourceLimits, resourceOpen, resourcePricing, retryAfter,
    reviewImportError, reviewSaved, selectArchive, semanticReview, semanticReviewKey,
    show, showHistory, showJob, start, startFree,
    startReason, stateTitleKey, timestamp, workspacePhase, workspaceView
  };
}
