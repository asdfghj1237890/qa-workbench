<template>
  <section class="qa-release-decision" :class="'qa-release-decision-' + decision.state" data-testid="qa-release-decision" :aria-labelledby="titleId">
    <header class="qa-release-decision-header">
      <div><p class="qa-release-decision-eyebrow">{{ $t('qaRunFlow.decisionTitle') }}</p><h2 :id="titleId" data-testid="qa-release-decision-verdict">{{ $t('qaRunFlow.states.' + decision.state) }}</h2></div>
      <span class="qa-release-decision-status">{{ decision.state === 'running' ? 'RUNNING' : decision.state === 'ready' ? 'PASS' : decision.state === 'blocked' ? 'FAIL' : 'INCOMPLETE' }}</span>
    </header>
    <p class="qa-release-decision-summary">{{ $t('qaRunFlow.summaries.' + (syncIssue ? 'syncIssue' : decision.state)) }}</p>
    <p class="qa-release-decision-scope">{{ $t(decision.scope === 'basic' ? 'qaRunFlow.basicScope' : 'qaRunFlow.qualityScope') }}</p>
    <div class="qa-release-decision-columns">
      <div data-testid="qa-release-blockers"><h3>{{ $t('qaRunFlow.blockersTitle') }}</h3><ul v-if="decision.blockers.length"><li v-for="blocker in decision.blockers" :key="blocker.mode + ':' + blocker.reason">{{ $t(blocker.i18nKey, { task: $t('qaRunFlow.tasks.' + blocker.mode) }) }}</li></ul><p v-else>{{ $t(decision.state === 'running' ? 'qaRunFlow.pendingBlockers' : 'qaRunFlow.noneBlockers') }}</p></div>
      <div data-testid="qa-release-missing"><h3>{{ $t('qaRunFlow.missingTitle') }}</h3><ul><li v-for="entry in decision.missing" :key="entry.id">{{ $t(entry.i18nKey) }}</li></ul></div>
    </div>
  </section>
</template>

<script setup>
import { computed, useId } from 'vue';
import { buildReleaseDecision } from '../lib/qaReleaseDecision.js';

const props = defineProps({
  job: { type: Object, default: null }, sourceSha: { type: String, default: null },
  kind: { type: String, default: 'offline_regression' }, capabilities: { type: Object, default: null }, validationObservation: { type: Object, default: null }, syncIssue: { type: Boolean, default: false },
});
const titleId = 'qa-release-decision-title-' + useId();
const decision = computed(() => buildReleaseDecision(props));
</script>

<style scoped>
.qa-release-decision { margin: 0 0 24px; padding: 20px; min-width: 0; border: 1px solid var(--border); border-left: 4px solid var(--ink-3); border-radius: 8px; background: var(--paper); color: var(--ink); font-family: var(--font-sans); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); overflow-wrap: anywhere; }
.qa-release-decision-ready { border-left-color: var(--accent); }
.qa-release-decision-blocked { border-left-color: var(--error, #b84337); }
.qa-release-decision-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.qa-release-decision-eyebrow { margin: 0 0 4px; color: var(--ink-2); font-size: var(--qa-type-meta); font-weight: 600; }
.qa-release-decision h2 { margin: 0; font-size: var(--qa-type-section-title); line-height: var(--qa-leading-title); font-family: var(--font-sans); font-weight: 600; }
.qa-release-decision-status { flex: 0 0 auto; padding: 3px 8px; border: 1px solid var(--border); border-radius: 4px; color: var(--ink-2); font-size: var(--qa-type-meta); font-weight: 700; }
.qa-release-decision-summary { margin: 12px 0 4px; }
.qa-release-decision-scope { margin: 0; color: var(--ink-2); font-size: var(--qa-type-meta); }
.qa-release-decision-columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
.qa-release-decision h3 { margin: 0 0 6px; font-size: var(--qa-type-subsection-title); font-weight: 600; }
.qa-release-decision-columns p, .qa-release-decision ul { margin: 0; color: var(--ink-2); }
.qa-release-decision ul { padding-left: 20px; }
.qa-release-decision li + li { margin-top: 4px; }
@media (max-width: 760px) { .qa-release-decision { padding: 16px; } .qa-release-decision-columns { grid-template-columns: minmax(0, 1fr); gap: 16px; } .qa-release-decision-header { align-items: flex-start; } }
</style>
