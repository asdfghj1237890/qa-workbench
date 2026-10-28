// Authenticated snapshot contract: agent-service/app/qa.py read_snapshot and qa/snapshot.py build_snapshot.
// Refresh reads an existing artifact; the browser never starts indexing or projection work.
export function validQaSnapshot(value) {
  const integer = (n) => Number.isSafeInteger(n) && n >= 0;
  const distribution = (rows) => Array.isArray(rows) && rows.every((row) =>
    typeof row?.name === "string" && integer(row.count));
  const e = value?.embedding;
  const p = value?.projection;
  const dimensions = p?.dimensions === undefined ? 2 : p.dimensions;
  return value?.schema_version === 1 && ["ok", "stale"].includes(value.status)
    && typeof value.index === "string" && Number.isFinite(Date.parse(value.generated_at))
    && integer(value.total) && value.refresh_interval_hours === 24
    && typeof e?.model === "string" && integer(e.dimensions) && typeof e.field === "string"
    && integer(e.count) && integer(e.missing) && e.count + e.missing === value.total
    && Number.isFinite(e.coverage) && e.coverage >= 0 && e.coverage <= 1
    && distribution(value.distributions?.categories) && distribution(value.distributions?.sources)
    && p?.method === "umap" && p.metric === "cosine" && p.seed === 42
    && [2, 3].includes(dimensions)
    && integer(p.sample_size) && p.sample_size <= 20000 && integer(p.population) && typeof p.sampled === "boolean"
    && ["ok", "insufficient_data"].includes(p.status)
    && p.sample_size <= p.population && p.population === e.count
    && p.sampled === (p.sample_size < p.population)
    && Array.isArray(p.points)
    && (p.status === "ok" ? p.points.length === p.sample_size && p.sample_size >= 3 : p.points.length === 0 && p.sample_size < 3)
    && p.points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)
      && (dimensions === 3 ? Number.isFinite(point.z) : !("z" in point))
      && typeof point.category === "string" && typeof point.site === "string"
      && ["title", "url"].every((key) => point[key] === undefined || typeof point[key] === "string"));
}

// News links come only from the snapshot producer. Never derive one from an
// embedding index, and never let URL's permissive parser repair unsafe input.
export function qaArticleUrl(value) {
  if (typeof value !== "string") return null;
  const raw = value.trim();
  if (!/^https?:\/\/[^/]/i.test(raw) || /[\u0000-\u0020\u007f\\]/.test(raw)
    || /^https?:\/\/[^/?#]*@/i.test(raw)) return null;
  try {
    const url = new URL(raw);
    return ["https:", "http:"].includes(url.protocol) && url.hostname && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function projectedPoints(points) {
  if (!points.length) return [];
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.max((maxX - minX) / 928, (maxY - minY) / 428) || 1;
  return points.map((point) => ({
    ...point,
    cx: 500 + (point.x - (minX + maxX) / 2) / scale,
    cy: 250 - (point.y - (minY + maxY) / 2) / scale,
  }));
}

export { QA_EVIDENCE, QA_REPOSITORY } from './runtime.js';
