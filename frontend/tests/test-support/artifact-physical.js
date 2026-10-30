/** Contract: browserArtifacts file parsing and useArtifactFiles URL ownership. */
import { effectScope } from 'vue';
import { vi } from 'vitest';
import { useArtifactFiles } from '../../src/composables/useArtifactFiles.js';

const opened = [];
export function openArtifactDriver(injected = false) {
  const saved = [], revoked = [], clicks = [], reads = [];
  let sequence = 0, files;
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  const create = vi.fn(blob => { const url = 'blob:fixture-' + ++sequence; saved.push({ url, type: blob.type }); return url; });
  const revoke = vi.fn(url => revoked.push(url));
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL');
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL');
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: create });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revoke });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { clicks.push(this.download); });
  const io = {
    saveBlob(_blob, filename) { const url = 'port:fixture-' + ++sequence; saved.push({ url, filename }); return { url, filename }; },
    saveJson(value, filename) { reads.push(value); return this.saveBlob(null, filename); },
    revoke(artifact) { revoked.push(artifact.url); },
  };
  const scope = effectScope();
  scope.run(() => { files = useArtifactFiles(injected ? io : undefined); });
  const artifacts = [];
  const driver = {
    saveReport() { artifacts.push(files.saveJson({ text: '繁體中文' }, 'report.json')); },
    saveAttachment() { artifacts.push(files.saveBlob(new Blob(['fixture'], { type: 'application/json' }), 'evidence.json')); },
    revokeAttachment() { files.revoke(artifacts.at(-1)); },
    async readEvidence(scenario) {
      const source = scenario === 'malformed' ? '{' : '{"text":"繁體中文"}';
      let read = false;
      const file = { size: scenario === 'oversize' ? 100 : source.length, async text() { read = true; return source; } };
      try { const value = await files.readJson(file, { maxBytes: 64, errorCode: 'file' }); return { value, read, error: null }; }
      catch (failure) { return { value: null, read, error: failure.message }; }
    },
    takeEvidence() {
      const event = { target: { files: [{ name: 'report.json' }], value: 'report.json' } };
      const file = files.takeFile(event);
      return { name: file.name, input: event.target.value };
    },
    async advanceTime(milliseconds) { await vi.advanceTimersByTimeAsync(milliseconds); },
    dispose() { scope.stop(); },
    observation() { return { saved: structuredClone(saved), revoked: [...revoked], clicks: [...clicks], reads: structuredClone(reads), timers: vi.getTimerCount(), anchors: document.querySelectorAll('a').length }; },
    cleanup() {
      scope.stop(); click.mockRestore();
      if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate); else delete URL.createObjectURL;
      if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke); else delete URL.revokeObjectURL;
      vi.useRealTimers();
    },
  };
  opened.push(driver);
  return driver;
}
export function closeArtifactDrivers() { opened.splice(0).reverse().forEach(driver => driver.cleanup()); }
