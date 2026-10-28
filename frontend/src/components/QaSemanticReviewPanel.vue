<template>
  <div v-if="entry && caseReview" class="qa-semantic-case" data-testid="qa-semantic-case">
    <h4>{{ $t('qaSemanticReview.caseResult') }}</h4>
    <dl class="qa-semantic-scores"><div v-for="dimension in dimensions" :key="dimension" :data-score="caseReview.scores[dimension] ? 'passed' : 'failed'"><dt>{{ $t('qaSemanticReview.dimensions.' + dimension) }}</dt><dd>{{ caseReview.scores[dimension] ? 'PASS' : 'FAIL' }}</dd></div></dl>
    <p class="qa-semantic-reason">{{ caseReview.reason }}</p>
  </div>
  <section v-else-if="!entry" class="qa-semantic-panel" data-testid="qa-semantic-panel" :aria-labelledby="titleId">
    <div class="qa-semantic-heading"><h3 :id="titleId">{{ $t(semanticReviewKey(job)) }}</h3><strong v-if="review" :class="{ 'qa-semantic-failed': review.failed > 0 }">{{ $t('qaSemanticReview.counts', { passed: review.passed, failed: review.failed }) }}</strong></div>
    <template v-if="review">
      <p>{{ $t('qaSemanticReview.reviewer', { name: review.reviewer, time: timestamp(review.reviewed_at) }) }}</p>
      <p data-testid="qa-semantic-coverage">{{ $t('qaSemanticReview.coverage', { reviewed: review.reviewed_cases, observed: review.observed_cases }) }} · {{ $t('qaSemanticReview.planned', { planned: review.planned_cases, unexecuted: review.planned_cases - review.observed_cases }) }}</p>
      <p class="qa-semantic-note">{{ $t('qaSemanticReview.completedNote') }}</p>
      <p v-if="job.archive_imported" class="qa-semantic-note"><strong>{{ $t('qaSemanticReview.imported') }}</strong> · {{ $t('qaSemanticReview.importedNote') }}</p>
    </template>
    <p v-else data-testid="qa-semantic-pending">{{ $t('qaSemanticReview.importHint') }}</p>
    <div v-if="job.report_available && !isLiveActive(job)" class="qa-semantic-actions">
      <button class="qa-button" data-testid="qa-semantic-import" type="button" :disabled="busy" @click="fileInput?.click()"><QaIcon name="upload" aria-hidden="true" />{{ $t('qaSemanticReview.import') }}</button>
      <button v-if="review" class="qa-button" data-testid="qa-semantic-download" type="button" :disabled="busy" @click="$emit('download')"><QaIcon name="download" aria-hidden="true" />{{ $t('qaSemanticReview.download') }}</button>
      <input ref="fileInput" type="file" accept="application/json,.json" :aria-label="$t('qaSemanticReview.import')" :disabled="busy" hidden @change="selected" />
    </div>
    <p v-if="error" class="qa-semantic-failed" role="alert">{{ $t(error) }}</p>
  </section>
</template>

<script setup>
import { computed, ref, useId } from "vue";
import { useI18n } from "vue-i18n";
import QaIcon from "./QaIcon.vue";
import { getCaseSemanticReview, getSemanticReview, semanticReviewKey } from "../lib/qaSemanticReview.js";
import { isLiveActive } from "../lib/qaLiveEvaluation.js";

const props = defineProps({ job: { type: Object, required: true }, entry: { type: Object, default: null }, busy: { type: Boolean, default: false }, error: { type: String, default: "" } });
const emit = defineEmits(["import", "download"]);
const { t: $t, locale } = useI18n();
const titleId = "qa-semantic-title-" + useId();
const fileInput = ref(null);
const dimensions = ["intent", "grounding", "completeness", "language"];
const review = computed(() => getSemanticReview(props.job));
const caseReview = computed(() => props.entry ? getCaseSemanticReview(props.job, props.entry) : null);
const timestamp = (value) => new Intl.DateTimeFormat(locale.value, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "Asia/Taipei" }).format(new Date(value));
function selected(event) {
  const file = event.target.files?.[0];
  if (file && !props.busy) emit("import", file);
  event.target.value = "";
}
</script>

<style scoped>
.qa-semantic-panel { margin: 20px 0; padding: 18px; border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 8px; background: var(--surface-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); overflow-wrap: anywhere; }
.qa-semantic-heading { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 8px 20px; }
.qa-semantic-heading h3 { margin: 0; font: 600 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); }
.qa-semantic-heading strong { color: var(--accent); }
.qa-semantic-panel p { margin: 10px 0 0; }
.qa-semantic-note { color: var(--ink-2); font-size: var(--qa-type-meta); }
.qa-semantic-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.qa-semantic-actions button { gap: 7px; }
.qa-semantic-case { margin-top: 18px; padding: 14px; border: 1px solid var(--border); border-radius: 6px; }
.qa-semantic-case h4 { margin: 0 0 12px; font-size: var(--qa-type-body); }
.qa-semantic-scores { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 0; }
.qa-semantic-scores div { display: flex; flex-wrap: wrap; gap: 5px 8px; color: var(--accent); }
.qa-semantic-scores dd { margin: 0; font-family: var(--font-mono); }
.qa-semantic-failed, .qa-semantic-heading .qa-semantic-failed, .qa-semantic-scores [data-score="failed"] { color: var(--danger); }
.qa-semantic-reason { margin: 14px 0 0; color: var(--ink); white-space: pre-wrap; }
@media (max-width: 650px) { .qa-semantic-panel { padding: 14px; } .qa-semantic-scores { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
