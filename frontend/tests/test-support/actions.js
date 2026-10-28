import { openWorkbench } from './physical.js';
import { authenticatedWorkbench, fallbackCancellationObservations } from './auth-physical.js';
export const authenticatedScenario = options => authenticatedWorkbench(options);
export const observeFallbackCancellation = () => fallbackCancellationObservations();
export async function workbenchScenario() {
  const driver = await openWorkbench();
  return {
    chooseTask: id => driver.select(id),
    authorizeCost: amount => driver.consent(amount),
    configureOptions: value => driver.options(value),
    startRun: () => driver.start(),
    observation: () => ({ text: driver.text(), calls: driver.calls(), startDisabled: driver.disabled() }),
    close: () => driver.close(),
  };
}
