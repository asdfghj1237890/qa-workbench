import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import fixtures from "../../../e2e/observatory-validation-physical.cjs";
import { validValidationCapabilities, validValidationJob, validValidationProgress, validationModes } from "../qaValidation.js";

describe("validation evidence records", () => {
  it("accepts additive measured pytest progress while rejecting invalid counters and unknown phases", () => {
    const job = fixtures.jobBody("all", "partial");
    expect(validValidationJob(job)).toBe(true);
    expect(validValidationProgress({ ...job.steps[1].progress, collected: null, completed: 0, passed: 0, skipped: 0 })).toBe(true);
    for (const patch of [{ collected: null }, { completed: 12 }, { passed: -1 }, { completed: 3.5 }, { collection_errors: -1 }, { phase: "passed" }, { current_test: "x".repeat(513) }]) {
      expect(validValidationProgress({ ...job.steps[1].progress, ...patch })).toBe(false);
    }
    job.steps[1].progress.completed = 12;
    expect(validValidationJob(job)).toBe(false);
  });
  it("keeps offline, real integration and real ES/model execution as distinct modes", () => {
    for (const mode of ["offline_regression", "es_integration", "real_es_llm_e2e"]) {
      expect(validValidationJob(fixtures.jobBody("all", "completed", mode))).toBe(true);
    }
    expect(validValidationCapabilities(fixtures.capabilitiesBody())).toBe(true);
  });
  it("rejects invented semantic approval and completed real runs without measured checks", () => {
    const job = fixtures.jobBody("all", "completed", "real_es_llm_e2e");
    expect(validValidationJob({ ...job, quality_passed: true, semantic_status: "passed" })).toBe(false);
    job.steps[0].checks = [];
    expect(validValidationJob(job)).toBe(false);
  });
  it("does not enable a real mode from legacy offline availability", () => {
    expect(validationModes({ available: true }).map((mode) => mode.available)).toEqual([true, false, false]);
    const value = fixtures.capabilitiesBody();
    value.modes[1].suites = ["rag"];
    expect(validValidationCapabilities(value)).toBe(false);
  });
});
