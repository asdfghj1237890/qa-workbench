<template>
  <section class="qa-execution-history" data-testid="qa-execution-history" aria-labelledby="qa-history-title" :aria-busy="loading">
    <header class="qa-history-heading"><div><h1 id="qa-history-title">{{ $t('qaWorkbench.history.title') }}</h1><p>{{ $t('qaWorkbench.history.intro') }}</p></div><button class="qa-button" type="button" data-testid="qa-history-refresh" :disabled="loading" @click="$emit('refresh')"><QaIcon name="refresh" aria-hidden="true" />{{ $t('qaWorkbench.release.actions.reload') }}</button></header>
    <div class="qa-history-filters">
      <label>{{ $t('qaWorkbench.history.mode') }}<select v-model="mode" data-testid="qa-history-mode"><option value="">{{ $t('qaWorkbench.history.allModes') }}</option><option v-for="value in modes" :key="value" :value="value">{{ modeTitle(value) }}</option></select></label>
      <label>{{ $t('qaWorkbench.history.status') }}<select v-model="status" data-testid="qa-history-status"><option value="">{{ $t('qaWorkbench.history.allStatuses') }}</option><option v-for="value in statuses" :key="value" :value="value">{{ value }}</option></select></label>
      <label class="qa-history-search">{{ $t('qaWorkbench.history.search') }}<input v-model.trim="search" type="search" data-testid="qa-history-search" :placeholder="$t('qaWorkbench.history.searchHint')"></label>
    </div>
    <p v-if="error" role="alert" class="qa-history-notice qa-history-error">{{ $t('qaWorkbench.history.error') }}</p>
    <p v-if="loading" role="status" class="qa-history-notice">{{ $t('qaWorkbench.history.loading') }}</p>
    <p v-if="!filtered.length && !loading && !error" class="qa-history-empty" role="status">{{ $t(entries.length ? 'qaWorkbench.history.noMatches' : 'qaWorkbench.history.empty') }}</p>
    <div v-if="filtered.length" class="qa-history-table-scroll">
      <table class="qa-history-table">
        <thead><tr><th>{{ $t('qaWorkbench.history.time') }}</th><th>{{ $t('qaWorkbench.history.run') }}</th><th>{{ $t('qaWorkbench.history.status') }}</th><th>{{ $t('qaWorkbench.history.revision') }}</th><th>{{ $t('qaWorkbench.history.measured') }}</th><th>{{ $t('qaWorkbench.history.actions') }}</th></tr></thead>
        <tbody>
          <tr v-for="entry in filtered" :key="entry.family + ':' + entry.id" data-testid="qa-history-row" :data-job-id="entry.id">
            <td><time v-if="validTime(entry.startedAt)" :datetime="entry.startedAt">{{ timestamp(entry.startedAt) }}</time><span v-else class="qa-history-muted">{{ $t('qaWorkbench.history.noTime') }}</span></td>
            <th scope="row"><span>{{ modeTitle(entry.mode) }}</span><code>{{ entry.id }}</code><small v-if="entry.mode === 'offline_regression'">{{ $t('qaValidation.suites.' + entry.job.suite) }}</small><small v-if="entry.family === 'evaluations'">{{ entry.job.model }} · {{ $t('qaLive.profiles.' + entry.job.profile) }}</small><small v-if="entry.family === 'corpus-evaluations'">{{ entry.job.bank.version }} · {{ entry.job.split }} · {{ entry.job.pricing?.model }}</small></th>
            <td><span class="qa-history-status" :class="'qa-history-status-' + entry.status.toLowerCase().replaceAll(' ', '-')">{{ entry.status }}</span><small v-if="entry.family === 'corpus-evaluations'" class="qa-history-quality">{{ $t(corpusReview(entry.job) ? corpusReview(entry.job).reviewer_kind === 'ai' ? 'qaSemanticReview.completedAi' : 'qaSemanticReview.completedHuman' : 'qaCorpus.pending') }}</small><small v-else-if="entry.family === 'evaluations' || entry.mode === 'real_es_llm_e2e'" class="qa-history-quality">{{ $t(entry.family === 'evaluations' && getSemanticReview(entry.job) ? semanticReviewKey(entry.job) : 'qaWorkbench.history.semanticPending') }}</small></td>
            <td><code v-if="entry.sourceSha" :title="entry.sourceSha">{{ entry.sourceSha.slice(0, 8) }}</code><span v-else class="qa-history-muted">{{ $t('qaWorkbench.history.noVersion') }}</span></td>
            <td><span v-if="entry.family === 'corpus-evaluations'" class="qa-history-muted">{{ $t('qaCorpus.historyMeasurement') }}</span><div v-else-if="entry.counts" class="qa-history-counts"><span><b>{{ number(entry.counts.passed) }}</b> PASS</span><span><b>{{ number(entry.counts.failed) }}</b> FAIL</span><span v-if="entry.counts.errors"><b>{{ number(entry.counts.errors) }}</b> ERROR</span><span v-if="entry.counts.skipped"><b>{{ number(entry.counts.skipped) }}</b> SKIP</span></div><span v-else class="qa-history-muted">{{ $t('qaWorkbench.history.noMeasurement') }}</span></td>
            <td><div class="qa-history-actions"><button class="qa-button" type="button" data-testid="qa-history-details" :disabled="loading" @click="$emit('select', entry)">{{ $t('qaWorkbench.history.details') }}<QaIcon name="arrow_forward" aria-hidden="true" /></button><button v-if="entry.family !== 'corpus-evaluations'" class="qa-history-log-link" type="button" data-testid="qa-history-logs" :disabled="loading" @click="$emit('logs', entry)"><QaIcon name="list" aria-hidden="true" />{{ $t('qaWorkbench.history.logs') }}</button></div></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="qa-history-retention"><QaIcon name="info" aria-hidden="true" />{{ $t('qaWorkbench.history.retention') }}</p>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import QaIcon from "./QaIcon.vue";
import { getSemanticReview, semanticReviewKey } from "../lib/qaSemanticReview.js";
import { corpusReview } from "../lib/qaCorpusEvaluation.js";
const props = defineProps({ entries: { type: Array, default: () => [] }, loading: { type: Boolean, default: false }, error: { type: [String, Boolean], default: "" } });
defineEmits(["select", "logs", "refresh"]);
const { locale, t } = useI18n();
const mode = ref(""), status = ref(""), search = ref("");
const modes = ["offline_regression", "es_integration", "real_es_llm_e2e", "model_evaluation", "real_corpus_quality"];
const statuses = ["PASS", "FAIL", "RUNNING", "INCOMPLETE", "UNKNOWN", "STALE", "NOT RUN"];
const filtered = computed(() => props.entries.filter((entry) => (!mode.value || entry.mode === mode.value) && (!status.value || entry.status === status.value)
  && (!search.value || [entry.id, entry.sourceSha, entry.job.model, entry.job.pricing?.model, entry.job.bank?.id, entry.job.bank?.version].filter(Boolean).join(" ").toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))));
const modeTitle = (value) => t("qaFlow.tasks." + value + ".title");
const validTime = (value) => value && Number.isFinite(Date.parse(value));
const timestamp = (value) => new Intl.DateTimeFormat(locale.value, { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(value));
const number = (value) => new Intl.NumberFormat(locale.value).format(value);
</script>

<style scoped>
.qa-execution-history { min-width:0; color:var(--ink); font:var(--qa-type-body)/var(--qa-leading-body) var(--font-sans); }
.qa-history-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:24px; }.qa-history-heading h1 { font:600 var(--qa-type-page-title)/var(--qa-leading-title) var(--font-sans); margin:0 0 8px; letter-spacing:-.02em; }.qa-history-heading p { color:var(--ink-2); margin:0; }.qa-history-heading>.qa-button { flex:none; min-height:36px; gap:8px; font-size:var(--qa-type-control); }
.qa-history-filters { display:grid; grid-template-columns:minmax(140px,1fr) minmax(130px,1fr) minmax(200px,1.8fr); gap:16px; padding:18px 20px; margin-bottom:20px; background:var(--surface); border:1px solid var(--border); border-radius:8px; }
.qa-history-filters label { display:grid; gap:7px; color:var(--ink-2); font-size:var(--qa-type-control); }.qa-history-filters input,.qa-history-filters select { min-width:0; width:100%; height:39px; box-sizing:border-box; border:1px solid var(--border); border-radius:5px; background:var(--surface-2); color:var(--ink); font:var(--qa-type-control)/var(--qa-leading-body) var(--font-sans); padding:8px 10px; }
.qa-history-filters input:focus-visible,.qa-history-filters select:focus-visible,.qa-history-actions button:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
.qa-history-notice { padding:12px 16px; border:1px solid var(--border); border-radius:6px; }.qa-history-error { color:var(--warning); }.qa-history-empty { text-align:center; padding:60px 20px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--ink-2); }
.qa-history-table-scroll { overflow:auto; border:1px solid var(--border); border-radius:8px; background:var(--surface); }.qa-history-table { border-collapse:collapse; width:100%; min-width:820px; text-align:left; }.qa-history-table th,.qa-history-table td { padding:18px 16px; vertical-align:top; border-bottom:1px solid var(--border); }.qa-history-table thead th { color:var(--ink-2); font-size:var(--qa-type-meta); font-weight:500; padding-top:13px; padding-bottom:13px; background:var(--surface-2); white-space:nowrap; }.qa-history-table tr:last-child th,.qa-history-table tr:last-child td { border-bottom:0; }.qa-history-table tbody th { font-weight:500; }.qa-history-table tbody th>span { display:block; }.qa-history-table code { display:block; font:var(--qa-type-code)/var(--qa-leading-body) var(--font-mono); color:var(--ink-2); overflow-wrap:anywhere; max-width:170px; margin-top:5px; }.qa-history-table td>code { margin-top:0; }.qa-history-table time { font-size:var(--qa-type-meta); white-space:nowrap; }.qa-history-table small { display:block; color:var(--ink-2); font-size:var(--qa-type-meta); font-weight:400; margin-top:5px; }
.qa-history-status { display:inline-flex; align-items:center; font:600 var(--qa-type-meta)/var(--qa-leading-body) var(--font-mono); color:var(--ink-2); border:1px solid var(--border); border-radius:4px; padding:3px 8px; white-space:nowrap; }.qa-history-status-pass { color:var(--accent); background:var(--accent-soft); border-color:color-mix(in srgb,var(--accent) 35%,transparent); }.qa-history-status-fail { color:var(--danger); border-color:color-mix(in srgb,var(--danger) 35%,transparent); }.qa-history-status-running { color:var(--accent); }.qa-history-status-incomplete,.qa-history-status-stale { color:var(--warning); }.qa-history-quality { max-width:135px; line-height:1.7; }.qa-history-counts { display:flex; flex-wrap:wrap; gap:4px 10px; min-width:110px; color:var(--ink-2); font:var(--qa-type-meta)/var(--qa-leading-body) var(--font-mono); }.qa-history-counts b { color:var(--ink); font-weight:500; }.qa-history-muted { font-size:var(--qa-type-meta); color:var(--ink-2); }
.qa-history-actions { display:grid; justify-items:start; gap:9px; }.qa-history-actions .qa-button { min-height:32px; padding:5px 9px; font-size:var(--qa-type-control); gap:8px; white-space:nowrap; }.qa-history-log-link { display:inline-flex; align-items:center; gap:6px; appearance:none; background:none; border:0; color:var(--accent); font:var(--qa-type-control)/var(--qa-leading-body) var(--font-sans); padding:2px 0; cursor:pointer; white-space:nowrap; }.qa-history-log-link:hover { text-decoration:underline; text-underline-offset:3px; }.qa-history-retention { display:flex; gap:9px; align-items:flex-start; margin:17px 0 0; color:var(--ink-2); font-size:var(--qa-type-meta); line-height: var(--qa-leading-body); }.qa-history-retention .qa-icon { flex:none; margin-top:3px; }
@media(max-width:800px) { .qa-history-filters { grid-template-columns:1fr 1fr; gap:12px; }.qa-history-search { grid-column:1/-1; }.qa-history-heading h1 { font-size:var(--qa-type-page-title); } }
@media(max-width:440px) { .qa-history-filters { padding:14px; grid-template-columns:1fr; }.qa-history-search { grid-column:auto; }.qa-history-table-scroll { max-width:100%; } }
</style>
