// Present supplied observation states only. No probing, freshness inference from
// old measurements, production scoring or provider calls belong in this module.
const measuredStates = new Set(['healthy', 'warning', 'critical']);
const isObserved = (item) => !!item && measuredStates.has(item.status) && item.fresh !== false;
const groups = [
  { id: 'service', members: ['frontend', 'agent', 'es', 'llm'] },
  { id: 'data', members: ['crawler', 'indexer'] },
];

export function buildHealthOverview(modules) {
  // Required inventory still contributes to coverage when an observation is
  // missing. Otherwise dropping one service could falsely improve coverage.
  const inventory = new Set([...groups.flatMap((group) => group.members), 'collector', ...modules.map((item) => item.id)]);
  const observationsById = [...inventory].map((id) => modules.find((item) => item.id === id) || { id, name: id, status: 'unknown', observedAt: null });
  const counts = { healthy: 0, warning: 0, critical: 0, unknown: 0 };
  for (const item of observationsById) counts[measuredStates.has(item.status) ? item.status : 'unknown']++;
  const observed = observationsById.filter(isObserved).length;
  return {
    counts, observed, total: inventory.size,
    coverage: modules.length ? observed / inventory.size : null,
    unknowns: observationsById.filter((item) => !isObserved(item)),
    groups: groups.map(({ id, members }) => {
      const observations = members.map((member) => modules.find((item) => item.id === member));
      const valid = observations.filter(isObserved);
      const warning = valid.filter((item) => item.status === 'warning').length;
      const critical = observations.some((item) => item?.status === 'critical');
      const dated = observations.filter((item) => item?.observedAt).sort((a, b) => a.observedAtEpoch != null && b.observedAtEpoch != null ? a.observedAtEpoch - b.observedAtEpoch : a.observedAt.localeCompare(b.observedAt));
      return {
        id, total: members.length, observed: valid.length, warning,
        tone: critical ? 'critical' : warning ? 'warning' : valid.length === members.length ? 'healthy' : 'stale',
        observedAt: dated[0]?.observedAt || null,
      };
    }),
  };
}
