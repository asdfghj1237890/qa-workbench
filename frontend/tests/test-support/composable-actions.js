/** Business operations expose detached observations; drivers remain private. */
import { mountExecutionFlow, disposeExecutionFlows } from './composable-physical.js';

class ExecutionFlow {
  #driver;
  constructor(driver) { this.#driver = driver; }
  choosePaidTask() { return this.#driver.choosePaidTask(); }
  authorizeCost(amount) { return this.#driver.authorizeCost(amount); }
  startRun() { return this.#driver.startRun(); }
  cancelRun() { return this.#driver.cancelRun(); }
  advanceTime(milliseconds) { return this.#driver.advanceTime(milliseconds); }
  holdNextPoll() { return this.#driver.holdNextPoll(); }
  releasePoll() { return this.#driver.releasePoll(); }
  failNextPoll() { return this.#driver.failNextPoll(); }
  completeRun() { return this.#driver.completeRun(); }
  prepareReview() { return this.#driver.prepareReview(); }
  submitReview() { return this.#driver.submitReview(); }
  observation() { return structuredClone(this.#driver.observation()); }
  close() { return this.#driver.close(); }
}

export async function openExecutionFlow(kind) {
  return new ExecutionFlow(await mountExecutionFlow(kind));
}

export function closeExecutionFlows() { disposeExecutionFlows(); }
