import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import { getCaseSemanticReview, getSemanticReview, semanticCasePassed, semanticReviewKey } from "../qaSemanticReview.js";
import { validLiveEvaluationJob } from "../qaLiveEvaluation.js";
import { allPassingReviewedJob, invalidIncompleteQualityPass, invalidReviewedObservations, invalidSummaryObservations,
  observeReviewedJob, observedReviewSummary, reviewedPackSizeObservation, unreviewedObservation } from "./qa/semantic-review-physical.js";

describe("hash-bound semantic review evidence", () => {
  it("accepts complete synthetic 49- and 51-case review boundaries while rejecting 52 cases", () => {
    for (const total of [49, 51]) {
      const job = reviewedPackSizeObservation(total);
      expect(getSemanticReview(job)).toMatchObject({ reviewed_cases: total, passed: total, combined_passed: total });
      expect(validLiveEvaluationJob(job)).toBe(true);
      delete job.cases;
      expect(getSemanticReview(job)).not.toBeNull();
      expect(validLiveEvaluationJob(job, { summary: true })).toBe(true);
    }
    const invalid = reviewedPackSizeObservation(52);
    expect(getSemanticReview(invalid)).toBeNull(); expect(validLiveEvaluationJob(invalid)).toBe(false);
    expect(getSemanticReview(observeReviewedJob({ incomplete: true })).planned_cases).toBe(49);
  });
  it("identifies AI completion separately from human review and preserves per-case reasons and dimensions", () => {
    const ai = observeReviewedJob(), human = observeReviewedJob({ reviewerKind: "human" });
    expect(semanticReviewKey(ai)).toBe("qaSemanticReview.completedAi");
    expect(semanticReviewKey(human)).toBe("qaSemanticReview.completedHuman");
    expect(getSemanticReview(ai)).toMatchObject({ reviewer_kind: "ai", reviewed_cases: 8, passed: 7, failed: 1 });
    const reviewedCase = getCaseSemanticReview(ai, ai.cases[0]);
    expect(reviewedCase.scores).toEqual({ intent: true, grounding: false, completeness: true, language: true });
    expect(reviewedCase.reason).toBe("The source does not support the numeric claim.");
    expect(semanticCasePassed(reviewedCase)).toBe(false);
    expect(semanticCasePassed(getCaseSemanticReview(ai, ai.cases[1]))).toBe(true);
    expect(getCaseSemanticReview(ai, human.semantic_review)).toBeNull();
  });
  it("leaves a structurally completed but unreviewed run pending", () => {
    const job = unreviewedObservation();
    expect(semanticReviewKey(job)).toBe("qaSemanticReview.pending");
    expect(getSemanticReview(job)).toBeNull();
    expect(getCaseSemanticReview(job, job.cases[0])).toBeNull();
  });
  it("completes review of observed rows without presenting the planned but unexecuted cases as quality PASS", () => {
    const job = observeReviewedJob({ incomplete: true });
    expect(getSemanticReview(job)).toMatchObject({ reviewed_cases: 8, observed_cases: 8, planned_cases: 49 });
    expect(job.quality_passed).toBe(false);
    expect(getSemanticReview(invalidIncompleteQualityPass())).toBeNull();
    expect(getSemanticReview(allPassingReviewedJob())).not.toBeNull();
  });
  it("retains archive provenance without upgrading historical evidence to current quality PASS", () => {
    const job = allPassingReviewedJob({ archived: true });
    expect(job.quality_passed).toBe(false);
    expect(validLiveEvaluationJob(job)).toBe(true);
    expect(getSemanticReview(job)).not.toBeNull();
  });
  it("rejects mismatched hashes, incomplete coverage, duplicate rows, false counts and malformed review fields", () => {
    for (const { name, job } of invalidReviewedObservations()) {
      expect(getSemanticReview(job), name).toBeNull();
      expect(validLiveEvaluationJob(job), name).toBe(false);
      expect(semanticReviewKey(job), name).toBe("qaSemanticReview.pending");
    }
  });
  it("validates summary review rows and counts even when capabilities omit original case details", () => {
    const job = observedReviewSummary();
    expect(getSemanticReview(job)).not.toBeNull();
    expect(semanticReviewKey(job)).toBe("qaSemanticReview.completedAi");
    expect(getSemanticReview(job, { summary: false })).toBeNull();
    for (const { name, job: invalid } of invalidSummaryObservations()) {
      expect(getSemanticReview(invalid), name).toBeNull();
      expect(validLiveEvaluationJob(invalid, { summary: true }), name).toBe(false);
    }
  });
});
