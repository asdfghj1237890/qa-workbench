<template>
  <section class="qa-testing qa-live" :class="{ 'qa-live-workbench': workbench }" aria-labelledby="qa-live-title" data-testid="qa-live-panel">
    <div class="qa-testing-heading">
      <div><div v-if="!workbench" class="qa-eyebrow">{{ $t('qaLive.eyebrow') }}</div><component :is="workbench ? 'h1' : 'h2'" id="qa-live-title" data-testid="qa-live-state-title">{{ $t(workbench ? stateTitleKey : 'qaLive.title') }}</component><p v-if="workbench" class="qa-testing-intro">{{ $t('qaLive.title') }}<template v-if="workspacePhase === 'settings'"> · {{ $t('qaFaithfulLive.intro') }}</template></p></div>
      <span v-if="!workbench" class="qa-live-tag">{{ $t('qaLive.realism') }}</span>
    </div>
    <p v-if="!workbench" class="qa-testing-intro">{{ $t('qaLive.scope') }}</p>
    <details class="qa-live-purpose" aria-labelledby="qa-live-purpose-title">
      <summary>
        <span id="qa-live-purpose-title" class="qa-live-purpose-title">{{ $t('qaEvaluationScope.title') }}</span>
        <span class="qa-live-purpose-summary">{{ $t('qaEvaluationScope.summary') }}</span>
        <QaIcon class="qa-live-purpose-toggle" name="expand_more" aria-hidden="true" />
      </summary>
      <div class="qa-live-purpose-content">
        <p class="qa-live-purpose-intro">{{ $t('qaEvaluationScope.purpose') }}</p>
        <dl>
          <div v-for="item in ['subject', 'method', 'result']" :key="item">
            <dt>{{ $t('qaEvaluationScope.' + item + 'Title') }}</dt>
            <dd>{{ $t('qaEvaluationScope.' + item + 'Note') }}</dd>
          </div>
        </dl>
        <p class="qa-live-purpose-limit">{{ $t('qaEvaluationScope.limit') }}</p>
      </div>
    </details>
    <div class="qa-live-archive-import">
      <button class="qa-button" type="button" data-testid="qa-live-import-archive" :disabled="loading || capabilities?.busy || isLiveActive(job)" @click="archiveInput?.click()"><QaIcon name="upload" aria-hidden="true" />{{ $t('qaSemanticReview.archiveImport') }}</button>
      <input ref="archiveInput" type="file" accept="application/json,.json" :aria-label="$t('qaSemanticReview.archiveImport')" hidden @change="selectArchive" />
      <p class="qa-small">{{ $t(importing ? 'qaSemanticReview.importing' : 'qaSemanticReview.archiveHint') }}</p>
      <p v-if="reviewImportError" role="alert" class="qa-gap">{{ $t(reviewImportError) }}</p>
      <p v-if="reviewSaved" role="status" class="qa-small">{{ $t('qaSemanticReview.saved') }}</p>
    </div>
    <div v-if="workbench && job" class="qa-live-view-actions">
      <button v-if="workspaceView === 'evidence'" class="qa-button" type="button" data-testid="qa-live-show-settings" @click="workspaceView = 'settings'"><QaIcon name="tune" aria-hidden="true" />{{ $t('qaRunFlow.backToSettings') }}</button>
      <button v-else class="qa-button" type="button" data-testid="qa-live-show-evidence" @click="workspaceView = 'evidence'">{{ $t(isLiveActive(job) ? 'qaRunFlow.running' : 'qaRunFlow.results') }}<span v-if="isLiveActive(job)" class="qa-live-tab-state">RUNNING</span></button>
    </div>
    <p v-if="error" class="qa-state qa-error" role="alert">{{ $t('qaLive.errors.' + error) }}</p>
    <p v-if="!loading && !capabilities?.available" class="qa-state" role="status">{{ $t('qaLive.unavailable') }}</p>
    <p v-if="capabilities?.busy && !isLiveActive(job)" class="qa-small" role="status">{{ $t('qaLive.busy') }}</p>
    <p v-if="retryAfter > 0" class="qa-small" role="status">{{ $t('qaLive.cooldown', { n: retryAfter }) }}</p>

    <div class="qa-live-layout" :class="{ 'qa-live-evidence-layout': workbench && workspaceView === 'evidence' && job }">
      <div v-show="!workbench || workspaceView === 'settings'" class="qa-live-left">
        <form id="qa-live-config-form" class="qa-panel qa-live-config" @submit.prevent="start">
          <div v-if="workbench" class="qa-live-config-heading"><h2>{{ $t('qaRunFlow.configuration') }}</h2><span v-if="isLiveActive(job)" class="qa-live-locked">{{ $t('qaLive.settingsLocked') }}</span></div>
          <div class="qa-live-fields">
            <div v-if="workbench" class="qa-live-field">
              <label for="qa-live-fixed-model">{{ $t('qaLive.model') }}</label>
              <div class="qa-live-model-shell"><output id="qa-live-fixed-model" class="qa-live-model" data-testid="qa-live-model">{{ capabilities?.model || '—' }}</output><span class="qa-live-fixed-model"><QaIcon name="lock" aria-hidden="true" />{{ $t('qaFaithfulLive.fixedModel') }}</span></div>
              <p class="qa-live-field-note qa-live-model-note"><span>{{ $t('qaFaithfulLive.modelNote') }}</span><QaIcon name="info" aria-hidden="true" /><span class="qa-live-scope-chip">{{ $t('qaFaithfulLive.noRealEs') }}</span></p>
            </div>
            <div class="qa-live-field">
              <label for="qa-live-profile-select">{{ $t('qaLive.profile') }}</label>
              <div class="qa-live-select-shell"><select id="qa-live-profile-select" v-model="profile" data-testid="qa-live-profile" :disabled="loading || isLiveActive(job)" :aria-describedby="workbench ? 'qa-live-profile-note' : undefined"><option v-for="entry in profiles" :key="entry.id" :value="entry.id">{{ $t('qaLive.profiles.' + entry.id) }} · {{ $t('qaLive.cases', { n: entry.case_count }) }}</option></select><QaIcon v-if="workbench" name="expand_more" aria-hidden="true" /></div>
              <p v-if="workbench" id="qa-live-profile-note" class="qa-live-field-note">{{ profileCounts }}</p>
            </div>
            <div class="qa-live-field">
              <label for="qa-live-budget-input">{{ $t('qaLive.budget') }}</label>
              <input id="qa-live-budget-input" v-model.number="budget" data-testid="qa-live-budget" type="number" min="0.01" :max="ceiling" step="0.01" inputmode="decimal" :disabled="loading || isLiveActive(job)" :aria-invalid="!budgetValid" aria-describedby="qa-live-budget-note" />
              <p v-if="workbench" id="qa-live-budget-note" class="qa-live-field-note"><span>{{ $t('qaFaithfulLive.budgetNote', { n: ceiling.toFixed(2) }) }}</span><QaIcon name="info" aria-hidden="true" /><span class="qa-live-paid-chip">{{ $t('qaFaithfulLive.paid') }}</span></p>
            </div>
          </div>
          <p v-if="!workbench" id="qa-live-budget-note" class="qa-small">{{ $t('qaLive.budgetNote', { n: ceiling }) }}</p>
          <label class="qa-live-ack"><input v-model="acknowledged" data-testid="qa-live-ack" type="checkbox" :disabled="loading || isLiveActive(job)" /><span>{{ $t(workbench ? 'qaFaithfulLive.acknowledge' : 'qaLive.acknowledge') }}<small v-if="workbench">{{ $t('qaFaithfulLive.acknowledgeNote') }}</small></span></label>
          <div class="qa-live-actions qa-live-start-actions"><button class="qa-button" :class="{ 'qa-primary': workbench }" data-testid="qa-live-start" type="submit" :disabled="cannotStart" :aria-describedby="workbench ? 'qa-live-start-reason' : undefined" @click.prevent="start"><span>{{ $t(workbench ? 'qaFaithfulLive.start' : 'qaLive.start') }}</span><span v-if="workbench" id="qa-live-start-reason" class="qa-live-start-reason" data-testid="qa-live-start-reason" role="status">{{ startReason }}<QaIcon name="info" aria-hidden="true" /></span></button><button v-if="!workbench" class="qa-button" type="button" :disabled="loading" @click="load">{{ $t('qaLive.refresh') }}</button></div>
          <div v-if="capabilities && !workbench" class="qa-live-resource"><p class="qa-small qa-live-limits">{{ resourceLimits }}</p><p v-if="capabilities.pricing" class="qa-small">{{ resourcePricing }}</p></div>
        </form>
      </div>

      <article v-if="job" v-show="!workbench || workspaceView === 'evidence'" class="qa-panel qa-live-result" data-testid="qa-live-result" :aria-busy="isLiveActive(job)">
        <div class="qa-panel-head"><component :is="workbench ? 'h2' : 'h3'">{{ $t('qaLive.result') }}</component><strong v-if="!workbench" role="status">{{ missingJob ? 'UNKNOWN' : $t('qaLive.status.' + job.status) }}</strong><button v-if="workbench && isLiveActive(job)" class="qa-button" data-testid="qa-live-cancel" :disabled="cancelling" @click="cancel">{{ $t('qaLive.cancel') }}</button></div>
        <QaReleaseDecision v-if="!isLiveActive(job) || missingJob || error" :job="job" :source-sha="capabilities?.source_sha" kind="model_evaluation" :sync-issue="Boolean(missingJob || error)" :validation-observation="validationObservation" />
        <p v-else class="qa-small" data-testid="qa-live-pending-decision">{{ $t('qaRunFlow.summaries.running') }}</p>
        <p v-if="workbench" class="qa-small"><strong role="status">{{ missingJob ? 'UNKNOWN' : $t('qaLive.status.' + job.status) }}</strong></p>
        <p v-if="missingJob" class="qa-small">{{ $t('qaWorkbench.lastKnownStatus', { status: $t('qaLive.status.' + job.status) }) }}</p>
        <p class="qa-small">{{ $t('qaLive.progress', { n: job.completed_cases, total: job.total_cases }) }} · {{ $t('qaLive.profiles.' + job.profile) }} · {{ job.model }}</p>
        <progress :value="job.completed_cases" :max="job.total_cases" :aria-label="$t('qaLive.progress', { n: job.completed_cases, total: job.total_cases })"></progress>
        <p class="qa-live-phase" data-testid="qa-live-phase">{{ $t('qaLive.phase.' + job.phase) }}<span v-if="job.current_case"> · {{ job.current_case }}</span><span v-if="job.current_tool"> · {{ job.current_tool }}</span></p>
        <dl class="qa-live-metrics">
          <div><dt>{{ $t('qaLive.structural') }}</dt><dd>{{ $t('qaLive.structuralCounts', { passed: job.structural.passed, failed: job.structural.failed }) }}</dd></div>
          <div><dt>{{ $t('qaLive.requests') }}</dt><dd>{{ number(job.usage.requests) }} / {{ number(job.max_requests) }}</dd></div>
          <div><dt>{{ $t('qaLive.tokens') }}</dt><dd>{{ $t('qaLive.tokenCounts', { input: number(job.usage.input_tokens), output: number(job.usage.output_tokens) }) }}</dd></div>
          <div><dt>{{ $t('qaLive.estimatedCost') }}</dt><dd>{{ money(job.usage.measured_estimated_usd) }} / {{ money(job.max_usd) }}</dd></div>
        </dl>
        <p class="qa-small">{{ $t('qaLive.reserved', { n: money(job.usage.reserved_estimated_usd) }) }}</p>
        <p v-if="job.usage.underestimated" class="qa-gap" role="status">{{ $t('qaLive.underestimated') }}</p>
        <p v-if="job.error" class="qa-small" role="alert">{{ $t('qaLive.executionError') }}: {{ logCaptureErrorKey(job.error) ? $t(logCaptureErrorKey(job.error)) : job.error }}</p>
        <QaSemanticReviewPanel :job="job" :busy="loading || importing || capabilities?.busy || isLiveActive(job)" @import="importReview" @download="downloadReview" />
        <QaExecutionLog ref="executionLog" family="evaluations" :job-id="job.id" :running="isLiveActive(job)" />
        <h3 v-if="workbench" class="qa-live-cases-heading">{{ $t('qaRunFlow.evidenceDetails') }}</h3>
        <ol v-if="job.cases.length" class="qa-live-cases">
          <li v-for="(entry, index) in job.cases" :key="entry.case_id" :data-testid="'qa-live-case-' + entry.case_id">
            <details>
              <summary><span v-if="workbench" class="qa-live-case-number">{{ String(index + 1).padStart(2, '0') }}</span><span>{{ entry.case_id }} · {{ entry.group }}</span><span class="qa-live-case-grades"><strong :class="{ 'qa-live-rule-failed': !entry.structural_pass }">{{ $t(entry.structural_pass ? 'qaLive.rulePassed' : 'qaLive.ruleFailed') }}</strong><strong v-if="caseReview(entry)" class="qa-live-case-semantic" :class="{ 'qa-live-rule-failed': !caseReviewPassed(entry) }">{{ $t(caseReviewPassed(entry) ? 'qaSemanticReview.casePass' : 'qaSemanticReview.caseFail') }}</strong></span><QaIcon v-if="workbench" class="qa-live-case-toggle" aria-hidden="true" name="expand_more" /></summary>
              <p class="qa-small">{{ entry.split }} · {{ $t('qaLive.duration', { n: number(entry.duration_ms / 1000) }) }} · {{ $t('qaLive.tokenCounts', { input: number(entry.input_tokens), output: number(entry.output_tokens) }) }}</p>
              <ul v-if="entry.hard_failures.length || entry.failures.length" class="qa-live-failures"><li v-for="(failure, failureIndex) in [...entry.hard_failures, ...entry.failures]" :key="failureIndex">{{ failure }}</li></ul>
              <QaSemanticReviewPanel :job="job" :entry="entry" />
              <h4>{{ $t('qaLive.answer') }}</h4><pre>{{ entry.answer || $t('qaLive.noAnswer') }}</pre>
            </details>
          </li>
        </ol>
        <p v-else class="qa-small">{{ $t('qaLive.noCases') }}</p>
        <div class="qa-live-review"><div><p class="qa-live-semantic" data-testid="qa-live-semantic">{{ $t(semanticReview ? semanticReviewKey(job) : 'qaLive.semanticPending') }}</p><p class="qa-gap">{{ $t(semanticReview ? 'qaSemanticReview.reviewedLimit' : 'qaLive.qualityLimit') }}</p></div><div class="qa-live-actions"><button v-if="!workbench && isLiveActive(job)" class="qa-button" data-testid="qa-live-cancel" :disabled="cancelling" @click="cancel">{{ $t('qaLive.cancel') }}</button><button v-if="!workbench && job.report_available" class="qa-button" data-testid="qa-live-report" :disabled="downloading" @click="download">{{ $t('qaLive.download') }}</button><a v-if="reportDownload" class="qa-button" data-testid="qa-live-report-retry" :href="reportDownload.url" :download="reportDownload.filename">{{ $t('qaLive.downloadAgain') }}</a></div></div>
        <p class="qa-small">{{ $t('qaLive.reportNote') }}</p>
      </article>
      <aside v-if="workbench" class="qa-live-guide qa-panel" :aria-labelledby="job && workspaceView === 'evidence' ? 'qa-live-next-title' : 'qa-live-guide-title'">
        <template v-if="job && workspaceView === 'evidence'">
          <h2 id="qa-live-next-title">{{ $t(isLiveActive(job) ? 'qaRunFlow.runningActions' : 'qaRunFlow.resultActions') }}</h2>
          <p class="qa-small">{{ $t(isLiveActive(job) ? 'qaFlowLive.runningNote' : 'qaFlowLive.reviewNote') }}</p>
          <button v-if="job.report_available" class="qa-button qa-primary" data-testid="qa-live-report" type="button" :disabled="downloading" @click="download"><QaIcon name="download" aria-hidden="true" />{{ $t('qaLive.download') }}</button>
          <button v-if="!isLiveActive(job)" class="qa-button" data-testid="qa-live-new-run" type="button" @click="prepareRun"><QaIcon name="tune" aria-hidden="true" />{{ $t('qaFlowLive.prepareRun') }}</button>
          <button class="qa-button" data-testid="qa-live-back-workbench" type="button" @click="emit('navigate', 'verification')"><QaIcon name="arrow_back" aria-hidden="true" />{{ $t('qaRunFlow.backToWorkbench') }}</button>
          <div class="qa-live-guide-limit"><h3>{{ $t('qaFlowLive.scopeTitle') }}</h3><p>{{ $t(semanticReview ? 'qaSemanticReview.reviewedLimit' : 'qaLive.qualityLimit') }}</p><p>{{ $t('qaFlowLive.syntheticLimit') }}</p></div>
        </template>
        <template v-else>
          <h2 id="qa-live-guide-title">{{ $t('qaFlowLive.whatYouGet') }}</h2>
          <ul class="qa-live-evidence-list"><li v-for="entry in evidenceGuide" :key="entry.id"><span class="qa-live-evidence-icon"><QaIcon :name="entry.icon" aria-hidden="true" /></span><div><h3>{{ $t('qaFaithfulLive.' + entry.id + 'Title') }}</h3><p>{{ $t('qaFaithfulLive.' + entry.id + 'Note') }}</p></div></li></ul>
          <div class="qa-live-guide-limit"><QaIcon name="info" aria-hidden="true" /><div><h3>{{ $t('qaFaithfulLive.semanticTitle') }}</h3><p>{{ $t('qaFaithfulLive.semanticNote') }}</p></div></div>
        </template>
      </aside>
    </div>
    <div v-if="workbench" class="qa-live-footer" :class="{ 'qa-live-footer-with-result': job }"><div v-if="!job" class="qa-live-not-run" data-testid="qa-live-empty"><QaIcon name="pending" aria-hidden="true" /><strong>NOT RUN</strong><span>{{ $t('qaFaithfulLive.notRunNote') }}</span></div><button class="qa-live-resource-toggle" type="button" :aria-expanded="resourceOpen" aria-controls="qa-live-resource-details" @click="resourceOpen = !resourceOpen">{{ $t('qaFaithfulLive.resourceLink') }}<QaIcon name="north_east" aria-hidden="true" /></button></div>
    <section v-if="workbench" v-show="resourceOpen" id="qa-live-resource-details" class="qa-live-resource qa-panel" :aria-label="$t('qaLive.resourceLimits')"><h2>{{ $t('qaLive.resourceLimits') }}</h2><template v-if="capabilities"><p class="qa-small">{{ resourceLimits }}</p><p class="qa-small">{{ $t('qaLive.budgetNote', { n: ceiling }) }}</p><p v-if="capabilities.pricing" class="qa-small">{{ resourcePricing }}</p></template><button class="qa-button" type="button" :disabled="loading" @click="load"><QaIcon name="refresh" aria-hidden="true" />{{ $t('qaLive.refresh') }}</button></section>
    <section v-if="historyOpen || (!workbench && recent.length)" ref="historyElement" class="qa-live-history" tabindex="-1" data-testid="qa-live-history"><component :is="workbench ? 'h2' : 'span'">{{ $t('qaLive.history') }}</component><button v-for="entry in recent" :key="entry.id" class="qa-text-link" :class="{ 'qa-history-current': job?.id === entry.id }" :disabled="isLiveActive(job)" @click="show(entry.id)"><time v-if="entry.finished_at || entry.started_at" :datetime="entry.finished_at || entry.started_at">{{ timestamp(entry.finished_at || entry.started_at) }}</time><span>{{ $t('qaLive.profiles.' + entry.profile) }}</span><strong>{{ $t('qaLive.status.' + entry.status) }}</strong></button><p v-if="!recent.length" class="qa-small">{{ $t('qaFaithfulLive.emptyHistory') }}</p></section>
  </section>
</template>

<script setup>
import { qaDownloadPrefix } from '../lib/runtime.js';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import QaIcon from "./QaIcon.vue";
import QaExecutionLog from "./QaExecutionLog.vue";
import { logCaptureErrorKey } from "../lib/qaLogs.js";
import QaReleaseDecision from "./QaReleaseDecision.vue";
import QaSemanticReviewPanel from "./QaSemanticReviewPanel.vue";
import { AGENT } from "../lib/runtime.js";
import { apiFetch } from "../lib/qaSession.js";
import { isLiveActive as isRawLiveActive, validLiveBudget, validLiveCapabilities, validLiveEvaluationJob } from "../lib/qaLiveEvaluation.js";
import { getCaseSemanticReview, getSemanticReview, semanticReviewKey } from "../lib/qaSemanticReview.js";

defineProps({ workbench: { type: Boolean, default: false }, validationObservation: { type: Object, default: null } });
const emit = defineEmits(["status-change", "phase-change", "navigate", "observation-change"]);
const { locale, t } = useI18n();
const capabilities = ref(null), job = ref(null), error = ref(""), retryAfter = ref(0);
const archiveInput = ref(null), importing = ref(false), reviewImportError = ref(""), reviewSaved = ref(false);
const semanticReview = computed(() => getSemanticReview(job.value));
const caseReview = (entry) => getCaseSemanticReview(job.value, entry);
const caseReviewPassed = (entry) => Object.values(caseReview(entry)?.scores || {}).every(Boolean);
const missingJob = ref(false);
function isLiveActive(value) { return isRawLiveActive(value) && !(missingJob.value && value?.id === job.value?.id); }
const workspaceView = ref("settings");
const historyOpen = ref(false), historyElement = ref(null), resourceOpen = ref(false);
const executionLog = ref(null);
const profile = ref("quick"), budget = ref(1), acknowledged = ref(false);
const loading = ref(false), cancelling = ref(false), downloading = ref(false);
const reportDownload = ref(null);
const profiles = computed(() => capabilities.value?.profiles || []);
const recent = computed(() => capabilities.value?.recent || []);
const ceiling = computed(() => Math.min(5, capabilities.value?.max_budget_usd || 5));
const selectedProfile = computed(() => profiles.value.find((entry) => entry.id === profile.value));
const profileCounts = computed(() => profiles.value.filter((entry) => entry.id !== "quick").map((entry) => t(entry.id === "all" ? "qaFaithfulLive.allProfiles" : "qaLive.profiles." + entry.id) + " " + entry.case_count).join(" / "));
const budgetValid = computed(() => validLiveBudget(budget.value, ceiling.value));
const cannotStart = computed(() => !capabilities.value?.available || !selectedProfile.value || !budgetValid.value || !acknowledged.value || loading.value || capabilities.value.busy || isLiveActive(job.value) || retryAfter.value > 0);
const workspacePhase = computed(() => workspaceView.value === "settings" || !job.value ? "settings" : isLiveActive(job.value) ? "execution" : "evidence");
const stateTitleKey = computed(() => workspacePhase.value === "settings" ? "qaRunFlow.settings" : workspacePhase.value === "execution" ? "qaRunFlow.running" : "qaRunFlow.results");
watch(workspacePhase, (value) => emit("phase-change", value), { immediate: true });
const startReason = computed(() => {
  if (loading.value) return t("qaFlowLive.loading");
  if (isLiveActive(job.value)) return t("qaLive.settingsLocked");
  if (capabilities.value?.busy) return t("qaLive.busy");
  if (retryAfter.value > 0) return t("qaLive.cooldown", { n: retryAfter.value });
  if (!capabilities.value?.available) return t("qaLive.unavailable");
  if (!selectedProfile.value) return t("qaFlowLive.chooseProfile");
  if (!budgetValid.value) return t("qaFlowLive.invalidBudget", { n: ceiling.value });
  return t(acknowledged.value ? "qaFlowLive.ready" : "qaFlowLive.consentRequired");
});
const evidenceGuide = [
  { id: "answers", icon: "chat_bubble_outline" },
  { id: "traces", icon: "account_tree" },
  { id: "rules", icon: "fact_check" },
  { id: "usage", icon: "bar_chart" },
];
const summaryJob = computed(() => {
  if (isLiveActive(job.value)) return job.value;
  const active = recent.value.find(isLiveActive);
  if (active && active.id !== job.value?.id) return active;
  return recent.value[0]?.id === job.value?.id ? job.value : recent.value[0] || job.value;
});
watch(() => ({ status: summaryJob.value?.status || "not_run", tests: summaryJob.value?.completed_cases ?? null, active: isLiveActive(summaryJob.value), available: capabilities.value?.available === true, error: error.value || null }), (value) => emit("status-change", value), { immediate: true });
watch(() => ({ capabilities: capabilities.value, job: job.value, loading: loading.value, error: error.value }), (value) => emit("observation-change", JSON.parse(JSON.stringify(value))), { immediate: true, deep: true });
const number = (value) => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 2 }).format(value);
const money = (value) => new Intl.NumberFormat(locale.value, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(value);
const resourceLimits = computed(() => capabilities.value ? t("qaLive.limits", { model: capabilities.value.model, cases: selectedProfile.value?.case_count || 0, requests: selectedProfile.value?.max_requests || 0, tokens: number(capabilities.value.max_output_tokens), minutes: number(capabilities.value.deadline_seconds / 60) }) : "");
const resourcePricing = computed(() => capabilities.value?.pricing ? t(capabilities.value.pricing.source === "server_configuration" ? "qaLive.pricingConfigured" : "qaLive.pricing", { input: money(capabilities.value.pricing.input_per_million), output: money(capabilities.value.pricing.output_per_million), date: capabilities.value.pricing.verified_at }) : "");
const timestamp = (value) => new Intl.DateTimeFormat(locale.value, { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(value));
const base = `${AGENT}/qa/evaluations`, controller = new AbortController();
async function importEvidence(file, archive = false) {
  if (!file || loading.value || importing.value || capabilities.value?.busy || isLiveActive(job.value)) return;
  importing.value = true; loading.value = true; reviewImportError.value = ""; reviewSaved.value = false;
  const revision = ++observationRevision;
  let accepted = false;
  try {
    if (!Number.isFinite(file.size) || file.size > 20 * 1024 * 1024) throw new Error("file");
    let value;
    try { value = JSON.parse(await file.text()); } catch (_) { throw new Error("file"); }
    const source = value.review || value;
    const review = { report_sha256: source.report_sha256, reviewer_kind: source.reviewer_kind, reviewer: source.reviewer, reviewed_at: source.reviewed_at, reviews: source.reviews };
    if (archive && (value.version !== 1 || !value.job?.id || !value.report || !value.review)) throw new Error("file");
    const expectedId = archive ? value.job.id : job.value?.id;
    if (!expectedId) throw new Error("file");
    const result = await apiFetch(base + (archive ? "/import" : "/" + encodeURIComponent(expectedId) + "/review"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(archive ? { version: 1, job: value.job, report: value.report, review } : review), cache: "no-store", signal: controller.signal });
    if (!result.ok) throw new Error(result.status === 503 ? "storage" : "import");
    const body = await result.json();
    if (controller.signal.aborted || revision !== observationRevision) return;
    if (!validLiveEvaluationJob(body.job) || body.job.id !== expectedId || !getSemanticReview(body.job)) throw new Error("import");
    job.value = body.job; missingJob.value = false; observationRevision += 1;
    workspaceView.value = "evidence"; acknowledged.value = false; statusReadFailures = 0;
    reviewSaved.value = true; accepted = true;
  } catch (failure) {
    if (!controller.signal.aborted) reviewImportError.value = failure.message === "file" ? "qaSemanticReview.fileError" : failure.message === "storage" ? "qaSemanticReview.storageError" : "qaSemanticReview.importError";
  } finally { importing.value = false; loading.value = false; }
  if (accepted) await load();
}
async function importReview(file) { await importEvidence(file); }
async function selectArchive(event) {
  const file = event.target.files?.[0]; event.target.value = "";
  await importEvidence(file, true);
}
let pollTimer, cooldownTimer, initialized = false, statusReadFailures = 0, observationRevision = 0;
function clearReportDownload() {
  if (reportDownload.value) URL.revokeObjectURL(reportDownload.value.url);
  reportDownload.value = null;
}
watch(() => job.value?.id, clearReportDownload);
function cooldown(seconds) {
  clearInterval(cooldownTimer); retryAfter.value = Math.max(0, Math.ceil(Number(seconds) || 0));
  if (retryAfter.value) cooldownTimer = setInterval(() => { retryAfter.value = Math.max(0, retryAfter.value - 1); if (!retryAfter.value) { clearInterval(cooldownTimer); load(); } }, 1000);
}
function schedule() {
  clearTimeout(pollTimer);
  if (controller.signal.aborted || missingJob.value) return;
  const retryDelay = Math.min(8000, 1000 * 2 ** Math.max(0, Math.min(statusReadFailures - 1, 3)));
  if (isLiveActive(job.value)) pollTimer = setTimeout(poll, retryDelay);
  else if (capabilities.value?.busy) pollTimer = setTimeout(load, 2000);
}
async function response(path = "", init = {}) {
  const result = await apiFetch(base + path, { ...init, cache: "no-store", signal: init.signal || controller.signal });
  if (!result.ok) {
    if (result.status === 429) cooldown(result.headers?.get("Retry-After") || 300);
    throw new Error(result.status === 409 ? "busy" : result.status === 429 ? "cooldown" : result.status === 503 ? "unavailable" : result.status === 404 ? "missing" : "request");
  }
  return result;
}
async function read(path = "") {
  if (controller.signal.aborted) throw new DOMException("Cancelled", "AbortError");
  const readController = new AbortController(), abort = () => readController.abort();
  controller.signal.addEventListener("abort", abort, { once: true });
  let timer;
  try {
    return await Promise.race([
      (async () => (await response(path, { signal: readController.signal })).json())(),
      new Promise((_, reject) => { timer = setTimeout(() => { readController.abort(); reject(new Error("request")); }, 15000); }),
    ]);
  } finally { clearTimeout(timer); controller.signal.removeEventListener("abort", abort); readController.abort(); }
}
function failed(failure) { if (!controller.signal.aborted) error.value = ["busy", "cooldown", "unavailable", "missing"].includes(failure.message) ? failure.message : "request"; }
async function detail(id) {
  const revision = observationRevision;
  const value = await read("/" + encodeURIComponent(id));
  if (controller.signal.aborted || revision !== observationRevision) return false;
  if (!validLiveEvaluationJob(value.job) || value.job.id !== id) throw new Error("schema");
  if (job.value?.id === id && !isRawLiveActive(job.value) && isRawLiveActive(value.job)) return false;
  if (!job.value || job.value.id !== value.job.id) workspaceView.value = "evidence";
  job.value = value.job; missingJob.value = false; observationRevision += 1;
  return true;
}
async function load() {
  if (loading.value) return;
  const revision = observationRevision;
  loading.value = true; error.value = "";
  try {
    const value = await read();
    if (controller.signal.aborted || revision !== observationRevision) return;
    if (!validLiveCapabilities(value)) throw new Error("schema");
    capabilities.value = value; cooldown(value.retry_after_seconds);
    if (!initialized) { budget.value = value.default_budget_usd; if (!value.profiles.some((entry) => entry.id === profile.value)) profile.value = value.profiles[0].id; initialized = true; }
    const active = value.recent.find((entry) => entry.id === value.active_job_id && isLiveActive(entry));
    if (active) { if (!await detail(active.id)) { schedule(); return; } }
    else if (job.value && value.recent.some((entry) => entry.id === job.value.id)) { if (!await detail(job.value.id)) { schedule(); return; } }
    else if (!job.value && value.recent.length) { if (!await detail(value.recent[0].id)) return; }
    else if (missingJob.value) throw new Error("missing");
    statusReadFailures = 0; error.value = "";
    schedule();
  } catch (failure) { if (revision === observationRevision) { failed(failure); statusReadFailures += 1; schedule(); } } finally { loading.value = false; }
}
async function start() {
  if (cannotStart.value) return;
  loading.value = true; error.value = "";
  try {
    const value = await (await response("", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: profile.value, max_usd: budget.value, acknowledge_cost: true }) })).json();
    if (!validLiveEvaluationJob(value.job)) throw new Error("schema");
    job.value = value.job; missingJob.value = false; observationRevision += 1; statusReadFailures = 0; workspaceView.value = "evidence"; capabilities.value.busy = true; acknowledged.value = false; schedule();
  } catch (failure) { failed(failure); } finally { loading.value = false; }
}
async function poll() {
  if (!isLiveActive(job.value)) return;
  if (loading.value) { schedule(); return; }
  const revision = observationRevision;
  try {
    if (!await detail(job.value.id)) { schedule(); return; }
    statusReadFailures = 0; error.value = "";
    if (isLiveActive(job.value)) schedule(); else await load();
  } catch (failure) { if (revision === observationRevision) { failed(failure); if (failure.message === "missing") missingJob.value = true; statusReadFailures += 1; schedule(); } }
}
async function cancel() {
  if (!isLiveActive(job.value) || cancelling.value) return;
  cancelling.value = true; error.value = ""; observationRevision += 1;
  try {
    const value = await (await response("/" + encodeURIComponent(job.value.id) + "/cancel", { method: "POST" })).json();
    if (!validLiveEvaluationJob(value.job)) throw new Error("schema");
    job.value = value.job; observationRevision += 1; statusReadFailures = 0; if (isLiveActive(job.value)) schedule(); else await load();
  } catch (failure) { failed(failure); } finally { cancelling.value = false; }
}
async function show(id) {
  return showJob(id);
}
function prepareRun() {
  if (loading.value || isLiveActive(job.value)) return false;
  acknowledged.value = false;
  workspaceView.value = "settings";
  return true;
}
function startFree() { return false; }
async function openLogs() {
  if (!job.value) return false;
  workspaceView.value = "evidence"; await nextTick();
  if (!executionLog.value) return false;
  await executionLog.value.openStep(""); return true;
}
async function showJob(id, { logs = false } = {}) {
  if (loading.value || !/^[a-zA-Z0-9-]{1,64}$/.test(id) || (isLiveActive(job.value) && job.value.id !== id)) return false;
  observationRevision += 1; loading.value = true; error.value = "";
  try {
    if (!await detail(id)) return false;
    clearTimeout(pollTimer); statusReadFailures = 0; workspaceView.value = "evidence"; acknowledged.value = false; schedule();
    if (logs) await openLogs();
    return true;
  } catch (failure) { failed(failure); if (failure.message === "missing" && job.value?.id === id) missingJob.value = true; return false; }
  finally { loading.value = false; }
}
async function showHistory() {
  historyOpen.value = true;
  await nextTick();
  historyElement.value?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  historyElement.value?.focus({ preventScroll: true });
}
defineExpose({ showHistory, prepareRun, startFree, showJob, openLogs, refresh: load });
async function downloadReview() { await download("review"); }
async function download(kind = "report") {
  // Click handlers pass a MouseEvent; only the explicit review action selects a sidecar.
  const review = kind === "review";
  if (!job.value?.report_available || downloading.value) return;
  const jobId = job.value.id;
  downloading.value = true; error.value = "";
  clearReportDownload();
  try {
    const result = await response("/" + encodeURIComponent(jobId) + (review ? "/review" : "/report"));
    const report = await result.blob();
    if (controller.signal.aborted || job.value?.id !== jobId) return;
    const url = URL.createObjectURL(report), link = document.createElement("a");
    link.href = url; link.download = (review ? qaDownloadPrefix() + "-semantic-review-" : qaDownloadPrefix() + "-live-evaluation-") + jobId + ".json";
    reportDownload.value = { url, filename: link.download };
    document.body.append(link);
    try { link.click(); } finally { link.remove(); }
  } catch (failure) { clearReportDownload(); failed(failure); } finally { downloading.value = false; }
}
onMounted(load);
onBeforeUnmount(() => { controller.abort(); clearTimeout(pollTimer); clearInterval(cooldownTimer); clearReportDownload(); });
</script>

<style scoped>
.qa-live-archive-import { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin: 0 0 18px; }
.qa-live-archive-import .qa-button { gap: 7px; }
.qa-live-archive-import p { margin: 0; }
.qa-live-case-semantic { white-space: nowrap; }
.qa-live-purpose { margin: 16px 0 20px; border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 8px; background: var(--surface); }
.qa-live-purpose summary { display: flex; align-items: center; gap: 16px; min-height: 52px; box-sizing: border-box; padding: 14px 22px; list-style: none; cursor: pointer; }
.qa-live-purpose summary::-webkit-details-marker { display: none; }
.qa-live-purpose summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 6px; }
.qa-live-purpose-title { font: 600 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); }
.qa-live-purpose-summary { flex: 1; min-width: 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-purpose-toggle { flex: none; margin-left: auto; font-size: 24px; }
.qa-live-purpose[open] .qa-live-purpose-toggle { transform: rotate(180deg); }
.qa-live-purpose-content { padding: 0 22px 18px; }
.qa-live-purpose-intro { margin: 8px 0 16px; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-purpose dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; margin: 0; }
.qa-live-purpose dt { color: var(--ink); font-size: var(--qa-type-body); font-weight: 600; }
.qa-live-purpose dd { margin: 5px 0 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); overflow-wrap: anywhere; }
.qa-live-purpose-limit { margin: 15px 0 0; padding-top: 12px; border-top: 1px solid var(--border); color: var(--ink-2); font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-live-tag { border: 1px solid var(--border); border-radius: 5px; padding: 6px 9px; color: var(--ink-2); font-size: var(--qa-type-meta); white-space: nowrap; }
.qa-live-config { margin-top: 18px; }
.qa-live-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(170px, .7fr); gap: 20px; max-width: 720px; }
.qa-live-fields label { display: grid; gap: 9px; font-size: var(--qa-type-meta); }
.qa-live-fields select, .qa-live-fields input { width: 100%; box-sizing: border-box; color: var(--ink); background: var(--surface); border: 1px solid var(--border); border-radius: 5px; padding: 10px 12px; font: inherit; min-width: 0; }
.qa-live-fields input[aria-invalid="true"] { border-color: var(--accent); }
.qa-live-ack { display: flex; align-items: flex-start; gap: 9px; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); margin-top: 18px; }
.qa-live-ack input { flex-shrink: 0; margin-top: 5px; accent-color: var(--accent); }
.qa-live-limits { margin-top: 18px; }
.qa-live-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.qa-live-result { margin-top: 22px; }
.qa-live-result progress { width: 100%; height: 8px; accent-color: var(--accent); }
.qa-live-phase { font: var(--qa-type-code)/var(--qa-leading-body) var(--font-mono); overflow-wrap: anywhere; }
.qa-live-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin: 22px 0; }
.qa-live-metrics div { padding-bottom: 13px; border-bottom: 1px solid var(--border-2); }
.qa-live-metrics dt { font-size: var(--qa-type-meta); color: var(--ink-2); }
.qa-live-metrics dd { font-size: var(--qa-type-body); margin: 9px 0 0; overflow-wrap: anywhere; }
.qa-live-semantic { font-size: var(--qa-type-meta); font-weight: 600; }
.qa-live-cases { list-style: none; padding: 0; margin: 24px 0 0; }
.qa-live-cases > li { border-top: 1px solid var(--border-2); padding: 15px 0; }
.qa-live-cases summary { cursor: pointer; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); overflow-wrap: anywhere; }
.qa-live-cases summary strong { margin-left: 15px; color: var(--accent); font-size: var(--qa-type-meta); }
.qa-live-cases summary .qa-live-rule-failed { color: var(--ink); }
.qa-live-cases h4 { font-size: var(--qa-type-subsection-title); }
.qa-live-cases pre { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; font: var(--qa-type-code)/var(--qa-leading-body) var(--font-sans); max-height: 380px; overflow: auto; }
.qa-live-failures { padding-left: 20px; font-size: var(--qa-type-meta); overflow-wrap: anywhere; }
.qa-live-history { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 20px; font-size: var(--qa-type-meta); }
.qa-live-history button { text-align: left; }
.qa-live-actions a.qa-button { text-decoration: none; }
.qa-live-actions a.qa-button:hover { border-color: var(--accent); color: var(--accent); }
.qa-live-history button { display: flex; flex-wrap: wrap; gap: 8px; }
.qa-live-history strong { font-weight: 500; }
.qa-live-workbench { margin: 0; padding: 0; border: 0; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-small { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-testing-heading { align-items: flex-start; margin-bottom: 13px; }
.qa-live-workbench .qa-testing-heading > div { min-width: 0; }
.qa-live-workbench h1 { margin: 0; font: 600 var(--qa-type-page-title)/var(--qa-leading-title) var(--font-sans); letter-spacing: .01em; }
.qa-live-workbench .qa-testing-intro { margin: 8px 0 0; color: var(--ink); font: 400 var(--qa-type-lead)/var(--qa-leading-body) var(--font-sans); }
.qa-live-workbench .qa-live-layout { display: grid; grid-template-columns: minmax(0, 680fr) minmax(0, 519fr); align-items: stretch; gap: 20px; }
.qa-live-workbench .qa-live-left, .qa-live-workbench .qa-live-result, .qa-live-workbench .qa-live-guide { min-width: 0; margin: 0; padding: 20px 22px 16px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
.qa-live-workbench .qa-live-config { background: transparent; padding: 0; margin: 0; border: 0; box-shadow: none; }
.qa-live-workbench .qa-live-config-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 16px; margin-bottom: 17px; border-bottom: 1px solid var(--border); }
.qa-live-workbench .qa-live-config-heading h2, .qa-live-workbench .qa-live-guide h2 { margin: 0; font: 600 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); }
.qa-live-workbench .qa-live-locked { color: var(--ink-2); font-size: var(--qa-type-body); }
.qa-live-workbench .qa-live-fields { grid-template-columns: minmax(0, 1fr); gap: 17px; max-width: none; }
.qa-live-field { display: grid; gap: 9px; min-width: 0; }
.qa-live-fields .qa-live-field > label { display: block; }
.qa-live-workbench .qa-live-field > label { font-size: var(--qa-type-control); font-weight: 500; line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-fields input, .qa-live-workbench .qa-live-fields select, .qa-live-workbench .qa-live-model-shell { box-sizing: border-box; width: 100%; min-width: 0; height: 48px; border: 1px solid var(--border); border-radius: 5px; background: var(--surface-2); color: var(--ink); font: 400 var(--qa-type-control)/var(--qa-leading-body) var(--font-sans); }
.qa-live-workbench .qa-live-fields input, .qa-live-workbench .qa-live-fields select { padding: 8px 17px; }
.qa-live-workbench .qa-live-fields input[aria-invalid="true"] { border-color: var(--danger); }
.qa-live-workbench .qa-live-model-shell { display: flex; align-items: center; gap: 16px; padding: 0 15px 0 17px; }
.qa-live-workbench .qa-live-model { flex: 1; min-width: 0; overflow-wrap: anywhere; font: var(--qa-type-body)/var(--qa-leading-body) var(--font-mono); color: var(--ink-2); }
.qa-live-workbench .qa-live-fixed-model { display: inline-flex; flex: none; align-items: center; gap: 9px; white-space: nowrap; color: var(--ink-2); font-size: var(--qa-type-body); }
.qa-live-workbench .qa-live-fixed-model .qa-icon { font-size: 20px; }
.qa-live-workbench .qa-live-select-shell { position: relative; min-width: 0; }
.qa-live-workbench .qa-live-select-shell select { appearance: none; padding-right: 43px; }
.qa-live-workbench .qa-live-select-shell > .qa-icon { pointer-events: none; position: absolute; top: 12px; right: 13px; font-size: 24px; }
.qa-live-workbench .qa-live-fields :disabled { cursor: not-allowed; color: var(--ink-2); opacity: .8; }
.qa-live-workbench .qa-live-field-note { display: flex; align-items: center; gap: 12px; min-width: 0; margin: 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-field-note > span:first-child { flex: 1; min-width: 0; }
.qa-live-workbench .qa-live-field-note > .qa-icon { flex: none; font-size: 23px; }
.qa-live-workbench .qa-live-model-note { gap: 12px; font-size: var(--qa-type-body); }
.qa-live-workbench .qa-live-scope-chip, .qa-live-workbench .qa-live-paid-chip { flex: none; padding: 2px 12px; border: 1px solid var(--border); border-radius: 5px; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); white-space: nowrap; }
.qa-live-workbench .qa-live-scope-chip { background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 28%, transparent); color: var(--ink); }
.qa-live-workbench .qa-live-paid-chip { color: var(--warning, #d8b677); background: color-mix(in srgb, var(--warning, #d8b677) 8%, transparent); border-color: color-mix(in srgb, var(--warning, #d8b677) 33%, transparent); }
.qa-live-workbench .qa-live-ack { align-items: flex-start; gap: 14px; margin: 18px 3px 0; color: var(--ink); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); cursor: pointer; }
.qa-live-workbench .qa-live-ack input { appearance: none; flex: none; box-sizing: border-box; width: 24px; height: 24px; margin: 1px 0 0; border: 2px solid var(--ink-2); border-radius: 3px; background: var(--surface-2); cursor: inherit; }
.qa-live-workbench .qa-live-ack input:checked { appearance: auto; accent-color: var(--accent); }
.qa-live-workbench .qa-live-ack input:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-live-workbench .qa-live-ack small { display: block; margin-top: 5px; color: var(--ink-2); font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-start-actions { margin-top: 16px; }
.qa-live-workbench .qa-live-start-actions .qa-button { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr); align-items: center; gap: 0; width: 100%; min-height: 48px; padding: 8px 12px; border-radius: 8px; font-size: var(--qa-type-control); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-start-actions .qa-button:disabled { opacity: 1 !important; color: var(--ink); background: color-mix(in srgb, var(--accent) 25%, var(--surface-2)); border-color: var(--border); }
.qa-live-workbench .qa-live-start-reason { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding-left: 16px; border-left: 1px solid color-mix(in srgb, currentColor 30%, transparent); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-start-reason .qa-icon { flex: none; font-size: 18px; }
.qa-live-workbench .qa-live-guide { padding-bottom: 20px; }
.qa-live-workbench .qa-live-guide h2 { padding-bottom: 17px; border-bottom: 1px solid var(--border); }
.qa-live-workbench .qa-live-evidence-list { list-style: none; padding: 0; margin: 0; }
.qa-live-workbench .qa-live-evidence-list li { display: flex; align-items: center; gap: 34px; min-height: 88px; padding: 14px 0; border-bottom: 1px solid var(--border); }
.qa-live-workbench .qa-live-evidence-icon { display: grid; place-items: center; flex: none; width: 64px; height: 64px; border-radius: 50%; background: var(--accent-soft); color: var(--accent); }
.qa-live-workbench .qa-live-evidence-icon > .qa-icon { font-size: 36px; }
.qa-live-workbench .qa-live-guide h3 { margin: 0 0 3px; font: 500 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); }
.qa-live-workbench .qa-live-guide p { margin: 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); overflow-wrap: anywhere; }
.qa-live-workbench .qa-live-guide-limit { display: flex; align-items: flex-start; gap: 18px; margin-top: 21px; padding: 0 5px; }
.qa-live-workbench .qa-live-guide-limit > .qa-icon { flex: none; margin-top: 2px; font-size: 26px; color: var(--ink-2); }
.qa-live-workbench .qa-live-guide-limit h3 { font: 400 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); }
.qa-live-workbench .qa-live-guide-limit p { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-footer { display: flex; align-items: center; justify-content: space-between; gap: 18px; box-sizing: border-box; min-height: 56px; margin-top: 14px; padding: 7px 20px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
.qa-live-workbench .qa-live-not-run { display: flex; align-items: center; gap: 24px; min-width: 0; }
.qa-live-workbench .qa-live-not-run > .qa-icon { flex: none; color: var(--ink-3); font-size: 40px; }
.qa-live-workbench .qa-live-not-run strong { flex: none; font: 500 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); padding-right: 24px; border-right: 1px solid var(--border); }
.qa-live-workbench .qa-live-not-run > span { color: var(--ink-2); font-size: var(--qa-type-body); }
.qa-live-workbench .qa-live-resource-toggle { appearance: none; display: inline-flex; align-items: center; flex: none; gap: 9px; padding: 0; border: 0; background: transparent; color: var(--link, #a7dbe2); font: var(--qa-type-control)/var(--qa-leading-body) var(--font-sans); cursor: pointer; }
.qa-live-workbench .qa-live-resource-toggle > .qa-icon { font-size: 18px; }
.qa-live-workbench .qa-live-resource-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 5px; }
.qa-live-workbench .qa-live-footer-with-result { justify-content: flex-end; }
.qa-live-workbench .qa-live-resource { margin: 14px 0 0; padding: 24px 28px; border: 1px solid var(--border); border-radius: 8px; }
.qa-live-workbench .qa-live-resource h2, .qa-live-workbench .qa-live-history h2 { font: 500 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); margin: 0 0 14px; }
.qa-live-workbench .qa-live-resource p { color: var(--ink-2); }
.qa-live-workbench .qa-live-resource > .qa-button { display: inline-flex; align-items: center; gap: 9px; }
.qa-live-workbench .qa-live-history { display: block; padding: 24px 28px; margin-top: 20px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); scroll-margin-top: 30px; }
.qa-live-workbench .qa-live-history button { appearance: none; display: grid; grid-template-columns: minmax(160px, 1fr) minmax(100px, 1fr) auto; align-items: center; gap: 8px 12px; width: 100%; padding: 16px 0; border: 0; border-bottom: 1px solid var(--border); background: transparent; font: var(--qa-type-body)/var(--qa-leading-body) var(--font-sans); text-decoration: none; cursor: pointer; }
.qa-live-workbench .qa-live-history button:not(:disabled):hover { background: var(--surface-2); }
.qa-live-workbench .qa-live-history button time { color: var(--ink-2); }
.qa-live-workbench .qa-live-history button strong { color: var(--ink-2); text-align: right; }
.qa-live-workbench .qa-live-history button:disabled { opacity: .7; cursor: default; }
.qa-live-workbench .qa-live-view-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.qa-live-workbench .qa-live-view-actions .qa-button { display: inline-flex; align-items: center; gap: 10px; }
.qa-live-workbench .qa-live-tab-state { font: var(--qa-type-body)/var(--qa-leading-body) var(--font-mono); }
.qa-live-workbench .qa-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 18px; border-bottom: 1px solid var(--border); }
.qa-live-workbench .qa-panel-head h2 { font: 500 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); margin: 0; }
.qa-live-workbench .qa-live-result > .qa-small { color: var(--ink-2); }
.qa-live-workbench .qa-live-result progress { height: 12px; margin: 5px 0; }
.qa-live-workbench .qa-live-phase { color: var(--ink-2); margin: 12px 0 0; font-size: var(--qa-type-code); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-metrics { gap: 20px; padding: 22px 0 0; border-top: 1px solid var(--border); }
.qa-live-workbench .qa-live-metrics dt { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-metrics dd { margin-top: 8px; font: var(--qa-type-body)/var(--qa-leading-body) var(--font-mono); }
.qa-live-workbench .qa-live-cases-heading { font: 500 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); margin: 25px 0 17px; }
.qa-live-workbench .qa-live-cases { margin: 0; border-bottom: 1px solid var(--border); }
.qa-live-workbench .qa-live-cases > li { padding: 16px 0; }
.qa-live-workbench .qa-live-cases summary { display: grid; grid-template-columns: 27px minmax(0, 1fr) auto; align-items: start; gap: 10px; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-case-toggle { grid-column: 3; grid-row: 1 / 3; font-size: 24px; color: var(--ink-3); justify-self: end; }
.qa-live-workbench .qa-live-cases details[open] > summary .qa-live-case-toggle { transform: rotate(180deg); }
.qa-live-workbench .qa-live-cases summary > span:nth-child(2) { min-width: 0; }
.qa-live-workbench .qa-live-case-number { font: var(--qa-type-body)/var(--qa-leading-body) var(--font-mono); color: var(--ink-2); }
.qa-live-case-grades { display: inline-flex; flex-wrap: wrap; gap: 6px 16px; }
.qa-live-workbench .qa-live-case-grades { grid-column: 2; grid-row: 2; }
.qa-live-workbench .qa-live-cases summary strong { margin: 0; font-size: var(--qa-type-body); }
.qa-live-workbench .qa-live-cases summary .qa-live-rule-failed { color: var(--danger); }
.qa-live-workbench .qa-live-cases h4 { font-size: var(--qa-type-subsection-title); line-height: var(--qa-leading-title); }
.qa-live-workbench .qa-live-cases details > .qa-small, .qa-live-workbench .qa-live-failures { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-live-workbench .qa-live-cases pre { font: var(--qa-type-code)/var(--qa-leading-body) var(--font-sans); padding: 16px; background: var(--bg); border: 1px solid var(--border); border-radius: 5px; }
.qa-live-workbench .qa-live-review { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; padding: 16px; margin-top: 25px; border: 1px solid var(--border); border-radius: 5px; }
.qa-live-workbench .qa-live-review > div:first-child { flex: 1; min-width: 200px; }
.qa-live-workbench .qa-live-semantic { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); margin: 0; }
.qa-live-workbench .qa-live-review .qa-gap { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); color: var(--ink-2); margin: 7px 0 0; }
.qa-live-workbench .qa-live-review .qa-live-actions { margin: 0; }
.qa-live-workbench .qa-live-review .qa-button { color: var(--accent); }
.qa-live-workbench .qa-live-guide > .qa-button { display: flex; align-items: center; justify-content: center; gap: 9px; width: 100%; margin-top: 16px; min-height: 48px; font-size: var(--qa-type-control); }
.qa-live-workbench .qa-live-guide > .qa-small { margin: 22px 0; }
.qa-live-workbench .qa-live-evidence-layout .qa-live-guide-limit { display: block; margin-top: 28px; padding-top: 20px; border-top: 1px solid var(--border); }
.qa-live-workbench .qa-live-guide-limit p + p { margin-top: 10px; }
.qa-live-workbench .qa-button { font-size: var(--qa-type-control); }
@media (max-width: 1190px) {
  .qa-live-workbench .qa-live-layout { grid-template-columns: minmax(0, 1fr); }
  .qa-live-workbench .qa-live-guide { padding-bottom: 28px; }
  .qa-live-workbench .qa-live-evidence-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 28px; }
  .qa-live-workbench .qa-live-evidence-list li { gap: 20px; }
}
@media (max-width: 650px) {
  .qa-live-purpose summary { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 5px 12px; padding: 14px 16px; }
  .qa-live-purpose-summary { grid-column: 1; }
  .qa-live-purpose-toggle { grid-column: 2; grid-row: 1 / 3; }
  .qa-live-purpose-content { padding: 0 16px 16px; }
  .qa-live-purpose dl { grid-template-columns: minmax(0, 1fr); gap: 14px; }
  .qa-live-workbench h1 { font-size: var(--qa-type-page-title); }
  .qa-live-workbench .qa-testing-intro { font-size: var(--qa-type-lead); }
  .qa-live-workbench .qa-live-left, .qa-live-workbench .qa-live-result, .qa-live-workbench .qa-live-guide, .qa-live-workbench .qa-live-history, .qa-live-workbench .qa-live-resource { padding: 20px; }
  .qa-live-workbench .qa-live-config-heading h2, .qa-live-workbench .qa-live-guide h2 { font-size: var(--qa-type-section-title); }
  .qa-live-workbench .qa-live-model-note { flex-wrap: wrap; }
  .qa-live-workbench .qa-live-model-note > span:first-child { flex-basis: 100%; }
  .qa-live-workbench .qa-live-field-note { font-size: var(--qa-type-body); }
  .qa-live-workbench .qa-live-start-actions .qa-button { grid-template-columns: minmax(0, 1fr); gap: 6px; padding: 12px; }
  .qa-live-workbench .qa-live-start-reason { padding: 0; border: 0; }
  .qa-live-workbench .qa-live-evidence-list { grid-template-columns: minmax(0, 1fr); }
  .qa-live-workbench .qa-live-evidence-list li { gap: 22px; }
  .qa-live-workbench .qa-live-footer { flex-wrap: wrap; gap: 12px; padding: 12px 16px; }
  .qa-live-workbench .qa-live-not-run { flex-wrap: wrap; gap: 12px; }
  .qa-live-workbench .qa-live-not-run > span { flex-basis: 100%; }
  .qa-live-workbench .qa-live-not-run strong { border: 0; padding: 0; }
  .qa-live-workbench .qa-live-resource-toggle { margin-left: auto; }
  .qa-live-workbench .qa-live-history button { grid-template-columns: minmax(0, 1fr) auto; font-size: var(--qa-type-body); }
  .qa-live-workbench .qa-live-history button time { grid-column: 1 / -1; }
  .qa-live-workbench .qa-live-metrics, .qa-live-fields { grid-template-columns: minmax(0, 1fr); }
  .qa-live .qa-testing-heading { align-items: flex-start; flex-direction: column; }
}
</style>
