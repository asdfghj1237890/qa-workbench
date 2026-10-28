<template>
  <section class="qa-evidence-scope" data-testid="qa-evidence-scope">
    <div v-if="covered.length"><h4>{{ $t('qaEvidence.coveredTitle') }}</h4><ul><li v-for="(code, index) in covered" :key="index">{{ describe(code) }}</li></ul></div>
    <div v-if="gaps.length"><h4>{{ $t('qaEvidence.gapsTitle') }}</h4><ul><li v-for="(code, index) in gaps" :key="index">{{ describe(code) }}</li></ul></div>
    <p>{{ $t('qaLive.semanticPending') }}</p>
    <details v-if="covered.length || gaps.length"><summary>{{ $t('qaEvidence.rawDetails') }}</summary><dl><template v-for="(codes, index) in [covered, gaps]" :key="index"><dt>{{ $t(index ? 'qaEvidence.gapsTitle' : 'qaEvidence.coveredTitle') }}</dt><dd><code v-for="(code, codeIndex) in codes" :key="codeIndex">{{ code }}</code><span v-if="!codes.length">—</span></dd></template></dl></details>
  </section>
</template>

<script setup>
import { useI18n } from 'vue-i18n';
import { getEvidenceCode, getEvidenceStep } from '../lib/qaEvidence.js';

defineProps({ covered: { type: Array, default: () => [] }, gaps: { type: Array, default: () => [] } });
const { t } = useI18n();
function describe(code) {
  const boundary = getEvidenceCode(code), step = getEvidenceStep(code);
  return boundary ? t(boundary.i18nKey) : step ? t('qaEvidence.stages.' + step.key + '.title') : t('qaEvidence.unknownBoundary');
}
</script>

<style scoped>
.qa-evidence-scope { display: grid; gap: 16px; min-width: 0; margin-top: 20px; padding: 16px; border: 1px solid var(--border); border-radius: 8px; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); overflow-wrap: anywhere; }
.qa-evidence-scope h4 { margin: 0 0 6px; color: var(--ink); font-size: var(--qa-type-subsection-title); font-weight: 600; }
.qa-evidence-scope ul { margin: 0; padding-left: 20px; }
.qa-evidence-scope li + li { margin-top: 4px; }
.qa-evidence-scope p { margin: 0; font-size: var(--qa-type-meta); }
.qa-evidence-scope details { border-top: 1px solid var(--border); padding-top: 12px; }
.qa-evidence-scope summary { width: fit-content; cursor: pointer; font-size: var(--qa-type-control); }
.qa-evidence-scope summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-evidence-scope dl { margin: 12px 0 0; font-size: var(--qa-type-meta); }
.qa-evidence-scope dt { margin-top: 8px; font-weight: 600; }
.qa-evidence-scope dd { margin: 4px 0 0; }
.qa-evidence-scope code { display: block; font-family: var(--font-mono); font-size: var(--qa-type-code); }
</style>
