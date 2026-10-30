/** Own browser object URLs and their cleanup separately from execution state. */
import { onScopeDispose, toRaw } from 'vue';
import { browserArtifacts } from '../lib/browserArtifacts.js';

export function useArtifactFiles(io = browserArtifacts) {
  const retained = new Set(), timers = new Set();
  function revoke(artifact) {
    artifact = toRaw(artifact);
    if (!retained.delete(artifact)) return;
    io.revoke(artifact);
  }
  function keep(artifact, temporary) {
    retained.add(artifact);
    if (temporary) {
      const timer = setTimeout(() => { timers.delete(timer); revoke(artifact); }, 1000);
      timers.add(timer);
    }
    return artifact;
  }
  onScopeDispose(() => {
    timers.forEach(clearTimeout); timers.clear();
    [...retained].forEach(revoke);
  });
  return {
    readJson: (file, options) => io.readJson(file, options),
    takeFile: event => io.takeFile(event),
    clearInput: event => io.clearInput(event),
    saveBlob: (blob, name) => keep(io.saveBlob(blob, name), false),
    saveJson: (value, name) => keep(io.saveJson(value, name), true),
    revoke,
  };
}
