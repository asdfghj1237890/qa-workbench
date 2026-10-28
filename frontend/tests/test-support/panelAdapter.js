/** Synthetic adapter for the extracted legacy panel protocol; no host imports. */
import { configureQaAdapter } from '../../src/lib/runtime.js';
const groups = [
  { name: '政治', key: 'politics', color: '#6678CE' }, { name: '國際', key: 'world', color: '#3D92B5' },
  { name: '兩岸', key: 'crossStrait', color: '#C29822' }, { name: '社會', key: 'society', color: '#C47733' },
  { name: '財經', key: 'business', color: '#688F38' }, { name: '科技', key: 'technology', color: '#168478' },
  { name: '娛樂', key: 'entertainment', color: '#B46087' }, { name: '體育', key: 'sports', color: '#AF6653' },
  { name: '生活', key: 'lifestyle', color: '#9272B9' },
];
configureQaAdapter({
  id: 'newscout', apiBase: '/qa/api', fetch: (...args) => fetch(...args), repository: 'https://example.test/project',
  evidence: ['ingestion', 'rag', 'agents'].map(id => ({ id, mode: 'offline_regression', links: [{ path: 'docs/testing-framework.md', label: 'Framework contract' }] })),
  tasks: [
    { id: 'offline_regression', icon: 'description', paid: false },
    { id: 'es_integration', icon: 'database', paid: false },
    { id: 'real_es_llm_e2e', icon: 'database', paid: true },
    { id: 'model_evaluation', icon: 'bar_chart', paid: true },
    { id: 'real_corpus_quality', icon: 'manage_search', paid: true },
  ],
  categories: {
    group: value => groups.some(group => group.name === value) ? value : '__other__',
    color: value => groups.find(group => group.name === value)?.color || '#7F8C99',
    labelKey: value => groups.find(group => group.name === value)?.key || 'other',
  },
  challenge: {
    get widget() { return window.turnstile; },
    async load() { if (!window.turnstile) throw new Error('turnstile'); },
  },
});
