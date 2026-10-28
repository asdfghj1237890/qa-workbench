// Contract: agent-service/app/qa_evaluations.py public capabilities/job records.
// Live execution and structural rules never imply completed semantic review.
import { getSemanticReview } from "./qaSemanticReview.js";
export const LIVE_PROFILES = ["quick", "dev", "holdout", "all"];
const STATES = new Set(["queued", "running", "completed", "incomplete", "failed", "cancelled", "timed_out"]);
const PHASES = new Set(["queued", "starting", "model", "tool", "case_complete", "finished"]);
// The backend limits the original report to 16 MiB of JSON bytes. Its legitimate
// long answers/failures must not hide an otherwise valid failed evaluation.
const REPORT_CHARS = 16 * 1024 * 1024;
const integer = (value, max = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(value) && value >= 0 && value <= max;
const number = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
const text = (value, max = 256) => typeof value === "string" && value.length <= max;
const nullableText = (value) => value === null || text(value);
const time = (value) => value === null || (text(value) && Number.isFinite(Date.parse(value)));
const strings = (value, max = 32, maxChars = 2048) => Array.isArray(value) && value.length <= max && value.every((item) => text(item, maxChars));
const identity = (value) => value?.mode === "live_llm_evaluation" && value.realism === "real_model_synthetic_retrieval" && text(value.model) && value.model.length > 0;
const id = (value) => typeof value === "string" && /^[a-zA-Z0-9-]{1,64}$/.test(value);
export const isLiveActive = (value) => !!value && ["queued", "running"].includes(value.status);
export const validLiveBudget = (value, ceiling = 5) => typeof value === "number" && Number.isFinite(value) && value >= 0.01 && value <= Math.min(5, ceiling);

function validPricing(value, { historical = false } = {}) {
  return !!value && text(value.model) && number(value.input_per_million) && number(value.output_per_million)
    && ((value.source === "server_configuration" && value.verified_at === "server_configuration")
      || (historical && value.source === "historical_report" && value.verified_at === undefined)
      || (text(value.source, 2048) && /^https:\/\//.test(value.source) && text(value.verified_at) && Number.isFinite(Date.parse(value.verified_at))));
}
function validUsage(value) {
  return !!value && integer(value.requests) && integer(value.input_tokens) && integer(value.output_tokens)
    && number(value.reserved_estimated_usd) && number(value.measured_estimated_usd) && typeof value.underestimated === "boolean";
}
function validCase(value) {
  return !!value && text(value.case_id) && value.case_id.length > 0 && text(value.group) && text(value.split)
    && text(value.status) && typeof value.structural_pass === "boolean" && strings(value.hard_failures, 200, REPORT_CHARS) && strings(value.failures, 200, REPORT_CHARS)
    && number(value.duration_ms) && text(value.answer, REPORT_CHARS) && integer(value.input_tokens) && integer(value.output_tokens)
    && typeof value.row_sha === "string" && /^[a-f0-9]{64}$/.test(value.row_sha);
}
export function validLiveEvaluationJob(value, { summary = false } = {}) {
  return identity(value) && id(value.id) && LIVE_PROFILES.includes(value.profile) && STATES.has(value.status)
    && time(value.started_at) && time(value.finished_at) && integer(value.total_cases, 51) && value.total_cases > 0
    && integer(value.completed_cases, value.total_cases) && (value.status !== "completed" || value.completed_cases === value.total_cases)
    && nullableText(value.current_case) && PHASES.has(value.phase)
    && nullableText(value.current_tool) && validLiveBudget(value.max_usd) && integer(value.max_requests, 768) && value.max_requests > 0
    && integer(value.max_output_tokens) && value.max_output_tokens > 0 && number(value.deadline_seconds) && value.deadline_seconds > 0
    && validPricing(value.pricing, { historical: value.archive_imported === true }) && validUsage(value.usage) && integer(value.structural?.passed, value.completed_cases)
    && integer(value.structural?.failed, value.completed_cases) && value.structural.passed + value.structural.failed <= value.completed_cases
    && ((value.semantic_status === "pending" && value.quality_passed === null && value.semantic_review == null)
      || !!getSemanticReview(value, { summary })) && strings(value.gaps)
    && (value.report_sha256 === undefined || (typeof value.report_sha256 === "string" && /^[a-f0-9]{64}$/.test(value.report_sha256)))
    && (value.archive_imported === undefined || typeof value.archive_imported === "boolean")
    && typeof value.report_available === "boolean" && nullableText(value.error)
    && ((summary && value.cases === undefined) || (Array.isArray(value.cases) && value.cases.length <= value.completed_cases
      && value.cases.every(validCase)));
}
export function validLiveCapabilities(value) {
  return identity(value) && typeof value.available === "boolean" && nullableText(value.reason)
    && Array.isArray(value.profiles) && value.profiles.length > 0 && value.profiles.length <= 4
    && new Set(value.profiles.map((profile) => profile.id)).size === value.profiles.length
    && value.profiles.every((profile) => LIVE_PROFILES.includes(profile.id) && integer(profile.case_count, 51) && profile.case_count > 0
      && integer(profile.max_requests, 768) && profile.max_requests > 0)
    && validLiveBudget(value.max_budget_usd) && validLiveBudget(value.default_budget_usd, value.max_budget_usd)
    && integer(value.max_output_tokens) && value.max_output_tokens > 0 && number(value.deadline_seconds) && value.deadline_seconds > 0
    && number(value.cooldown_seconds) && number(value.retry_after_seconds) && typeof value.busy === "boolean"
    && (value.active_job_id === null || id(value.active_job_id))
    && ((!value.available && value.pricing === null) || validPricing(value.pricing)) && strings(value.gaps)
    && Array.isArray(value.recent) && value.recent.length <= 5 && value.recent.every((job) => validLiveEvaluationJob(job, { summary: true }));
}
