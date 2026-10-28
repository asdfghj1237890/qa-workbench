// Contract: qa_semantic_review.py validated report sidecars. Completed execution
// or structural PASS cannot establish review completion without bound row hashes.
const DIMENSIONS = ["intent", "grounding", "completeness", "language"];
const TERMINAL = new Set(["completed", "incomplete", "failed", "cancelled", "timed_out"]);
const hash = (value) => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const count = (value, max = 51) => Number.isSafeInteger(value) && value >= 0 && value <= max;
const text = (value, max) => typeof value === "string" && value.trim().length > 0 && value.length <= max;
const timestamp = (value) => typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
export const semanticCasePassed = (row) => !!row?.scores && DIMENSIONS.every((dimension) => row.scores[dimension] === true);

function validRow(row) {
  return !!row && text(row.case_id, 256) && row.key === row.case_id + "/0" && hash(row.row_sha)
    && text(row.reviewer, 200) && text(row.reason, 12000) && !!row.scores
    && Object.keys(row.scores).length === DIMENSIONS.length
    && DIMENSIONS.every((dimension) => typeof row.scores[dimension] === "boolean");
}

export function getSemanticReview(job, { summary = job?.cases === undefined } = {}) {
  const review = job?.semantic_review;
  if (!job || job.semantic_status !== "reviewed" || typeof job.quality_passed !== "boolean"
    || !TERMINAL.has(job.status) || job.report_available !== true || !hash(job.report_sha256)
    || !review || review.status !== "completed" || !["ai", "human"].includes(review.reviewer_kind)
    || !text(review.reviewer, 200) || !timestamp(review.reviewed_at) || review.report_sha256 !== job.report_sha256
    || !count(job.total_cases) || !job.total_cases || !count(job.completed_cases, job.total_cases) || !job.completed_cases
    || (job.status === "completed" && job.completed_cases !== job.total_cases)
    || !count(review.planned_cases) || review.planned_cases !== job.total_cases
    || !count(review.observed_cases) || review.observed_cases !== job.completed_cases
    || !count(review.reviewed_cases) || review.reviewed_cases !== review.observed_cases
    || !count(review.passed) || !count(review.failed) || review.passed + review.failed !== review.reviewed_cases
    || !count(review.combined_passed, review.passed)
    || !count(job.structural?.passed) || !count(job.structural?.failed)
    || job.structural.passed + job.structural.failed !== job.completed_cases
    || review.combined_passed > job.structural.passed || review.combined_passed < review.passed - job.structural.failed
    || !Array.isArray(review.cases) || review.cases.length !== review.reviewed_cases || !review.cases.every(validRow)) return null;
  for (const field of ["key", "case_id", "row_sha"]) if (new Set(review.cases.map((row) => row[field])).size !== review.cases.length) return null;
  if (review.cases.filter(semanticCasePassed).length !== review.passed) return null;
  if (job.archive_imported !== undefined && typeof job.archive_imported !== "boolean") return null;
  const qualityPassed = job.archive_imported !== true && job.status === "completed" && job.completed_cases === job.total_cases
    && job.structural.passed === job.total_cases && job.structural.failed === 0 && review.failed === 0;
  if (job.quality_passed !== qualityPassed) return null;
  if (job.cases === undefined) return summary ? review : null;
  if (!Array.isArray(job.cases) || job.cases.length !== job.completed_cases
    || job.cases.some((row) => !row || !text(row.case_id, 256) || !hash(row.row_sha) || typeof row.structural_pass !== "boolean")
    || new Set(job.cases.map((row) => row.case_id)).size !== job.cases.length
  ) return null;
  const byId = new Map(review.cases.map((row) => [row.case_id, row]));
  if (job.cases.some((row) => byId.get(row.case_id)?.row_sha !== row.row_sha)) return null;
  if (job.cases.filter((row) => row.structural_pass).length !== job.structural.passed) return null;
  const combined = job.cases.filter((row) => row.structural_pass && semanticCasePassed(byId.get(row.case_id))).length;
  return combined === review.combined_passed ? review : null;
}

export function semanticReviewKey(job) {
  const review = getSemanticReview(job);
  return review ? review.reviewer_kind === "ai" ? "qaSemanticReview.completedAi" : "qaSemanticReview.completedHuman" : "qaSemanticReview.pending";
}

export function getCaseSemanticReview(job, row) {
  const review = getSemanticReview(job);
  return review?.cases.find((entry) => entry.case_id === row?.case_id && entry.row_sha === row?.row_sha) || null;
}
