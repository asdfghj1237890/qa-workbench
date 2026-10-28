const ids = new Set(['frontend', 'agent', 'es', 'crawler', 'indexer', 'llm', 'collector']);
const states = new Set(['healthy', 'warning', 'critical', 'unknown', 'stale']);
const metricUnits = { not_measured: 'none', response_check: 'checks', read_probe_duration: 'milliseconds', job_report_age: 'seconds', assembly_duration: 'milliseconds', frontend_response_duration: 'milliseconds' };
const stamp = (value) => typeof value === 'string' && value.length <= 40 && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const number = (value) => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1e12);
metricUnits.llm_success_rate = 'percent';

function parseSampling(value, generated) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const nullableStamp = (at) => at === null || stamp(at) && Date.parse(at) <= Date.parse(generated) + 30000;
  if (!nullableStamp(value.last_success_at) || !nullableStamp(value.missed_since_at)
    || !(value.overdue_seconds === null || Number.isSafeInteger(value.overdue_seconds) && value.overdue_seconds >= 0 && value.overdue_seconds <= 1e12)
    || !(value.missed_intervals === null || Number.isInteger(value.missed_intervals) && value.missed_intervals >= 0 && value.missed_intervals <= 2017)
    || (value.missed_since_at && (!value.last_success_at || Date.parse(value.missed_since_at) > Date.parse(value.last_success_at)))) return null;
  const attempt = value.last_attempt;
  if (attempt !== null && (!attempt || !stamp(attempt.started_at) || !nullableStamp(attempt.finished_at) || attempt.finished_at === null
    || Date.parse(attempt.started_at) > Date.parse(attempt.finished_at) || !['ok', 'lock_busy', 'failed'].includes(attempt.outcome))) return null;
  return { last_success_at: value.last_success_at, missed_since_at: value.missed_since_at,
    overdue_seconds: value.overdue_seconds, missed_intervals: value.missed_intervals,
    last_attempt: attempt === null ? null : { started_at: attempt.started_at, finished_at: attempt.finished_at, outcome: attempt.outcome } };
}

export function parseHealthHistory(value, { module, window, now = Date.now() }) {
  if (!value || value.schema_version !== 1 || value.kind !== 'health_history' || value.environment !== 'qa'
    || value.scope !== 'active_qa_instance_and_shared_ingestion' || value.module !== module || !ids.has(module)
    || value.window !== window || !['24h', '7d'].includes(window) || value.interval_seconds !== 300 || value.retention_seconds !== 604800
    || value.score !== null || value.quality_review !== 'unmeasured' || !stamp(value.generated_at) || !stamp(value.start_at) || !stamp(value.end_at)
    || Date.parse(value.end_at) !== Date.parse(value.generated_at)
    || Date.parse(value.generated_at) - now > 30000
    || Date.parse(value.end_at) - Date.parse(value.start_at) !== (window === '24h' ? 86400000 : 604800000)
    || !Array.isArray(value.samples) || value.samples.length > 2017) return null;
  let previous = -Infinity;
  const rows = [];
  for (const row of value.samples) {
    const m = row?.measurement, at = Date.parse(row?.sampled_at), target = row?.target_sha ?? null;
    if (!row || !stamp(row.sampled_at) || at <= previous || at < Date.parse(value.start_at) || at > Date.parse(value.end_at)
      || !/^[a-f0-9]{40}$/.test(row.source_sha) || !states.has(row.status) || !['fresh', 'stale', 'unmeasured'].includes(row.freshness)
      || (target !== null && (module !== 'frontend' || typeof target !== 'string' || !/^[a-f0-9]{40}$/.test(target)))
      || !(row.observed_at === null || (stamp(row.observed_at) && Date.parse(row.observed_at) <= at + 30000))
      || !m || !Object.hasOwn(metricUnits, m.key) || metricUnits[m.key] !== m.unit || !number(m.value) || !number(m.threshold)
      || (m.key === 'frontend_response_duration' && module !== 'frontend')
      || (m.key === 'llm_success_rate' && (module !== 'llm' || m.value === null || m.value > 100 || m.threshold !== null))
      || (row.freshness === 'fresh' && (m.value === null || row.observed_at === null))
      || (row.freshness === 'unmeasured' && (m.value !== null || row.observed_at !== null || row.status === 'healthy'))) return null;
    previous = at;
    rows.push({ sampled_at: row.sampled_at, source_sha: row.source_sha, target_sha: target, status: row.status, freshness: row.freshness,
      observed_at: row.observed_at, measurement: { key: m.key, value: m.value, unit: m.unit, threshold: m.threshold } });
  }
  const sampling = Object.hasOwn(value, 'sampling') ? parseSampling(value.sampling, value.generated_at) : null;
  if (Object.hasOwn(value, 'sampling') && !sampling) return null;
  return { module, window, generated_at: value.generated_at, start_at: value.start_at, end_at: value.end_at, interval_seconds: 300, samples: rows, sampling };
}

export function healthHistoryPlot(history) {
  const left = 44, right = 588, top = 12, bottom = 142;
  const start = Date.parse(history.start_at), end = Date.parse(history.end_at);
  const candidates = history.samples.filter((p) => p.freshness === 'fresh' && p.measurement.value !== null);
  const latest = candidates.at(-1)?.measurement;
  // Different units never share a numeric axis. Their sampled states remain visible.
  const matches = (p) => p.freshness === 'fresh' && p.measurement.value !== null && p.measurement.key === latest?.key && p.measurement.unit === latest?.unit;
  const measured = candidates.filter(matches);
  const ceiling = latest?.unit === 'percent' ? 100 : Math.max(1, ...measured.map((p) => p.measurement.value)) * 1.15;
  const x = (at) => left + (Date.parse(at) - start) / (end - start) * (right - left);
  const y = (value) => bottom - value / ceiling * (bottom - top);
  const segments = [], dots = [], bars = [];
  let segment = [], previous = null;
  for (const point of history.samples) {
    const m = point.measurement, valid = matches(point);
    bars.push({ x: x(point.sampled_at), width: Math.max(0.4, Math.min(12, 300000 / (end - start) * (right - left))), status: point.status });
    const joined = previous && valid && matches(previous)
      && Date.parse(point.sampled_at) - Date.parse(previous.sampled_at) <= 450000
      && point.source_sha === previous.source_sha && m.key === previous.measurement.key && m.unit === previous.measurement.unit
      && point.target_sha === previous.target_sha
      && m.threshold === previous.measurement.threshold;
    if (!joined && segment.length) { segments.push(segment); segment = []; }
    if (valid) { const dot = { x: x(point.sampled_at), y: y(m.value), status: point.status }; segment.push(dot); dots.push(dot); }
    previous = point;
  }
  if (segment.length) segments.push(segment);
  return { ceiling, segments: segments.filter((s) => s.length > 1).map((s) => s.map((p) => `${p.x},${p.y}`).join(' ')), dots, bars,
    metric: latest?.key || 'not_measured', unit: latest?.unit || 'none', lastSampleAt: history.samples.at(-1)?.sampled_at || null };
}
