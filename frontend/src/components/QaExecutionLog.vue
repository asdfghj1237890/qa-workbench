<template>
  <section class="qa-execution-log" data-testid="qa-full-log" :aria-labelledby="headingId">
    <header>
      <div><h3 :id="headingId">{{ $t('qaLog.title') }}</h3><p>{{ $t('qaLog.separateReport') }}</p></div>
      <button class="qa-button" data-testid="qa-full-log-open" type="button" :aria-expanded="opened" :aria-controls="bodyId" @click="toggle">{{ $t(opened ? 'qaLog.close' : 'qaLog.open') }}</button>
    </header>
    <div v-if="opened" :id="bodyId" class="qa-execution-log-body">
      <div class="qa-execution-log-controls">
        <label v-if="family === 'validations' && steps.length" class="qa-execution-log-scope">{{ $t('qaLog.scope') }}<select v-model="scope" data-testid="qa-full-log-scope"><option value="">{{ $t('qaLog.entireRun') }}</option><option v-for="name in stepNames" :key="name" :value="name">{{ name }}</option></select></label>
        <label class="qa-execution-log-follow"><input v-model="following" data-testid="qa-full-log-follow" type="checkbox" :disabled="!running" />{{ $t('qaLog.follow') }}</label>
        <button v-if="conclusionOffset !== null" class="qa-button" data-testid="qa-full-log-conclusion" type="button" :disabled="loading" @click="showConclusion">{{ $t('qaLog.conclusion') }}</button>
        <button class="qa-button" data-testid="qa-full-log-download" type="button" :disabled="downloading" @click="download">{{ $t('qaLog.download') }}</button>
        <a v-if="downloadLink" class="qa-text-link" data-testid="qa-full-log-download-again" :href="downloadLink.url" :download="downloadLink.filename">{{ $t('qaLog.downloadAgain') }}</a>
      </div>
      <div v-if="downloadLink" class="qa-execution-log-snapshot" data-testid="qa-full-log-download-integrity" role="status">
        <strong>{{ $t('qaLog.downloadSnapshot') }}</strong>
        <p v-if="!downloadIntegrityKnown" class="qa-execution-log-warning">{{ $t('qaLog.downloadUnknown') }}</p>
        <p v-if="downloadLink.integrity.complete === false" class="qa-execution-log-warning">{{ $t('qaLog.downloadCapturing') }}</p>
        <p v-if="downloadLink.integrity.truncated === true" class="qa-execution-log-warning">{{ $t('qaLog.downloadTruncated') }}</p>
        <p v-if="downloadLink.integrity.legacy === true" class="qa-execution-log-warning">{{ $t('qaLog.downloadLegacy') }}</p>
        <p v-if="downloadIntegrityKnown && downloadLink.integrity.complete && !downloadLink.integrity.truncated && !downloadLink.integrity.legacy" class="qa-execution-log-note">{{ $t('qaLog.downloadEnded') }}</p>
      </div>
      <p v-if="running" class="qa-execution-log-note">{{ $t('qaLog.runningNote') }}</p>
      <p v-if="legacy" class="qa-execution-log-warning" data-testid="qa-full-log-legacy">{{ $t('qaLog.legacy') }}</p>
      <p v-if="truncated" class="qa-execution-log-warning" data-testid="qa-full-log-truncated">{{ $t('qaLog.truncated') }}</p>
      <p v-if="readError" class="qa-execution-log-warning" data-testid="qa-full-log-error" role="alert">{{ $t(readError === 'missing' ? 'qaLog.missing' : 'qaLog.readError') }} <button class="qa-text-link" data-testid="qa-full-log-retry" type="button" :disabled="loading" @click="retry">{{ $t('qaLog.retry') }}</button></p>
      <p v-if="downloadError" class="qa-execution-log-warning" role="alert">{{ $t('qaLog.downloadError') }}</p>
      <div class="qa-execution-log-metadata" aria-live="polite"><span v-if="received">{{ $t('qaLog.range', { start: number(windowStart), end: number(nextOffset), total: number(totalBytes) }) }}</span><span v-if="loading">{{ $t('qaLog.loading') }}</span><span v-else-if="received">{{ $t(complete ? 'qaLog.ended' : 'qaLog.capturing') }}</span></div>
      <p v-if="received && !outputText && !loading" class="qa-execution-log-note">{{ $t('qaLog.empty') }}</p>
      <pre ref="output" class="qa-execution-log-output" data-testid="qa-full-log-output" tabindex="0" :aria-label="$t('qaLog.output')" :aria-busy="loading"><code>{{ outputText }}</code></pre>
      <div class="qa-execution-log-pagination">
        <button v-if="windowStart > 0" class="qa-button" data-testid="qa-full-log-earlier" type="button" :disabled="loading" @click="earlier">{{ $t('qaLog.earlier') }}</button>
        <button v-if="hasMore" class="qa-button" data-testid="qa-full-log-more" type="button" :disabled="loading" @click="readNext">{{ $t('qaLog.more') }}</button>
        <button class="qa-button" data-testid="qa-full-log-refresh" type="button" :disabled="loading" @click="readNext">{{ $t('qaLog.refresh') }}</button>
      </div>
      <p class="qa-execution-log-note">{{ $t('qaLog.windowNote') }}</p>
    </div>
  </section>
</template>

<script setup>
import { qaDownloadPrefix } from '../lib/runtime.js';
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from "vue";
import { useI18n } from "vue-i18n";
import { AGENT } from "../lib/runtime.js";
import { apiFetch } from "../lib/qaSession.js";

const props = defineProps({
  family: { type: String, required: true, validator: (value) => ["validations", "evaluations"].includes(value) },
  jobId: { type: String, required: true }, running: { type: Boolean, default: false },
  steps: { type: Array, default: () => [] },
});
const { locale } = useI18n();
const identifier = useId(), headingId = "qa-log-heading-" + identifier, bodyId = "qa-log-body-" + identifier;
const PAGE_BYTES = 65536, WINDOW_BYTES = 262144;
const opened = ref(false), following = ref(false), scope = ref("");
const chunks = ref([]), nextOffset = ref(0), totalBytes = ref(0), hasMore = ref(false);
const complete = ref(false), legacy = ref(false), truncated = ref(false), received = ref(false);
const conclusionOffset = ref(null);
const loading = ref(false), downloading = ref(false), readError = ref(""), downloadError = ref("");
const output = ref(null), downloadLink = ref(null);
const downloadIntegrityKnown = computed(() => downloadLink.value && Object.values(downloadLink.value.integrity).every((value) => typeof value === "boolean"));
const stepNames = computed(() => [...new Set(props.steps.map((step) => typeof step === "string" ? step : step.name).filter(Boolean))]);
const outputText = computed(() => chunks.value.map((chunk) => chunk.text).join(""));
const windowStart = computed(() => chunks.value[0]?.offset || 0);
const number = (value) => new Intl.NumberFormat(locale.value).format(value);
let session = 0, controller = new AbortController(), timer, pendingFinal = false, failedRead;
let anchors = new Set([0]);

function clearDownload() { if (downloadLink.value) URL.revokeObjectURL(downloadLink.value.url); downloadLink.value = null; }
function reset() {
  session++; controller.abort(); controller = new AbortController(); clearTimeout(timer); clearDownload();
  chunks.value = []; nextOffset.value = 0; totalBytes.value = 0; hasMore.value = false;
  complete.value = false; legacy.value = false; truncated.value = false; received.value = false;
  conclusionOffset.value = null;
  loading.value = false; downloading.value = false; readError.value = ""; downloadError.value = "";
  pendingFinal = false; failedRead = null;
  anchors = new Set([0]);
}
function path(download = false, offset = 0, limit = PAGE_BYTES) {
  if (!["validations", "evaluations"].includes(props.family) || !/^[a-zA-Z0-9-]{1,64}$/.test(props.jobId)) throw new Error("schema");
  const query = new URLSearchParams();
  if (!download) { query.set("offset", offset); query.set("limit", limit); }
  if (scope.value && props.family === "validations") query.set("step", scope.value);
  return AGENT + "/qa/" + props.family + "/" + encodeURIComponent(props.jobId) + "/logs" + (download ? "/download" : "") + (query.size ? "?" + query : "");
}
function validPage(page, offset, limit) {
  return page && typeof page.text === "string" && Number.isSafeInteger(page.next_offset) && page.next_offset >= offset
    && Number.isSafeInteger(page.total_bytes) && page.total_bytes >= page.next_offset
    && page.next_offset - offset <= limit && new TextEncoder().encode(page.text).length === page.next_offset - offset
    && ["has_more", "complete", "truncated", "legacy"].every((key) => typeof page[key] === "boolean")
    && (page.conclusion_offset == null || (page.complete && Number.isSafeInteger(page.conclusion_offset) && page.conclusion_offset >= 0 && page.conclusion_offset < page.total_bytes))
    && page.has_more === (page.next_offset < page.total_bytes) && (!page.has_more || page.next_offset > offset);
}
function schedule() {
  clearTimeout(timer);
  if (opened.value && following.value && props.running && !controller.signal.aborted) timer = setTimeout(readNext, 1000);
}
async function read(offset = nextOffset.value, mode = "append", limit = PAGE_BYTES) {
  if (loading.value || !opened.value) return;
  clearTimeout(timer); loading.value = true; readError.value = "";
  const revision = session, parent = controller, readController = new AbortController();
  const abort = () => readController.abort(); parent.signal.addEventListener("abort", abort, { once: true });
  const scrollTop = output.value?.scrollTop || 0;
  let timeout;
  try {
    const page = await Promise.race([
      (async () => { const response = await apiFetch(path(false, offset, limit), { cache: "no-store", signal: readController.signal }); if (!response.ok) throw new Error(response.status === 404 ? "missing" : "request"); return response.json(); })(),
      new Promise((_, reject) => { timeout = setTimeout(() => { readController.abort(); reject(new Error("request")); }, 15000); }),
    ]);
    if (revision !== session || parent.signal.aborted) return;
    if (!validPage(page, offset, limit)) throw new Error("schema");
    const chunk = { offset, end: page.next_offset, text: page.text };
    if (mode === "reset") { chunks.value = [chunk]; anchors.add(offset); }
    else if (offset === nextOffset.value && page.text) {
      const last = chunks.value.at(-1);
      if (last && page.next_offset - last.offset <= PAGE_BYTES) chunks.value = [...chunks.value.slice(0, -1), { ...last, end: page.next_offset, text: last.text + page.text }];
      else { chunks.value = [...chunks.value, chunk]; anchors.add(offset); }
      while (chunks.value.length > 1 && page.next_offset - chunks.value[0].offset > WINDOW_BYTES) chunks.value.shift();
    }
    // Bound cursor metadata as well as rendered bytes, including unusually long
    // streams of tiny chunks. Every retained cursor came from the UTF-8 API.
    if (anchors.size > 512) anchors = new Set([0, ...[...anchors].sort((a, b) => a - b).slice(-511)]);
    nextOffset.value = page.next_offset; totalBytes.value = page.total_bytes; hasMore.value = page.has_more;
    complete.value = page.complete; legacy.value = page.legacy; truncated.value = page.truncated; received.value = true; failedRead = null;
    conclusionOffset.value = page.conclusion_offset ?? null;
    await nextTick();
    if (revision !== session) return;
    if (output.value) output.value.scrollTop = following.value ? output.value.scrollHeight : mode === "reset" ? 0 : scrollTop;
  } catch (failure) {
    if (revision === session && !parent.signal.aborted) { readError.value = failure.message === "missing" ? "missing" : "request"; failedRead = { offset, mode, limit }; }
  } finally {
    clearTimeout(timeout); parent.signal.removeEventListener("abort", abort); readController.abort();
    if (revision === session) { loading.value = false; if (pendingFinal) { pendingFinal = false; readNext(); } else schedule(); }
  }
}
const readNext = () => read(nextOffset.value);
function retry() { if (failedRead) read(failedRead.offset, failedRead.mode, failedRead.limit); else readNext(); }
function earlier() { following.value = false; const offset = Math.max(0, ...[...anchors].filter((value) => value < windowStart.value)); read(offset, "reset"); }
function showConclusion() { if (conclusionOffset.value !== null) { following.value = false; read(conclusionOffset.value, "reset"); } }
function toggle() { if (opened.value) { opened.value = false; reset(); following.value = false; } else { opened.value = true; read(0, "reset"); } }
async function openStep(name = "") {
  if (props.family === "validations" && name && !stepNames.value.includes(name)) return;
  if (scope.value !== name) { opened.value = true; scope.value = name; }
  else if (!opened.value) { opened.value = true; await read(0, "reset"); }
  await nextTick();
  output.value?.focus({ preventScroll: true });
  output.value?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
}
defineExpose({ openStep });
async function download() {
  if (downloading.value) return;
  clearDownload(); downloading.value = true; downloadError.value = "";
  const revision = session, parent = controller;
  try {
    const response = await apiFetch(path(true), { cache: "no-store", signal: parent.signal });
    if (!response.ok) throw new Error("request");
    const integrity = Object.fromEntries(["complete", "truncated", "legacy"].map((key) => {
      const value = response.headers?.get?.("X-Log-" + key[0].toUpperCase() + key.slice(1));
      return [key, value === "true" ? true : value === "false" ? false : null];
    }));
    const blob = await response.blob();
    if (revision !== session || parent.signal.aborted) return;
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = qaDownloadPrefix() + "-" + props.family + "-" + props.jobId + (scope.value ? "-step" : "") + ".txt";
    // These flags belong to these downloaded bytes. A later or delayed page
    // response must not replace this snapshot's integrity state.
    downloadLink.value = { url, filename: link.download, integrity }; document.body.append(link);
    try { link.click(); } finally { link.remove(); }
  } catch { if (revision === session && !parent.signal.aborted) downloadError.value = "request"; }
  finally { if (revision === session) downloading.value = false; }
}
watch([() => props.family, () => props.jobId, scope], () => { reset(); if (opened.value) read(0, "reset"); });
watch(following, (value) => { clearTimeout(timer); if (value) readNext(); });
watch(() => props.running, (value, previous) => {
  if (value) schedule();
  else { clearTimeout(timer); if (previous && opened.value) { if (loading.value) pendingFinal = true; else readNext(); } }
});
onBeforeUnmount(() => { session++; controller.abort(); clearTimeout(timer); clearDownload(); });
</script>

<style scoped>
.qa-execution-log { margin: 22px 0; border: 1px solid var(--border, #50524d); border-radius: 6px; padding: 18px; min-width: 0; }
.qa-execution-log header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.qa-execution-log h3 { margin: 0; font: 500 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans, sans-serif); color: var(--ink); }
.qa-execution-log header p, .qa-execution-log-note, .qa-execution-log-metadata { color: var(--ink-2); font: var(--qa-type-meta)/var(--qa-leading-body) var(--font-sans, sans-serif); margin: 8px 0; }
.qa-execution-log-controls { display: flex; flex-wrap: wrap; gap: 12px 18px; align-items: center; padding-top: 16px; }
.qa-execution-log-scope, .qa-execution-log-follow { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font: var(--qa-type-body)/var(--qa-leading-body) var(--font-sans, sans-serif); }
.qa-execution-log-scope select { max-width: 100%; min-width: 120px; padding: 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); color: var(--ink); font: inherit; }
.qa-execution-log-follow input { accent-color: var(--accent); }
.qa-execution-log-warning { color: var(--ink); border-left: 3px solid var(--accent); padding-left: 12px; font: var(--qa-type-body)/var(--qa-leading-body) var(--font-sans, sans-serif); overflow-wrap: anywhere; }
.qa-execution-log-snapshot { margin: 16px 0; padding: 12px; border: 1px solid var(--border); background: var(--surface-2); font: var(--qa-type-body)/var(--qa-leading-body) var(--font-sans, sans-serif); }
.qa-execution-log-metadata { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.qa-execution-log .qa-execution-log-output { display: block; box-sizing: border-box; padding: 14px; margin: 12px 0; height: 340px; max-height: 52vh; min-height: 160px; overflow: auto; overflow-anchor: none; white-space: pre-wrap; overflow-wrap: anywhere; background: var(--bg); color: var(--ink); border: 1px solid var(--border); border-radius: 4px; font: var(--qa-type-code)/var(--qa-leading-body) var(--font-mono, monospace); }
.qa-execution-log-output code { font: inherit; }
.qa-execution-log-pagination { display: flex; flex-wrap: wrap; gap: 10px; }
.qa-execution-log :is(button, input, select, pre, a):focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (max-width: 600px) { .qa-execution-log { padding: 14px; }.qa-execution-log-scope { width: 100%; }.qa-execution-log-scope select { flex: 1; min-width: 0; } }
</style>
