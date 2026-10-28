// Physical HTTP fixture. Contract: app/qa_validation.py capabilities/start/status/
// cancel and app/qa_runner.py packaged_steps/JUnit observations. This exercises real
// browser polling and authenticated transport, but executes no tests, ES or models.
// The visible step names/logs explicitly identify offline browser fixture evidence.
const STEPS = [
  ["indexer", "ingestion"], ["crawler", "ingestion"], ["storage", "ingestion"],
  ["retrieval", "rag"], ["retrieval-evaluator", "rag"],
  ["agent-behavior", "agents"], ["trajectory-evaluator", "agents"],
];
const GAPS = ["live_llm_quality_not_evaluated", "es_integration_not_executed", "human_semantic_review_pending"];
const VALIDATION_BASE = "/qa/api/qa/validations";
const clone = (value) => JSON.parse(JSON.stringify(value));
const MODES = ["offline_regression", "es_integration", "real_es_llm_e2e"];
// Synthetic revision shared by this fixture's runtime and newly-created jobs.
// It is intentionally unrelated to any deployed NewsCout commit.
const SOURCE_SHA = "1111111111111111111111111111111111111111";
// Layout contract: qa_real_runner.py integration stage identifiers. Counts
// and evidence remain synthetic; this fixture performs no ES/API operations.
const SERVICE_EVIDENCE_LAYOUT = [
  ["identity_and_restricted_es", 12], ["news_mapping_category_vectors", 5],
  ["record_and_recommendation", 4], ["seeded_two_turn_storage_api", 1],
  ["feedback_and_history_readback", 4], ["exact_owned_document_cleanup", 1],
];
function jobBody(suite, status = "queued", mode = "offline_regression") {
  const real = mode !== "offline_regression";
  const selected = real ? [["isolated-es", "all"], [mode === "es_integration" ? "qa-api" : "real-es-model-chain", "all"]]
    : STEPS.filter((step) => suite === "all" || step[1] === suite);
  const step = ([name, layer], index, state) => ({
    name: (real ? "[BROWSER FIXTURE] " : "[OFFLINE FIXTURE] ") + name, suite: layer, status: state,
    ...(real ? { checks: state === "completed" ? [{ name: "Observed isolated fixture check", status: "passed", evidence: { fixture: true, observed: "fixture-only" } }] : [], evidence: { fixture: true } } : {
    tests: ["completed", "failed"].includes(state) ? 11 + index : null,
    failed: state === "failed" ? 1 : state === "completed" ? 0 : null, errors: ["completed", "failed"].includes(state) ? 0 : null,
    skipped: ["completed", "failed"].includes(state) ? 1 : null,
    ...(state === "running" ? { progress: { phase: "running", collected: 11 + index, completed: 3, passed: 2, failed: 0, errors: 0, skipped: 1, current_test: "tests/test_fixture.py::test_current_fixture" } } : {}) }), exit_code: state === "completed" ? 0 : state === "failed" ? 1 : null,
    log: "Synthetic browser API fixture; no regression tests, ES or models executed.", log_truncated: false,
  });
  const steps = !real ? selected.map((item, index) => step(item, index,
    status === "completed" ? "completed" : status === "queued" ? "pending" : status === "partial" ? (index === 0 ? "completed" : index === 1 ? "running" : "pending") : index === 0 ? status : "pending"))
    : status === "completed" ? selected.map((item, index) => step(item, index, "completed"))
      : status === "partial" ? selected.slice(0, 2).map((item, index) => step(item, index, index ? "running" : "completed"))
        : status === "queued" ? [] : [step(selected[0], 0, status)];
  return {
    id: "offline-browser-" + suite, source_sha: SOURCE_SHA, suite, status: status === "partial" ? "running" : status,
    started_at: "2026-10-19T00:00:00Z", finished_at: ["completed", "failed", "cancelled", "timed_out"].includes(status) ? "2026-10-19T00:00:02Z" : null,
    total_steps: selected.length, steps, mode, live_quality_evaluated: false,
    es_integration_executed: real && status === "completed", gaps: real ? ["human_semantic_review_pending"] : GAPS,
    covered: real && ["completed", "partial"].includes(status) ? ["browser_fixture_contract"] : [],
    semantic_status: "pending", quality_passed: null, report_available: ["completed", "partial"].includes(status),
  };
}

function capabilitiesBody({ available = true, busy = false, job = null, retryAfter = 0, realAvailable = true, turnstileRequired = false } = {}) {
  return {
    available, source_sha: SOURCE_SHA, busy: busy || ["queued", "running"].includes(job?.status),
    active_job_id: ["queued", "running"].includes(job?.status) ? job.id : null,
    recent: job ? [clone(job)] : [], retry_after_seconds: retryAfter, cooldown_seconds: 60,
    deadline_seconds: 180, suites: ["ingestion", "rag", "agents", "all"], mode: "offline_regression",
    live_quality_evaluated: false, es_integration_executed: false, gaps: GAPS,
    modes: MODES.map((id) => ({ id, available: available && (id === "offline_regression" || realAvailable),
      reason: available && (id === "offline_regression" || realAvailable) ? null : "mode_unavailable",
      suites: id === "offline_regression" ? ["ingestion", "rag", "agents", "all"] : ["all"], cost_required: id === "real_es_llm_e2e", turnstile_required: id === "real_es_llm_e2e" && turnstileRequired,
      limits: { deadline_seconds: 180, max_concurrent: 1, ...(id === "real_es_llm_e2e" ? { max_budget_usd: 50, default_budget_usd: 1, turns: 2 } : {}) },
      pricing: id === "real_es_llm_e2e" ? { model: "fixture-model", judge_model: "fixture-judge", embedding_model: "fixture-embedding",
        main: { input_per_million: 1, output_per_million: 2 }, judge: { input_per_million: 1, output_per_million: 2 }, embedding: { input_per_million: 0.1 }, reserved_estimated_usd: 0.1 } : null })),
  };
}

async function routeValidation(page, mode = "unavailable") {
  let job = mode === "resume-completed" ? jobBody("all", "completed") : null, rejection = null, readFailure = null, ready, started = 0;
  const served = new Promise((resolve) => { ready = resolve; });
  const requests = [];
  const enabled = mode !== "unavailable", busy = mode === "busy";
  let retryUntil = 0, initialCooldownPending = mode === "cooldown";
  const retryAfter = () => Math.max(0, Math.ceil((retryUntil - Date.now()) / 1000));
  const capabilities = () => {
    if (initialCooldownPending) { retryUntil = Date.now() + 2000; initialCooldownPending = false; }
    return capabilitiesBody({ available: enabled, busy, job, retryAfter: retryAfter(), realAvailable: mode !== "real-unavailable", turnstileRequired: mode === "turnstile-required" });
  };
  await page.route("**/api/qa/validations**", async (route) => {
    const request = route.request(), pathname = new URL(request.url()).pathname;
    const suffix = pathname.split("/qa/validations")[1];
    const payload = request.method() === "POST" && !suffix ? request.postDataJSON() : undefined;
    requests.push({ method: request.method(), path: pathname, token: request.headers().authorization, ...(payload || {}) });
    const respond = (body, status = 200, headers = {}) => route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
    if (!suffix && request.method() === "GET") { await respond(capabilities()); ready(); return; }
    if (!suffix && request.method() === "POST") {
      if (rejection) {
        const reason = rejection; rejection = null;
        if (reason === "cooldown") retryUntil = Date.now() + 2000;
        return respond({ detail: "validation_" + reason }, { busy: 409, cooldown: 429, unavailable: 503 }[reason], reason === "cooldown" ? { "Retry-After": "2" } : {});
      }
      job = jobBody(payload.suite, "queued", payload.mode || "offline_regression");
      started += 1; if (started > 1) job.id += "-" + started;
      if (mode === "completion-cooldown") retryUntil = Date.now() + 5000;
      return respond({ job }, 202);
    }
    if (job && suffix === "/" + job.id + "/cancel" && request.method() === "POST") {
      const previous = job;
      job = { ...previous, status: "cancelled", finished_at: "2026-10-19T00:00:02Z",
        steps: previous.steps.map((step) => ({ ...step, status: step.status === "completed" ? "completed" : "cancelled" })) };
      return respond({ job });
    }
    if (job && suffix === "/" + job.id + "/report" && request.method() === "GET") return respond({ job_id: job.id, mode: job.mode, status: job.status, semantic_status: "pending", quality_passed: null, steps: job.steps, covered: job.covered, gaps: job.gaps });
    if (job && suffix === "/" + job.id && request.method() === "GET") {
      if (readFailure) { const failure = readFailure; readFailure = null; return failure === "schema" ? respond({ job: { ...job, status: "completed", steps: [] } }) : respond({ detail: "fixture_read_unavailable" }, failure); }
      return respond({ job });
    }
    return respond({ detail: "validation_not_found" }, 404);
  });
  return {
    ready: () => served,
    requests: () => clone(requests),
    advance: (status) => { if (!job) throw new Error("Start a fixture job before advancing it"); job = { ...jobBody(job.suite, status, job.mode), id: job.id }; },
    useServiceEvidenceLayout: () => {
      if (job?.mode !== "es_integration" || job.status !== "completed") throw new Error("Service layout requires a completed integration fixture");
      const sample = job.steps[0];
      job = { ...job, total_steps: SERVICE_EVIDENCE_LAYOUT.length,
        covered: SERVICE_EVIDENCE_LAYOUT.map(([name]) => name),
        gaps: ["human_semantic_review_pending", "crawler_ingestion_not_executed", "public_ingress_not_exercised", "live_llm_quality_not_evaluated"],
        steps: SERVICE_EVIDENCE_LAYOUT.map(([name, count]) => ({
        ...clone(sample), name,
        checks: Array.from({ length: count }, (_, index) => ({ name: "Synthetic layout check " + (index + 1), status: "passed", evidence: { fixture: true } })),
      })) };
    },
    failNextRead: (status) => { readFailure = status; },
    forgetJob: () => { job = null; },
    rejectNextStart: (reason) => { rejection = reason; },
  };
}

const panel = (page) => page.getByTestId("qa-validation-panel");
// DOM contract: QaValidationPanel.vue separates execution status from the release
// decision. Active progress uses <progress>; terminal metadata and measured rows
// remain observable without treating execution completion as a release PASS.
async function validationState(page) {
  return panel(page).evaluate((root) => {
    const result = root.querySelector('[data-testid="qa-validation-result"]');
    const progress = result?.querySelector("progress");
    const completion = result?.querySelector(".qa-faithful-run-metadata");
    const executionStatus = result?.querySelector('[data-testid="qa-validation-execution-status"] strong');
    const decision = result?.querySelector('[data-testid="qa-release-decision"]');
    const suite = root.querySelector('[data-testid="qa-validation-suite"]');
    const taskNavigation = { 'qa-nav-validation': 'offline_regression', 'qa-nav-es-integration': 'es_integration', 'qa-nav-rag-chain': 'real_es_llm_e2e' };
    const activeTask = root.closest('.qa-page')?.querySelector('[aria-current="page"]')?.dataset.testid;
    return {
      text: root.textContent,
      allDisabled: root.querySelector('[data-testid="qa-run-all"]').disabled,
      startReason: root.querySelector('[data-testid="qa-validation-start-reason"]')?.textContent || null,
      acknowledged: root.querySelector('[data-testid="qa-validation-ack"]')?.checked ?? null,
      suiteDisabled: suite?.disabled ?? null,
      suiteOptions: [...(suite?.options || [])].map((option) => option.value),
      selectedSuite: suite?.value || null,
      notRun: root.querySelector('.qa-guided-not-run strong')?.textContent || null,
      alerts: [...root.querySelectorAll('[role="alert"]')].map((item) => item.textContent),
      resultStatus: executionStatus?.textContent || null,
      resultStatusCount: result?.querySelectorAll('[data-testid="qa-validation-execution-status"] strong').length || 0,
      syncIssue: result?.querySelector('[data-testid="qa-validation-sync-issue"] strong')?.textContent || null,
      workspacePhase: root.closest('.qa-page')?.dataset.flowPhase || null,
      title: root.querySelector('#qa-testing-title')?.textContent || null,
      releaseDecision: decision ? {
        verdict: decision.querySelector('[data-testid="qa-release-decision-verdict"]')?.textContent || null,
        status: decision.querySelector('.qa-release-decision-status')?.textContent || null,
        blockers: decision.querySelector('[data-testid="qa-release-blockers"]')?.textContent || null,
        missing: decision.querySelector('[data-testid="qa-release-missing"]')?.textContent || null,
      } : null,
      outcomeCounts: Object.fromEntries([...root.querySelectorAll('.qa-guided-outcomes > div')].map((entry) => [entry.querySelector('span')?.textContent, Number((entry.querySelector('strong')?.textContent || '').replace(/,/g, ''))])),
      resultBusy: result?.getAttribute("aria-busy") || null,
      progress: progress ? { value: Number(progress.value), max: Number(progress.max) } : null,
      completion: completion ? { completed: Number(completion.dataset.completed), total: Number(completion.dataset.total) } : null,
      evidenceHeaders: [...(result?.querySelectorAll(".qa-faithful-evidence-table > thead th") || [])].map((cell) => cell.textContent),
      steps: [...(result?.querySelectorAll(".qa-faithful-evidence-table > tbody") || [])].map((step) => ({
        name: step.querySelector(".qa-guided-raw-step code")?.textContent || "",
        displayName: step.querySelector('th[scope="row"]')?.textContent || "",
        report: step.querySelector(".qa-guided-step-detail")?.textContent || "",
        checks: step.querySelector(".qa-measured-checks")?.textContent || "",
        status: step.querySelector(".qa-guided-step-status")?.dataset.status || null,
        expanded: step.querySelector(".qa-faithful-log-button")?.getAttribute("aria-expanded") === "true",
      })),
      cancelVisible: !!root.querySelector('[data-testid="qa-cancel-validation"]'),
      history: root.querySelector(".qa-validation-history")?.textContent || "",
      mode: taskNavigation[activeTask] || root.querySelector('[data-testid="qa-validation-mode"] [aria-pressed="true"]')?.getAttribute("data-mode") || new URLSearchParams(location.search).get('task') || 'offline_regression',
      budgetVisible: !!root.querySelector('[data-testid="qa-validation-budget"]'),
      reportVisible: !!root.querySelector('[data-testid="qa-validation-report"]'),
      overflow: root.scrollWidth > root.clientWidth || document.documentElement.scrollWidth > document.documentElement.clientWidth,
      theme: root.closest(".qa-page")?.getAttribute("data-mode"),
    };
  });
}
async function startValidation(page, suite) {
  const scope = panel(page).getByTestId('qa-validation-suite');
  if (!await panel(page).getByTestId('qa-run-all').isVisible()) await panel(page).locator('[data-testid="qa-validation-settings"]:visible').click();
  if (await scope.count()) await scope.selectOption(suite);
  await panel(page).getByTestId('qa-run-all').click();
}
async function selectValidationMode(page, mode) {
  const nav = { offline_regression: 'validation', es_integration: 'es-integration', real_es_llm_e2e: 'rag-chain' };
  // Reuse the shell's mobile drawer gestures; lazy require avoids factory cycles.
  await require('./observatory-physical.cjs').selectView(page, nav[mode]);
}
async function configureValidationCost(page, budget = "1") { await panel(page).getByTestId("qa-validation-budget").fill(budget); }
async function acknowledgeValidationCost(page) { await panel(page).getByTestId("qa-validation-ack").check(); }
async function downloadValidationReport(page) {
  const downloaded = page.waitForEvent("download");
  await panel(page).getByTestId("qa-validation-report").click();
  const file = await downloaded;
  const fs = require("node:fs/promises");
  return { filename: file.suggestedFilename(), report: JSON.parse(await fs.readFile(await file.path(), "utf8")) };
}
async function cancelValidation(page) { await panel(page).getByTestId("qa-cancel-validation").click(); }
async function refreshValidation(page) { await panel(page).getByRole("button", { name: "重新讀取狀態", exact: true }).click(); }
async function openValidationLog(page) { await panel(page).locator('.qa-faithful-log-button[aria-expanded="false"]').first().click(); }
async function openValidationEvidence(page) {
  const logs = panel(page).locator('.qa-faithful-log-button[aria-expanded="false"]');
  while (await logs.count()) await logs.first().click();
}
async function captureValidation(page, name, playwright) {
  const { test } = playwright || require("@playwright/test");
  const viewport = page.viewportSize();
  if (name === "measured-progress-desktop") await page.setViewportSize({ width: viewport.width, height: 2000 });
  const targets = [panel(page).locator('.qa-guided-heading'), panel(page).locator(".qa-validation-cost"), panel(page).getByTestId('qa-validation-result')];
  try { for (let index = 0; index < targets.length; index++) if (await targets[index].isVisible()) {
      await targets[index].scrollIntoViewIfNeeded();
      await page.screenshot({ path: test.info().outputPath("validation-fixture-" + name + "-" + index + ".png"), fullPage: name.startsWith("measured-progress") });
    }
  } finally { if (name === "measured-progress-desktop") await page.setViewportSize(viewport); }
}
async function observeAfterPollingInterval(page) { await page.waitForTimeout(1250); }
async function readyValidation(page, fixture) { await fixture.ready(); await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))); }

const physical = { VALIDATION_BASE, jobBody, capabilitiesBody, routeValidation, validationState, startValidation, selectValidationMode, configureValidationCost, acknowledgeValidationCost, downloadValidationReport, cancelValidation, refreshValidation, captureValidation, observeAfterPollingInterval, readyValidation, openValidationLog, openValidationEvidence };

// Bind runner-owned artifacts per consumer; imports and standalone fixtures stay lazy.
function createValidationPhysical(playwright) {
  return { ...physical,
    captureValidation: (page, name) => captureValidation(page, name, playwright),
  };
}
module.exports = { ...physical, createValidationPhysical };
