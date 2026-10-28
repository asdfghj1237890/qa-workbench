/** Host boundary for the reusable workbench. No authentication SDK is imported. */
const palette = ['#168478', '#6678CE', '#C47733', '#B46087', '#688F38', '#3D92B5'];
const defaultCategories = {
  group: value => typeof value === 'string' && value ? value : '__other__',
  color: value => palette[[...String(value)].reduce((sum, char) => sum + char.charCodeAt(0), 0) % palette.length],
  labelKey: value => value === '__other__' ? 'other' : value,
  distribution: rows => {
    const counts = new Map();
    for (const row of rows) counts.set(row.name || '__other__', (counts.get(row.name || '__other__') || 0) + row.count);
    return [...counts].map(([name, count]) => ({ name, count }));
  },
};
let adapter = {
  id: 'workbench', name: 'QA Workbench', apiBase: '/api', repository: '',
  fetch: (...args) => fetch(...args), categories: defaultCategories,
  branding: { name: 'QA Workbench', mark: '', home: '/' },
  tasks: [], evidence: [], designPreview: false, challengeSitekey: '',
  challenge: { get widget() { return null; }, async load() { throw new Error('challenge_provider_required'); } },
  session() { throw new Error('Host authentication adapter required'); },
};
export let AGENT = adapter.apiBase;
export let TS_SITEKEY = '';
export let QA_DESIGN_PREVIEW = false;
export let QA_REPOSITORY = '';
export let QA_EVIDENCE = [];
export let WORKBENCH_TASKS = [];

export function configureQaAdapter(value) {
  if (!value || typeof value.id !== 'string' || !value.id || typeof value.apiBase !== 'string' || typeof value.fetch !== 'function') throw new TypeError('Invalid QA frontend adapter');
  adapter = { ...adapter, ...value, categories: { ...defaultCategories, ...value.categories }, branding: { ...adapter.branding, ...value.branding } };
  AGENT = adapter.apiBase;
  TS_SITEKEY = adapter.challengeSitekey || '';
  QA_DESIGN_PREVIEW = adapter.designPreview === true;
  QA_REPOSITORY = adapter.repository || '';
  QA_EVIDENCE = adapter.evidence || [];
  WORKBENCH_TASKS = Object.freeze([...(adapter.tasks || [])]);
  return adapter;
}
export const getQaAdapter = () => adapter;
export const qaDownloadPrefix = () => adapter.id;

/** A challenge provider owns script loading and widget behavior. */
export const qaChallenge = {
  get widget() { return adapter.challenge?.widget; },
  load: signal => adapter.challenge.load(signal),
};
