// Display names only. The raw backend identifiers remain the source of traceability.
// Contracts: qa_runner.packaged_steps(), qa_real_runner.RealRun.begin(), and
// qa_validation.GAPS / ValidationService.start(). Never infer a result from a name.
const STEPS = Object.freeze({
  indexer: "indexer",
  crawler: "crawler",
  storage: "storage",
  retrieval: "retrieval",
  "retrieval-evaluator": "retrievalEvaluator",
  "agent-behavior": "agentBehavior",
  "trajectory-evaluator": "trajectoryEvaluator",
  identity_and_restricted_es: "identityAccess",
  news_mapping_category_vectors: "newsData",
  record_and_recommendation: "recordRecommendation",
  seeded_two_turn_storage_api: "conversationStorage",
  real_chat_turn_1: "chatTurn1",
  real_chat_turn_2: "chatTurn2",
  feedback_and_history_readback: "feedbackHistory",
  exact_owned_document_cleanup: "cleanup",
});

const BOUNDARY_CODES = Object.freeze({
  live_llm_quality_not_evaluated: "modelQuality",
  es_integration_not_executed: "serviceIntegration",
  human_semantic_review_pending: "humanReview",
  crawler_ingestion_not_executed: "crawlerIngestion",
  public_ingress_not_exercised: "publicIngress",
  mutation_outcome_unknown: "unconfirmedMutation",
});

export function getEvidenceStep(name) {
  return typeof name === "string" && Object.hasOwn(STEPS, name) ? { key: STEPS[name] } : null;
}

export function getEvidenceCode(code) {
  return typeof code === "string" && Object.hasOwn(BOUNDARY_CODES, code)
    ? { i18nKey: `qaEvidence.boundaryCodes.${BOUNDARY_CODES[code]}` }
    : null;
}
