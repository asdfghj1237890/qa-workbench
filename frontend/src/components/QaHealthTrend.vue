<template>
  <figure class="qh-trend">
    <figcaption><strong>{{ title }}</strong><QaIcon name="info" aria-hidden="true" /><span>{{ $t('qaHealth.mockChart') }}</span></figcaption>
    <canvas ref="canvas" role="img" :aria-label="$t('qaHealth.chartDescription')"></canvas>
    <details class="qh-chart-values"><summary>{{ $t('qaHealth.chartValues') }}</summary><table><caption>{{ title }} · {{ $t('qaHealth.minutes') }}</caption><thead><tr><th>{{ $t('qaHealth.time') }}</th><th>{{ $t('qaHealth.measured') }}</th></tr></thead><tbody><tr v-for="[time, value] in samples" :key="time"><td>{{ time }}</td><td>{{ value }}</td></tr></tbody></table></details>
  </figure>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import QaIcon from './QaIcon.vue';
const props = defineProps({ samples: { type: Array, required: true }, threshold: { type: Number, required: true }, title: { type: String, required: true }, dark: Boolean });
const { t, locale } = useI18n();
const canvas = ref(null);
let observer;
// A data chart, not a raster illustration: the same measurements are available
// in the accessible table. Resize/redraw never makes a network request.
function draw() {
  const el = canvas.value;
  if (!el || !el.clientWidth) return;
  const ctx = el.getContext('2d');
  if (!ctx) return;
  const width = el.clientWidth, height = 190, ratio = window.devicePixelRatio || 1;
  el.width = Math.round(width * ratio); el.height = height * ratio;
  ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height);
  const left = 39, top = 25, right = 40, bottom = 29, plotWidth = width - left - right, plotHeight = height - top - bottom;
  const ink = props.dark ? '#bcbfba' : '#535b57', grid = props.dark ? '#35393a' : '#d7dcd7', accent = props.dark ? '#ffbd48' : '#805615';
  const minutes = (time) => { const [h, m] = time.split(':').map(Number); return h * 60 + m; };
  const x = (time) => left + (minutes(time) - minutes('13:30')) / 60 * plotWidth;
  const y = (value) => top + (40 - value) / 40 * plotHeight;
  ctx.font = '12px "NewsCout QA Sans", sans-serif'; ctx.fillStyle = ink;
  ctx.fillText(t('qaHealth.minutes'), 0, 13);
  for (const value of [0, 20, 40]) {
    ctx.fillText(String(value), 1, y(value) + 4); ctx.strokeStyle = grid; ctx.lineWidth = 0.6;
    ctx.beginPath(); ctx.moveTo(left, y(value)); ctx.lineTo(width - right, y(value)); ctx.stroke();
  }
  for (const time of ['13:30', '13:45', '14:00', '14:15', '14:30']) {
    if (width < 400 && ['13:45', '14:15'].includes(time)) continue;
    ctx.textAlign = 'center'; ctx.fillText(time, x(time), height - 7);
    ctx.strokeStyle = grid; ctx.beginPath(); ctx.moveTo(x(time), top); ctx.lineTo(x(time), height - bottom); ctx.stroke();
  }
  ctx.textAlign = 'right'; ctx.fillStyle = ink;
  ctx.setLineDash([4, 4]); ctx.strokeStyle = ink; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(left, y(props.threshold)); ctx.lineTo(width - right, y(props.threshold)); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillText(t('qaHealth.threshold') + ' ' + props.threshold + ' ' + t('qaHealth.minutes'), width - right, y(props.threshold) - 9);
  ctx.strokeStyle = accent; ctx.lineWidth = 2; ctx.beginPath();
  props.samples.forEach(([time, value], index) => index ? ctx.lineTo(x(time), y(value)) : ctx.moveTo(x(time), y(value))); ctx.stroke();
  ctx.fillStyle = accent;
  props.samples.forEach(([time, value]) => { ctx.beginPath(); ctx.arc(x(time), y(value), 3.3, 0, Math.PI * 2); ctx.fill(); });
  const last = props.samples.at(-1);
  if (last) { ctx.font = '600 13px "NewsCout QA Sans", sans-serif'; ctx.fillText(last[1] + ' ' + t('qaHealth.minutes'), width - right, y(last[1]) - 13); }
}
onMounted(async () => { await nextTick(); draw(); if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(draw); observer.observe(canvas.value); } });
watch(() => [props.samples, props.dark, locale.value], () => nextTick(draw));
onBeforeUnmount(() => observer?.disconnect());
</script>
