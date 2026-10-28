// Frozen visual observations for the health-page design, never live telemetry.
// No HTTP clients, timers, verdict calculation or provider calls belong here.
export const HEALTH_PREVIEW = Object.freeze({
  observedAt: '2026-10-26T14:32:10+08:00',
  environment: 'QA',
  version: 'design-preview',
  modules: [
    { id: 'indexer', name: 'Indexer', status: 'warning', score: null, value: 38, threshold: 20, pending: 126, unit: 'minutes', observedAt: '14:32:10', lastSuccess: '13:54', source: 'pipeline', events: ['13:54', '14:15', '14:32'], samples: [['13:30', 6], ['13:33', 6], ['13:40', 9], ['13:48', 12], ['13:55', 15], ['14:00', 16], ['14:07', 22], ['14:15', 26], ['14:22', 30], ['14:30', 38]] },
    { id: 'collector', name: 'collector', status: 'stale', score: null, value: 6, threshold: 2, pending: null, unit: 'minutes', observedAt: '14:26:10', lastSuccess: '14:26', source: 'heartbeat', events: ['14:26', '14:28', '14:32'], samples: [] },
    { id: 'frontend', name: 'Frontend', status: 'healthy', score: null, value: 186, threshold: 500, pending: null, unit: 'milliseconds', observedAt: '14:32:10', lastSuccess: '14:32', source: 'synthetic', events: ['14:32'], samples: [] },
    { id: 'agent', name: 'Agent API', status: 'healthy', score: null, value: 99.4, threshold: 99, pending: null, unit: 'percent', observedAt: '14:32:10', lastSuccess: '14:32', source: 'requests', events: ['14:32'], samples: [] },
    { id: 'es', name: 'Elasticsearch', status: 'healthy', score: null, value: 42, threshold: 200, pending: null, unit: 'milliseconds', observedAt: '14:32:03', lastSuccess: '14:32', source: 'search', events: ['14:32'], samples: [] },
    { id: 'crawler', name: 'Crawler', status: 'healthy', score: null, value: 8, threshold: 30, pending: null, unit: 'minutes', observedAt: '14:32:10', lastSuccess: '14:24', source: 'pipeline', events: ['14:24'], samples: [] },
    { id: 'llm', name: 'LLM API', status: 'healthy', score: null, value: 0, threshold: 2, pending: null, unit: 'errors', observedAt: '14:32:10', lastSuccess: '14:32', source: 'requests', events: ['14:32'], samples: [] },
  ],
});
