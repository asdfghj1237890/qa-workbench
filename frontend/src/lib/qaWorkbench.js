// Workbench evidence is assembled from the existing owner-scoped public QA APIs.
// A currently deployed SHA never supplies missing provenance for an earlier run.
import { corpusResult } from "./qaCorpusEvaluation.js";
const REQUIRED = ["offline_regression", "es_integration"];
const ACTIVE = new Set(["queued", "running"]);
const sha = (value) => typeof value === "string" && /^[a-f0-9]{40}$/.test(value) ? value : null;
const natural = (value) => Number.isSafeInteger(value) && value >= 0;
const active = (job) => !!job && ACTIVE.has(job.status);
const time = (job) => Date.parse(job?.started_at) || 0;
const familyMode = (family, job) => family === "evaluations" ? "model_evaluation" : family === "corpus-evaluations" ? "real_corpus_quality" : job.mode;
const missingActive = (observation, job) => observation?.error === "missing" && active(job) && observation.job?.id === job.id;

function measuredCounts(family, job) {
  if (!job) return null;
  if (family === "evaluations") {
    const { passed, failed } = job.structural || {};
    return natural(passed) && natural(failed) && passed + failed > 0 ? { passed, failed, errors: 0, skipped: 0, total: passed + failed } : null;
  }
  const steps = job.steps || [];
  if (job.mode !== "offline_regression") {
    const checks = steps.flatMap((step) => step.checks || []);
    return checks.length ? { passed: checks.filter((check) => check.status === "passed").length, failed: checks.filter((check) => check.status === "failed").length, errors: 0, skipped: 0, total: checks.length } : null;
  }
  const measured = steps.filter((step) => [step.tests, step.failed, step.errors, step.skipped].every(natural));
  return measured.length ? measured.reduce((sum, step) => ({ passed: sum.passed + Math.max(0, step.tests - step.failed - step.errors - step.skipped), failed: sum.failed + step.failed, errors: sum.errors + step.errors, skipped: sum.skipped + step.skipped, total: sum.total + step.tests }), { passed: 0, failed: 0, errors: 0, skipped: 0, total: 0 }) : null;
}

function measuredComplete(family, job) {
  if (family === "evaluations") return natural(job.total_cases) && job.total_cases > 0 && job.completed_cases === job.total_cases
    && natural(job.structural?.passed) && natural(job.structural?.failed) && job.structural.passed + job.structural.failed === job.total_cases;
  if (!natural(job.total_steps) || !job.total_steps || job.steps?.length !== job.total_steps) return false;
  return job.steps.every((step) => step.status === "completed" && (job.mode === "offline_regression"
    ? [step.tests, step.failed, step.errors, step.skipped].every(natural) && step.tests > 0
      && step.failed + step.errors + step.skipped <= step.tests
    : Array.isArray(step.checks) && step.checks.length > 0 && step.checks.every((check) => ["passed", "failed"].includes(check.status))));
}

function result(family, job, currentSha, { requireRevision = true } = {}) {
  if (family === "corpus-evaluations") {
    const observed = corpusResult(job);
    if (observed.status === "PASS" && (!currentSha || !sha(job.source_sha))) return { ...observed, status: "STALE", reason: "version_unknown" };
    if (observed.status === "PASS" && sha(job.source_sha) !== currentSha) return { ...observed, status: "STALE", reason: "version_mismatch" };
    return observed;
  }
  if (!job) return { status: "NOT RUN", reason: "not_run", counts: null };
  const counts = measuredCounts(family, job);
  if (active(job)) return { status: "RUNNING", reason: "running", counts };
  if (["failed", "timed_out"].includes(job.status) || (counts && counts.failed + counts.errors > 0)) return { status: "FAIL", reason: "failed_checks", counts };
  if (["incomplete", "cancelled"].includes(job.status)) return { status: "INCOMPLETE", reason: "incomplete", counts };
  if (job.status !== "completed") return { status: "UNKNOWN", reason: "unmeasured", counts };
  if (requireRevision && (!currentSha || !sha(job.source_sha))) return { status: "STALE", reason: "version_unknown", counts };
  if (requireRevision && sha(job.source_sha) !== currentSha) return { status: "STALE", reason: "version_mismatch", counts };
  if (!measuredComplete(family, job) || !counts || counts.passed === 0) return { status: "UNKNOWN", reason: "unmeasured", counts };
  if (counts.skipped > 0) return { status: "INCOMPLETE", reason: "skipped_checks", counts };
  return { status: "PASS", reason: "passed", counts };
}

function records(observation, family, currentSha) {
  const merged = new Map();
  for (const job of observation?.capabilities?.recent || []) if (job?.id) merged.set(job.id, job);
  // A later detail observation always wins over an earlier capabilities snapshot.
  if (observation?.job?.id) merged.set(observation.job.id, observation.job);
  return [...merged.values()].map((job) => { const observed = result(family, job, currentSha, { requireRevision: false }); return { family, id: job.id, mode: familyMode(family, job), ...observed, ...(family === "corpus-evaluations" && observed.status === "PASS" && observation.capabilities?.bank?.sha256 !== job.bank.sha256 ? { status: "STALE", reason: "corpus_drift" } : {}), ...(missingActive(observation, job) ? { status: "UNKNOWN", reason: "sync_error" } : {}), startedAt: job.started_at || null, sourceSha: sha(job.source_sha), job }; });
}

export function buildWorkbenchModel({ validation = {}, evaluation = {}, corpus = null } = {}) {
  const validationSha = sha(validation.capabilities?.source_sha), evaluationSha = sha(evaluation.capabilities?.source_sha);
  const sourceSha = validationSha && evaluationSha && validationSha !== evaluationSha ? null : validation.capabilities ? validationSha : evaluationSha;
  const history = [...records(validation, "validations", sourceSha), ...records(evaluation, "evaluations", sourceSha), ...(corpus ? records(corpus, "corpus-evaluations", sourceSha) : [])].sort((a, b) => time(b.job) - time(a.job) || a.family.localeCompare(b.family) || a.id.localeCompare(b.id));
  const validationHistory = history.filter((entry) => entry.family === "validations");
  const rows = REQUIRED.map((mode) => {
    const candidates = validationHistory.filter((entry) => entry.mode === mode && entry.job.suite === "all");
    const entry = candidates.find((candidate) => active(candidate.job)) || candidates[0];
    const measured = result("validations", entry?.job, sourceSha);
    return { mode, job: entry?.job || null, ...measured, ...(missingActive(validation, entry?.job) ? { status: "UNKNOWN", reason: "sync_error" } : {}), ...(!entry && validationHistory.some((candidate) => candidate.mode === mode) ? { reason: "partial_scope" } : {}) };
  });
  const errors = [["validations", validation], ["evaluations", evaluation], ["corpus-evaluations", corpus || {}]].filter(([, observation]) => observation.error).map(([family, observation]) => ({ family, error: observation.error }));
  const loading = !!validation.loading || !!evaluation.loading || !!corpus?.loading;
  const busy = !!validation.capabilities?.busy || !!evaluation.capabilities?.busy || !!corpus?.capabilities?.busy || history.some((entry) => entry.status === "RUNNING");
  const retryAfterSeconds = Math.max(0, Number(validation.capabilities?.retry_after_seconds) || 0, Number(evaluation.capabilities?.retry_after_seconds) || 0);
  const optional = ["real_es_llm_e2e", "model_evaluation"].map((mode) => {
    const family = mode === "model_evaluation" ? "evaluations" : "validations";
    const job = history.find((entry) => entry.mode === mode)?.job || null;
    const available = family === "evaluations" ? evaluation.capabilities?.available === true : validation.capabilities?.modes?.find((entry) => entry.id === mode)?.available === true;
    return { mode, family, available, job, ...result(family, job, sourceSha, { requireRevision: false }), ...(missingActive(family === "evaluations" ? evaluation : validation, job) ? { status: "UNKNOWN", reason: "sync_error" } : {}), ...(!available && !job ? { reason: "unavailable" } : {}) };
  });
  if (corpus) {
    const entry = history.find((entry) => entry.mode === "real_corpus_quality"), job = entry?.job || null;
    optional.push({ mode: "real_corpus_quality", family: "corpus-evaluations", available: corpus.capabilities?.available === true, job, ...corpusResult(null), ...(entry ? { status: entry.status, reason: entry.reason } : {}), ...(corpus.error ? { status: "UNKNOWN", reason: "sync_error" } : {}) });
  }
  const ownedActive = history.find((entry) => entry.status === "RUNNING");
  let readiness;
  if (!validation.capabilities && validation.loading) readiness = "loading";
  else if (!validation.capabilities) readiness = "unknown";
  else if (ownedActive && REQUIRED.includes(ownedActive.mode)) readiness = "running";
  else if (validation.error) readiness = "unknown";
  else if (rows.some((row) => row.status === "FAIL")) readiness = "blocked";
  else if (rows.some((row) => ["STALE", "UNKNOWN"].includes(row.status))) readiness = "unknown";
  else if (rows.every((row) => row.status === "PASS")) readiness = "ready";
  else readiness = "blocked";

  let nextAction;
  if (ownedActive) nextAction = { kind: "resume", mode: ownedActive.mode, family: ownedActive.family, id: ownedActive.id, disabled: false, reason: "running" };
  else if (validation.error || !validation.capabilities) nextAction = { kind: "reload", mode: "offline_regression", family: "validations", id: null, disabled: !!validation.loading, reason: "sync_error" };
  else {
    const target = rows.find((row) => row.status !== "PASS") || rows[rows.length - 1];
    const inspect = ["FAIL", "INCOMPLETE", "UNKNOWN"].includes(target.status) && target.job;
    const available = validation.capabilities.modes?.find((mode) => mode.id === target.mode)?.available === true;
    const cooldown = Number(validation.capabilities.retry_after_seconds) > 0;
    const reason = inspect ? target.reason : busy ? "busy" : cooldown ? "cooldown" : !available ? "unavailable" : target.status === "PASS" ? "ready" : target.reason;
    nextAction = { kind: inspect || target.status === "PASS" ? "details" : "start", mode: target.mode, family: "validations", id: target.job?.id || null, disabled: !inspect && target.status !== "PASS" && (busy || cooldown || !available || !!validation.loading), reason };
  }
  return { sourceSha, loading, errors, readiness, rows, nextAction, latest: history[0] || null, history, optional, busy, retryAfterSeconds };
}
