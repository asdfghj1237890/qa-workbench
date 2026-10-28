<template>
  <div class="ns qa-page qa-workbench qa-release-shell" :data-mode="dark ? 'dark' : 'light'" data-font="workbench" :data-flow-view="activeView" :data-flow-task="currentTask" :data-flow-phase="currentPhase" data-context-header="false" @keydown.esc="closeNavigation">
    <header class="qa-mobile-bar">
      <router-link to="/" class="qa-brand" :aria-label="branding.name"><img :src="brandMark" alt="" /><span>{{ branding.name }}<span class="qa-accent">.</span></span></router-link>
      <button ref="menuButton" class="qa-icon-button" :aria-label="$t('qaWorkbench.navigation')" :aria-expanded="navigationOpen" aria-controls="qa-navigation" @click="navigationOpen = !navigationOpen"><QaIcon aria-hidden="true" name="menu" /></button>
    </header>
    <button v-if="navigationOpen" class="qa-navigation-scrim" :aria-label="$t('qaWorkbench.closeNavigation')" @click="closeNavigation"></button>
    <aside id="qa-navigation" class="qa-sidebar" :class="{ 'is-open': navigationOpen }">
      <router-link to="/" class="qa-brand" :aria-label="branding.name"><img :src="brandMark" alt="" /><span>{{ branding.name }}<span class="qa-accent">.</span></span></router-link>
      <nav class="qa-navigation" :aria-label="$t('qaWorkbench.navigation')">
        <button data-testid="qa-nav-verification" :aria-current="activeView === 'verification' || taskView ? 'page' : undefined" @click="selectView('verification')"><QaIcon aria-hidden="true" name="fact_check" /><span>{{ $t('qaWorkbench.shell.workbench') }}</span><span v-if="workbenchModel.busy" class="qa-nav-running" :aria-label="$t('qaFlow.activeNotice')"><QaIcon name="pending" aria-hidden="true" /></span></button>
        <button data-testid="qa-nav-health" :aria-current="activeView === 'health' ? 'page' : undefined" @click="selectView('health')"><QaIcon aria-hidden="true" name="monitor_heart" /><span>{{ $t('qaHealth.title') }}</span></button>
        <button data-testid="qa-nav-history" :aria-current="activeView === 'history' ? 'page' : undefined" @click="openExecutionHistory"><QaIcon name="history" aria-hidden="true" /><span>{{ $t('qaFaithfulShell.history') }}</span></button>
        <button data-testid="qa-nav-data" :aria-current="dataView ? 'page' : undefined" @click="selectView('overview')"><QaIcon aria-hidden="true" name="manage_search" /><span>{{ $t('qaWorkbench.shell.data') }}</span></button>
      </nav>
      <div class="qa-sidebar-bottom">
        <details class="qa-account-menu">
          <summary :aria-label="$t('qaFaithfulShell.account')"><QaIcon name="language" aria-hidden="true" /></summary>
          <div><span v-if="canLogout">{{ accountEmail }}</span><router-link to="/">{{ $t('observatory.back') }}</router-link><router-link to="/workbench">QA Workbench</router-link><a :href="repository" target="_blank" rel="noopener noreferrer">GitHub</a><button v-if="canLogout" class="qa-button" @click="logout">{{ $t('qa.logout') }}</button></div>
        </details>
        <div class="qa-preferences">
          <div class="seg-ctl" role="group" :aria-label="$t('side.language')"><button :class="{ on: locale === 'zh-TW' }" :aria-pressed="locale === 'zh-TW'" @click="setLanguage('zh-TW')">中文</button><button :class="{ on: locale === 'en' }" :aria-pressed="locale === 'en'" @click="setLanguage('en')">EN</button></div>
          <button class="qa-icon-button" :aria-label="$t('app.darkToggle')" :aria-pressed="dark" @click="toggleDark"><QaIcon aria-hidden="true" name="contrast" /></button>
        </div>
      </div>
    </aside>

    <main ref="workspace" class="scroll qa-scroll qa-workspace" tabindex="-1" :inert="navigationOpen || undefined" :aria-busy="activeView === 'health' ? false : dataView ? loading : workbenchModel.loading">
      <div class="qa-wrap">
        <QaHealthWorkspace v-if="activeView === 'health'" :dark="dark" :preview="QA_DESIGN_PREVIEW" />
        <QaWorkbench v-show="activeView === 'verification' || taskView" :model="workbenchModel" :selected-mode="workbenchTask" :detail="taskView" :availability="workbenchAvailability" :preview="QA_DESIGN_PREVIEW" @select="selectWorkbenchTask" @overview="selectView('verification')" @history="openExecutionHistory" @primary="runPrimaryAction" @evidence="showEvidence($event)" @optional="navigateTask" @refresh="reloadWorkbench">
          <div v-show="activeView === 'validation'" data-testid="qa-validation-workspace"><QaValidationPanel ref="validationPanel" workbench :requested-mode="requestedMode" @mode-change="syncValidationMode" @navigate="navigateTask" @phase-change="validationPhase = $event" @status-change="validationSummary = $event" @observation-change="validationObservation = $event" /></div>
          <div v-show="activeView === 'live'" data-testid="qa-live-workspace"><QaLiveEvaluationPanel ref="livePanel" workbench :validation-observation="validationObservation" @navigate="navigateTask" @phase-change="livePhase = $event" @status-change="liveSummary = $event" @observation-change="evaluationObservation = $event" /></div>
          <div v-show="activeView === 'corpus'" data-testid="qa-corpus-workspace"><QaCorpusEvaluationPanel ref="corpusPanel" @phase-change="corpusPhase = $event" @observation-change="corpusObservation = $event" /></div>
        </QaWorkbench>
        <QaExecutionHistory v-show="activeView === 'history'" :entries="workbenchModel.history" :loading="workbenchModel.loading" :error="workbenchModel.errors.length ? 'sync_error' : null" @select="showEvidence($event)" @logs="showEvidence($event, true)" @refresh="reloadWorkbench" />
        <p v-if="navigationError" class="qa-state qa-error" role="alert">{{ $t('qaWorkbench.shell.activeHistory') }}</p>
        <div v-show="dataView" class="qa-release-data-tabs" role="group" :aria-label="$t('qaWorkbench.shell.data')"><button v-for="item in dataViews" :key="item.id" class="qa-button" :data-testid="'qa-nav-' + item.id" :aria-pressed="activeView === item.id" @click="selectView(item.id)"><QaIcon aria-hidden="true" :name="item.icon" />{{ $t('qaWorkbench.' + item.id) }}</button></div>
        <header v-show="dataView" class="qa-workbench-heading">
          <h1 id="qa-title" tabindex="-1">{{ $t('qaWorkbench.' + (dataView ? activeView : 'overview')) }}</h1>
          <div class="qa-heading-actions"><time v-if="snapshot" :datetime="snapshot.generated_at">{{ generatedAt }}</time><button class="qa-button qa-primary" :disabled="loading" @click="loadSnapshot">{{ $t(loading ? 'observatory.loading' : 'observatory.refresh') }}<QaIcon aria-hidden="true" name="refresh" /></button></div>
        </header>

        <div v-show="dataView">
          <div v-if="loading && !snapshot" class="qa-state" role="status">{{ $t('observatory.loading') }}</div>
          <div v-if="error" class="qa-state qa-error" role="alert"><div><strong>{{ $t(error === 'unavailable' ? 'observatory.unavailable' : 'observatory.error') }}</strong><p>{{ $t(error === 'unavailable' ? 'observatory.unavailableHint' : 'observatory.errorHint') }}</p></div><button class="qa-button" :disabled="loading" @click="loadSnapshot">{{ $t('observatory.retry') }}</button></div>
          <template v-if="snapshot">
            <div v-if="snapshot.status === 'stale'" class="qa-state qa-stale" role="status"><strong>{{ $t('observatory.stale') }}</strong><span>{{ staleDetail }}</span></div>

            <section v-show="activeView === 'overview'" class="qa-overview" aria-labelledby="qa-title" data-testid="qa-overview">
              <div class="qa-context-line"><span>{{ $t('observatory.schedule') }}</span><span><code>{{ snapshot.index }}</code> · {{ snapshot.embedding.model }} · {{ $t('observatory.dimensions', { n: number(snapshot.embedding.dimensions) }) }}</span></div>
              <div class="qa-stats">
                <article class="qa-stat"><QaIcon class="qa-stat-icon" aria-hidden="true" name="description" /><div><span>{{ $t('qaWorkbench.documents') }}</span><strong data-testid="qa-total">{{ number(snapshot.total) }}</strong></div></article>
                <article class="qa-stat"><QaIcon class="qa-stat-icon" aria-hidden="true" name="database" /><div><span>Embedding</span><strong data-testid="qa-vectors">{{ number(snapshot.embedding.count) }}</strong></div></article>
                <article class="qa-stat"><QaIcon class="qa-stat-icon" aria-hidden="true" name="check_circle" /><div><span>{{ $t('observatory.coverage') }}</span><strong>{{ percentage(snapshot.embedding.coverage) }}</strong></div></article>
                <article class="qa-stat"><QaIcon class="qa-stat-icon" aria-hidden="true" name="description" /><div><span>{{ $t('qaWorkbench.missing') }}</span><strong>{{ number(snapshot.embedding.missing) }}</strong></div></article>
              </div>
              <div class="qa-overview-grid">
                <section v-for="group in distributionGroups" :key="group.id" class="qa-panel qa-distribution" :aria-labelledby="'qa-' + group.id">
                  <div class="qa-panel-head"><h2 :id="'qa-' + group.id">{{ $t('observatory.' + group.id) }}</h2><span class="qa-count-label">{{ $t('observatory.fullCorpus') }}</span></div>
                  <p class="qa-small">{{ $t('observatory.distributionNote', { total: number(snapshot.total) }) }}</p>
                  <div v-if="!group.rows.length" class="qa-empty-inline">{{ $t('observatory.noDistribution') }}</div>
                  <ol v-else class="qa-workbench-bars"><li v-for="row in group.rows" :key="row.name"><span class="qa-distribution-name"><i v-if="group.id === 'categories'" :style="{ background: qaCategoryColor(row.name) }" aria-hidden="true"></i>{{ group.id === 'categories' ? categoryLabel(row.name) : groupLabel(row.name) }}</span><b>{{ number(row.count) }}</b><div class="qa-bar-track" aria-hidden="true"><div :style="{ width: `${Math.min(100, snapshot.total ? row.count / snapshot.total * 100 : 0)}%`, background: group.id === 'categories' ? qaCategoryColor(row.name) : undefined }"></div></div><small>{{ percentage(snapshot.total ? row.count / snapshot.total : 0) }}</small></li></ol>
                  <div v-if="group.id === 'sources'" class="qa-sample-summary"><h3>{{ $t('qaWorkbench.sample') }} <span>{{ number(snapshot.projection.sample_size) }} / {{ number(snapshot.projection.population) }} · {{ sampleRatio }}</span></h3><p>{{ $t('qaWorkbench.sampleHint') }}</p><button class="qa-button qa-primary" @click="selectView('vectors')"><QaIcon aria-hidden="true" name="scatter_plot" />{{ $t('qaWorkbench.exploreVectors') }}</button></div>
                </section>
              </div>
            </section>

            <section v-show="activeView === 'vectors'" class="qa-vectors" aria-labelledby="qa-title" data-testid="qa-vector-workspace">
              <div class="qa-context-line qa-vector-context"><span>{{ $t('qaWorkbench.documents') }} <b>{{ number(snapshot.total) }}</b> · Embedding <b>{{ number(snapshot.embedding.count) }}</b> · {{ $t('observatory.coverage') }} <b>{{ percentage(snapshot.embedding.coverage) }}</b> · {{ $t('qaWorkbench.sample') }} <b>{{ number(snapshot.projection.sample_size) }} / {{ number(snapshot.projection.population) }} · {{ sampleRatio }}</b></span><span>UMAP · cosine · seed {{ snapshot.projection.seed }}</span></div>
              <div class="qa-vector-grid">
                <section class="qa-panel qa-vector-canvas" aria-labelledby="qa-projection-title">
                  <h2 id="qa-projection-title" class="qa-sr-only">{{ $t('observatory.projection') }}</h2>
                  <div class="qa-vector-mode"><div class="seg-ctl qa-color-controls" role="group" :aria-label="$t('observatory.colorBy')"><button :class="{ on: colorBy === 'category' }" :aria-pressed="colorBy === 'category'" @click="setColorBy('category')">{{ $t('observatory.byCategory') }}</button><button :class="{ on: colorBy === 'site' }" :aria-pressed="colorBy === 'site'" @click="setColorBy('site')">{{ $t('observatory.bySource') }}</button></div><span class="qa-count-label">{{ $t(snapshot.projection.dimensions === 3 ? 'qaWorkbench.threeDimensions' : 'qaWorkbench.twoDimensions') }}</span></div>
                  <div v-if="snapshot.total === 0" class="qa-state qa-empty" role="status">{{ $t('observatory.emptyIndex') }}</div>
                  <div v-else-if="snapshot.projection.status !== 'ok' || !points.length" class="qa-state qa-empty" role="status">{{ $t('observatory.insufficient') }}</div>
                  <QaProjection v-else workbench :points="visiblePoints" :dimensions="snapshot.projection.dimensions || 2" :color-by="colorBy" :color-for="colorFor" :group-label="plotGroupLabel" :reset-key="snapshot" :description="$t('observatory.scatterDescription', { n: number(visiblePoints.length), total: number(snapshot.projection.population) })" @selection-change="selectedPoint = $event" />
                  <p class="qa-visible" aria-live="polite">{{ $t('observatory.visible', { n: number(visiblePoints.length), total: number(points.length) }) }}</p>
                </section>

                <aside class="qa-panel qa-inspector" :aria-label="$t('qaWorkbench.inspector')">
                  <div class="seg-ctl qa-inspector-tabs" role="group" :aria-label="$t('qaWorkbench.inspector')"><button :class="{ on: inspectorTab === 'legend' }" :aria-pressed="inspectorTab === 'legend'" @click="inspectorTab = 'legend'">{{ $t('qaWorkbench.sampleLegend') }}</button><button :class="{ on: inspectorTab === 'corpus' }" :aria-pressed="inspectorTab === 'corpus'" @click="inspectorTab = 'corpus'">{{ $t('observatory.fullCorpus') }}</button></div>
                  <div v-if="inspectorTab === 'legend'">
                    <h2 class="qa-inspector-title">{{ $t('qaWorkbench.sampleLegend') }}</h2>
                    <div class="qa-legend" role="group" :aria-label="$t('observatory.legend')"><button v-for="series in legend" :key="series.name" class="qa-legend-item" :aria-pressed="!hidden.has(series.name)" @click="toggleSeries(series.name)"><QaIcon class="qa-series-check" aria-hidden="true" :name="hidden.has(series.name) ? 'check_box_outline_blank' : 'check_box'" /><i :style="{ background: colorFor(series.name) }" aria-hidden="true"></i><span>{{ plotGroupLabel(series.name) }}</span><b>{{ number(series.count) }}</b></button></div>
                    <p class="qa-inspector-note">{{ $t('qaWorkbench.legendHint') }}</p>
                  </div>
                  <div v-else class="qa-inspector-corpus"><h2 class="qa-inspector-title">{{ $t('observatory.fullCorpus') }}</h2><p class="qa-inspector-note">{{ $t('observatory.distributionNote', { total: number(snapshot.total) }) }}</p><section v-for="group in distributionGroups" :key="group.id"><h3>{{ $t('observatory.' + group.id) }}</h3><dl><div v-for="row in group.rows" :key="row.name"><dt>{{ group.id === 'categories' ? categoryLabel(row.name) : groupLabel(row.name) }}</dt><dd>{{ number(row.count) }}<small>{{ percentage(snapshot.total ? row.count / snapshot.total : 0) }}</small></dd></div></dl></section></div>
                  <div class="qa-inspector-section"><h3>{{ $t('observatory.plot.labels') }}</h3><p>{{ $t('qaWorkbench.regionHint') }}</p><details><summary>{{ $t('qaWorkbench.projectionDetails') }}</summary><p>{{ $t('observatory.projectionNote') }}</p></details></div>
                  <div class="qa-inspector-section qa-selected-point" aria-live="polite"><h3>{{ $t('observatory.plot.selected') }}</h3><template v-if="selectedPoint"><strong>{{ selectedPoint.title || $t('observatory.plot.articleTitleUnavailable') }}</strong><p>{{ categoryLabel(selectedPoint.category) }} · {{ groupLabel(selectedPoint.site) }}</p></template><p v-else><QaIcon aria-hidden="true" name="ads_click" />{{ $t('qaWorkbench.selectPoint') }}</p></div>
                </aside>
              </div>
            </section>
          </template>

          <section class="qa-run-summary" :aria-label="$t('qaWorkbench.executionStatus')">
            <h2>{{ $t('qaWorkbench.executionStatus') }}</h2>
            <div class="qa-run-summary-item" :class="{ 'qa-summary-error': validationSummary.error }"><QaIcon aria-hidden="true" :name="validationSummary.error ? 'cloud_off' : validationSummary.mode === 'offline_regression' && validationSummary.status === 'completed' ? 'check_circle' : 'fact_check'" /><div><small>{{ $t('qaWorkbench.validation') }}</small><strong>{{ validationSummary.error ? $t('qaWorkbench.statusReadError') : validationSummaryLabel }}</strong><small v-if="validationSummary.error">{{ $t('qaWorkbench.lastKnownStatus', { status: validationSummaryLabel }) }}</small><span v-else-if="validationSummary.tests !== null" class="qa-run-count">{{ $t('qaWorkbench.tests', { n: number(validationSummary.tests) }) }}</span></div></div>
            <div class="qa-run-summary-item" :class="{ 'qa-summary-error': liveSummary.error }"><QaIcon aria-hidden="true" :name="liveSummary.error ? 'cloud_off' : 'smart_toy'" /><div><small>{{ $t('qaWorkbench.live') }}</small><strong>{{ liveSummary.error ? $t('qaWorkbench.statusReadError') : liveSummaryLabel }}</strong><small v-if="liveSummary.error">{{ $t('qaWorkbench.lastKnownStatus', { status: liveSummaryLabel }) }}</small><span class="qa-semantic-pending">{{ $t('qaWorkbench.qualityPending') }}</span></div></div>
            <button class="qa-button" @click="selectView(validationSummary.active ? 'validation' : liveSummary.active ? 'live' : 'validation')">{{ $t('qaWorkbench.viewValidation') }}<QaIcon aria-hidden="true" name="arrow_forward" /></button>
          </section>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import QaIcon from "../components/QaIcon.vue";
import { getQaAdapter } from "../lib/runtime.js";
const branding = getQaAdapter().branding, brandMark = branding.mark;
import { AGENT, QA_DESIGN_PREVIEW } from "../lib/runtime.js";
import { apiFetch } from "../lib/qaSession.js";
import { QA_REPOSITORY, projectedPoints, validQaSnapshot } from "../lib/qa.js";
import { qaCategoryColor, qaCategoryDistribution, qaCategoryGroup, qaCategoryLabelKey } from "../lib/qaCategories.js";
import QaProjection from "../components/QaProjection.vue";
import { normalize3d } from "../lib/qaProjection3d.js";
import QaValidationPanel from "../components/QaValidationPanel.vue";
import QaLiveEvaluationPanel from "../components/QaLiveEvaluationPanel.vue";
import QaCorpusEvaluationPanel from "../components/QaCorpusEvaluationPanel.vue";
import QaWorkbench from "../components/QaWorkbench.vue";
import QaExecutionHistory from "../components/QaExecutionHistory.vue";
import QaHealthWorkspace from "../components/QaHealthWorkspace.vue";
import { buildWorkbenchModel } from "../lib/qaWorkbench.js";
import "../css/panel-base.css";
import "../css/qa.css";
import "../css/qa-fonts.css";
import "../css/qa-typography.css";
import "../css/qa-workbench.css";
import "../css/qa-task-workbench.css";

const { t, locale } = useI18n();
const storedDark = localStorage.getItem("ns_dark");
const dark = ref(storedDark !== null ? storedDark === "1" : true);
const route = useRoute(), router = useRouter();
const dataViews = [{ id: "overview", icon: "home" }, { id: "vectors", icon: "scatter_plot" }];
const verificationTasks = [
  { id: "offline_regression", icon: "fact_check", testId: "qa-nav-validation" },
  { id: "es_integration", icon: "link", testId: "qa-nav-es-integration" },
  { id: "real_es_llm_e2e", icon: "database", testId: "qa-nav-rag-chain" },
  { id: "model_evaluation", icon: "smart_toy", testId: "qa-nav-live" },
  { id: "real_corpus_quality", icon: "find_in_page", testId: "qa-nav-corpus" },
];
const validView = (value) => ["health", "overview", "vectors", "verification", "validation", "live", "corpus", "history"].includes(value) ? value : "verification";
const validTask = (value) => verificationTasks.slice(0, 3).some((task) => task.id === value) ? value : "offline_regression";
const activeView = ref(validView(route?.query?.view || new URLSearchParams(window.location.search).get("view")));
const requestedMode = ref(validTask(route?.query?.task || new URLSearchParams(window.location.search).get("task")));
const workbenchTask = ref(activeView.value === "live" ? "model_evaluation" : activeView.value === "corpus" ? "real_corpus_quality" : activeView.value === "validation" ? requestedMode.value : "es_integration");
const currentTask = computed(() => activeView.value === "live" ? "model_evaluation" : activeView.value === "corpus" ? "real_corpus_quality" : activeView.value === "verification" ? workbenchTask.value : requestedMode.value);
const taskView = computed(() => ["validation", "live", "corpus"].includes(activeView.value));
watch(currentTask, value => { if (taskView.value) workbenchTask.value = value; });
const validationPanel = ref(null), livePanel = ref(null), corpusPanel = ref(null);
const validationObservation = ref({ capabilities: null, job: null, loading: true, error: null });
const evaluationObservation = ref({ capabilities: null, job: null, loading: true, error: null });
const corpusObservation = ref({ capabilities: null, job: null, loading: true, error: null });
const workbenchModel = computed(() => buildWorkbenchModel({ validation: validationObservation.value, evaluation: evaluationObservation.value, corpus: corpusObservation.value }));
const workbenchAvailability = computed(() => ({ ...Object.fromEntries((validationObservation.value.capabilities?.modes || []).map(mode => [mode.id, mode.available])), model_evaluation: evaluationObservation.value.capabilities?.available, real_corpus_quality: corpusObservation.value.capabilities?.available }));
const navigationError = ref(false);
const validationPhase = ref("settings"), livePhase = ref("settings"), corpusPhase = ref("settings");
const currentPhase = computed(() => activeView.value === "verification" ? "workbench" : activeView.value === "history" ? "history" : activeView.value === "live" ? livePhase.value : activeView.value === "corpus" ? corpusPhase.value : activeView.value === "validation" ? validationPhase.value : "data");
watch(currentPhase, (phase, previous) => {
  if (taskView.value && previous === "settings" && ["execution", "evidence"].includes(phase)) focusTaskWorkspace();
});
const shellControls = inject("qa-shell-controls", null);
const accountEmail = computed(() => shellControls?.user?.value?.email || "");
const canLogout = computed(() => typeof shellControls?.logout === "function");
const logout = () => shellControls?.logout?.();
const navigationOpen = ref(false), menuButton = ref(null), workspace = ref(null), inspectorTab = ref("legend"), selectedPoint = ref(null);
const dataView = computed(() => ["overview", "vectors"].includes(activeView.value));
const validationSummary = ref({ status: "not_run", mode: "offline_regression", tests: null, active: false, available: false, error: null });
const liveSummary = ref({ status: "not_run", tests: null, active: false, available: false, error: null });
const validationSummaryLabel = computed(() => validationSummary.value.status === "not_run" ? t("qaValidation.notRun") : t("qaValidation.modes." + validationSummary.value.mode + ".title") + " · " + t("qaValidation." + (validationSummary.value.mode === "offline_regression" ? "status." : "realStatus.") + validationSummary.value.status));
const liveSummaryLabel = computed(() => liveSummary.value.status === "not_run" ? t("qaWorkbench.notRun") : t("qaLive.status." + liveSummary.value.status));
watch(() => route?.query?.view, (value) => { activeView.value = validView(value); });
watch(() => route?.query?.task, (value) => { requestedMode.value = validTask(value); });
watch(activeView, async () => { navigationOpen.value = false; await nextTick(); if (workspace.value) workspace.value.scrollTop = 0; });
function selectView(value) {
  const fromDrawer = navigationOpen.value;
  activeView.value = validView(value); navigationOpen.value = false; navigationError.value = false;
  if (router && route) {
    const query = { ...route.query, view: activeView.value };
    if (activeView.value === "validation") query.task = requestedMode.value;
    else delete query.task;
    if (route.query.view !== query.view || route.query.task !== query.task) router.push({ query });
  }
  if (fromDrawer) nextTick(() => workspace.value?.focus({ preventScroll: true }));
}
function focusTaskWorkspace() { nextTick(() => { if (workspace.value) { workspace.value.scrollTop = 0; workspace.value.focus({ preventScroll: true }); } }); }
function navigateTask(value) {
  if (value === "history") { openExecutionHistory(); return; }
  if (value === "verification") { selectView(value); return; }
  if (value === "model_evaluation") { selectView("live"); livePanel.value?.prepareRun?.(); focusTaskWorkspace(); return; }
  if (value === "real_corpus_quality") { selectView("corpus"); corpusPanel.value?.prepareRun?.(); focusTaskWorkspace(); return; }
  requestedMode.value = validationSummary.value.active ? validationSummary.value.mode : validTask(value);
  activeView.value = "validation"; navigationOpen.value = false;
  if (router && route) router.push({ query: { ...route.query, view: "validation", task: requestedMode.value } });
  focusTaskWorkspace();
  nextTick(() => validationPanel.value?.prepareRun?.(requestedMode.value));
}
async function selectWorkbenchTask(value) {
  if (!verificationTasks.some(task => task.id === value)) return;
  workbenchTask.value = value;
  const entry = workbenchModel.value.history.find(item => item.mode === value);
  const active = workbenchModel.value.history.find(item => item.status === "RUNNING");
  // A shared validation controller must retain its active run. Other selections
  // can show their overview without replacing that controller's current job.
  if (entry && (!active || entry.family !== active.family || entry.id === active.id)) await showEvidence(entry);
  else selectView("verification");
}
async function openExecutionHistory() {
  selectView("history");
  await reloadWorkbench();
}
async function reloadWorkbench() {
  await Promise.allSettled([validationPanel.value?.refresh?.(), livePanel.value?.refresh?.(), corpusPanel.value?.refresh?.()]);
}
async function showEvidence(entry, logs = false) {
  if (!entry || !["validations", "evaluations", "corpus-evaluations"].includes(entry.family)) return;
  workbenchTask.value = entry.mode;
  if (entry.family === "corpus-evaluations") { selectView("corpus"); await nextTick(); navigationError.value = await corpusPanel.value?.showJob?.(entry.id) === false; focusTaskWorkspace(); return; }
  const model = entry.family === "evaluations";
  if (model) selectView("live");
  else { requestedMode.value = validTask(entry.mode); selectView("validation"); }
  await nextTick();
  const opened = await (model ? livePanel.value : validationPanel.value)?.showJob?.(entry.id, { logs });
  navigationError.value = opened === false;
  focusTaskWorkspace();
}
async function runPrimaryAction(action) {
  if (!action || action.disabled) return;
  if (action.kind === "reload") { await reloadWorkbench(); return; }
  if (action.kind === "resume" || action.kind === "details") { await showEvidence(action); return; }
  if (action.kind !== "start" || !["offline_regression", "es_integration"].includes(action.mode)) return;
  navigateTask(action.mode);
}
function syncValidationMode(value) {
  requestedMode.value = validTask(value);
  if (activeView.value === "validation" && router && route && route.query.task !== requestedMode.value) router.replace({ query: { ...route.query, view: "validation", task: requestedMode.value } });
}
async function closeNavigation() {
  if (!navigationOpen.value) return;
  navigationOpen.value = false;
  await nextTick(); menuButton.value?.focus();
}
const snapshot = ref(null), loading = ref(false), error = ref("");
const colorBy = ref("category"), hidden = ref(new Set());
const repository = QA_REPOSITORY;
const palette = ["#168478", "#6678CE", "#C47733", "#B46087", "#688F38", "#3D92B5", "#AF6653", "#9272B9", "#7F8C99", "#B28F35", "#529D88", "#B667B4", "#7087B0", "#AD805D"];
let controller;
const number = (value) => new Intl.NumberFormat(locale.value).format(value);
const percentage = (value) => new Intl.NumberFormat(locale.value, { style: "percent", maximumFractionDigits: 1 }).format(value);
const groupLabel = (name) => name === "__other__" ? t("observatory.other") : !name || name === "__missing__" ? t("observatory.unknown") : name;
const categoryLabel = (name) => t("observatory.categoryGroups." + qaCategoryLabelKey(name));
const plotGroupLabel = (name) => colorBy.value === "category" ? categoryLabel(name) : groupLabel(name);
const generatedAt = computed(() => snapshot.value ? new Intl.DateTimeFormat(locale.value, { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(snapshot.value.generated_at)) + " (UTC+8)" : "");
const sampleRatio = computed(() => percentage(snapshot.value?.projection.population ? snapshot.value.projection.sample_size / snapshot.value.projection.population : 0));
const staleDetail = computed(() => (snapshot.value?.stale_reasons || ["age"]).map((reason) => t("observatory.staleReasons." + (["age", "configuration", "future_timestamp"].includes(reason) ? reason : "age"))).join(" · "));
const points = computed(() => {
  const projected = projectedPoints(snapshot.value?.projection.points || []).map((point) => ({ ...point, category: qaCategoryGroup(point.category) }));
  return snapshot.value?.projection.dimensions === 3 ? normalize3d(projected) : projected;
});
const legend = computed(() => {
  const counts = new Map();
  for (const point of points.value) counts.set(point[colorBy.value], (counts.get(point[colorBy.value]) || 0) + 1);
  return [...counts].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
});
const visiblePoints = computed(() => points.value.filter((point) => !hidden.value.has(point[colorBy.value])));
const distributionGroups = computed(() => ["categories", "sources"].map((id) => {
  const source = snapshot.value?.distributions[id] || [];
  const rows = (id === "categories" ? qaCategoryDistribution(source) : [...source]).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  return { id, rows, max: rows[0]?.count || 0 };
}));
function colorFor(name) { return colorBy.value === "category" ? qaCategoryColor(name) : palette[Math.max(0, legend.value.findIndex((item) => item.name === name)) % palette.length]; }
function toggleSeries(name) { const next = new Set(hidden.value); if (next.has(name)) next.delete(name); else next.add(name); hidden.value = next; }
function setColorBy(value) { colorBy.value = value; hidden.value = new Set(); selectedPoint.value = null; }
function toggleDark() { dark.value = !dark.value; localStorage.setItem("ns_dark", dark.value ? "1" : "0"); }
function setLanguage(value) { locale.value = value; localStorage.setItem("ns_lang", value); document.documentElement.lang = value === "en" ? "en" : "zh-Hant"; }
async function loadSnapshot() {
  controller?.abort();
  controller = new AbortController();
  const current = controller;
  const timeout = setTimeout(() => current.abort(), 15000);
  loading.value = true; error.value = "";
  try {
    const response = await apiFetch(`${AGENT}/qa/snapshot`, { method: "GET", signal: current.signal, cache: "no-store" });
    if (!response.ok) throw new Error(response.status === 503 ? "unavailable" : "fetch");
    const value = await response.json();
    if (!validQaSnapshot(value)) throw new Error("schema");
    snapshot.value = value; hidden.value = new Set(); selectedPoint.value = null;
  } catch (failure) {
    if (current !== controller) return;
    error.value = failure.message === "unavailable" ? "unavailable" : "fetch";
  } finally { clearTimeout(timeout); if (current === controller) loading.value = false; }
}
function ensureDataSnapshot() {
  if (dataView.value && !snapshot.value && !loading.value) loadSnapshot();
}
watch(dataView, ensureDataSnapshot);
onMounted(ensureDataSnapshot);
onBeforeUnmount(() => { controller?.abort(); controller = null; });
</script>
