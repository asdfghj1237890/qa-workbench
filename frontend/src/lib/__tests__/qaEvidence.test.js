import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from "vitest";
import zh from "../../i18n/zh-TW.json";
import en from "../../i18n/en.json";
import { getEvidenceCode, getEvidenceStep } from "../qaEvidence.js";

// Expected identifiers are the public step/scope contract from
// qa_runner.packaged_steps(), qa_real_runner.RealRun, and qa_validation.GAPS/start.
const STEPS = ["indexer", "crawler", "storage", "retrieval", "retrieval-evaluator", "agent-behavior",
  "trajectory-evaluator", "identity_and_restricted_es", "news_mapping_category_vectors",
  "record_and_recommendation", "seeded_two_turn_storage_api", "real_chat_turn_1", "real_chat_turn_2",
  "feedback_and_history_readback", "exact_owned_document_cleanup"];
const GAPS = ["live_llm_quality_not_evaluated", "es_integration_not_executed", "human_semantic_review_pending",
  "crawler_ingestion_not_executed", "public_ingress_not_exercised", "mutation_outcome_unknown"];
const readTranslation = (messages, path) => path.split(".").reduce((value, key) => value?.[key], messages);
function stepExplanation(name, messages) {
  const step = getEvidenceStep(name);
  return step ? messages.qaEvidence.stages[step.key] : null;
}

describe("plain-language QA evidence", () => {
  it("explains every measured offline and service step in both languages", () => {
    for (const name of STEPS) {
      for (const messages of [zh, en]) {
        expect(stepExplanation(name, messages)?.title, name).toBeTruthy();
        expect(stepExplanation(name, messages)?.description, name).toBeTruthy();
      }
    }
  });
  it("explains every known coverage gap in both languages without changing its raw code", () => {
    for (const code of GAPS) {
      const explanation = getEvidenceCode(code);
      expect(explanation, code).not.toBeNull();
      for (const messages of [zh, en]) expect(readTranslation(messages, explanation.i18nKey), code).toBeTruthy();
    }
  });
  it("keeps unknown identifiers unexplained instead of inventing a meaning", () => {
    for (const raw of [null, undefined, "", "future_stage", "toString", "constructor", "__proto__", {}, []]) {
      expect(getEvidenceStep(raw)).toBeNull();
      expect(getEvidenceCode(raw)).toBeNull();
    }
  });
  it("makes the fixed two-turn storage test visibly different from a real model run", () => {
    expect(stepExplanation("seeded_two_turn_storage_api", zh).description).toContain("不會呼叫模型");
    expect(stepExplanation("seeded_two_turn_storage_api", en).description).toContain("no model generates answers");
    expect(stepExplanation("real_chat_turn_1", zh).description).toContain("人工確認答案品質");
    expect(stepExplanation("record_and_recommendation", zh).description).toContain("不評估推薦內容品質");
  });
});
