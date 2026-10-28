<template>
  <section class="qh-history" data-testid="health-history" :aria-busy="loading">
    <header><h3>{{ $t('qaHealth.history.title') }}</h3><div class="qh-history-windows" role="group" :aria-label="$t('qaHealth.history.window')"><button v-for="range in ['24h', '7d']" :key="range" type="button" :data-testid="'history-window-' + range" :aria-pressed="window === range" @click="window = range">{{ $t('qaHealth.history.' + range) }}</button></div></header>
    <p v-if="loading" role="status">{{ $t('qaHealth.history.loading') }}</p>
    <p v-if="error" role="alert">{{ $t('qaHealth.history.unavailable') }}</p>
    <template v-if="history && !error">
      <p class="qh-history-note">{{ $t('qaHealth.history.schedule') }} {{ $t('qaHealth.history.count', { count: history.samples.length }) }}</p>
      <div v-if="history.sampling" class="qh-history-notice" data-testid="history-sampling" :class="{ 'is-delayed': history.sampling.overdue_seconds > 60 || history.sampling.last_attempt?.outcome === 'failed' }" role="note">
        <strong>{{ $t('qaHealth.history.samplingTitle') }}</strong>
        <p>{{ $t('qaHealth.history.lastSuccess') }} {{ time(history.sampling.last_success_at) }} · {{ $t('qaHealth.history.overdue', { seconds: history.sampling.overdue_seconds ?? '—' }) }}</p>
        <p>{{ $t('qaHealth.history.missed', { count: history.sampling.missed_intervals ?? '—' }) }} <span v-if="history.sampling.missed_since_at">{{ $t('qaHealth.history.since', { time: time(history.sampling.missed_since_at) }) }}</span></p>
        <p>{{ $t('qaHealth.history.samplerOutcomes.' + (history.sampling.last_attempt?.outcome || 'unavailable')) }}<template v-if="history.sampling.last_attempt"> · {{ time(history.sampling.last_attempt.finished_at) }}</template></p>
        <p class="qh-history-note">{{ $t('qaHealth.history.samplingScope') }}</p>
      </div>
      <button type="button" class="qa-button" data-testid="health-history-download" @click="download">{{ $t('qaHealth.history.download') }}</button>
      <div v-if="!plot.dots.length && (history.samples.length || ['not_connected', 'invalid_probe_target'].includes(currentReason))" class="qh-history-notice" data-testid="history-unmeasured" role="note"><strong>{{ $t('qaHealth.history.noMeasurementTitle') }}</strong><p>{{ $t(historyHint) }}</p></div>
      <p v-if="!history.samples.length && !['not_connected', 'invalid_probe_target'].includes(currentReason)" class="qh-history-empty">{{ $t('qaHealth.live.noHistory') }} · {{ $t('qaHealth.history.accumulating') }}</p>
      <template v-else>
        <p>{{ $t('qaHealth.history.last') }} {{ time(plot.lastSampleAt) }} · {{ $t('qaHealth.history.units') }} {{ plot.unit === 'none' ? '—' : $t('qaHealth.' + plot.unit) }}</p>
        <figure v-if="plot.dots.length">
          <svg viewBox="0 0 600 184" role="img" :aria-label="$t('qaHealth.history.chart')" data-testid="history-chart">
            <path v-if="plot.dots.length" d="M44 12V142H588" class="qh-history-axis" />
            <text v-if="plot.dots.length" x="1" y="20">{{ axisValue(plot.ceiling) }}</text><text v-if="plot.dots.length" x="24" y="142">0</text>
            <polyline v-for="(line, index) in plot.segments" :key="index" :points="line" class="qh-history-line" data-testid="history-line" />
            <circle v-for="(dot, index) in plot.dots" :key="'d' + index" :cx="dot.x" :cy="dot.y" r="1.8" :class="'qh-history-' + dot.status" />
            <rect v-for="(bar, index) in plot.bars" :key="'b' + index" :x="bar.x" y="150" :width="bar.width" height="7" :class="'qh-history-' + bar.status" />
            <text x="44" y="179">{{ axisTime(history.start_at) }}</text><text x="588" y="179" text-anchor="end">{{ axisTime(history.end_at) }}</text>
          </svg>
          <figcaption>{{ $t('qaHealth.history.gaps') }}</figcaption>
        </figure>
        <p v-if="plot.dots.length === 1">{{ $t('qaHealth.history.single') }}</p>
        <details @toggle="tableOpen = $event.target.open">
          <summary>{{ $t('qaHealth.history.table') }}</summary>
          <div v-if="tableOpen" class="qh-history-table"><table><caption>{{ $t('qaHealth.history.tableNote') }}</caption><thead><tr><th>{{ $t('qaHealth.time') }}</th><th>{{ $t('qaHealth.measured') }}</th><th>{{ $t('qaHealth.history.status') }}</th><th>{{ $t(moduleId === 'frontend' ? 'qaHealth.history.entryVersion' : 'qaHealth.history.version') }}</th></tr></thead><tbody><tr v-for="point in history.samples.slice(-100).reverse()" :key="point.sampled_at"><td>{{ time(point.sampled_at) }}</td><td>{{ point.measurement.value === null ? '—' : value(point.measurement.value) + ' ' + $t('qaHealth.' + point.measurement.unit) }}</td><td>{{ $t('qaHealth.status.' + point.status) }}</td><td>{{ (moduleId === 'frontend' ? point.target_sha : point.source_sha)?.slice(0, 12) || '—' }}</td></tr></tbody></table></div>
        </details>
      </template>
    </template>
    <button v-if="error" type="button" class="qa-button" data-testid="health-history-retry" @click="reload">{{ $t('qaHealth.live.retry') }}</button>
  </section>
</template>

<script setup>
import { qaDownloadPrefix } from '../lib/runtime.js';
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { AGENT } from '../lib/runtime.js';
import { apiFetch } from '../lib/qaSession.js';
import { healthTimestamp } from '../lib/qaHealth.js';
import { healthHistoryPlot, parseHealthHistory } from '../lib/qaHealthHistory.js';
const props = defineProps({ moduleId: { type: String, required: true }, refreshKey: String, currentReason: String });
const window = ref('24h'), history = ref(null), error = ref(false), loading = ref(false), tableOpen = ref(false);
const plot = computed(() => history.value ? healthHistoryPlot(history.value) : null);
const historyHint = computed(() => props.currentReason === 'invalid_probe_target' ? 'qaHealth.history.invalidSource'
  : props.currentReason === 'not_connected' ? 'qaHealth.history.sourceNotConnected'
    : props.currentReason?.startsWith('llm_') ? 'qaHealth.history.waitingForLlmRequest'
    : ['frontend_entry_ok', 'frontend_entry_failed'].includes(props.currentReason) ? 'qaHealth.history.waitingForFrontendSample' : 'qaHealth.history.unmeasured');
let controller, generation = 0;
const time = (stamp) => healthTimestamp(stamp) || '—';
const axisTime = (stamp) => time(stamp).slice(5, 16);
const value = (number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(number);
const axisValue = (number) => new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(number);
function download() {
  const blob = new Blob([JSON.stringify({ schema_version: 1, kind: 'health_history', environment: 'qa', scope: 'active_qa_instance_and_shared_ingestion', retention_seconds: 604800, ...history.value, score: null, quality_review: 'unmeasured' }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = `${qaDownloadPrefix()}-health-${props.moduleId}-${window.value}.json`; link.click();
  globalThis.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function reload() {
  controller?.abort(); controller = new AbortController();
  const current = ++generation, owned = controller, module = props.moduleId, range = window.value;
  const deadline = globalThis.setTimeout(() => owned.abort(), 6000);
  loading.value = true; error.value = false; history.value = null;
  try {
    const response = await apiFetch(`${AGENT}/qa/health/history?module=${module}&window=${range}`, { method: 'GET', cache: 'no-store', signal: owned.signal });
    if (!response.ok) throw new Error('unavailable');
    const parsed = parseHealthHistory(await response.json(), { module, window: range });
    if (!parsed) throw new Error('invalid');
    if (current === generation) history.value = parsed;
  } catch { if (current === generation) error.value = true; }
  finally { globalThis.clearTimeout(deadline); if (current === generation) loading.value = false; }
}
watch(() => [props.moduleId, props.refreshKey, window.value], reload, { immediate: true });
onBeforeUnmount(() => { generation++; controller?.abort(); });
</script>
