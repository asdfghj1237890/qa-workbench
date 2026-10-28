// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { authenticatedScenario, observeFallbackCancellation } from './test-support/actions.js';
const opened = [];
async function open(options) { const scenario = await authenticatedScenario(options); opened.push(scenario); return scenario; }
afterEach(() => { opened.splice(0).forEach(scenario => scenario.close()); document.body.innerHTML = ''; localStorage.clear(); sessionStorage.clear(); });
describe('standalone bearer identity lifecycle', () => {
  it('retries authenticated reads after sign-in and never runs on login or selection', async () => {
    const scenario = await open();
    expect(scenario.observation().applications).toBe(0);
    await scenario.signIn(false);
    expect(scenario.observation().text).toContain('Credentials were rejected');
    expect(scenario.observation().text).not.toContain('Backend credential details');
    expect(scenario.observation().credential).toBe('');
    await scenario.signIn(); await scenario.choose();
    expect(scenario.observation().applications).toBe(1);
    expect(scenario.observation().calls.filter(call => call.authorized)).toHaveLength(2);
    expect(scenario.observation().calls.every(call => call.method === 'GET')).toBe(true);
    expect(scenario.observation().tokenInStorage).toBe(false);
    await scenario.logout();
    expect(scenario.observation().applications).toBe(0);
    expect(scenario.observation().credential).toBe('');
    expect(scenario.observation().text).not.toContain('Private checks');
  });
  it('revokes pending transport and discards private run UI when signing out', async () => {
    const scenario = await open({ pending: true });
    await scenario.signIn();
    await scenario.logout();
    expect(scenario.observation().aborted).toBe(1);
    expect(scenario.observation().applications).toBe(0);
  });
  it('supports an injected identity provider without asking for a manual credential', async () => {
    const scenario = await open({ provider: true });
    expect(scenario.observation().applications).toBe(1);
    expect(scenario.observation().calls.every(call => call.authorized && call.method === 'GET')).toBe(true);
    expect(scenario.observation().tokenInStorage).toBe(false);
  });
  it('physically propagates either cancellation source without AbortSignal.any', async () => {
    expect(observeFallbackCancellation()).toEqual([{ source: 'request', aborted: true }, { source: 'identity', aborted: true }]);
    const scenario = await open({ pending: true, fallback: true });
    await scenario.signIn(); await scenario.logout();
    expect(scenario.observation().aborted).toBe(1);
    expect(scenario.observation().applications).toBe(0);
  });
});
