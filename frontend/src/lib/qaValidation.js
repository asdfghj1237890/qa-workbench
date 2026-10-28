// Contract: app/qa_validation.py capabilities/jobs; execution is separate from
// human semantic review. A selected mode is never evidence that it was executed.
export const VALIDATION_MODES = ["offline_regression", "es_integration", "real_es_llm_e2e"];
const SUITES = new Set(["ingestion", "rag", "agents", "all"]);
const STATES = new Set(["pending", "queued", "running", "completed", "incomplete", "failed", "cancelled", "timed_out"]);
const nonnegative = (value) => Number.isSafeInteger(value) && value >= 0;
const strings = (value) => Array.isArray(value) && value.length <= 128 && value.every((item) => typeof item === "string" && item.length <= 2048);
const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value) && JSON.stringify(value).length <= 131072;
const counts = (step) => [step.tests, step.failed, step.errors, step.skipped];
const measured = (step) => counts(step).every(nonnegative) && step.tests > step.skipped && step.failed === 0 && step.errors === 0;
const rate = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
export function validValidationProgress(value) {
  return record(value) && ["collecting", "running", "finished"].includes(value.phase)
    && (value.collected === null || nonnegative(value.collected))
    && [value.completed, value.passed, value.failed, value.errors, value.skipped].every(nonnegative)
    && (value.collection_errors === undefined || nonnegative(value.collection_errors))
    && value.passed + value.failed + value.errors + value.skipped === value.completed
    && (value.collected === null ? value.completed === 0 : value.completed <= value.collected)
    && (value.current_test === null || (typeof value.current_test === "string" && value.current_test.length <= 512));
}
export function validValidationPricing(value) {
  return record(value) && [value.model, value.judge_model, value.embedding_model].every((name) => typeof name === "string" && name.length > 0 && name.length <= 256)
    && rate(value.reserved_estimated_usd) && rate(value.embedding?.input_per_million)
    && [value.main, value.judge].every((cost) => rate(cost?.input_per_million) && rate(cost?.output_per_million));
}

export function validationModes(value) {
  return VALIDATION_MODES.map((id) => value?.modes?.find((item) => item.id === id) || {
    id, available: id === "offline_regression" && value?.available === true && !value?.modes,
    reason: "mode_unavailable", suites: id === "offline_regression" ? [...SUITES] : ["all"],
    cost_required: id === "real_es_llm_e2e", limits: {}, pricing: null,
  });
}

export function validValidationCapabilities(value) {
  return typeof value?.available === "boolean" && Array.isArray(value.recent)
    && (value.modes === undefined || (Array.isArray(value.modes) && value.modes.length <= 3
      && new Set(value.modes.map((mode) => mode.id)).size === value.modes.length
      && value.modes.every((mode) => VALIDATION_MODES.includes(mode.id) && typeof mode.available === "boolean"
        && (mode.reason === null || typeof mode.reason === "string") && typeof mode.cost_required === "boolean"
        && Array.isArray(mode.suites) && mode.suites.length > 0 && mode.suites.every((suite) => SUITES.has(suite))
        && (mode.id === "offline_regression" || mode.suites.every((suite) => suite === "all"))
        && record(mode.limits) && (mode.pricing == null || record(mode.pricing))
        && (!mode.available || mode.id !== "real_es_llm_e2e" || (validValidationPricing(mode.pricing)
          && rate(mode.limits.max_budget_usd) && mode.limits.max_budget_usd >= 0.01
          && rate(mode.limits.default_budget_usd) && mode.limits.default_budget_usd >= mode.pricing.reserved_estimated_usd
          && mode.limits.default_budget_usd <= mode.limits.max_budget_usd)))));
}

export function validValidationJob(value) {
  return typeof value?.id === "string" && /^[a-zA-Z0-9-]{1,64}$/.test(value.id)
    && VALIDATION_MODES.includes(value.mode) && SUITES.has(value.suite)
    && (value.mode === "offline_regression" || value.suite === "all")
    && STATES.has(value.status) && value.status !== "pending"
    && value.semantic_status === "pending" && value.quality_passed === null
    && strings(value.covered) && strings(value.gaps) && typeof value.report_available === "boolean"
    && nonnegative(value.total_steps) && value.total_steps <= 16
    && [value.started_at, value.finished_at].every((time) => time == null || Number.isFinite(Date.parse(time)))
    && Array.isArray(value.steps) && value.steps.length <= value.total_steps
    && value.steps.every((step) => typeof step.name === "string" && SUITES.has(step.suite)
      && STATES.has(step.status)
      && (step.progress === undefined || validValidationProgress(step.progress))
      && (value.mode === "offline_regression" ? counts(step).every((count) => count === null || nonnegative(count))
        : Array.isArray(step.checks) && step.checks.length <= 128 && step.checks.every((check) =>
          typeof check.name === "string" && check.name.length <= 2048 && ["passed", "failed"].includes(check.status) && record(check.evidence))
          && record(step.evidence))
      && typeof step.log === "string" && step.log.length <= 16384
      && typeof step.log_truncated === "boolean")
    && (value.status !== "completed" || (value.total_steps > 0 && value.steps.length === value.total_steps
      && value.steps.every((step) => step.status === "completed"
        && (value.mode === "offline_regression" ? measured(step)
          : step.checks.length > 0 && step.checks.every((check) => check.status === "passed")))
      && (value.mode === "offline_regression" || value.covered.length > 0)));
}
