<template>
  <section class="qa-task-workbench" data-testid="qa-workbench" :aria-busy="Boolean(model.loading)">
    <header class="qt-header">
      <h1>{{ tr('title') }}</h1><span class="qt-environment" data-testid="wb-environment">{{ tr('environment') }}</span>
      <span class="qt-version">{{ tr('currentVersion') }} <code :title="sourceSha || undefined">{{ sourceSha ? sourceSha.slice(0, 7) : tr('unknownVersion') }}</code><button v-if="sourceSha" class="qt-icon-button" data-testid="wb-copy-version" :aria-label="tr('copyVersion')" @click="copySha(sourceSha)"><QaIcon name="content_copy" /></button></span>
      <span v-if="preview" class="qt-preview">{{ $t('qaWorkbench.release.preview') }}</span>
      <span class="wb-sr-only" role="status">{{ copyStatus }}</span>
    </header>
    <p v-if="model.errors?.length" class="qt-sync-error" role="alert">{{ tr('syncError') }}<button class="qa-text-link" @click="$emit('refresh')">{{ tr('reload') }}</button></p>
    <div class="qt-grid">
      <section class="qt-tasks qt-pane" :aria-label="tr('items')">
        <h2>{{ tr('items') }}</h2>
        <div class="qt-task-groups">
          <template v-for="(task, index) in tasks" :key="task.id">
            <p v-if="index === 0 || index === 2" class="qt-group-label">{{ tr(index === 0 ? 'freeGroup' : 'paidGroup') }}<QaIcon name="expand_less" /></p>
            <button class="qt-task" :class="{ selected: selectedMode === task.id }" :aria-pressed="selectedMode === task.id" :data-testid="'wb-task-' + task.id" @click="$emit('select', task.id)">
              <QaIcon :name="task.icon" /><span class="qt-task-number">{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ tr('tasks.' + task.id + '.title') }}</strong><span class="qt-status" :data-tone="tone(taskEntry(task.id).status)"><QaIcon :name="statusIcon(taskEntry(task.id).status)" />{{ statusText(taskEntry(task.id).status) }}</span>
            </button>
          </template>
        </div>
        <label class="qt-mobile-select">{{ tr('selectTask') }}<select :value="selectedMode" @change="$emit('select', $event.target.value)"><option v-for="task in tasks" :key="task.id" :value="task.id">{{ tr('tasks.' + task.id + '.title') }} · {{ statusText(taskEntry(task.id).status) }}</option></select></label>
        <p class="qt-footer"><QaIcon name="info" />{{ tr('selectionHint') }}</p>
      </section>

      <section class="qt-workspace qt-pane" aria-labelledby="qt-task-title">
        <header class="qt-task-heading"><h2 id="qt-task-title" tabindex="-1">{{ tr('tasks.' + selected.id + '.title') }}</h2><span class="qt-cost">{{ tr(selected.paid ? 'paid' : 'free') }}</span><span v-if="!selected.paid" class="qt-no-model">{{ tr('noModel') }}</span></header>
        <h3 class="qt-subtitle">{{ tr('tasks.' + selected.id + '.subtitle') }}</h3><p class="qt-description">{{ tr('tasks.' + selected.id + '.description') }}</p>
        <button v-if="detail" class="qa-text-link qt-back" data-testid="qa-return-workbench" @click="$emit('overview')"><QaIcon name="arrow_back" />{{ tr('backOverview') }}</button>
        <div v-show="!detail" class="qt-overview">
          <section class="qt-before"><h3>{{ tr('before') }}</h3><ul><li><QaIcon :name="available === true ? 'check_circle_filled' : 'info'" />{{ tr(available === true ? 'available' : available === false ? 'unavailable' : 'environmentPending') }}</li><li><QaIcon :name="model.busy ? 'pending' : 'check_circle_filled'" />{{ tr(model.busy ? 'busy' : 'idle') }}</li><li><QaIcon name="info" />{{ tr('scopeHint') }}</li></ul><div class="qt-start-row"><button class="qa-button qa-primary" data-testid="wb-configure" :disabled="Boolean(model.loading || model.busy)" @click="$emit('optional', selected.id)"><QaIcon name="play_arrow" />{{ tr('configure') }}</button><p>{{ tr('explicitStart') }}</p></div><details class="qt-plan-details"><summary>{{ tr('planDetails') }}<QaIcon name="chevron_right" /></summary><p>{{ $t('qaFlow.tasks.' + selected.id + '.scope') }}</p><p>{{ $t('qaFlow.tasks.' + selected.id + '.limit') }}</p><p v-if="selected.id === 'real_es_llm_e2e'">{{ $t('qaCorpus.smokeLimit') }}</p></details></section>
          <section class="qt-latest">
            <div class="qt-section-title"><h3>{{ tr('latest') }}</h3><span class="qt-status" :data-tone="tone(current.status)">{{ statusText(current.status) }}</span><button class="qa-text-link" @click="$emit('history')">{{ tr('history') }}<QaIcon name="chevron_right" /></button></div>
            <template v-if="current.job"><p v-if="current.partial" class="qt-warning">{{ tr('partialHint') }}</p><p v-if="current.status === 'STALE'" class="qt-warning" data-testid="wb-evidence-stale">{{ tr('staleHint') }}</p><p class="qt-evidence-version">{{ tr('runVersion') }} <code>{{ runSha ? runSha.slice(0, 7) : tr('unknownVersion') }}</code><button v-if="runSha" class="qt-icon-button" data-testid="wb-copy-evidence-version" :aria-label="tr('copyRunVersion')" @click="copySha(runSha)"><QaIcon name="content_copy" /></button></p><dl v-if="current.family !== 'corpus-evaluations'" class="qt-counts"><div v-for="key in metrics" :key="key"><dt>{{ metricLabels[key] }}</dt><dd :data-testid="'wb-count-' + key">{{ measured(current.counts?.[key]) }}</dd></div></dl><p v-else>{{ $t('qaCorpus.historyMeasurement') }}</p><p v-if="!current.counts && current.family !== 'corpus-evaluations'">{{ tr('unmeasured') }}</p><button class="qa-text-link" data-testid="wb-evidence" :disabled="Boolean(model.loading)" :aria-label="tr('evidenceAccessible')" @click="$emit('evidence', current)">{{ tr('evidence') }}<QaIcon name="chevron_right" /></button></template>
            <div v-else data-testid="wb-empty-evidence"><p>{{ tr('noEvidence') }}</p><p>{{ tr('evidenceHint') }}</p></div>
          </section>
          <section class="qt-plan"><h3>{{ tr('plan') }}</h3><ol><li v-for="index in 3" :key="index"><span>{{ index }}</span><div><strong>{{ $t('qaFaithfulFlow.scopes.' + selected.id + '.' + (index - 1) + '.title') }}</strong><p>{{ $t('qaFaithfulFlow.scopes.' + selected.id + '.' + (index - 1) + '.body') }}</p></div></li></ol></section>
        </div>
        <!-- Keep controller components mounted while another task is selected. -->
        <div v-show="detail" class="qt-detail"><slot /></div>
      </section>

      <aside class="qt-summary qt-pane" :aria-label="tr('summary')">
        <button class="qt-summary-toggle" :aria-expanded="summaryOpen" @click="summaryOpen = !summaryOpen">{{ tr('summary') }}<QaIcon :name="summaryOpen ? 'expand_less' : 'expand_more'" /></button><h2>{{ tr('summary') }}</h2>
        <div class="qt-summary-content" :class="{ open: summaryOpen }">
          <section class="qt-readiness" :data-tone="hasFailures ? 'danger' : 'warning'"><QaIcon :name="hasFailures ? 'error_filled' : 'info'" /><div><h3 data-testid="wb-readiness-title">{{ tr(model.loading ? 'loading' : model.errors?.length || model.readiness === 'unknown' || !sourceSha ? 'unknown' : hasFailures ? 'blocked' : 'incomplete') }}</h3><p>{{ tr('qualitySeparate') }}</p></div></section>
          <section class="qt-status-list"><h3>{{ tr('currentEvidence') }}</h3><div v-for="task in summaryTasks" :key="task.id"><QaIcon :name="task.icon" /><strong>{{ tr('tasks.' + task.id + '.title') }}</strong><span class="qt-status" :data-tone="tone(taskEntry(task.id).status)"><QaIcon :name="statusIcon(taskEntry(task.id).status)" />{{ statusText(taskEntry(task.id).status) }}</span></div></section>
          <section class="qt-next"><h3>{{ tr('next') }}</h3><button class="qt-next-button" data-testid="wb-primary" :disabled="!actionEnabled" @click="onPrimary"><QaIcon name="arrow_forward" /><span><strong>{{ nextLabel }}</strong><small>{{ tr('nextHint') }}</small></span></button><p v-if="model.retryAfterSeconds" class="qt-warning">{{ $t('qaWorkbench.release.reason.cooldown', { seconds: model.retryAfterSeconds }) }}</p></section>
          <section class="qt-follow"><h3>{{ tr('follow') }}</h3><button class="qa-button" data-testid="wb-configure-model" @click="openTaskEvidence('model_evaluation')"><QaIcon name="bar_chart" />{{ tr('modelResult') }}<QaIcon name="chevron_right" /></button><button class="qa-button" data-testid="wb-configure-corpus" @click="openTaskEvidence('real_corpus_quality')"><QaIcon name="manage_search" />{{ tr('corpusResult') }}<QaIcon name="chevron_right" /></button></section>
          <p class="qt-footer"><QaIcon name="info" />{{ tr('footer') }}</p>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import QaIcon from './QaIcon.vue';
import { WORKBENCH_TASKS, workbenchTaskEntry, workbenchStatusTone, validWorkbenchSha } from '../lib/qaTaskWorkbench.js';
const props = defineProps({ model: { type: Object, required: true }, selectedMode: { type: String, default: 'es_integration' }, detail: Boolean, preview: Boolean, availability: { type: Object, default: () => ({}) } });
const emit = defineEmits(['select', 'optional', 'overview', 'primary', 'evidence', 'history', 'refresh']);
const { t, locale } = useI18n();
const tr = (key, values) => t('qaTaskWorkbench.' + key, values || {});
const tasks = WORKBENCH_TASKS, summaryTasks = tasks.filter(task => task.id !== 'real_es_llm_e2e');
const metrics = ['passed', 'failed', 'errors', 'skipped'], metricLabels = { passed: 'PASS', failed: 'FAIL', errors: 'ERROR', skipped: 'SKIP' };
const sourceSha = computed(() => validWorkbenchSha(props.model.sourceSha));
const selected = computed(() => tasks.find(task => task.id === props.selectedMode) || tasks[1]);
const taskEntry = mode => workbenchTaskEntry(props.model, mode);
const current = computed(() => taskEntry(selected.value.id));
const runSha = computed(() => validWorkbenchSha(current.value.job?.source_sha || current.value.sourceSha));
const available = computed(() => props.availability[selected.value.id]);
const tone = workbenchStatusTone;
const statusText = status => ['STRUCTURAL', 'PARTIAL'].includes(status) ? tr('statuses.' + status) : status;
const statusIcon = status => ['PASS', 'STRUCTURAL'].includes(status) ? 'check_circle_filled' : ['RUNNING', 'QUEUED'].includes(status) ? 'progress_activity' : ['FAIL', 'ERROR'].includes(status) ? 'error_filled' : 'remove_circle';
const measured = value => Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString(locale.value) : '—';
const hasFailures = computed(() => tasks.some(task => ['FAIL', 'ERROR'].includes(taskEntry(task.id).status)));
const summaryOpen = ref(false), copyStatus = ref('');
const qualityTask = computed(() => {
  if (props.model.readiness !== 'ready' || props.model.busy || props.model.errors?.length) return null;
  const model = taskEntry('model_evaluation'), corpus = taskEntry('real_corpus_quality');
  return !['PASS', 'STRUCTURAL'].includes(model.status) ? model : corpus.status !== 'PASS' ? corpus : model;
});
const action = computed(() => props.model.nextAction);
const actionEnabled = computed(() => !props.model.loading && Boolean(qualityTask.value || (action.value && !action.value.disabled && (action.value.kind === 'start' ? ['offline_regression', 'es_integration'].includes(action.value.mode) : ['resume', 'details', 'reload'].includes(action.value.kind)))));
const nextLabel = computed(() => qualityTask.value ? qualityTask.value.job ? tr(qualityTask.value.mode === 'model_evaluation' ? 'modelResult' : 'corpusResult') : tr('configureNamed', { name: tr('tasks.' + qualityTask.value.mode + '.title') }) : !action.value ? tr('waiting') : action.value.kind === 'reload' ? tr('reload') : action.value.kind === 'resume' ? tr('resume') : action.value.kind === 'details' ? tr('evidence') : tr('configureNamed', { name: tr('tasks.' + action.value.mode + '.title') }));
function onPrimary() {
  if (!actionEnabled.value) return;
  if (qualityTask.value) { if (qualityTask.value.job) emit('evidence', qualityTask.value); else emit('optional', qualityTask.value.mode); }
  else emit('primary', action.value);
}
function openTaskEvidence(mode) { const entry = taskEntry(mode); if (entry.job) emit('evidence', entry); else emit('select', mode); }
async function copySha(value) { const sha = validWorkbenchSha(value); if (!sha) return; try { await navigator.clipboard.writeText(sha); copyStatus.value = tr('copied'); } catch { copyStatus.value = tr('copyFailed'); } }
</script>
