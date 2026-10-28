import { createApp } from 'vue';
import StandaloneShell from './StandaloneShell.vue';
import { configureQaAdapter } from './lib/runtime.js';
import './css/standalone.css';

// Hosts may inject an SSO request/token provider. Manual bearer credentials are
// held only by StandaloneShell and are never persisted or exported.
const config = window.QA_WORKBENCH_CONFIG || {};
const request = config.request || ((...args) => fetch(...args));
configureQaAdapter({ id: config.projectId || 'workbench', apiBase: config.apiBase || '/api', fetch: request, branding: { name: config.name || 'QA Workbench' } });
createApp(StandaloneShell, { config }).mount('#app');
