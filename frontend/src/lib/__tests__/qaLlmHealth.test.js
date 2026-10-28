import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from 'vitest';
import fixtures from '../../../e2e/observatory-health-physical.cjs';
import { parseHealthSnapshot } from '../qaHealth.js';

// Contract: the shared synthetic public API physical fixture and the actual
// health allowlist; no provider transport exists in these frontend scenarios.
function packet() { return fixtures.healthBody('llm-failed'); }

describe('passive LLM evidence allowlist', () => {
  it('preserves the classified denominator while excluding private fields', () => {
    const value = packet(); value.modules[5].details.private = 'PRIVATE-SENTINEL';
    const row = parseHealthSnapshot(value).modules[5];
    expect(row.measurement.value).toBe(33.33); expect(row.details.completed_count).toBe(3);
    expect(row.details.cancelled_count).toBe(1); expect(JSON.stringify(row)).not.toContain('PRIVATE-SENTINEL');
  });
  it.each([
    (row) => { row.measurement.value = 100; },
    (row) => { row.details.completed_count = 4; },
    (row) => { row.details.request_count = 3; },
    (row) => { row.details.timeout_count = -1; },
    (row) => { row.details.last_success_at = '2099-01-01T00:00:00Z'; },
    (row) => { row.status = 'healthy'; },
    (row) => { row.details.window_limited = 'false'; },
    (row) => { row.measurement.threshold = 95; },
    (row) => { row.id = 'es'; },
  ])('rejects unsupported or contradictory model evidence (%#)', (damage) => {
    const value = packet(); damage(value.modules[5]); expect(parseHealthSnapshot(value)).toBeNull();
  });
});
