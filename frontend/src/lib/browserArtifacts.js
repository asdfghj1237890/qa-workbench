/** Browser-only file and download adapter. Execution modules do not import it. */
export const browserArtifacts = {
  async readJson(file, { maxBytes, errorCode, requireSize = true } = {}) {
    if (!file || (requireSize && !Number.isFinite(file.size)) || file.size > maxBytes) {
      throw new Error(errorCode || 'Import exceeds 8 MiB');
    }
    try { return JSON.parse(await file.text()); }
    catch (failure) { if (errorCode) throw new Error(errorCode); throw failure; }
  },
  takeFile(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    return file;
  },
  clearInput(event) { event.target.value = ''; },
  saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = filename;
    document.body.append(link);
    try { link.click(); }
    catch (failure) { URL.revokeObjectURL(url); throw failure; }
    finally { link.remove(); }
    return { url, filename };
  },
  saveJson(value, filename) {
    return this.saveBlob(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }), filename);
  },
  revoke(artifact) { if (artifact) URL.revokeObjectURL(artifact.url); },
};
