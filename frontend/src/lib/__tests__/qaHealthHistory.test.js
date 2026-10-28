import "../../../tests/test-support/panelAdapter.js";
import { describe, expect, it } from 'vitest';
import example from '../../../e2e/fixtures/health-history-v1.json';
import { healthHistoryPlot, parseHealthHistory } from '../qaHealthHistory.js';

const options = { module: 'indexer', window: '24h', now: Date.parse(example.generated_at) };
const packet = () => structuredClone(example);

describe('bounded historical observations', () => {
  it('keeps model success-rate plots bounded to the full zero-to-100 percent scale', () => {
    const value = packet(); value.module = 'llm';
    for (const point of value.samples) point.measurement = { key: 'llm_success_rate', value: 100, unit: 'percent', threshold: null };
    const chart = healthHistoryPlot(parseHealthHistory(value, { ...options, module: 'llm' }));
    expect(chart.ceiling).toBe(100); expect(chart.dots.every((p) => p.y === 12)).toBe(true);
  });
  it('keeps only public measurements and explicit source identity', () => {
    const value = packet(); value.private = 'hidden'; value.samples[0].private = 'hidden';
    const result = parseHealthHistory(value, options);
    expect(result.samples).toHaveLength(5);
    expect(JSON.stringify(result)).not.toContain('hidden');
    expect(result.samples.at(-1).source_sha).toBe('b'.repeat(40));
  });
  it.each([
    (p) => { p.module = 'es'; }, (p) => { p.score = 95; }, (p) => { p.quality_review = 'pass'; },
    (p) => { p.interval_seconds = 60; }, (p) => { p.samples[0].measurement.value = -1; },
    (p) => { p.samples[0].measurement.value = Infinity; }, (p) => { p.samples[0].source_sha = null; },
    (p) => { p.samples[1].sampled_at = p.samples[0].sampled_at; },
    (p) => { p.samples[0].observed_at = '2099-01-01T00:00:00Z'; },
    (p) => { p.samples[0].freshness = 'unmeasured'; },
    (p) => { p.samples[0].measurement.unit = 'minutes'; },
    (p) => { p.start_at = p.end_at; },
    (p) => { p.generated_at = p.end_at = new Date(options.now + 60000).toISOString(); p.start_at = new Date(options.now + 60000 - 86400000).toISOString(); },
  ])('rejects malformed, mis-scoped or fabricated evidence (%#)', (damage) => {
    const value = packet(); damage(value); expect(parseHealthHistory(value, options)).toBeNull();
  });
  it('leaves gaps across missed intervals, expired sources and release changes', () => {
    const chart = healthHistoryPlot(parseHealthHistory(packet(), options));
    expect(chart.dots).toHaveLength(4);
    expect(chart.segments).toHaveLength(1);
    expect(chart.segments[0].split(' ')).toHaveLength(2);
    expect(chart.bars.map((p) => p.status)).toEqual(['healthy', 'healthy', 'healthy', 'stale', 'healthy']);
    expect(chart.dots.every((p) => p.x >= 44 && p.x <= 588 && p.y >= 12 && p.y <= 142)).toBe(true);
  });
  it('renders a single measurement as a point without inventing a line', () => {
    const value = packet(); value.samples = value.samples.slice(0, 1);
    const chart = healthHistoryPlot(parseHealthHistory(value, options));
    expect(chart.dots).toHaveLength(1); expect(chart.segments).toEqual([]);
  });
  it('never bridges a changed threshold even when observations are adjacent', () => {
    const value = packet(); value.samples = value.samples.slice(0, 2); value.samples[1].measurement.threshold = 7200;
    expect(healthHistoryPlot(parseHealthHistory(value, options)).segments).toEqual([]);
  });
  it('keeps an empty range empty and unmeasured', () => {
    const value = packet(); value.samples = [];
    const chart = healthHistoryPlot(parseHealthHistory(value, options));
    expect(chart.dots).toEqual([]); expect(chart.bars).toEqual([]); expect(chart.lastSampleAt).toBeNull();
  });
  it('keeps older units in status evidence without combining them on a numeric axis', () => {
    const value = packet(); value.samples.at(-1).measurement = { key: 'read_probe_duration', value: 20, unit: 'milliseconds', threshold: 2000 };
    const chart = healthHistoryPlot(parseHealthHistory(value, options));
    expect(chart.unit).toBe('milliseconds'); expect(chart.dots).toHaveLength(1);
    expect(chart.segments).toEqual([]); expect(chart.bars).toHaveLength(5);
  });
  it('does not connect frontend releases when the sampler stays on the same revision', () => {
    const value = packet(); value.module = 'frontend'; value.samples = value.samples.slice(0, 2);
    for (const point of value.samples) { point.target_sha = 'f'.repeat(40); point.measurement = { key: 'frontend_response_duration', value: 120, unit: 'milliseconds', threshold: 1000 }; }
    const config = { ...options, module: 'frontend' };
    expect(healthHistoryPlot(parseHealthHistory(value, config)).segments).toHaveLength(1);
    value.samples[1].target_sha = 'e'.repeat(40);
    expect(healthHistoryPlot(parseHealthHistory(value, config)).segments).toEqual([]);
    value.samples[1].target_sha = 'unknown';
    expect(parseHealthHistory(value, config)).toBeNull();
  });
});
