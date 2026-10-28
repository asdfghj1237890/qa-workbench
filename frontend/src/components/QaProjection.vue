<template>
  <div class="qa-interactive-projection">
    <div class="qa-plot-controls" role="group" :aria-label="$t('observatory.plot.controls')">
      <button class="qa-plot-button" data-testid="qa-mode-3d" :aria-pressed="is3d" :disabled="!has3d" @click="setMode(true)">3D</button>
      <button class="qa-plot-button" data-testid="qa-mode-2d" :aria-pressed="!is3d" @click="setMode(false)">{{ has3d ? $t('observatory.plot.xyPlane') : '2D' }}</button>
      <button v-if="is3d" class="qa-plot-button" data-testid="qa-orbit-mode" :aria-pressed="!panMode" @click="panMode = false">{{ $t('observatory.plot.rotate') }}</button>
      <button v-if="is3d" class="qa-plot-button" data-testid="qa-pan-mode" :aria-pressed="panMode" @click="panMode = true">{{ $t('observatory.plot.pan') }}</button>
      <button class="qa-plot-button" data-testid="qa-zoom-in" :aria-label="$t('observatory.plot.zoomIn')" :disabled="view.scale >= 12" @click="zoom(1.5)">+</button>
      <button class="qa-plot-button" data-testid="qa-zoom-out" :aria-label="$t('observatory.plot.zoomOut')" :disabled="view.scale <= 1" @click="zoom(1 / 1.5)">−</button>
      <output class="qa-zoom-level" data-testid="qa-zoom-level" :aria-label="$t('observatory.plot.zoomLevel')">{{ Math.round(view.scale * 100) }}%</output>
      <button class="qa-plot-button" data-testid="qa-reset-view" @click="reset">{{ $t('observatory.plot.reset') }}</button>
      <button class="qa-plot-button qa-label-toggle" data-testid="qa-label-toggle" :aria-pressed="showLabels" @click="showLabels = !showLabels">{{ $t('observatory.plot.labels') }}</button>
    </div>
    <template v-if="!workbench"><p class="qa-plot-help" data-testid="qa-dimension-note">{{ $t(is3d ? 'observatory.plot.true3d' : has3d ? 'observatory.plot.xyNote' : 'observatory.plot.legacy2d') }}</p><p :id="helpId" class="qa-plot-help">{{ $t(is3d ? 'observatory.plot.help3d' : 'observatory.plot.help') }}</p></template>
    <details v-else class="qa-plot-disclosure"><summary>{{ $t('observatory.plot.controls') }}</summary><p class="qa-plot-help" data-testid="qa-dimension-note">{{ $t(is3d ? 'observatory.plot.true3d' : has3d ? 'observatory.plot.xyNote' : 'observatory.plot.legacy2d') }}</p><p :id="helpId" class="qa-plot-help">{{ $t(is3d ? 'observatory.plot.help3d' : 'observatory.plot.help') }}</p><p class="qa-plot-help">{{ $t('observatory.plot.labelNote') }}</p></details>
    <div ref="container" class="qa-plot-surface" :class="{ 'is-3d': is3d }">
      <canvas v-if="is3d" ref="canvas" class="qa-scatter-canvas" aria-hidden="true" data-testid="qa-3d-canvas" :data-count="screenPoints.length" :data-yaw="camera.yaw" :data-pitch="camera.pitch" :data-frame="frame" />
      <svg ref="svg" class="qa-scatter" :class="{ 'is-panning': dragging }" :viewBox="`0 0 ${size.width} ${size.height}`" role="group" tabindex="0" aria-haspopup="dialog" :aria-controls="selected ? articlePopoverId : undefined" :aria-label="$t('observatory.projection')" :aria-describedby="`${helpId} ${descriptionId}`"
           @wheel="wheel" @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="cancelPointer" @lostpointercapture="cancelPointer" @keydown="keydown">
        <title>{{ $t('observatory.projection') }}</title><desc :id="descriptionId">{{ description }}</desc>
        <template v-if="!is3d">
          <path v-for="fraction in [.1, .3, .5, .7, .9]" :key="'x' + fraction" :d="`M ${size.width * fraction} 12 V ${size.height - 24}`" class="qa-grid-line" />
          <path v-for="fraction in [.1, .3, .5, .7, .9]" :key="'y' + fraction" :d="`M 12 ${size.height * fraction} H ${size.width - 12}`" class="qa-grid-line" />
        </template>
        <g v-else class="qa-3d-axes" aria-hidden="true">
          <g v-for="axis in axes" :key="axis.name"><line :x1="axis.origin.sx" :y1="axis.origin.sy" :x2="axis.end.sx" :y2="axis.end.sy" /><text :x="axis.end.sx + 5" :y="axis.end.sy - 5">{{ axis.name }}</text></g>
        </g>
        <circle v-for="point in renderedCircles" :key="point.index" :cx="point.sx" :cy="point.sy" :r="point.original === selected ? 6 : 3.5" :fill="colorFor(point[colorBy])" :data-group="point[colorBy]" :class="{ 'is-selected': point.original === selected }" fill-opacity="0.72" aria-hidden="true" />
        <g v-if="showLabels" class="qa-plot-labels" aria-hidden="true">
          <g v-for="label in labels" :key="label.key" class="qa-plot-label" :data-region="label.key" :data-group="label.name || '__mixed__'" :data-count="label.count" :data-mixed="label.mixed">
            <title>{{ label.fullText }}</title>
            <line :x1="label.anchorX" :y1="label.anchorY" :x2="label.x + label.width / 2" :y2="label.y + label.height / 2" :stroke="label.mixed ? '#7F8C99' : colorFor(label.name)" />
            <rect :x="label.x" :y="label.y" :width="label.width" :height="label.height" rx="5" />
            <text :x="label.x + label.width / 2" :y="label.y + 16" text-anchor="middle">{{ label.text }}</text>
          </g>
        </g>
        <template v-if="!is3d"><text :x="size.width - 12" :y="size.height - 9" text-anchor="end" class="qa-axis">UMAP 1</text><text x="12" y="16" class="qa-axis">UMAP 2</text></template>
      </svg>
      <section v-if="selected && selectedScreenPoint" :id="articlePopoverId" ref="popover" class="qa-point-popover" role="dialog" aria-modal="false" :aria-labelledby="articleTitleId" :style="popoverStyle" data-testid="qa-point-popover"
               @pointerdown.stop @pointermove.stop @pointerup.stop @wheel.stop @keydown.esc.prevent.stop="closeSelection(true)">
        <div class="qa-point-popover-heading"><span>{{ $t('observatory.plot.selected') }}</span><button class="qa-plot-button" :aria-label="$t('observatory.plot.clearSelection')" data-testid="qa-close-article" @click="closeSelection(true)"><QaIcon aria-hidden="true" name="close" /></button></div>
        <h3 :id="articleTitleId" data-testid="qa-article-title">{{ selectedTitle }}</h3>
        <dl class="qa-article-metadata"><div><dt>{{ $t('observatory.byCategory') }}</dt><dd>{{ $t('observatory.categoryGroups.' + qaCategoryLabelKey(selected.category)) }}</dd></div><div><dt>{{ $t('observatory.bySource') }}</dt><dd>{{ metadataLabel(selected.site) }}</dd></div></dl>
        <a v-if="selectedUrl" :href="selectedUrl" target="_blank" rel="noopener noreferrer" class="qa-article-link" data-testid="qa-article-link">{{ $t('observatory.plot.openArticle') }} <QaIcon aria-hidden="true" name="north_east" /></a>
        <p v-else class="qa-article-unavailable" data-testid="qa-article-unavailable">{{ $t('observatory.plot.articleLinkUnavailable') }}</p>
      </section>
    </div>
    <div class="qa-point-detail" :class="{ 'qa-projection-sr-only': workbench }" role="status" aria-live="polite" data-testid="qa-point-detail">
      <template v-if="selected"><strong>{{ $t('observatory.plot.selected') }}</strong><dl><div><dt>{{ $t('observatory.byCategory') }}</dt><dd>{{ $t('observatory.categoryGroups.' + qaCategoryLabelKey(selected.category)) }}</dd></div><div><dt>{{ $t('observatory.bySource') }}</dt><dd>{{ metadataLabel(selected.site) }}</dd></div><div><dt>UMAP 1</dt><dd>{{ coordinate(selected.x) }}</dd></div><div><dt>UMAP 2</dt><dd>{{ coordinate(selected.y) }}</dd></div><div v-if="has3d"><dt>UMAP 3</dt><dd>{{ coordinate(selected.z) }}</dd></div></dl></template>
      <span v-else>{{ $t('observatory.plot.selectHint') }}</span>
    </div>
    <p class="qa-plot-help qa-label-note"><span v-if="!workbench">{{ $t('observatory.plot.labelNote') }} </span><span data-testid="qa-viewport-count">{{ $t('observatory.plot.inView', { n: viewportPoints.length }) }}</span></p>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, useId, watch } from "vue";
import QaIcon from "./QaIcon.vue";
import { useI18n } from "vue-i18n";
import { boundedView, fittedInitialView, groupLabels, initialView, inViewport, nearestPoint, screenPoint, spatialRegions, zoomView } from "../lib/qaProjection.js";
import { qaCategoryLabelKey } from "../lib/qaCategories.js";
import { initialOrbit, orbitCamera, screenPoint3d, spatialRegions3d } from "../lib/qaProjection3d.js";
import { qaArticleUrl } from "../lib/qa.js";

const props = defineProps({
  points: { type: Array, required: true }, colorBy: { type: String, required: true },
  colorFor: { type: Function, required: true }, groupLabel: { type: Function, required: true },
  description: { type: String, required: true }, resetKey: { type: Object, required: true },
  dimensions: { type: Number, default: 2 },
  workbench: { type: Boolean, default: false },
});
const emit = defineEmits(["selection-change"]);
const { t, locale } = useI18n();
const metadataLabel = (name) => name === "__other__" ? t("observatory.other") : !name || name === "__missing__" ? t("observatory.unknown") : name;
const helpId = useId(), descriptionId = useId(), articleTitleId = useId(), articlePopoverId = useId();
const container = ref(null), svg = ref(null), canvas = ref(null), popover = ref(null), showLabels = ref(true), dragging = ref(false);
const has3d = computed(() => props.dimensions === 3), is3d = ref(has3d.value), camera = ref(initialOrbit()), panMode = ref(false), frame = ref(0);
// Keep the original point identity, including nonreactive computed projection data.
const selected = shallowRef(null);
const size = ref({ width: 1000, height: 440 }), view = ref(initialView());
const popoverSize = ref({ width: 320, height: 220 });
let observer, popoverObserver, pointer = null, gesture = null, drawRequest = 0, fittedView = null;
const touches = new Map();
const project = (point, currentView, width, height) => is3d.value ? screenPoint3d(point, currentView, width, height, camera.value) : screenPoint(point, currentView, width, height);
const screenPoints = computed(() => props.points.map((point, index) => ({ ...project(point, view.value, size.value.width, size.value.height), index, original: point })));
const selectedScreenPoint = computed(() => selected.value ? screenPoints.value.find((point) => point.original === selected.value) : null);
const selectedTitle = computed(() => typeof selected.value?.title === "string" && selected.value.title.trim() ? selected.value.title : t("observatory.plot.articleTitleUnavailable"));
const selectedUrl = computed(() => qaArticleUrl(selected.value?.url));
const popoverStyle = computed(() => {
  const margin = 8, gap = 14, point = selectedScreenPoint.value;
  const width = Math.max(0, Math.min(320, size.value.width - margin * 2));
  const height = Math.min(popoverSize.value.height, size.value.height - margin * 2);
  const clamp = (value, extent, available) => Math.max(margin, Math.min(available - extent - margin, value));
  const x = point ? (point.sx + gap + width <= size.value.width - margin ? point.sx + gap : point.sx - width - gap) : margin;
  const y = point ? (point.sy - height - gap >= margin ? point.sy - height - gap : point.sy + gap) : margin;
  return { left: `${clamp(x, width, size.value.width)}px`, top: `${clamp(y, height, size.value.height)}px`, width: `${width}px`, maxHeight: `${Math.max(0, size.value.height - margin * 2)}px` };
});
const renderedCircles = computed(() => is3d.value ? screenPoints.value.filter((point) => point.original === selected.value) : screenPoints.value);
const viewportPoints = computed(() => screenPoints.value.filter((point) => inViewport(point, size.value.width, size.value.height)));
const regions = computed(() => has3d.value ? spatialRegions3d(props.points, props.colorBy) : spatialRegions(props.points, props.colorBy));
const labels = computed(() => groupLabels(regions.value, view.value, size.value.width, size.value.height, props.groupLabel, (parts) => t('observatory.plot.mixedRegion', { parts }), project));
const axes = computed(() => ["nx", "ny", "nz"].map((axis, index) => ({ name: `UMAP ${index + 1}`, origin: project({ nx: -1.15, ny: -1.15, nz: -1.15 }, view.value, size.value.width, size.value.height), end: project({ nx: -1.15, ny: -1.15, nz: -1.15, [axis]: -.55 }, view.value, size.value.width, size.value.height) })));
const coordinate = (value) => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 4 }).format(value);
function closeSelection(restoreFocus = false) { selected.value = null; if (restoreFocus) svg.value?.focus({ preventScroll: true }); }
function measurePopover() {
  const rect = popover.value?.getBoundingClientRect();
  if (rect?.width > 0 && rect.height > 0) popoverSize.value = { width: rect.width, height: rect.height };
}
function fitInitial() { fittedView = fittedInitialView(props.points, size.value.width, size.value.height, project); return fittedView; }
function isInitialView() { return !fittedView || ["scale", "x", "y"].every((key) => view.value[key] === fittedView[key]) && camera.value.yaw === initialOrbit().yaw && camera.value.pitch === initialOrbit().pitch; }
function reset() { camera.value = initialOrbit(); view.value = fitInitial(); selected.value = null; cancelPointer(); }
function setMode(next) { is3d.value = next && has3d.value; reset(); }
function drawCanvas() {
  drawRequest = 0;
  if (!is3d.value || !canvas.value) return;
  const ratio = Math.min(2, window.devicePixelRatio || 1), element = canvas.value;
  element.width = Math.round(size.value.width * ratio); element.height = Math.round(size.value.height * ratio);
  const context = element.getContext("2d");
  if (!context) return;
  context.scale(ratio, ratio); context.clearRect(0, 0, size.value.width, size.value.height);
  const points = [...viewportPoints.value].sort((a, b) => a.depth - b.depth || a.index - b.index);
  for (const point of points) {
    context.globalAlpha = .55 + (point.depth + 1.75) / 3.5 * .3;
    context.fillStyle = props.colorFor(point[props.colorBy]); context.beginPath(); context.arc(point.sx, point.sy, point.radius, 0, Math.PI * 2); context.fill();
  }
  frame.value++;
}
function queueDraw() { if (is3d.value && !drawRequest) drawRequest = requestAnimationFrame(drawCanvas); }
function zoom(factor, anchor = { x: size.value.width / 2, y: size.value.height / 2 }) { view.value = zoomView(view.value, factor, anchor, size.value.width, size.value.height); }
function location(event) {
  const rect = svg.value.getBoundingClientRect();
  return { x: (event.clientX - rect.left) * size.value.width / (rect.width || size.value.width), y: (event.clientY - rect.top) * size.value.height / (rect.height || size.value.height) };
}
function wheel(event) {
  if (!event.ctrlKey && !event.metaKey) return;
  event.preventDefault();
  zoom(Math.exp(-Math.max(-200, Math.min(200, event.deltaY)) * .004), location(event));
}
function pointerDown(event) {
  if (event.button !== undefined && event.button !== 0) return;
  const at = location(event);
  touches.set(event.pointerId, at);
  if (touches.size === 2) {
    const [a, b] = [...touches.values()];
    gesture = { distance: Math.hypot(a.x - b.x, a.y - b.y), center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, view: { ...view.value } };
    if (pointer) pointer.moved = true;
  } else if (!pointer) pointer = { id: event.pointerId, at, view: { ...view.value }, camera: { ...camera.value }, pan: event.shiftKey || panMode.value, moved: false };
  svg.value.setPointerCapture?.(event.pointerId);
  svg.value.focus({ preventScroll: true });
}
function pointerMove(event) {
  if (!touches.has(event.pointerId)) return;
  touches.set(event.pointerId, location(event));
  if (gesture && touches.size === 2) {
    const [a, b] = [...touches.values()], center = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const zoomed = zoomView(gesture.view, Math.hypot(a.x - b.x, a.y - b.y) / Math.max(1, gesture.distance), gesture.center, size.value.width, size.value.height);
    view.value = boundedView({ ...zoomed, x: zoomed.x + center.x - gesture.center.x, y: zoomed.y + center.y - gesture.center.y }, size.value.width, size.value.height);
    dragging.value = true; return;
  }
  if (!pointer || pointer.id !== event.pointerId) return;
  const at = location(event), dx = at.x - pointer.at.x, dy = at.y - pointer.at.y;
  if (Math.hypot(dx, dy) > 5) pointer.moved = true;
  if (!pointer.moved) return;
  dragging.value = true;
  if (is3d.value && !pointer.pan) camera.value = orbitCamera(pointer.camera, dx, dy);
  else view.value = boundedView({ ...pointer.view, x: pointer.view.x + dx, y: pointer.view.y + dy }, size.value.width, size.value.height);
}
function pointerUp(event) {
  if (!pointer || pointer.id !== event.pointerId) return;
  if (!pointer.moved) {
    const at = location(event);
    selected.value = nearestPoint(is3d.value ? [...viewportPoints.value].sort((a, b) => a.depth - b.depth) : viewportPoints.value, at.x, at.y)?.original || null;
  }
  cancelPointer();
  if (svg.value.hasPointerCapture?.(event.pointerId)) svg.value.releasePointerCapture(event.pointerId);
}
function cancelPointer() { pointer = null; gesture = null; touches.clear(); dragging.value = false; }
function keydown(event) {
  if (["+", "="].includes(event.key)) { event.preventDefault(); zoom(1.5); }
  else if (event.key === "-") { event.preventDefault(); zoom(1 / 1.5); }
  else if (event.key === "Home" || event.key === "0") { event.preventDefault(); reset(); }
  else if (event.key === "Escape") closeSelection();
  else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
    event.preventDefault();
    if (is3d.value && event.altKey) {
      camera.value = orbitCamera(camera.value, event.key === "ArrowLeft" ? -12 : event.key === "ArrowRight" ? 12 : 0, event.key === "ArrowUp" ? -12 : event.key === "ArrowDown" ? 12 : 0);
    } else if (event.shiftKey) {
      const dx = event.key === "ArrowLeft" ? 40 : event.key === "ArrowRight" ? -40 : 0;
      const dy = event.key === "ArrowUp" ? 40 : event.key === "ArrowDown" ? -40 : 0;
      view.value = boundedView({ ...view.value, x: view.value.x + dx, y: view.value.y + dy }, size.value.width, size.value.height);
    } else if (viewportPoints.value.length) {
      const points = viewportPoints.value;
      const current = points.findIndex((point) => point.original === selected.value);
      const direction = ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1;
      selected.value = points[current < 0 ? (direction > 0 ? 0 : points.length - 1) : (current + direction + points.length) % points.length].original;
    }
  } else if (event.key === "Enter" && viewportPoints.value.length) {
    event.preventDefault();
    if (!selected.value) selected.value = viewportPoints.value[0].original;
    else nextTick(() => (popover.value?.querySelector("a") || popover.value?.querySelector("button"))?.focus());
  }
}
watch([() => props.resetKey, () => props.colorBy], reset);
watch(() => props.dimensions, () => setMode(has3d.value));
watch(() => props.points, (points) => {
  if (selected.value && !points.includes(selected.value)) selected.value = null;
  if (isInitialView()) view.value = fitInitial();
});
watch(selected, (point) => emit("selection-change", point));
// Camera navigation dismisses a pinned article, so it never points at a stale
// screen location. Resizing alone keeps the anchor and clamps the HTML dialog.
watch([() => view.value.scale, () => view.value.x, () => view.value.y, () => camera.value.yaw, () => camera.value.pitch], () => closeSelection());
watch([selected, size, locale], () => nextTick(measurePopover), { flush: "post" });
watch(popover, (element) => {
  popoverObserver?.disconnect();
  if (element && typeof ResizeObserver !== "undefined") { popoverObserver = new ResizeObserver(measurePopover); popoverObserver.observe(element); }
}, { flush: "post" });
watch([screenPoints, () => props.colorFor, () => props.colorBy, is3d], queueDraw, { flush: "post" });
onMounted(() => {
  const resize = () => {
    const rect = container.value.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      // Keep a pinned article anchored while its popover adapts to the viewport.
      const untouched = isInitialView();
      size.value = { width: Math.round(rect.width), height: Math.round(rect.height) };
      if (!selected.value) view.value = untouched ? fitInitial() : boundedView(view.value, size.value.width, size.value.height);
    }
  };
  view.value = fitInitial();
  resize();
  queueDraw();
  if (typeof ResizeObserver !== "undefined") { observer = new ResizeObserver(resize); observer.observe(container.value); }
});
onBeforeUnmount(() => { observer?.disconnect(); popoverObserver?.disconnect(); cancelPointer(); cancelAnimationFrame(drawRequest); });
</script>

<style scoped>
.qa-projection-sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; min-height: 0; }
.qa-plot-disclosure { margin-bottom: 12px; font-size: var(--qa-type-meta); color: var(--ink-2); }
.qa-plot-disclosure summary { width: fit-content; cursor: pointer; font-size: var(--qa-type-control); }
.qa-plot-disclosure summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-plot-disclosure .qa-plot-help { margin-top: 8px; }
.qa-point-popover { position: absolute; z-index: 5; box-sizing: border-box; padding: 15px 16px 16px; overflow: auto; overscroll-behavior: contain; border: 1px solid var(--border); border-radius: 9px; background: var(--surface); color: var(--ink); box-shadow: 0 8px 28px #0002; text-align: left; }
.qa-point-popover-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--ink-2); font-size: var(--qa-type-meta); }
.qa-point-popover-heading button { flex-shrink: 0; min-width: 32px; min-height: 32px; padding: 2px 8px; font-size: 20px; line-height: 1; }
.qa-point-popover h3 { margin: 8px 0 14px; font-family: var(--font-sans); font-size: var(--qa-type-subsection-title); font-weight: 600; line-height: var(--qa-leading-body); overflow-wrap: anywhere; }
.qa-article-metadata { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0 0 15px; font-size: var(--qa-type-meta); }
.qa-article-metadata > div { display: flex; gap: 7px; }
.qa-article-metadata dt { color: var(--ink-2); }
.qa-article-metadata dd { margin: 0; overflow-wrap: anywhere; }
.qa-article-link { display: inline-flex; align-items: center; gap: 10px; min-height: 32px; color: var(--accent); font-size: var(--qa-type-control); font-weight: 600; line-height: var(--qa-leading-body); text-decoration: none; }
.qa-article-link:hover { text-decoration: underline; }
.qa-article-link:focus-visible, .qa-point-popover button:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-article-unavailable { margin: 0; color: var(--ink-2); font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
@media (max-width: 600px) { .qa-point-popover { padding: 12px; } .qa-point-popover-heading button { min-width: 44px; min-height: 44px; } .qa-article-link { min-height: 44px; } }
</style>
