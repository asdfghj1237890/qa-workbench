// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { openExecutionFlow, closeExecutionFlows } from './test-support/composable-actions.js';

afterEach(closeExecutionFlows);

describe('independent execution composables', () => {
  it.each(['workbench', 'validation', 'live'])('opening and configuring %s cannot start paid work', async kind => {
    const flow = await openExecutionFlow(kind);
    await flow.choosePaidTask();
    await flow.startRun();
    expect(flow.observation().mutations).toEqual([]);
    await flow.authorizeCost(0.25);
    await flow.startRun();
    const result = flow.observation();
    expect(result.mutations).toHaveLength(1);
    expect(result.mutations[0].body).toMatchObject({ acknowledge_cost: true, max_usd: 0.25 });
    expect(result.acknowledged).toBe(false);
    expect(result.job.status).toBe('queued');
  });

  it.each(['workbench', 'validation', 'live'])('%s polls the selected run and keeps cancellation on its original API', async kind => {
    const flow = await openExecutionFlow(kind);
    await flow.choosePaidTask();
    await flow.authorizeCost(0.25);
    await flow.startRun();
    await flow.advanceTime(2000);
    expect(flow.observation().detailReads).toBeGreaterThan(0);
    await flow.cancelRun();
    const result = flow.observation();
    expect(result.job.status).toBe('cancelled');
    expect(result.mutations.at(-1)).toMatchObject({ method: 'POST', path: result.cancelPath });
    await flow.advanceTime(4000);
    expect(flow.observation().job.status).toBe('cancelled');
    expect(flow.observation().mutations).toHaveLength(2);
  });

  it.each(['validation', 'live'])('%s ignores a pending poll received after cancellation', async kind => {
    const flow = await openExecutionFlow(kind);
    await flow.choosePaidTask();
    await flow.authorizeCost(0.25);
    await flow.startRun();
    await flow.holdNextPoll();
    await flow.advanceTime(1000);
    expect(flow.observation().pendingReads).toBe(1);
    await flow.cancelRun();
    await flow.releasePoll();
    expect(flow.observation().job.status).toBe('cancelled');
    expect(flow.observation().events.filter(event => event.name === 'observation-change').at(-1).value.job.status).toBe('cancelled');
  });

  it.each(['workbench', 'validation', 'live'])('%s aborts an outstanding read and stops polling on disposal', async kind => {
    const flow = await openExecutionFlow(kind);
    await flow.choosePaidTask();
    await flow.authorizeCost(0.25);
    await flow.startRun();
    await flow.holdNextPoll();
    await flow.advanceTime(2000);
    expect(flow.observation().pendingReads).toBe(1);
    const previous = flow.observation().calls.length;
    await flow.close();
    await flow.advanceTime(30000);
    expect(flow.observation().heldReadAborted).toBe(true);
    expect(flow.observation().calls).toHaveLength(previous);
  });

  it.each(['workbench', 'validation', 'live'])('%s requires new cost consent after a completed run', async kind => {
    const flow = await openExecutionFlow(kind);
    await flow.choosePaidTask();
    await flow.authorizeCost(0.25);
    await flow.startRun();
    await flow.completeRun();
    await flow.advanceTime(2000);
    expect(flow.observation().job.status).toBe('completed');
    await flow.startRun();
    expect(flow.observation().mutations).toHaveLength(1);
  });

  it.each(['validation', 'live'])('%s retains observed evidence across a transient status failure', async kind => {
    const flow = await openExecutionFlow(kind);
    await flow.choosePaidTask();
    await flow.authorizeCost(0.25);
    await flow.startRun();
    const id = flow.observation().job.id;
    await flow.failNextPoll();
    await flow.advanceTime(1000);
    expect(flow.observation().error).toBe('unavailable');
    expect(flow.observation().job.id).toBe(id);
    await flow.completeRun();
    await flow.advanceTime(2000);
    expect(flow.observation().error).toBe('');
    expect(flow.observation().job.status).toBe('completed');
    expect(flow.observation().mutations).toHaveLength(1);
  });

  it('binds a standalone review to the retrieved report and row hashes', async () => {
    const flow = await openExecutionFlow('workbench');
    await flow.choosePaidTask();
    await flow.authorizeCost(0.25);
    await flow.startRun();
    await flow.completeRun();
    await flow.advanceTime(2000);
    await flow.prepareReview();
    expect(flow.observation().reviewRows).toEqual([{ row_sha256: 'd'.repeat(64), verdict: '', reason: '' }]);
    await flow.submitReview();
    expect(flow.observation().mutations.at(-1).body).toEqual({
      report_sha256: 'b'.repeat(64), reviewer: 'Synthetic fixture reviewer', reason: 'Compared the fixture row',
      verdict: 'failed', rows: [{ row_sha256: 'd'.repeat(64), verdict: 'failed', reason: 'Fixture mismatch' }],
    });
  });

  it('imports a model review through the unchanged sidecar contract', async () => {
    const flow = await openExecutionFlow('live');
    await flow.choosePaidTask();
    await flow.authorizeCost(0.25);
    await flow.startRun();
    await flow.completeRun();
    await flow.advanceTime(1000);
    await flow.submitReview();
    const result = flow.observation();
    expect(result.reviewSaved).toBe(true);
    expect(result.mutations.at(-1).body).toEqual(result.expectedReview);
    expect(result.job.semantic_status).toBe('reviewed');
  });

  it.each(['workbench', 'validation', 'live'])('%s instances keep their execution state and consent separate', async kind => {
    const first = await openExecutionFlow(kind);
    const second = await openExecutionFlow(kind);
    await first.choosePaidTask();
    await first.authorizeCost(0.25);
    await first.startRun();
    expect(first.observation().job.status).toBe('queued');
    expect(second.observation().job).toBeNull();
    expect(second.observation().acknowledged).toBe(false);
    expect(second.observation().mutations).toEqual([]);
  });
});
