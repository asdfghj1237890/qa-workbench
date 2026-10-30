/** Browser operations keep the driver private and expose detached observations. */
import { openArtifactDriver, closeArtifactDrivers } from './artifact-physical.js';
class ArtifactFiles {
  #driver;
  constructor(driver) { this.#driver = driver; }
  saveReport() { this.#driver.saveReport(); }
  saveAttachment() { this.#driver.saveAttachment(); }
  revokeAttachment() { this.#driver.revokeAttachment(); }
  async readEvidence(scenario) { return structuredClone(await this.#driver.readEvidence(scenario)); }
  takeEvidence() { return structuredClone(this.#driver.takeEvidence()); }
  advanceTime(milliseconds) { return this.#driver.advanceTime(milliseconds); }
  dispose() { this.#driver.dispose(); }
  observation() { return structuredClone(this.#driver.observation()); }
}
export function openArtifactFiles(injected = false) { return new ArtifactFiles(openArtifactDriver(injected)); }
export function closeArtifactFiles() { closeArtifactDrivers(); }
