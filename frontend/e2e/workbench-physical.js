/** Contract: generic /api adapter protocol. Browser fixtures never call a model. */
import fs from 'node:fs/promises';
import http from 'node:http';
import healthFixtures from './observatory-health-physical.cjs';
export async function browserWorkbench(page) {
  const sha = 'a'.repeat(40), hash = 'b'.repeat(64), requests = [], runs = [];
  const tasks = [{ id: 'inventory', title: 'Inventory integrity', description: 'Reconcile a different business domain.', paid: false, input_schema: { type: 'object' } }, { id: 'support', title: 'Support answer review', paid: true, requires_review: true }];
  const response = (route, value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
  await page.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method(), body = method === 'POST' ? request.postDataJSON() : null;
    requests.push({ path, method, body });
    if (path === '/api/capabilities') return response(route, { project: { id: 'warehouse', name: 'Warehouse QA', source_sha: sha }, source_sha: sha, tasks });
    if (path === '/api/runs' && method === 'GET') return response(route, { runs });
    if (path === '/api/health') return response(route, { status: 'unknown', observations: [], quality_status: 'not_evaluated' });
    if (path === '/api/runs' && method === 'POST') {
      const job = { id: '1'.repeat(32), task_id: body.task_id, status: 'completed', source_sha: sha, structural_status: 'passed', semantic_status: 'pending_review', quality_passed: false, report_sha256: hash, report_available: true, evidence_kind: 'synthetic', gaps: ['human_review_pending'], created_at: '2026-10-28T00:00:00Z' };
      runs.unshift(job); return response(route, { job }, 202);
    }
    if (path === '/api/runs/import' && method === 'POST') { const job = { ...body.job, id: '2'.repeat(32), source_sha: 'c'.repeat(40), imported: true, quality_passed: false }; runs.unshift(job); return response(route, { job }, 201); }
    const id = path.split('/')[3], job = runs.find(value => value.id === id);
    if (!job) return response(route, { detail: 'run_not_found' }, 404);
    if (path.endsWith('/logs')) return response(route, { text: url.searchParams.get('offset') === '0' ? 'Measured fixture output\n' : '', next_offset: 24, total_bytes: 24, has_more: false, complete: true, truncated: false });
    if (path.endsWith('/report')) return response(route, { job, report: { evidence_kind: 'synthetic', rows: [{ case_id: 'inventory-1' }] }, report_sha256: hash, review_contract: { rows_key: 'rows', rows: [{ index: 0, row_sha256: 'd'.repeat(64) }] } });
    if (path.endsWith('/review')) { job.semantic_status = 'reviewed'; job.review = { verdict: body.verdict }; job.quality_passed = false; return response(route, { job }); }
    return response(route, { job });
  });
  await page.goto('/');
  await page.getByRole('heading', { level: 1, name: 'Inventory integrity' }).waitFor();
  return {
    choose: id => page.getByTestId('task-' + id).click(),
    start: () => page.getByTestId('start-run').click(),
    consent: async () => { await page.getByTestId('task-budget').fill('0.25'); await page.getByTestId('task-consent').check(); },
    starts: () => structuredClone(requests.filter(value => value.path === '/api/runs' && value.method === 'POST')),
    reviews: () => structuredClone(requests.filter(value => value.path.endsWith('/review'))),
    imports: () => structuredClone(requests.filter(value => value.path.endsWith('/import'))),
    text: () => page.locator('.wb-main').innerText(),
    disabled: () => page.getByTestId('start-run').isDisabled(),
    async download() { const event = page.waitForEvent('download'); await page.getByRole('button', { name: 'Download report' }).click(); const download = await event; return { name: download.suggestedFilename(), text: await fs.readFile(await download.path(), 'utf8') }; },
    async prepareReview() { await page.getByText('Submit an evidence-bound review', { exact: true }).click(); await page.getByRole('button', { name: 'Load exact row hashes for review' }).click(); },
    reviewTemplate: async () => JSON.parse(await page.getByLabel('Case reviews (JSON array of row_sha256, verdict, reason)').inputValue()),
    async review() { await page.getByLabel('Reviewer', { exact: true }).fill('Independent fixture reviewer'); await page.getByLabel('Evidence-based reason').fill('The captured response lacks the required source evidence.'); await page.getByLabel('Case reviews (JSON array of row_sha256, verdict, reason)').fill(JSON.stringify([{ row_sha256: 'd'.repeat(64), verdict: 'failed', reason: 'The captured answer omits inventory source evidence.' }])); await page.getByRole('button', { name: 'Submit review', exact: true }).click(); },
    async import(text) { await page.locator('input[type=file]').setInputFiles({ name: 'historical-evidence.json', mimeType: 'application/json', buffer: Buffer.from(text) }); },
    history: () => page.getByRole('button', { name: /Execution history/ }).click(),
    async mobile() { await page.setViewportSize({ width: 390, height: 844 }); },
    overflow: () => page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth })),
    screenshot: path => page.screenshot({ path, fullPage: true }),
  };
}

export async function browserHealthHistory(page) {
  const requests = [];
  await page.route('**/api/qa/health**', route => {
    const request = route.request(), url = new URL(request.url());
    requests.push({ method: request.method(), path: url.pathname });
    const body = url.pathname.endsWith('/history')
      ? healthFixtures.historyBody({ module: url.searchParams.get('module'), window: url.searchParams.get('window'), scenario: 'normal' })
      : healthFixtures.currentHealthBody('llm-failed');
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/tests/health-preview.html');
  await page.getByTestId('health-module-indexer').waitFor();
  await page.getByTestId('health-module-indexer').click();
  await page.getByTestId('history-chart').waitFor();
  await page.evaluate(() => document.fonts.ready);
  return {
    requests: () => structuredClone(requests),
    text: () => page.getByTestId('health-history').innerText(),
    sevenDays: () => page.getByTestId('history-window-7d').click(),
    async mobile() { await page.setViewportSize({ width: 390, height: 844 }); await page.getByTestId('health-module-indexer').click(); },
    screenshot: path => page.screenshot({ path, fullPage: true }),
    overflow: () => page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth })),
  };
}

/** An actual local HTTP server enforces bearer auth; no browser route mock. */
export async function browserAuthenticatedWorkbench(page) {
  const fixtureToken = 'offline-http-authorized-identity', requests = [];
  const server = http.createServer((request, response) => {
    response.setHeader('Access-Control-Allow-Origin', request.headers.origin || '*');
    response.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type');
    response.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    if (request.method === 'OPTIONS') { response.writeHead(204); response.end(); return; }
    const authorized = request.headers.authorization === 'Bearer ' + fixtureToken;
    requests.push({ method: request.method, authorized });
    response.setHeader('Content-Type', 'application/json');
    if (!authorized) { response.writeHead(401); response.end(JSON.stringify({ detail: 'Rejected credential must stay private: ' + request.headers.authorization })); return; }
    response.end(JSON.stringify(request.url.endsWith('/capabilities') ? { project: { id: 'protected-project', name: 'Protected project' }, tasks: [{ id: 'private-check', title: 'Authenticated project checks', paid: false }] } : { runs: [] }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port + '/api';
  await page.addInitScript(value => { window.QA_WORKBENCH_CONFIG = { apiBase: value }; }, base);
  await page.goto('/');
  await page.getByRole('heading', { name: 'Sign in to QA Workbench' }).waitFor();
  return {
    async signIn(valid = true) { await page.getByTestId('auth-token').fill(valid ? fixtureToken : 'rejected-http-fixture'); await page.getByTestId('auth-signin').click(); },
    choose: () => page.getByTestId('task-private-check').click(),
    logout: () => page.getByTestId('auth-signout').click(),
    reload: () => page.reload(),
    observation: async () => ({ requests: structuredClone(requests), text: await page.locator('body').innerText(), applications: await page.locator('.wb-app').count(), credential: await page.getByTestId('auth-token').count() ? await page.getByTestId('auth-token').inputValue() : null, tokenInStorage: await page.evaluate(value => [localStorage, sessionStorage].some(storage => JSON.stringify({ ...storage }).includes(value)), fixtureToken) }),
    async close() { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); },
  };
}
