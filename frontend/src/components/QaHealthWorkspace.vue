<template>
  <section class="qh-live-workspace" data-testid="qa-health-workspace" :aria-busy="loading">
    <component :is="healthPanel" v-if="healthPanel && !preview" :dark="dark" />
    <div v-if="!snapshot" class="qh-state">
      <h1>{{ $t('qaHealth.title') }}</h1><p v-if="preview" class="qh-preview-label">{{ $t('qaHealth.preview') }}</p>
      <p v-if="loading" role="status">{{ $t('qaHealth.live.loading') }}</p>
      <p v-else-if="error" role="alert">{{ $t('qaHealth.live.errors.' + error) }}</p>
      <button v-if="!loading" class="qa-button" data-testid="health-retry" @click="reload">{{ $t('qaHealth.live.retry') }}</button>
    </div>
    <template v-else>
      <p v-if="error" class="qh-fetch-error" role="alert">{{ $t('qaHealth.live.errors.' + error) }} {{ $t('qaHealth.live.retained') }}</p>
      <p v-else-if="model.expired" class="qh-fetch-error" role="status">{{ $t('qaHealth.live.expired') }}</p>
      <QaHealthPanel :model="model" :preview="preview" :dark="dark" :loading="loading" @refresh="reload" />
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { AGENT, getQaAdapter } from '../lib/runtime.js';
import { apiFetch } from '../lib/qaSession.js';
import { observedHealthModel, parseHealthSnapshot } from '../lib/qaHealth.js';
import QaHealthPanel from './QaHealthPanel.vue';
const props = defineProps({ dark: Boolean, preview: Boolean });
const healthPanel = getQaAdapter().healthPanel;
const snapshot = ref(null), loading = ref(false), error = ref(''), clock = ref(Date.now());
const model = computed(() => snapshot.value ? observedHealthModel(snapshot.value, { now: clock.value, forceStale: !!error.value, preview: props.preview }) : null);
let controller, timer, generation = 0;
async function reload() {
  controller?.abort(); controller = new AbortController();
  const current = ++generation, ownedController = controller, signal = ownedController.signal;
  const timeout = window.setTimeout(() => ownedController.abort(), 6000);
  loading.value = true;
  try {
    const response = await apiFetch(`${AGENT}/qa/health`, { method: 'GET', cache: 'no-store', signal });
    if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'authentication' : 'unavailable');
    const parsed = parseHealthSnapshot(await response.json());
    if (!parsed) throw new Error('invalid');
    if (current !== generation) return;
    snapshot.value = parsed; clock.value = Date.now(); error.value = '';
  } catch (failure) {
    if (current === generation) error.value = ['authentication', 'unavailable', 'invalid'].includes(failure.message) ? failure.message : 'unavailable';
  } finally { window.clearTimeout(timeout); if (current === generation) loading.value = false; }
}
onMounted(() => { reload(); timer = window.setInterval(() => { clock.value = Date.now(); }, 5000); });
onBeforeUnmount(() => { generation++; controller?.abort(); window.clearInterval(timer); });
</script>
