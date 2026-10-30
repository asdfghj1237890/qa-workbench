/** Headless model execution and review-import lifecycle. */
import { computed, ref, watch, reactive, readonly, onScopeDispose } from 'vue';
import { isLiveActive as isRawLiveActive, validLiveBudget, validLiveCapabilities, validLiveEvaluationJob } from '../lib/qaLiveEvaluation.js';
import { getSemanticReview } from '../lib/qaSemanticReview.js';

export function useLiveExecution({ request: apiFetch, base, onStatus = () => {}, onObservation = () => {} }) {
  if (typeof apiFetch !== 'function' || typeof base !== 'string') throw new TypeError('Explicit evaluation transport required');
  const selection = ref(null); let selectionRevision = 0;
  const capabilities = ref(null);
  const job = ref(null);
  const error = ref("");
  const retryAfter = ref(0);
  const importing = ref(false);
  const reviewError = ref("");
  const reviewSaved = ref(false);
  const missingJob = ref(false);
  function isLiveActive(value) { return isRawLiveActive(value) && !(missingJob.value && value?.id === job.value?.id); }
  const profile = ref("quick");
  const budget = ref(1);
  const acknowledged = ref(false);
  const loading = ref(false);
  const cancelling = ref(false);
  const profiles = computed(() => capabilities.value?.profiles || []);
  const recent = computed(() => capabilities.value?.recent || []);
  const ceiling = computed(() => Math.min(5, capabilities.value?.max_budget_usd || 5));
  const selectedProfile = computed(() => profiles.value.find((entry) => entry.id === profile.value));
  const budgetValid = computed(() => validLiveBudget(budget.value, ceiling.value));
  const cannotStart = computed(() => !capabilities.value?.available || !selectedProfile.value || !budgetValid.value || !acknowledged.value || loading.value || capabilities.value.busy || isLiveActive(job.value) || retryAfter.value > 0);
  const summaryJob = computed(() => {
    if (isLiveActive(job.value)) return job.value;
    const active = recent.value.find(isLiveActive);
    if (active && active.id !== job.value?.id) return active;
    return recent.value[0]?.id === job.value?.id ? job.value : recent.value[0] || job.value;
  });
  watch(() => ({ status: summaryJob.value?.status || "not_run", tests: summaryJob.value?.completed_cases ?? null, active: isLiveActive(summaryJob.value), available: capabilities.value?.available === true, error: error.value || null }), (value) => onStatus(value), { immediate: true });
  watch(() => ({ capabilities: capabilities.value, job: job.value, loading: loading.value, error: error.value }), (value) => onObservation(JSON.parse(JSON.stringify(value))), { immediate: true, deep: true });
  const controller = new AbortController();
  async function importEvidence(readArtifact, archive = false) {
    if (!readArtifact || controller.signal.aborted || loading.value || importing.value || capabilities.value?.busy || isLiveActive(job.value)) return;
    importing.value = true; loading.value = true; reviewError.value = ""; reviewSaved.value = false;
    const revision = ++observationRevision;
    let accepted = false;
    try {
      const value = typeof readArtifact === 'function' ? await readArtifact() : readArtifact;
      if (controller.signal.aborted || revision !== observationRevision) return;
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
      selection.value = { reason: "observed", revision: ++selectionRevision }; acknowledged.value = false; statusReadFailures = 0;
      reviewSaved.value = true; accepted = true;
    } catch (failure) {
      if (!controller.signal.aborted) reviewError.value = failure.message === "file" ? "file" : failure.message === "storage" ? "storage" : "import";
    } finally { importing.value = false; loading.value = false; }
    if (accepted) await load();
  }
  let pollTimer;
  let cooldownTimer;
  let initialized = false;
  let statusReadFailures = 0;
  let observationRevision = 0;
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
    if (!job.value || job.value.id !== value.job.id) selection.value = { reason: "observed", revision: ++selectionRevision };
    job.value = value.job; missingJob.value = false; observationRevision += 1;
    return true;
  }
  async function load() {
    if (controller.signal.aborted || loading.value) return;
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
    if (controller.signal.aborted || cannotStart.value) return;
    loading.value = true; error.value = "";
    try {
      const value = await (await response("", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: profile.value, max_usd: budget.value, acknowledge_cost: true }) })).json();
      if (controller.signal.aborted) return;
      if (!validLiveEvaluationJob(value.job)) throw new Error("schema");
      job.value = value.job; missingJob.value = false; observationRevision += 1; statusReadFailures = 0; selection.value = { reason: "observed", revision: ++selectionRevision }; capabilities.value.busy = true; acknowledged.value = false; schedule();
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
    if (controller.signal.aborted || !isLiveActive(job.value) || cancelling.value) return;
    cancelling.value = true; error.value = ""; observationRevision += 1;
    try {
      const value = await (await response("/" + encodeURIComponent(job.value.id) + "/cancel", { method: "POST" })).json();
      if (controller.signal.aborted) return;
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
    selection.value = { reason: "configure", revision: ++selectionRevision };
    return true;
  }
  function startFree() { return false; }
  async function showJob(id) {
    if (loading.value || !/^[a-zA-Z0-9-]{1,64}$/.test(id) || (isLiveActive(job.value) && job.value.id !== id)) return false;
    observationRevision += 1; loading.value = true; error.value = "";
    try {
      if (!await detail(id)) return false;
      clearTimeout(pollTimer); statusReadFailures = 0; selection.value = { reason: "observed", revision: ++selectionRevision }; acknowledged.value = false; schedule();

      return true;
    } catch (failure) { failed(failure); if (failure.message === "missing" && job.value?.id === id) missingJob.value = true; return false; }
    finally { loading.value = false; }
  }
  function dispose() { controller.abort(); clearTimeout(pollTimer); clearInterval(cooldownTimer); }
  onScopeDispose(dispose);
  async function fetchArtifact(id, kind) {
    if (controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError');
    return (await response('/' + encodeURIComponent(id) + (kind === 'review' ? '/review' : '/report'))).blob();
  }
  return {
    state: readonly(reactive({ capabilities, job, error, retryAfter, importing, reviewError, reviewSaved, missingJob, loading, cancelling, profiles, recent, ceiling, selectedProfile, budgetValid, cannotStart, summaryJob, selection, isLiveActive })),
    form: reactive({ profile, budget, acknowledged }),
    actions: { refresh: load, start, poll, cancel, show, showJob, prepareRun, startFree, importEvidence, fetchArtifact, reportFailure: failed, clearError() { error.value = ''; } },
    lifecycle: Object.freeze({ signal: controller.signal, dispose }),
  };
}
