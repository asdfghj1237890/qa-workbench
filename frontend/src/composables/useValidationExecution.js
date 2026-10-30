/** Headless validation lifecycle. No locale, DOM, files or host singleton. */
import { computed, ref, watch, reactive, readonly, onScopeDispose } from 'vue';
import { validValidationCapabilities, validValidationJob, validValidationPricing, validationModes } from '../lib/qaValidation.js';

export function useValidationExecution({ request: apiFetch, base, requestedMode = () => '', security = { available: false, clear() {}, async token() { throw new Error('turnstile'); } }, onModeChange = () => {}, onStatus = () => {}, onObservation = () => {} }) {
  if (typeof apiFetch !== 'function' || typeof base !== 'string') throw new TypeError('Explicit validation transport required');
  const selection = ref(null); let selectionRevision = 0;
  const busy = ref(false);
  const loading = ref(false);
  const cancelling = ref(false);
  const modes = ref(validationModes());
  const mode = ref("offline_regression");
  const budget = ref(null);
  const acknowledged = ref(false);
  const selectedSuite = ref("all");
  const selectedMode = computed(() => modes.value.find((entry) => entry.id === mode.value));
  const available = computed(() => selectedMode.value.available);
  const isOffline = computed(() => mode.value === "offline_regression");
  const costRequired = computed(() => mode.value === "real_es_llm_e2e" || selectedMode.value.cost_required);
  const turnstileRequired = computed(() => mode.value === "real_es_llm_e2e" && selectedMode.value.turnstile_required === true);
  const budgetCeiling = computed(() => Number(selectedMode.value.limits.max_budget_usd) || 0);
  const budgetValid = computed(() => typeof budget.value === "number" && Number.isFinite(budget.value) && budget.value >= 0.01
      && budget.value <= budgetCeiling.value && validValidationPricing(selectedMode.value.pricing)
      && budget.value >= selectedMode.value.pricing.reserved_estimated_usd);
  const capabilities = ref(null);
  const recent = ref([]);
  const job = ref(null);
  const error = ref("");
  const retryAfter = ref(0);
  const syncIssue = ref(false);
  const missingJob = ref(false);

  const isActive = (value) => value && ["queued", "running"].includes(value.status);
  const runningJob = computed(() => Boolean(isActive(job.value)) && !missingJob.value);
  const cannotStart = computed(() => !available.value || loading.value || busy.value || runningJob.value || retryAfter.value > 0 || (turnstileRequired.value && !security.available)
      || (costRequired.value && (!budgetValid.value || !acknowledged.value)));
  const modeHistory = computed(() => recent.value.filter((entry) => entry.mode === mode.value));
  const finishedSteps = computed(() => job.value?.steps.filter((step) => ["completed", "failed", "timed_out"].includes(step.status)).length || 0);
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
  watch(() => ({ status: summaryJob.value?.status || "not_run", mode: summaryJob.value?.mode || mode.value, tests: countsFor(summaryJob.value)?.tests ?? null, active: Boolean(isActive(summaryJob.value)) && !(missingJob.value && summaryJob.value?.id === job.value?.id), available: available.value, error: error.value || null }), (value) => onStatus(value), { immediate: true });
  watch(() => ({ capabilities: capabilities.value ? { ...capabilities.value, recent: recent.value, busy: busy.value, retry_after_seconds: retryAfter.value } : null, job: job.value, loading: loading.value, error: error.value }), (value) => onObservation(JSON.parse(JSON.stringify(value))), { immediate: true, deep: true });
  const latestFor = (suite) => isActive(job.value) && job.value.mode === mode.value && [suite, "all"].includes(job.value.suite) ? job.value : recent.value.find((entry) => entry.mode === mode.value && (entry.suite === suite || entry.suite === "all"));
  const controller = new AbortController();
  let pollTimer;
  let cooldownTimer;
  let refreshNeeded = false;
  let observationRevision = 0;
  function selectMode(id) {
    if (loading.value) return;
    if (!modes.value.some((entry) => entry.id === id) || runningJob.value) { onModeChange(mode.value); return; }
    selection.value = { reason: "configure", revision: ++selectionRevision };
    if (mode.value === id) { onModeChange(mode.value); return; }
    security.clear(); mode.value = id; acknowledged.value = false; error.value = ""; syncIssue.value = false; missingJob.value = false;
    selectedSuite.value = "all";
    job.value = recent.value.find((entry) => entry.mode === id) || null;
    if (costRequired.value) budget.value = selectedMode.value.limits.default_budget_usd ?? null;
  }
  function prepareRun(id = mode.value) {
    if (loading.value || runningJob.value || !modes.value.some((entry) => entry.id === id)) return false;
    selectMode(id);
    acknowledged.value = false; selectedSuite.value = "all"; security.clear(); selection.value = { reason: "configure", revision: ++selectionRevision };
    return mode.value === id;
  }
  async function startFree(id) {
    if (!["offline_regression", "es_integration"].includes(id) || !prepareRun(id)) return false;
    return start("all");
  }
  async function showJob(id) {
    if (loading.value || !/^[a-zA-Z0-9-]{1,64}$/.test(id) || (runningJob.value && job.value.id !== id)) return false;
    const revision = observationRevision;
    loading.value = true;
    try {
      const value = await request("/" + encodeURIComponent(id));
      if (controller.signal.aborted || revision !== observationRevision) return false;
      if (!validValidationJob(value.job) || value.job.id !== id) throw new Error("schema");
      if (runningJob.value && job.value.id !== id) return false;
      clearTimeout(pollTimer); security.clear(); acknowledged.value = false;
      mode.value = value.job.mode; remember(value.job); error.value = ""; syncIssue.value = false;
      selection.value = { reason: "history", revision: ++selectionRevision }; schedule();

      return true;
    } catch (failure) { failed(failure); return false; }
    finally { loading.value = false; }
  }
  watch([requestedMode, loading], ([value]) => { if (value && value !== mode.value) selectMode(value); }, { immediate: true });
  watch(mode, (value) => onModeChange(value), { immediate: true });
  watch(() => selectedMode.value.suites, (suites) => { if (!suites.includes(selectedSuite.value)) selectedSuite.value = suites.includes("all") ? "all" : suites[0]; }, { immediate: true });
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
    if (controller.signal.aborted) return;
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
        else if (!job.value && modeHistory.value.length) { job.value = modeHistory.value[0]; selection.value = { reason: "restore", revision: ++selectionRevision }; }
      }
      schedule();
    } catch (failure) { if (revision === observationRevision) { failed(failure); syncIssue.value = Boolean(runningJob.value); refreshNeeded = true; schedule(); } } finally { loading.value = false; }
  }
  async function start(suite) {
    if (controller.signal.aborted || cannotStart.value || !selectedMode.value.suites.includes(suite)) return false;
    loading.value = true; error.value = "";
    let submitted = false;
    try {
      const payload = { mode: mode.value, suite, ...(costRequired.value ? { max_usd: budget.value, acknowledge_cost: true } : {}) };
      const token = turnstileRequired.value ? await security.token(controller.signal) : undefined;
      if (controller.signal.aborted) return;
      if (token) payload.cf_token = token;
      submitted = true;
      const value = await request("", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (controller.signal.aborted) return false;
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
    if (controller.signal.aborted || !job.value || cancelling.value) return;
    cancelling.value = true; error.value = ""; observationRevision += 1;
    try {
      const value = await request("/" + encodeURIComponent(job.value.id) + "/cancel", { method: "POST" });
      if (controller.signal.aborted) return;
      if (!validValidationJob(value.job)) throw new Error("schema");
      remember(value.job); busy.value = Boolean(isActive(value.job)); syncIssue.value = false; if (isActive(job.value)) schedule(); else await load();
    } catch (failure) { failed(failure); syncIssue.value = Boolean(isActive(job.value)); schedule(); } finally { cancelling.value = false; }
  }
  function show(entry) { clearTimeout(pollTimer); job.value = entry; selection.value = { reason: "history", revision: ++selectionRevision }; schedule(); }
  function dispose() { controller.abort(); security.clear(); clearTimeout(pollTimer); clearInterval(cooldownTimer); }
  onScopeDispose(dispose);
  async function fetchArtifact(id) {
    if (controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError');
    return (await responseFor('/' + encodeURIComponent(id) + '/report')).blob();
  }
  return {
    state: readonly(reactive({ busy, loading, cancelling, modes, capabilities, recent, job, error, retryAfter, syncIssue, missingJob, selectedMode, available, isOffline, costRequired, turnstileRequired, budgetCeiling, budgetValid, runningJob, cannotStart, modeHistory, finishedSteps, measuredCounts, outcomeCounts, progressPercent, summaryJob, selection, isActive, hasCounts, countsFor, latestFor })),
    form: reactive({ mode, budget, acknowledged, selectedSuite }),
    actions: { refresh: load, selectMode, prepareRun, startFree, start, cancel, show, showJob, fetchArtifact, reportFailure: failed, clearError() { error.value = ''; } },
    lifecycle: Object.freeze({ signal: controller.signal, dispose }),
  };
}
