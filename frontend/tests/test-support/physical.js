/** Contract: App.vue consumes qa_workbench.api via an explicitly injected client. */
import { mount, flushPromises } from '@vue/test-utils';
import App from '../../src/App.vue';
const SHA = 'a'.repeat(40);
export async function openWorkbench() {
  const calls = [], runs = [];
  const tasks = [
    { id: 'warehouse-inventory', title: 'Inventory reconciliation', paid: false, input_schema: { type: 'object' } },
    { id: 'support-quality', title: 'Support answer quality', paid: true, requires_review: true },
  ];
  const client = {
    capabilities: async () => ({ project: { id: 'warehouse', name: 'Warehouse QA', source_sha: SHA }, source_sha: SHA, tasks }),
    history: async () => ({ runs: [...runs] }),
    health: async () => ({ status: 'unknown', observations: [] }),
    async start(task, form) { calls.push({ method: 'POST', task: task.id, form: structuredClone(form) }); const job = { id: 'owned-run', task_id: task.id, status: 'completed', source_sha: SHA, structural_status: 'passed', semantic_status: 'pending_review', quality_passed: false, evidence_kind: 'synthetic', report_available: true, gaps: ['human_review_not_performed'] }; runs.push(job); return { job }; },
    run: async () => ({ job: runs.at(-1) }),
    logs: async () => ({ text: 'captured adapter output', next_offset: 23, total_bytes: 23, has_more: false, truncated: false }),
  };
  const wrapper = mount(App, { props: { client }, attachTo: document.body });
  await flushPromises();
  return {
    async select(id) { await wrapper.get('[data-testid="task-' + id + '"]').trigger('click'); await flushPromises(); },
    async start() { await wrapper.get('[data-testid="start-run"]').trigger('click'); await flushPromises(); },
    async consent(budget) { await wrapper.get('[data-testid="task-budget"]').setValue(budget); await wrapper.get('[data-testid="task-consent"]').setValue(true); },
    async options(text) { await wrapper.get('[data-testid="task-options"]').setValue(text); },
    text: () => wrapper.text(),
    calls: () => structuredClone(calls),
    disabled: () => wrapper.get('[data-testid="start-run"]').element.disabled,
    close: () => wrapper.unmount(),
  };
}
