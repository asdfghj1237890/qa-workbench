import { getQaAdapter } from './runtime.js';
export const apiFetch = (url, options) => getQaAdapter().fetch(url, options);
export const getQaSession = () => getQaAdapter().session();
