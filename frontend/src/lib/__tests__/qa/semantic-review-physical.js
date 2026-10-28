import liveFixtures from "../../../../e2e/observatory-live-evaluation-physical.cjs";

// Contract: eval/behavior_cases.json adds two dev regressions. The shared
// 49-case archive fixture stays unchanged; this current-pack observation is
// detached and synthetic, with no provider or ES calls.
export function expandedLivePackObservation() {
  const job = liveFixtures.jobBody("all", "incomplete");
  job.total_cases = 51;
  const capabilities = liveFixtures.capabilitiesBody({ job });
  for (const profile of capabilities.profiles) {
    if (profile.id === "dev") profile.case_count = 36;
    if (profile.id === "holdout") profile.case_count = 15;
    if (profile.id === "all") profile.case_count = 51;
  }
  return { job, capabilities };
}

// Synthetic count-boundary records only: no CLI report or real model quality
// result is manufactured or rewritten. The original golden rows remain intact.
export function reviewedPackSizeObservation(total) {
  const job = allPassingReviewedJob(), originals = structuredClone(job.cases), reviews = structuredClone(job.semantic_review.cases);
  job.total_cases = job.completed_cases = total;
  job.structural = { passed: total, failed: 0 };
  job.cases = Array.from({ length: total }, (_, index) => ({ ...structuredClone(originals[index % originals.length]),
    case_id: "synthetic-count-boundary-" + (index + 1), row_sha: (index + 1).toString(16).padStart(64, "0") }));
  Object.assign(job.semantic_review, { planned_cases: total, observed_cases: total, reviewed_cases: total,
    passed: total, failed: 0, combined_passed: total,
    cases: job.cases.map((row, index) => ({ ...structuredClone(reviews[index % reviews.length]),
      key: row.case_id + "/0", case_id: row.case_id, row_sha: row.row_sha })) });
  return job;
}

// Contract: qa_evaluations.py public jobs and qa_semantic_review.py validated
// sidecars. These synthetic frozen backend rows are never private review data.
export function reviewedObservation({ reviewerKind = "ai", failed = true, incomplete = false, archived = false } = {}) {
  const job = liveFixtures.jobBody("quick", "completed");
  job.report_sha256 = "a".repeat(64);
  if (incomplete) { job.profile = "all"; job.status = "incomplete"; job.total_cases = 49; }
  if (archived) job.archive_imported = true;
  job.semantic_status = "reviewed";
  const cases = job.cases.map((row, index) => ({ key: row.case_id + "/0", case_id: row.case_id, row_sha: row.row_sha,
    reviewer: reviewerKind === "ai" ? "Codex (AI)" : "QA reviewer",
    scores: { intent: true, grounding: !(failed && index === 0), completeness: true, language: true },
    reason: failed && index === 0 ? "The source does not support the numeric claim." : "The response follows the request and the cited evidence." }));
  const passed = cases.filter((row) => Object.values(row.scores).every(Boolean)).length;
  const combined = cases.filter((row, index) => job.cases[index].structural_pass && Object.values(row.scores).every(Boolean)).length;
  job.semantic_review = { status: "completed", reviewer_kind: reviewerKind, reviewer: cases[0].reviewer,
    reviewed_at: "2026-10-23T02:00:00Z", report_sha256: job.report_sha256,
    reviewed_cases: cases.length, observed_cases: job.completed_cases, planned_cases: job.total_cases,
    passed, failed: cases.length - passed, combined_passed: combined, cases };
  job.quality_passed = !archived && !incomplete && !job.structural.failed && !job.semantic_review.failed;
  return job;
}

export function observeReviewedJob(options = {}, change = () => {}) {
  const job = reviewedObservation(options);
  change(job);
  return job;
}

export function observedReviewSummary(options = {}, change = () => {}) {
  const job = observeReviewedJob(options, change);
  delete job.cases;
  return job;
}

export function allPassingReviewedJob({ archived = false, incomplete = false } = {}) {
  const job = reviewedObservation({ failed: false, archived, incomplete });
  job.cases.forEach((row) => { row.structural_pass = true; });
  job.structural = { passed: job.completed_cases, failed: 0 };
  job.semantic_review.combined_passed = job.completed_cases;
  job.quality_passed = !archived && !incomplete;
  return job;
}

export function unreviewedObservation() { return liveFixtures.jobBody("quick", "completed"); }

export function invalidReviewedObservations() {
  const corruptions = [
    ["report hash mismatch", (job) => { job.semantic_review.report_sha256 = "b".repeat(64); }],
    ["missing bound report hash", (job) => { delete job.report_sha256; }],
    ["row hash mismatch", (job) => { job.semantic_review.cases[0].row_sha = "b".repeat(64); }],
    ["duplicate reviewed row", (job) => { job.semantic_review.cases[1] = structuredClone(job.semantic_review.cases[0]); }],
    ["partial review", (job) => { job.semantic_review.cases.pop(); job.semantic_review.reviewed_cases--; }],
    ["fabricated passing count", (job) => { job.semantic_review.passed++; job.semantic_review.failed--; }],
    ["fabricated combined count", (job) => { job.semantic_review.combined_passed--; }],
    ["wrong planned count", (job) => { job.semantic_review.planned_cases++; }],
    ["wrong observed count", (job) => { job.semantic_review.observed_cases++; }],
    ["fractional count", (job) => { job.semantic_review.reviewed_cases = 7.5; }],
    ["invalid review timestamp", (job) => { job.semantic_review.reviewed_at = "yesterday"; }],
    ["missing review timestamp zone", (job) => { job.semantic_review.reviewed_at = "2026-10-23T02:00:00"; }],
    ["unknown reviewer type", (job) => { job.semantic_review.reviewer_kind = "automatic_human"; }],
    ["blank reviewer", (job) => { job.semantic_review.reviewer = "  "; }],
    ["oversized reason", (job) => { job.semantic_review.cases[0].reason = "a".repeat(12001); }],
    ["missing failure reason", (job) => { job.semantic_review.cases[0].reason = ""; }],
    ["nonboolean score", (job) => { job.semantic_review.cases[0].scores.grounding = 0; }],
    ["unknown score dimension", (job) => { job.semantic_review.cases[0].scores.style = true; }],
    ["unknown case key", (job) => { job.semantic_review.cases[0].key = "unknown/0"; }],
    ["duplicate observed row", (job) => { job.cases[1] = structuredClone(job.cases[0]); }],
    ["invalid observed row", (job) => { job.cases[0] = null; }],
    ["unmeasured structural count", (job) => { job.structural.passed--; }],
    ["premature running review", (job) => { job.status = "running"; }],
    ["completed state with missing planned execution", (job) => { job.total_cases = 49; job.semantic_review.planned_cases = 49; }],
    ["quality PASS with semantic failure", (job) => { job.quality_passed = true; }],
  ];
  return corruptions.map(([name, change]) => ({ name, job: observeReviewedJob({}, change) }));
}

export function invalidSummaryObservations() {
  const corruptions = [
    ["fabricated summary score count", (job) => { job.semantic_review.passed++; job.semantic_review.failed--; }],
    ["duplicate summary review", (job) => { job.semantic_review.cases[1] = structuredClone(job.semantic_review.cases[0]); }],
    ["summary combined exceeds structure", (job) => { job.semantic_review.combined_passed = job.structural.passed + 1; }],
    ["missing summary row", (job) => { job.semantic_review.cases.pop(); }],
    ["invalid summary hash", (job) => { job.semantic_review.cases[0].row_sha = "not-verified"; }],
  ];
  return corruptions.map(([name, change]) => ({ name, job: observedReviewSummary({}, change) }));
}

export function invalidIncompleteQualityPass() {
  return observeReviewedJob({ incomplete: true }, (job) => { job.quality_passed = true; });
}

// Contract: qa_evaluations.py imported report pricing preserves historical rates
// without claiming a current source URL or a fabricated verification timestamp.
export function historicalPricingObservation(change = () => {}) {
  return observeReviewedJob({ archived: true }, (job) => {
    job.pricing.source = "historical_report";
    delete job.pricing.verified_at;
    change(job);
  });
}

export function invalidHistoricalPricingObservations() {
  const corruptions = [
    ["historical pricing on a server execution", (job) => { delete job.archive_imported; }],
    ["truthy archive flag", (job) => { job.archive_imported = "true"; }],
    ["missing input rate", (job) => { delete job.pricing.input_per_million; }],
    ["missing output rate", (job) => { delete job.pricing.output_per_million; }],
    ["infinite historical rate", (job) => { job.pricing.input_per_million = Infinity; }],
    ["negative historical rate", (job) => { job.pricing.output_per_million = -1; }],
    ["nonnumeric historical rate", (job) => { job.pricing.output_per_million = "2"; }],
    ["invented verification date", (job) => { job.pricing.verified_at = "2026-10-23"; }],
  ];
  return corruptions.map(([name, change]) => ({ name, job: historicalPricingObservation(change) }));
}
