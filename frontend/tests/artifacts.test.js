// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { openArtifactFiles, closeArtifactFiles } from './test-support/artifact-actions.js';
afterEach(closeArtifactFiles);

describe('artifact files outside execution cores', () => {
  it('keeps manual downloads until replacement and revokes each URL once on disposal', () => {
    const files = openArtifactFiles();
    files.saveReport();
    files.saveAttachment();
    expect(files.observation()).toMatchObject({ clicks: ['report.json', 'evidence.json'], anchors: 0, revoked: [], timers: 1 });
    files.revokeAttachment();
    files.revokeAttachment();
    expect(files.observation().revoked).toEqual(['blob:fixture-2']);
    files.dispose();
    expect(files.observation().revoked).toEqual(['blob:fixture-2', 'blob:fixture-1']);
    expect(files.observation().timers).toBe(0);
  });
  it('expires automatic JSON download URLs through an independently injected file port', async () => {
    const files = openArtifactFiles(true);
    files.saveReport();
    files.saveAttachment();
    await files.advanceTime(1000);
    expect(files.observation()).toMatchObject({ reads: [{ text: '繁體中文' }], revoked: ['port:fixture-1'], timers: 0 });
    files.dispose();
    expect(files.observation().revoked).toEqual(['port:fixture-1', 'port:fixture-2']);
  });
  it('parses selected evidence and clears the browser input separately from import submission', async () => {
    const files = openArtifactFiles();
    expect(await files.readEvidence('valid')).toEqual({ value: { text: '繁體中文' }, read: true, error: null });
    expect(files.takeEvidence()).toEqual({ name: 'report.json', input: '' });
  });
  it.each([['oversize', false], ['malformed', true]])('rejects %s evidence before any execution API is involved', async (scenario, read) => {
    const files = openArtifactFiles();
    expect(await files.readEvidence(scenario)).toEqual({ value: null, read, error: 'file' });
  });
});
