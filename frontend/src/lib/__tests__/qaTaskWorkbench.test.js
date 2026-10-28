import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from 'vitest';
import { workbenchTaskEntry } from '../qaTaskWorkbench.js';
const SHA = 'a'.repeat(40);
const evidence = (overrides = {}) => ({ sourceSha: SHA, history: [{ mode: 'offline_regression', status: 'PASS', sourceSha: SHA, counts: { passed: 218 }, job: { source_sha: SHA, suite: 'all' }, ...overrides }] });
describe('workbench evidence presentation', () => {
  it('retains measured partial coverage without certifying a full regression', () => {
    const entry = workbenchTaskEntry(evidence({ job: { source_sha: SHA, suite: 'rag' } }), 'offline_regression');
    expect(entry.status).toBe('PARTIAL'); expect(entry.counts.passed).toBe(218);
  });
  it('never applies a passing old or unknown revision to the deployed revision', () => {
    for (const sourceSha of [null, 'b'.repeat(40)]) {
      expect(workbenchTaskEntry(evidence({ sourceSha, job: { source_sha: sourceSha } }), 'offline_regression').status).toBe('STALE');
    }
  });
  it('distinguishes measured model contracts from semantic quality', () => {
    expect(workbenchTaskEntry(evidence({ mode: 'model_evaluation' }), 'model_evaluation').status).toBe('STRUCTURAL');
  });
  it('prefers a running observation and retains absent counts as unknown', () => {
    const model = evidence(); model.history.push({ mode: 'offline_regression', status: 'RUNNING', job: { id: 'active' } });
    expect(workbenchTaskEntry(model, 'offline_regression').job.id).toBe('active');
    expect(workbenchTaskEntry(model, 'es_integration').counts).toBe(null);
  });
});
