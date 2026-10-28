import { buildWorkbenchModel } from "./qaWorkbench.js";
import { getEvidenceCode } from "./qaEvidence.js";
import { getSemanticReview } from "./qaSemanticReview.js";

// Contract: owner-scoped QA job/capabilities APIs. A completed process is not a
// release verdict; only full, measured, same-revision evidence satisfies a gate.
const BASIC = ["offline_regression", "es_integration"];
const revision = (value) => typeof value === "string" && /^[a-f0-9]{40}$/.test(value) ? value : null;
const ACTIVE = new Set(["queued", "running"]);

export function buildReleaseDecision({ job = null, sourceSha = null, kind = job?.mode || "offline_regression", capabilities = null, validationObservation = null, syncIssue = false } = {}) {
  const modelEvaluation = kind === "model_evaluation";
  const observedSha = revision(sourceSha);
  // A model capability response cannot supply validation history or overwrite
  // its revision. Use the owner's independently observed validation state intact.
  const validation = modelEvaluation && validationObservation !== null ? validationObservation : {
    capabilities: { ...(capabilities || {}), source_sha: observedSha, recent: (capabilities?.recent || []).filter((run) => BASIC.includes(run.mode) || run.mode === "real_es_llm_e2e") },
    job: modelEvaluation ? null : job,
    error: !modelEvaluation && syncIssue ? "missing" : "",
  };
  const evaluation = modelEvaluation ? { capabilities: { source_sha: observedSha, recent: [] }, job, error: syncIssue ? "missing" : "" } : {};
  const evidence = buildWorkbenchModel({ validation, evaluation });
  const currentSha = evidence.sourceSha;
  const validationUncertain = !!validation.error || !validation.capabilities;
  const family = modelEvaluation ? "evaluations" : "validations";
  const selected = evidence.history.find((entry) => entry.family === family && entry.id === job?.id) || { status: "NOT RUN", reason: "not_run", counts: null };
  const blockers = [], missing = [];
  const addBlocker = (mode, reason, i18nKey = "qaRunFlow.reasons." + reason) => {
    if (!blockers.some((entry) => entry.mode === mode && entry.reason === reason)) blockers.push({ mode, reason, i18nKey });
  };
  const addMissing = (id, i18nKey) => {
    if (!missing.some((entry) => entry.id === id)) missing.push({ id, i18nKey });
  };

  if (syncIssue) addBlocker(kind, "sync_error");
  if (job && !ACTIVE.has(job.status)) {
    if (!["PASS", "NOT RUN"].includes(selected.status)) addBlocker(kind, selected.reason);
    if (!currentSha || !revision(job.source_sha)) addBlocker(kind, "version_unknown");
    else if (revision(job.source_sha) !== currentSha) addBlocker(kind, "version_mismatch");
    if (BASIC.includes(kind) && job.suite !== "all") addBlocker(kind, "partial_scope");
  }

  for (const row of evidence.rows) {
    if (row.status !== "PASS" || validationUncertain) addMissing(row.mode, "qaRunFlow.missing." + row.mode);
    if (row.job && !["PASS", "NOT RUN", "RUNNING"].includes(row.status)) addBlocker(row.mode, row.reason);
    if (validation.error) addBlocker(row.mode, "sync_error");
  }
  // Only the selected model job's validated, hash-bound review resolves this
  // boundary. AI reviewers remain explicitly distinct from human reviewers.
  const semanticReview = modelEvaluation ? getSemanticReview(job) : null;
  if (!semanticReview) addMissing("human_semantic_review_pending", "qaRunFlow.missing.humanReview");
  else if (semanticReview.failed > 0) addBlocker(kind, "semantic_failed", "qaSemanticReview.failedReview");
  for (const code of job?.gaps || []) {
    if (code === "human_semantic_review_pending") continue;
    if (code === "es_integration_not_executed" && !validationUncertain && evidence.rows.find((row) => row.mode === "es_integration")?.status === "PASS") continue;
    addMissing(code, getEvidenceCode(code)?.i18nKey || "qaRunFlow.missing.unknownBoundary");
  }
  const basicReady = evidence.readiness === "ready";
  const running = !!job && ACTIVE.has(job.status) && !syncIssue;
  const failed = blockers.some((entry) => ["failed_checks", "semantic_failed"].includes(entry.reason));
  const state = running ? "running" : failed ? "blocked" : BASIC.includes(kind) && selected.status === "PASS" && basicReady && blockers.length === 0 ? "ready" : "incomplete";
  return { state, basicReady, selected, blockers, missing, currentSha, rows: evidence.rows, scope: BASIC.includes(kind) ? "basic" : "quality" };
}
