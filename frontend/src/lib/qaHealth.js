// Public /qa/health v1 allowlist. Unknown fields and transport diagnostics never
// become UI evidence, and invalid payloads cannot fall back to design examples.
const names = { frontend: 'Frontend', agent: 'Agent API', es: 'Elasticsearch', crawler: 'Crawler', indexer: 'Indexer', llm: 'LLM API', collector: 'collector' };
const states = new Set(['healthy', 'warning', 'critical', 'unknown', 'stale']);
const reasons = new Set(['not_connected', 'api_responded', 'read_probe_ok', 'read_probe_failed', 'collection_completed', 'job_reported', 'job_failed', 'old_artifact', 'missing_artifact', 'invalid_artifact', 'future_artifact', 'frontend_entry_ok', 'frontend_entry_failed', 'invalid_probe_target']);
const sources = new Set(['not_connected', 'qa_request', 'news_read_probe', 'crawler_summary', 'indexer_summary', 'health_assembly', 'qa_frontend_http']);
const metrics = new Set(['not_measured', 'response_check', 'read_probe_duration', 'job_report_age', 'assembly_duration', 'frontend_response_duration']);
const units = new Set(['none', 'checks', 'seconds', 'milliseconds']);
for (const reason of ['llm_no_recent_requests', 'llm_inconclusive', 'llm_requests_ok', 'llm_requests_failed', 'llm_observation_unavailable']) reasons.add(reason);
sources.add('qa_llm_passive'); metrics.add('llm_success_rate'); units.add('percent');
const numberOrNull = (value) => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1e12);
const timestamp = (value) => typeof value === 'string' && value.length <= 40 && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));

export function parseHealthSnapshot(value) {
  if (!value || value.schema_version !== 1 || value.kind !== 'observed_health' || value.environment !== 'qa'
    || value.scope !== 'current_qa_instance_and_shared_ingestion' || value.quality_review !== 'unmeasured'
    || !timestamp(value.generated_at) || !Number.isInteger(value.max_age_seconds) || value.max_age_seconds < 10 || value.max_age_seconds > 3600
    || !Number.isInteger(value.cache_seconds) || value.cache_seconds < 0 || value.cache_seconds > value.max_age_seconds
    || !(value.source_sha === null || /^[a-f0-9]{40}$/.test(value.source_sha))
    || !Array.isArray(value.modules) || value.modules.length !== Object.keys(names).length) return null;
  const seen = new Set(), rows = [];
  for (const row of value.modules) {
    const m = row?.measurement;
    if (!row || !Object.hasOwn(names, row.id) || seen.has(row.id) || !states.has(row.status)
      || !reasons.has(row.reason) || !sources.has(row.source) || !['fresh', 'stale', 'unmeasured'].includes(row.freshness)
      || !(row.observed_at === null || timestamp(row.observed_at)) || !(row.last_success_at === null || timestamp(row.last_success_at))
      || (row.observed_at && Date.parse(row.observed_at) > Date.parse(value.generated_at) + 30000)
      || (row.last_success_at && (!row.observed_at || Date.parse(row.last_success_at) > Date.parse(row.observed_at)))
      || !m || !metrics.has(m.key) || !units.has(m.unit) || !numberOrNull(m.value) || !numberOrNull(m.threshold)
      || ((m.key === 'frontend_response_duration' || row.source === 'qa_frontend_http') && row.id !== 'frontend')
      || ((m.key === 'llm_success_rate' || row.source === 'qa_llm_passive' || row.reason.startsWith('llm_')) && row.id !== 'llm')
      || (m.key === 'llm_success_rate' && (m.unit !== 'percent' || m.value === null || m.value > 100 || m.threshold !== null))
      || !row.details || typeof row.details !== 'object' || Array.isArray(row.details)) return null;
    if (row.freshness === 'unmeasured' && (row.observed_at !== null || m.value !== null || row.status === 'healthy')) return null;
    if (row.freshness === 'fresh' && (!row.observed_at || m.value === null)) return null;
    const details = {};
    for (const key of ['errors', 'skipped_embed_error', 'retry_pending']) {
      if (Object.hasOwn(row.details, key)) {
        if (!Number.isSafeInteger(row.details[key]) || row.details[key] < 0 || row.details[key] > 1e12) return null;
        details[key] = row.details[key];
      }
    }
    if (Object.hasOwn(row.details, 'http_status')) {
      if (row.id !== 'frontend' || !Number.isInteger(row.details.http_status) || row.details.http_status < 100 || row.details.http_status > 599) return null;
      details.http_status = row.details.http_status;
    }
    if (Object.hasOwn(row.details, 'frontend_revision')) {
      if (row.id !== 'frontend' || typeof row.details.frontend_revision !== 'string' || !/^[a-f0-9]{40}$/.test(row.details.frontend_revision)) return null;
      details.frontend_revision = row.details.frontend_revision;
    }
    if (row.source === 'qa_llm_passive' && row.reason !== 'llm_observation_unavailable') {
      const counts = ['request_count', 'completed_count', 'success_count', 'error_count', 'timeout_count', 'rate_limit_count', 'cancelled_count', 'unclassified_count'];
      for (const key of counts) {
        if (!Number.isInteger(row.details[key]) || row.details[key] < 0 || row.details[key] > 4096) return null;
        details[key] = row.details[key];
      }
      if (row.details.window_seconds !== 900 || !numberOrNull(row.details.mean_duration_ms)
        || !(row.details.last_success_at === null || timestamp(row.details.last_success_at) && Date.parse(row.details.last_success_at) <= Date.parse(value.generated_at) + 30000)
        || (Object.hasOwn(row.details, 'window_limited') && typeof row.details.window_limited !== 'boolean')
        || details.completed_count !== details.success_count + details.error_count + details.timeout_count + details.rate_limit_count
        || details.request_count !== details.completed_count + details.cancelled_count + details.unclassified_count
        || (details.completed_count > 0 ? m.key !== 'llm_success_rate' : m.key !== 'not_measured')
        || (m.key === 'llm_success_rate' && (!details.completed_count || Math.abs(m.value - Math.round(details.success_count / details.completed_count * 10000) / 100) > 1e-8))
        || (row.status === 'healthy' && (!details.completed_count || details.completed_count !== details.success_count || details.unclassified_count || row.details.window_limited))) return null;
      Object.assign(details, { window_seconds: 900, mean_duration_ms: row.details.mean_duration_ms,
        last_success_at: row.details.last_success_at, window_limited: row.details.window_limited ?? false });
    }
    rows.push({ id: row.id, status: row.status, reason: row.reason, freshness: row.freshness,
      observed_at: row.observed_at, last_success_at: row.last_success_at, source: row.source,
      measurement: { key: m.key, value: m.value, unit: m.unit, threshold: m.threshold }, details });
    seen.add(row.id);
  }
  return { schema_version: 1, kind: value.kind, environment: 'qa', scope: value.scope,
    generated_at: value.generated_at, source_sha: value.source_sha, max_age_seconds: value.max_age_seconds,
    cache_seconds: value.cache_seconds, quality_review: 'unmeasured', modules: rows };
}

export function healthTimestamp(value) {
  if (!value || !timestamp(value)) return null;
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(value));
}

export function observedHealthModel(packet, { now = Date.now(), forceStale = false, preview = false } = {}) {
  const generated = Date.parse(packet.generated_at);
  const expired = forceStale || (!preview && (now - generated > packet.max_age_seconds * 1000 || generated - now > 30000));
  return {
    observedAt: packet.generated_at, version: packet.source_sha?.slice(0, 12) || null,
    environment: 'QA', expired, packet,
    modules: packet.modules.map((row) => {
      const fresh = !expired && row.freshness === 'fresh';
      const status = row.status === 'critical' ? 'critical' : row.freshness === 'unmeasured' ? 'unknown' : fresh ? row.status : 'stale';
      return { id: row.id, name: names[row.id], status, fresh, reason: row.reason, score: null,
        value: row.measurement.value, unit: row.measurement.unit, threshold: row.measurement.threshold,
        metric: row.measurement.key, observedAt: healthTimestamp(row.observed_at),
        observedAtEpoch: row.observed_at ? Date.parse(row.observed_at) : null,
        lastSuccess: healthTimestamp(row.last_success_at), source: row.source,
        details: row.details, pending: null, events: [], samples: [], raw: row };
    }),
  };
}
