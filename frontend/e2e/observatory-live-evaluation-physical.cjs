// Physical HTTP fixture. Contract: app/qa_evaluations.py capabilities/start/status/
// cancel/report and qa_live_runner.py bounded public job records. Synthetic browser
// observations exercise UI/auth transport only; no model, paid request or ES runs.
const LIVE_REPORT_GOLDEN = require("./fixtures/live-report-golden.json");
const LIVE_BASE = "/qa/api/qa/evaluations";
const PROFILES = [
  { id: "quick", label_key: "quick", case_count: 8, max_requests: 128 },
  { id: "dev", label_key: "dev", case_count: 34, max_requests: 512 },
  { id: "holdout", label_key: "holdout", case_count: 15, max_requests: 256 },
  { id: "all", label_key: "all", case_count: 49, max_requests: 768 },
];
const PRICING = { model: "gpt-5-mini", input_per_million: 0.25, output_per_million: 2,
  source: "https://developers.openai.com/api/docs/models/gpt-5-mini", verified_at: "2026-10-19" };
const GAPS = ["es_integration_not_executed", "human_semantic_review_pending"];
// Synthetic runtime/job provenance; not a production or QA deployment revision.
const SOURCE_SHA = "1111111111111111111111111111111111111111";
const clone = (value) => JSON.parse(JSON.stringify(value));
function caseBody(index) {
  if (!LIVE_REPORT_GOLDEN.public_cases[index]) throw new Error("Completed browser fixture exceeds the 8 frozen backend cases");
  return clone(LIVE_REPORT_GOLDEN.public_cases[index]);
}
function jobBody(profile = "quick", status = "queued", maxUsd = 1) {
  const selection = PROFILES.find((entry) => entry.id === profile);
  const completed = status === "completed" ? selection.case_count : ["partial", "incomplete", "cancelled", "timed_out"].includes(status) ? 1 : 0;
  const active = ["model", "tool", "partial", "running"].includes(status);
  const terminal = ["completed", "incomplete", "cancelled", "timed_out", "failed"].includes(status);
  const requests = active ? 3 : completed * 2;
  return { id: "live-browser-" + profile, source_sha: SOURCE_SHA, profile, status: active ? "running" : status,
    mode: "live_llm_evaluation", realism: "real_model_synthetic_retrieval", model: "gpt-5-mini",
    started_at: "2026-10-19T01:00:00Z", finished_at: terminal ? "2026-10-19T01:00:30Z" : null,
    total_cases: selection.case_count, completed_cases: completed,
    current_case: active ? "fixture-case-" + (completed + 1) : null,
    phase: terminal ? "finished" : status === "tool" ? "tool" : active ? "model" : "queued",
    current_tool: status === "tool" ? "search_news" : null, max_usd: maxUsd, max_requests: selection.max_requests,
    max_output_tokens: 8192, deadline_seconds: 1800, pricing: clone(PRICING),
    usage: { requests, reserved_estimated_usd: active ? 0.02 : 0, measured_estimated_usd: requests * 0.00045,
      input_tokens: completed * 1200, output_tokens: completed * 300, underestimated: false },
    structural: { passed: Math.max(0, completed - (status === "completed" ? 1 : 0)), failed: status === "completed" ? 1 : 0 },
    semantic_status: "pending", quality_passed: null, gaps: GAPS,
    cases: Array.from({ length: completed }, (_, index) => caseBody(index)),
    report_available: completed > 0, error: status === "incomplete" ? "budget_limit" : status === "failed" ? "evaluation_runner_error" : null };
}
function capabilitiesBody({ available = true, busy = false, job = null, retryAfter = 0 } = {}) {
  const recent = job ? [clone(job)] : [];
  recent.forEach((entry) => delete entry.cases);
  return { available, source_sha: SOURCE_SHA, reason: available ? null : "live_package_unavailable", mode: "live_llm_evaluation",
    realism: "real_model_synthetic_retrieval", model: "gpt-5-mini", profiles: clone(PROFILES),
    max_budget_usd: 5, default_budget_usd: 1, max_output_tokens: 8192, deadline_seconds: 1800,
    cooldown_seconds: 300, retry_after_seconds: retryAfter, busy: busy || ["queued", "running"].includes(job?.status),
    active_job_id: ["queued", "running"].includes(job?.status) ? job.id : null, pricing: clone(PRICING), gaps: GAPS, recent };
}
// Contract: qa_live_runner.py read_report/apply_report returns the original CLI
// report via qa_evaluations.py evaluation_report, not the public job's cases.
// fixtures/generate-live-report-golden.py calls the actual Python read_report /
// _digest with a synthetic catalog. Fixed public SHA values are independent of
// this JS adapter. No JS hashing: Python's 1820.0 JSON differs from JS's 1820.
// These observations establish backend ABI + blob transport, not a model run.
function reportRow(entry) {
  const row = LIVE_REPORT_GOLDEN.report.rows.find((value) => value.case_id === entry.case_id);
  if (!row) throw new Error("Missing frozen backend report row: " + entry.case_id);
  return clone(row);
}
function reportBody(job) {
  return { version: 1, complete: job.status === "completed", metadata: { model: job.model, realism: job.realism,
    selection: { ids: Array.from({ length: job.total_cases }, (_, index) => "fixture-case-" + (index + 1)), repeats: 1, seed: 17 },
    budget_policy: { max_usd: job.max_usd, max_requests: job.max_requests,
      input_per_million: job.pricing.input_per_million, output_per_million: job.pricing.output_per_million } },
    rows: job.cases.map(reportRow), summary: {}, shared_run_usage: clone(job.usage) };
}
function reportJson(job) {
  // Embed Python's original row JSON verbatim. Parsing/stringifying it in JS
  // would erase integer-valued float representations used by backend _digest.
  const rows = job.cases.map((entry) => LIVE_REPORT_GOLDEN.raw_rows[
    LIVE_REPORT_GOLDEN.public_cases.findIndex((value) => value.case_id === entry.case_id)]);
  return JSON.stringify({ ...reportBody(job), rows: [] }).replace('"rows":[]', '"rows":[' + rows.join(",") + "]");
}
async function routeLiveEvaluation(page, mode = "unavailable") {
  let job = mode === "resume" ? jobBody("quick", "partial") : null, rejection = null, reportRejection = null, observedJob = null, ready;
  let retryUntil = mode === "cooldown" ? Date.now() + 2000 : 0;
  const served = new Promise((resolve) => { ready = resolve; }), requests = [];
  await page.route("**/api/qa/evaluations**", async (route) => {
    const request = route.request(), pathname = new URL(request.url()).pathname, suffix = pathname.split("/qa/evaluations")[1];
    const body = request.method() === "POST" && !suffix ? request.postDataJSON() : null;
    requests.push({ method: request.method(), path: pathname, token: request.headers().authorization, ...(body ? { body } : {}) });
    const respond = (value, status = 200, headers = {}) => route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(value) });
    if (!suffix && request.method() === "GET") { await respond(capabilitiesBody({ available: mode !== "unavailable", busy: mode === "busy", job, retryAfter: Math.max(0, Math.ceil((retryUntil - Date.now()) / 1000)) })); ready(); return; }
    if (!suffix && request.method() === "POST") {
      if (rejection) {
        const reason = rejection; rejection = null;
        if (reason === "cooldown") retryUntil = Date.now() + 2000;
        return respond({ detail: "evaluation_" + reason }, { busy: 409, cooldown: 429, unavailable: 503 }[reason], reason === "cooldown" ? { "Retry-After": "2" } : {});
      }
      job = jobBody(body.profile, "queued", body.max_usd); return respond({ job }, 202);
    }
    if (job && suffix === "/" + job.id + "/cancel" && request.method() === "POST") { job = jobBody(job.profile, "cancelled", job.max_usd); return respond({ job }); }
    if (job && suffix === "/" + job.id + "/report") {
      if (reportRejection) { const status = reportRejection; reportRejection = null; return respond({ detail: "evaluation_report_unavailable" }, status); }
      return route.fulfill({ status: 200, contentType: "application/json",
        headers: { "Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="qa-evaluation-' + job.id + '.json"' },
        body: reportJson(job) });
    }
    if (job && suffix === "/" + job.id) { observedJob = clone(job); return respond({ job }); }
    return respond({ detail: "evaluation_not_found" }, 404);
  });
  return { ready: () => served, requests: () => clone(requests), observedJob: () => clone(observedJob), advance: (status) => { if (!job) throw new Error("Start a fixture run before advancing"); job = jobBody(job.profile, status, job.max_usd); }, rejectNextStart: (reason) => { rejection = reason; }, rejectNextReport: (status) => { reportRejection = status; } };
}
const panel = (page) => page.getByTestId("qa-live-panel");
// DOM contract: QaLiveEvaluationPanel.vue retains the mounted settings form while
// QaPage.vue exposes its settings/execution/evidence phase on data-flow-phase.
async function liveState(page) {
  return panel(page).evaluate((root) => {
    const result = root.querySelector('[data-testid="qa-live-result"]'), progress = result?.querySelector("progress");
    return { text: root.textContent, startDisabled: root.querySelector('[data-testid="qa-live-start"]').disabled,
      workspacePhase: root.closest(".qa-page")?.dataset.flowPhase || null,
      configuredModel: root.querySelector('[data-testid="qa-live-model"]')?.textContent || null,
      acknowledged: root.querySelector('[data-testid="qa-live-ack"]').checked,
      alerts: [...root.querySelectorAll('[role="alert"]')].map((entry) => entry.textContent),
      status: result?.querySelector('[role="status"]')?.textContent || null,
      phase: result?.querySelector('[data-testid="qa-live-phase"]')?.textContent || null,
      progress: progress ? { value: Number(progress.value), max: Number(progress.max) } : null,
      semantic: result?.querySelector('[data-testid="qa-live-semantic"]')?.textContent || null,
      retryLink: (() => { const link = root.querySelector('[data-testid="qa-live-report-retry"]'); return link ? { href: link.href, download: link.download, tag: link.tagName } : null; })(),
      cases: [...(result?.querySelectorAll('.qa-live-cases > li') || [])].map((entry) => entry.textContent),
      cancelVisible: !!root.querySelector('[data-testid="qa-live-cancel"]'), reportVisible: !!root.querySelector('[data-testid="qa-live-report"]'),
      overflow: root.scrollWidth > root.clientWidth || document.documentElement.scrollWidth > document.documentElement.clientWidth,
      theme: root.closest(".qa-page")?.getAttribute("data-mode") };
  });
}
async function configureLive(page, profile = "quick", budget = "1") {
  if (!await panel(page).getByTestId('qa-live-profile').isVisible()) await panel(page).getByTestId('qa-live-show-settings').click();
  await panel(page).getByTestId("qa-live-profile").selectOption(profile); await panel(page).getByTestId("qa-live-budget").fill(budget);
}
async function acknowledgeLive(page) { await panel(page).getByTestId("qa-live-ack").check(); }
async function startLive(page) { await panel(page).getByTestId("qa-live-start").click(); }
async function cancelLive(page) { await panel(page).getByTestId("qa-live-cancel").click(); }
async function openLiveAnswer(page) { await panel(page).locator(".qa-live-cases summary").first().click(); }
async function downloadLiveReport(page, retry = false) {
  const pending = page.waitForEvent("download"); await panel(page).getByTestId(retry ? "qa-live-report-retry" : "qa-live-report").click();
  const download = await pending, stream = await download.createReadStream(), chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const rawBody = Buffer.concat(chunks).toString("utf8");
  return { filename: download.suggestedFilename(), failure: await download.failure(), report: JSON.parse(rawBody), rawBody };
}
async function attemptRejectedReport(page) {
  let downloads = 0;
  const received = () => { downloads++; };
  page.on("download", received);
  try {
    const response = page.waitForResponse((value) => new URL(value.url()).pathname.endsWith("/report"));
    await panel(page).getByTestId("qa-live-report").click();
    const result = await response; await result.finished();
    await panel(page).getByRole("alert").waitFor({ state: "visible" });
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    return { status: result.status(), downloads };
  } finally { page.off("download", received); }
}
async function captureLive(page, name) {
  const { test } = require("@playwright/test");
  const paths = [];
  // The page scrolls inside .qa-scroll. An element screenshot taller than that
  // viewport clips its invisible children; capture actual visible sections instead.
  for (const [section, selector] of [["config", ".qa-live-config"], ["result", ".qa-live-run-summary"], ["evidence", '[data-testid="qa-live-semantic"]']]) {
    const target = panel(page).locator(selector);
    if (!await target.isVisible()) continue;
    await target.evaluate((element) => element.scrollIntoView({ block: "start" }));
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const path = test.info().outputPath("live-fixture-" + name + "-" + section + ".png");
    await page.screenshot({ path }); paths.push(path);
  }
  return paths;
}
async function readyLive(page, fixture) { await fixture.ready(); await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))); }
module.exports = { LIVE_BASE, LIVE_REPORT_GOLDEN, PROFILES, PRICING, jobBody, caseBody, capabilitiesBody, reportBody, routeLiveEvaluation, liveState, configureLive, acknowledgeLive, startLive, cancelLive, openLiveAnswer, downloadLiveReport, attemptRejectedReport, captureLive, readyLive };
