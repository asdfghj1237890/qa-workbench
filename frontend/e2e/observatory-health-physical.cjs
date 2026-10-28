// Contract: app/qa_health.py /qa/health; shared v1 example is also inspected by
// backend contract tests. These are synthetic observations, never a model run.
const example = require('./fixtures/health-v1.json');
const historyExample = require('./fixtures/health-history-v1.json');
const PRIVATE_HEALTH_DETAIL = 'PRIVATE-HEALTH-SENTINEL-do-not-publish';
function healthBody(scenario = 'normal') {
  const body = JSON.parse(JSON.stringify(example));
  if (scenario === 'invalid') body.modules[0].id = 'unsupported';
  if (scenario === 'missing') body.modules.pop();
  if (scenario === 'future-success') body.modules[1].last_success_at = '2026-10-26T00:00:01+00:00';
  if (scenario === 'future-observation') body.modules[1].observed_at = '2026-10-26T00:01:00+00:00';
  if (scenario === 'private') { body.secret = PRIVATE_HEALTH_DETAIL; body.modules[4].details.private = PRIVATE_HEALTH_DETAIL; }
  if (scenario === 'recovered') { body.generated_at = '2026-10-26T00:00:11+00:00'; }
  if (scenario.startsWith('llm-')) {
    const empty = ['llm-no-traffic', 'llm-cancelled', 'llm-unavailable'].includes(scenario), failed = scenario === 'llm-failed';
    const details = { window_seconds: 900, request_count: empty ? scenario === 'llm-cancelled' ? 1 : 0 : failed ? 4 : 2,
      completed_count: empty ? 0 : failed ? 3 : 2, success_count: empty ? 0 : failed ? 1 : 2,
      error_count: 0, timeout_count: failed ? 1 : 0, rate_limit_count: failed ? 1 : 0,
      cancelled_count: failed || scenario === 'llm-cancelled' ? 1 : 0, unclassified_count: 0,
      mean_duration_ms: empty ? null : 120, last_success_at: empty ? null : body.generated_at, window_limited: false };
    body.modules[5] = { id: 'llm', status: empty ? 'unknown' : failed ? 'warning' : 'healthy',
      freshness: empty ? 'unmeasured' : 'fresh', source: 'qa_llm_passive',
      reason: scenario === 'llm-unavailable' ? 'llm_observation_unavailable' : scenario === 'llm-no-traffic' ? 'llm_no_recent_requests' : scenario === 'llm-cancelled' ? 'llm_inconclusive' : failed ? 'llm_requests_failed' : 'llm_requests_ok',
      observed_at: empty ? null : body.generated_at, last_success_at: empty ? null : body.generated_at,
      measurement: empty ? { key: 'not_measured', value: null, unit: 'none', threshold: null }
        : { key: 'llm_success_rate', value: scenario === 'llm-invalid-rate' ? 110 : failed ? 33.33 : 100, unit: 'percent', threshold: null },
      details: scenario === 'llm-unavailable' ? {} : details };
    if (scenario === 'llm-private') body.modules[5].details.private = PRIVATE_HEALTH_DETAIL;
  }
  if (['frontend-ok', 'frontend-failed', 'frontend-invalid-status', 'frontend-invalid-revision'].includes(scenario)) {
    body.modules[0] = { id: 'frontend', status: scenario === 'frontend-failed' ? 'critical' : 'healthy', freshness: 'fresh',
      reason: scenario === 'frontend-failed' ? 'frontend_entry_failed' : 'frontend_entry_ok', source: 'qa_frontend_http',
      observed_at: body.generated_at, last_success_at: scenario === 'frontend-failed' ? null : body.generated_at,
      measurement: { key: 'frontend_response_duration', value: scenario === 'frontend-failed' ? 1000 : 120, unit: 'milliseconds', threshold: 1000 },
      details: scenario === 'frontend-failed' ? { http_status: 503 } : { http_status: 200, frontend_revision: 'f'.repeat(40) } };
    if (scenario === 'frontend-invalid-status') body.modules[0].details.http_status = 700;
    if (scenario === 'frontend-invalid-revision') body.modules[0].details.frontend_revision = PRIVATE_HEALTH_DETAIL;
  }
  return body;
}

// Rebase the shared example for the non-preview artifact's real freshness rules.
// Original relative job ages remain intact; this never enters application code.
function currentHealthBody(scenario = 'normal', now = Date.now()) {
  const body = healthBody(scenario);
  const offset = now - Date.parse(body.generated_at) - (scenario === 'expired' ? 121000 : 0);
  const shift = (stamp) => stamp === null ? null : new Date(Date.parse(stamp) + offset).toISOString();
  body.generated_at = shift(body.generated_at);
  for (const row of body.modules) { row.observed_at = shift(row.observed_at); row.last_success_at = shift(row.last_success_at); if (Object.hasOwn(row.details, 'last_success_at')) row.details.last_success_at = shift(row.details.last_success_at); }
  return body;
}

function historyBody({ module = 'indexer', window = '24h', scenario = 'empty', now = Date.now() } = {}) {
  const body = JSON.parse(JSON.stringify(historyExample));
  const offset = now - Date.parse(body.generated_at);
  const shift = (at) => at === null ? null : new Date(Date.parse(at) + offset).toISOString();
  body.generated_at = shift(body.generated_at); body.end_at = body.generated_at;
  body.start_at = new Date(now - (window === '7d' ? 604800000 : 86400000)).toISOString();
  body.module = module; body.window = window;
  body.samples = scenario === 'empty' ? [] : body.samples.map((point) => ({ ...point, sampled_at: shift(point.sampled_at), observed_at: shift(point.observed_at) }));
  if (module !== 'indexer') {
    const row = example.modules.find((item) => item.id === module);
    body.samples = body.samples.map((point) => ({ ...point, status: row.status, freshness: row.freshness,
      observed_at: row.observed_at === null ? null : point.sampled_at, measurement: { ...row.measurement } }));
  }
  if (module === 'frontend' && scenario === 'frontend') {
    body.samples = body.samples.map((point, index) => ({ ...point, source_sha: 'a'.repeat(40),
      sampled_at: new Date(now - (5 - index) * 300000).toISOString(),
      observed_at: index ? new Date(now - (5 - index) * 300000).toISOString() : null,
      target_sha: !index || index === 4 ? null : (index < 3 ? 'f' : 'e').repeat(40),
      status: !index ? 'unknown' : index === 4 ? 'critical' : 'healthy', freshness: index ? 'fresh' : 'unmeasured',
      measurement: !index ? { key: 'not_measured', value: null, unit: 'none', threshold: null }
        : { key: 'frontend_response_duration', value: index === 4 ? 1000 : 120, unit: 'milliseconds', threshold: 1000 } }));
  }
  if (scenario === 'invalid') body.samples[0].source_sha = 'unverified';
  if (module === 'llm' && scenario === 'llm') {
    body.samples = body.samples.map((point, index) => ({ ...point, status: index ? index === 4 ? 'warning' : 'healthy' : 'unknown', freshness: index ? 'fresh' : 'unmeasured',
      observed_at: index ? point.sampled_at : null, measurement: index ? { key: 'llm_success_rate', value: index === 4 ? 50 : 100, unit: 'percent', threshold: null } : { key: 'not_measured', value: null, unit: 'none', threshold: null } }));
  }
  const last = body.samples.at(-1)?.sampled_at || null;
  body.sampling = { last_success_at: last, overdue_seconds: last ? Math.max(0, Math.floor((now - Date.parse(last)) / 1000) - 300) : null,
    missed_intervals: last ? (() => { const slots = new Set(body.samples.map((p) => Math.floor(Date.parse(p.sampled_at) / 300000))); return Math.max(...slots) - Math.min(...slots) + 1 - slots.size + Math.floor(Math.max(0, now - Date.parse(last) - 60000) / 300000); })() : null, missed_since_at: body.samples[0]?.sampled_at || null,
    last_attempt: last ? { started_at: new Date(now - 2000).toISOString(), finished_at: new Date(now).toISOString(), outcome: scenario === 'sampling-lock' ? 'lock_busy' : scenario === 'sampling-failed' ? 'failed' : 'ok' } : null };
  if (scenario === 'sampling-delayed') body.sampling.overdue_seconds = 601;
  if (scenario === 'sampling-invalid') body.sampling.last_attempt.outcome = PRIVATE_HEALTH_DETAIL;
  return body;
}

async function routeHealth(page, initial = 'normal', initialHistory = 'empty') {
  let scenario = initial;
  let historyScenario = initialHistory;
  const requests = [], historyRequests = [];
  await page.route('**/api/qa/health/history?**', async (route) => {
    const request = route.request(), url = new URL(request.url());
    historyRequests.push({ method: request.method(), module: url.searchParams.get('module'), window: url.searchParams.get('window'), token: request.headers().authorization });
    const status = !request.headers().authorization ? 401 : historyScenario === 'error' ? 503 : 200;
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(status === 200 ? historyBody({ module: url.searchParams.get('module'), window: url.searchParams.get('window'), scenario: historyScenario }) : { status: 'unavailable' }) });
  });
  await page.route('**/api/qa/health', async (route) => {
    const request = route.request();
    requests.push({ method: request.method(), path: new URL(request.url()).pathname, token: request.headers().authorization });
    const status = request.method() !== 'GET' ? 405 : !request.headers().authorization ? 401 : scenario === 'error' ? 503 : 200;
    await route.fulfill({ status, contentType: 'application/json', headers: { 'Cache-Control': 'no-store' },
      body: JSON.stringify(status === 200 ? currentHealthBody(scenario) : { status: 'unavailable', generated_at: null }) });
  });
  return { change(value) { scenario = value; }, changeHistory(value) { historyScenario = value; }, requests: () => requests.map((entry) => ({ ...entry })), historyRequests: () => historyRequests.map((entry) => ({ ...entry })) };
}

async function openHealthPage(page, { scenario = 'normal', history = 'empty', signedIn = true, phone = false, tablet = false, navigation = false } = {}) {
  const common = require('./observatory-physical.cjs');
  if (phone) await page.setViewportSize({ width: 390, height: 844 });
  if (tablet) await page.setViewportSize({ width: 1024, height: 768 });
  const sources = await common.routeSnapshot(page);
  const health = await routeHealth(page, scenario, history);
  const auth = await common.authenticate(page, { signedIn });
  await page.goto(common.BASE + '/observatory' + (navigation ? '' : '?view=health'));
  if (signedIn) {
    if (navigation) await common.selectView(page, 'health');
    await page.getByTestId('qa-health-workspace').waitFor();
  } else await page.getByRole('button', { name: '使用 Google 帳號登入' }).waitFor();
  return { health, sources, ...auth };
}

async function healthState(page) {
  const workspace = page.getByTestId('qa-health-workspace'), panel = workspace.getByTestId('qa-health');
  return { text: await workspace.innerText(), visible: await panel.isVisible(),
    coverage: await workspace.getByTestId('health-coverage').count() ? await workspace.getByTestId('health-coverage').innerText() : '',
    counts: await workspace.getByTestId('health-run-counts').count() ? await workspace.getByTestId('health-run-counts').innerText() : '',
    observedIssues: await workspace.getByTestId('health-observed-issues').count() ? await workspace.getByTestId('health-observed-issues').innerText() : '',
    missingObservations: await workspace.getByTestId('health-unobserved-modules').count() ? await workspace.getByTestId('health-unobserved-modules').innerText() : '',
    view: await panel.count() ? await panel.getAttribute('data-mobile-view') : null,
    all: await panel.count() ? await panel.getByTestId('health-filter-all').getAttribute('aria-pressed') : null,
    focus: await page.evaluate(() => document.activeElement?.getAttribute('data-testid')),
    scroll: await page.locator('.qa-workspace').evaluate((element) => element.scrollTop),
    overflow: await page.evaluate(() => document.documentElement.scrollWidth > innerWidth) };
}

async function refreshHealth(page) {
  const retry = page.getByTestId('health-retry');
  await (await retry.isVisible() ? retry : page.getByTestId('health-refresh')).click();
}
async function inspectAllHealth(page) {
  await page.getByTestId('health-filter-all').click();
  await page.getByTestId('health-module-indexer').scrollIntoViewIfNeeded();
}
const chooseHealth = (page, id) => page.getByTestId('health-module-' + id).click();
const returnHealth = (page) => page.getByTestId('health-back-to-issues').click();
const openHealthEvidence = (page) => page.getByTestId('health-evidence').click();
const closeHealthEvidence = (page) => page.getByTestId('health-close-evidence').click();
const healthEvidenceKey = (page, key) => page.getByRole('tab', { name: /檢查摘要|Check summary/, exact: true }).press(key);
async function rawHealthEvidence(page) {
  await page.getByTestId('health-evidence-tab-raw').click();
  return JSON.parse(await page.locator('dialog[open] pre').innerText());
}
async function downloadJSON(page, control) {
  const pending = page.waitForEvent('download');
  await page.getByTestId(control).click();
  const download = await pending, stream = await download.createReadStream(), chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return { filename: download.suggestedFilename(), failure: await download.failure(),
    body: JSON.parse(Buffer.concat(chunks).toString('utf8')) };
}
const downloadHealthEvidence = (page) => downloadJSON(page, 'health-download');
const downloadHealthHistory = (page) => downloadJSON(page, 'health-history-download');
const chooseHistoryWindow = (page, value) => page.getByTestId('history-window-' + value).click();
const retryHealthHistory = (page) => page.getByTestId('health-history-retry').click();
async function healthHistoryState(page) {
  const history = page.getByTestId('health-history');
  return { text: await history.innerText(), lines: await history.getByTestId('history-line').count(), chart: await history.getByTestId('history-chart').count(),
    unmeasured: await history.getByTestId('history-unmeasured').count(),
    sevenDays: await history.getByTestId('history-window-7d').getAttribute('aria-pressed'), theme: await page.locator('.qa-page').getAttribute('data-mode') };
}
const setHealthTheme = (page, dark) => require('./observatory-physical.cjs').setTheme(page, dark);
async function captureHistoryProof(page, name) {
  if (!process.env.QA_HEALTH_HISTORY_PROOF_DIR) return;
  const fs = require('node:fs/promises'), path = require('node:path');
  await fs.mkdir(process.env.QA_HEALTH_HISTORY_PROOF_DIR, { recursive: true });
  await page.getByTestId('health-history').screenshot({ path: path.join(process.env.QA_HEALTH_HISTORY_PROOF_DIR, name + '.png') });
}
async function capturePassiveProof(page, name) {
  if (!process.env.QA_HEALTH_PASSIVE_PROOF_DIR) return;
  const fs = require('node:fs/promises'), path = require('node:path');
  await fs.mkdir(process.env.QA_HEALTH_PASSIVE_PROOF_DIR, { recursive: true });
  await page.locator('.qa-workspace').evaluate((element) => { element.scrollTop = 0; });
  await page.screenshot({ path: path.join(process.env.QA_HEALTH_PASSIVE_PROOF_DIR, name + '.png'), animations: 'disabled' });
}
async function healthEvidenceState(page) {
  const dialog = page.locator('dialog[open]');
  return { open: await dialog.count(), text: await dialog.count() ? await dialog.innerText() : '',
    selected: await page.getByTestId('health-evidence-tab-raw').getAttribute('aria-selected'),
    focus: await page.evaluate(() => document.activeElement?.getAttribute('data-testid')) };
}
const signOutHealth = (page) => require('./observatory-physical.cjs').logout(page);
async function signedOutHealthState(page) { return { login: await page.getByRole('button', { name: '使用 Google 帳號登入' }).isVisible(), health: await page.getByTestId('qa-health-workspace').count() }; }

module.exports = { healthBody, historyBody, currentHealthBody, PRIVATE_HEALTH_DETAIL, openHealthPage, healthState,
  refreshHealth, inspectAllHealth, chooseHealth, returnHealth, openHealthEvidence, closeHealthEvidence,
  downloadHealthHistory, chooseHistoryWindow, retryHealthHistory, healthHistoryState,
  captureHistoryProof, capturePassiveProof,
  setHealthTheme,
  rawHealthEvidence, downloadHealthEvidence, healthEvidenceKey, healthEvidenceState, signOutHealth, signedOutHealthState };
