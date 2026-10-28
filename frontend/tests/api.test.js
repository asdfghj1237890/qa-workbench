import { describe, expect, it } from 'vitest';
import { startPayload, runEvidence } from '../src/lib/workbenchApi.js';
describe('adapter-independent evidence and execution contract', () => {
  it('rejects paid dispatch without explicit limits and never attaches paid options to a free task', () => {
    expect(() => startPayload({ id: 'task', paid: true }, { maxUsd: 2 })).toThrow('explicit consent');
    expect(() => startPayload({ id: 'task', paid: true }, { maxUsd: Infinity, acknowledgeCost: true })).toThrow();
    expect(startPayload({ id: 'task', paid: false }, { options: { warehouse: 'north' }, acknowledgeCost: true, maxUsd: 2 })).toEqual({ task_id: 'task', options: { warehouse: 'north' } });
  });
  it('retains structural success, pending quality and historical revision separately', () => {
    expect(runEvidence({ structural_status: 'passed', semantic_status: 'pending_review', quality_passed: false, source_sha: 'old' }, 'new')).toEqual({ structural: 'passed', semantic: 'pending_review', quality: 'not_passed', revision: 'historical' });
    expect(runEvidence(null, null).revision).toBe('unknown');
  });
});
