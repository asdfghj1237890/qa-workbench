/** Independent request contract for the frozen, synthetic execution API. */
const object = value => !!value && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string' && !!value.trim();
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const keys = (value, required, optional = []) => object(value) && required.every(key => key in value) && Object.keys(value).every(key => [...required, ...optional].includes(key));
const paid = body => body.acknowledge_cost === true && typeof body.max_usd === 'number' && Number.isFinite(body.max_usd) && body.max_usd > 0;
function sidecar(value) {
  return keys(value, ['report_sha256', 'reviewer_kind', 'reviewer', 'reviewed_at', 'reviews']) && hash(value.report_sha256)
    && ['ai', 'human'].includes(value.reviewer_kind) && text(value.reviewer) && text(value.reviewed_at)
    && Array.isArray(value.reviews) && value.reviews.length > 0 && value.reviews.every(row =>
      keys(row, ['key', 'row_sha', 'reviewer', 'scores', 'reason']) && text(row.key) && hash(row.row_sha) && text(row.reviewer) && text(row.reason)
      && keys(row.scores, ['intent', 'grounding', 'completeness', 'language']) && Object.values(row.scores).every(score => typeof score === 'boolean'));
}
function workbenchReview(value) {
  return keys(value, ['report_sha256', 'reviewer', 'reason', 'verdict', 'rows']) && hash(value.report_sha256)
    && text(value.reviewer) && text(value.reason) && ['passed', 'failed'].includes(value.verdict)
    && Array.isArray(value.rows) && value.rows.every(row => keys(row, ['row_sha256', 'verdict', 'reason']) && hash(row.row_sha256) && ['passed', 'failed'].includes(row.verdict) && text(row.reason));
}
export function executionRequest({ kind, base, path, method, body, query }) {
  const reject = () => { throw new TypeError('Unexpected execution API request: ' + method + ' ' + path); };
  if (path !== base && !path.startsWith(base + '/')) reject();
  const suffix = path.slice(base.length), generic = kind === 'workbench';
  const root = generic ? '/runs' : '';
  const detail = suffix.match(generic ? /^\/runs\/([a-zA-Z0-9-]{1,64})(?:\/(cancel|review|report|logs))?$/ : /^\/([a-zA-Z0-9-]{1,64})(?:\/(cancel|review|report))?$/);
  const op = detail?.[2] || 'detail';
  if (method === 'GET' && body === undefined) {
    if (query && !(generic && op === 'logs' && /^\?offset=\d+&limit=32768$/.test(query))) reject();
    if (generic && suffix === '/capabilities') return { operation: 'capabilities' };
    if (generic && suffix === '/health') return { operation: 'health' };
    if (suffix === root) return { operation: generic ? 'history' : 'capabilities' };
    if (detail && ['detail', 'report', ...(generic ? ['logs'] : kind === 'live' ? ['review'] : [])].includes(op)) return { operation: op, id: detail[1] };
  }
  if (method === 'POST' && !query) {
    if (suffix === root) {
      const valid = generic ? keys(body, ['task_id', 'options'], ['acknowledge_cost', 'max_usd']) && ['inventory', 'quality'].includes(body.task_id) && object(body.options)
          && (body.task_id === 'quality' ? paid(body) : !('acknowledge_cost' in body) && !('max_usd' in body))
        : kind === 'validation' ? keys(body, ['mode', 'suite'], ['max_usd', 'acknowledge_cost', 'cf_token']) && ['offline_regression', 'es_integration', 'real_es_llm_e2e'].includes(body.mode)
          && ['all', 'ingestion', 'rag', 'agents'].includes(body.suite) && (body.mode === 'offline_regression' || body.suite === 'all')
          && (body.mode === 'real_es_llm_e2e' ? paid(body) : !('acknowledge_cost' in body) && !('max_usd' in body)) && (body.cf_token === undefined || text(body.cf_token))
        : keys(body, ['profile', 'max_usd', 'acknowledge_cost']) && ['quick', 'dev', 'holdout', 'all'].includes(body.profile) && paid(body);
      if (!valid) reject();
      return { operation: 'start' };
    }
    if (suffix === root + '/import' && kind !== 'validation') {
      if (!(generic ? keys(body, ['job', 'report', 'report_sha256'], ['review', 'review_contract']) : keys(body, ['version', 'job', 'report', 'review']))
        || (generic ? !hash(body.report_sha256) : body.version !== 1 || !sidecar(body.review))
        || !object(body.job) || !text(body.job.id) || !object(body.report)) reject();
      return { operation: 'import' };
    }
    if (detail && op === 'cancel') {
      if (generic ? !keys(body, []) : body !== undefined) reject();
      return { operation: 'cancel', id: detail[1] };
    }
    if (detail && op === 'review' && kind !== 'validation') {
      if (!(generic ? workbenchReview(body) : sidecar(body))) reject();
      return { operation: 'review', id: detail[1] };
    }
  }
  reject();
}
