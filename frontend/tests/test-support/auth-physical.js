/** Contract: StandaloneShell keeps bearer identity in memory and aborts old work. */
import { mount, flushPromises } from '@vue/test-utils';
import StandaloneShell from '../../src/StandaloneShell.vue';
import { combineAbortSignals } from '../../src/lib/abortSignals.js';
function withoutNativeSignalAny() {
  const owner = globalThis.AbortSignal, original = Object.getOwnPropertyDescriptor(owner, 'any');
  Object.defineProperty(owner, 'any', { configurable: true, value: undefined });
  return () => { if (original) Object.defineProperty(owner, 'any', original); else delete owner.any; };
}
export function fallbackCancellationObservations() {
  const restore = withoutNativeSignalAny();
  try {
    return ['request', 'identity'].map(source => {
      const request = new AbortController(), identity = new AbortController();
      const combined = combineAbortSignals([request.signal, identity.signal]);
      (source === 'request' ? request : identity).abort();
      const aborted = combined.signal.aborted; combined.cleanup();
      return { source, aborted };
    });
  } finally { restore(); }
}
export async function authenticatedWorkbench({ provider = false, pending = false, fallback = false } = {}) {
  const restore = fallback ? withoutNativeSignalAny() : () => {};
  const fixtureToken = 'offline-authorized-identity', calls = [];
  let aborted = 0;
  const request = async (url, options = {}) => {
    const authorized = options.headers.Authorization === 'Bearer ' + fixtureToken;
    calls.push({ url, method: options.method || 'GET', authorized });
    if (!authorized) return { status: 401, ok: false, json: async () => ({ detail: 'Backend credential details must not be displayed' }) };
    if (pending && url.endsWith('/runs')) return new Promise((_resolve, reject) => { options.signal.addEventListener('abort', () => { aborted++; reject(new DOMException('Cancelled', 'AbortError')); }, { once: true }); });
    return { status: 200, ok: true, json: async () => url.endsWith('/capabilities') ? { project: { id: 'protected-project', name: 'Protected project' }, tasks: [{ id: 'private-check', title: 'Private checks', paid: false }] } : { runs: [] } };
  };
  const wrapper = mount(StandaloneShell, { props: { request, config: provider ? { tokenProvider: async () => fixtureToken } : {} }, attachTo: document.body });
  await flushPromises();
  return {
    async signIn(valid = true) { await wrapper.get('[data-testid="auth-token"]').setValue(valid ? fixtureToken : 'rejected-fixture'); await wrapper.get('form').trigger('submit'); await flushPromises(); },
    async choose() { await wrapper.get('[data-testid="task-private-check"]').trigger('click'); await flushPromises(); },
    async logout() { await wrapper.get('[data-testid="auth-signout"]').trigger('click'); await flushPromises(); },
    observation: () => ({ calls: structuredClone(calls), text: wrapper.text(), applications: wrapper.findAll('.wb-app').length, credential: wrapper.find('[data-testid="auth-token"]').exists() ? wrapper.get('[data-testid="auth-token"]').element.value : null, tokenInStorage: [localStorage, sessionStorage].some(storage => JSON.stringify({ ...storage }).includes(fixtureToken)), aborted }),
    close: () => { wrapper.unmount(); restore(); },
  };
}
