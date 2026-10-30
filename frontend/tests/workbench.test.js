// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { workbenchScenario } from './test-support/actions.js';
const opened = [];
async function open() { const scenario = await workbenchScenario(); opened.push(scenario); return scenario; }
afterEach(() => { opened.splice(0).forEach(scenario => scenario.close()); document.body.innerHTML = ''; });
describe('portable project workbench', () => {
  it('accepts a different domain and selection only opens configuration', async () => {
    const scenario = await open();
    await scenario.chooseTask('warehouse-inventory');
    expect(scenario.observation().text).toContain('Inventory reconciliation');
    expect(scenario.observation().calls).toEqual([]);
    await scenario.startRun();
    expect(scenario.observation().calls[0].task).toBe('warehouse-inventory');
    expect(scenario.observation().text).toContain('pending_review');
    expect(scenario.observation().text).toContain('not_passed');
    expect(scenario.observation().text).toContain('human_review_not_performed');
  });
  it('requires fresh paid consent and retains an explicit budget in the request', async () => {
    const scenario = await open();
    await scenario.chooseTask('support-quality');
    expect(scenario.observation().startDisabled).toBe(true);
    await scenario.authorizeCost(0.25);
    await scenario.startRun();
    expect(scenario.observation().calls[0].form).toMatchObject({ acknowledgeCost: true, maxUsd: 0.25 });
    expect(scenario.observation().startDisabled).toBe(true);
  });
  it('does not execute malformed settings', async () => {
    const scenario = await open();
    await scenario.configureOptions('not json');
    await scenario.startRun();
    expect(scenario.observation().calls).toEqual([]);
  });
  it('keeps paid execution disabled when the budget input is cleared', async () => {
    const scenario = await open();
    await scenario.chooseTask('support-quality');
    await scenario.authorizeCost('');
    expect(scenario.observation().startDisabled).toBe(true);
    await scenario.startRun();
    expect(scenario.observation().calls).toEqual([]);
  });
});
