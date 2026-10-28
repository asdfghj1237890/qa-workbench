<template>
  <div class="wb-app">
    <header class="wb-top">
      <a
        class="wb-brand"
        href="./"
      >{{ project.name || adapter.branding.name }}</a><span>QA Workbench</span><code
        v-if="sourceSha"
        :title="sourceSha"
      >{{ sourceSha.slice(0, 12) }}</code><button
        :disabled="loading"
        @click="refresh"
      >
        Refresh
      </button>
    </header>
    <div
      v-if="error"
      class="wb-error"
      role="alert"
    >
      {{ error }}
    </div>
    <div class="wb-layout">
      <aside class="wb-sidebar">
        <h2>Tasks</h2><p class="wb-muted">
          Choose a task, configure it, then explicitly start.
        </p><button
          v-for="task in tasks"
          :key="task.id"
          :data-testid="'task-' + task.id"
          :aria-pressed="selectedTaskId === task.id"
          @click="chooseTask(task)"
        >
          <span>{{ task.title || task.id }}</span><small>{{ task.paid ? 'Paid · consent required' : 'Offline / configured adapter' }}</small>
        </button><p v-if="!loading && !tasks.length">
          No tasks provided by this adapter.
        </p><hr><button @click="view = 'history'">
          Execution history <small>{{ history.length }} retained runs</small>
        </button><button @click="openHealth">
          System health
        </button><label class="wb-import">Import execution evidence<input
          type="file"
          accept="application/json,.json"
          @change="importEvidence"
        ></label>
      </aside>
      <main class="wb-main">
        <template v-if="view === 'task'">
          <div class="wb-heading">
            <p class="wb-eyebrow">
              Configure / Execute / Review
            </p><h1>{{ selectedTask?.title || 'Select a task' }}</h1><p>{{ selectedTask?.description }}</p>
          </div>
          <section
            v-if="selectedTask"
            class="wb-panel"
          >
            <h2>Run settings</h2><details v-if="selectedTask.input_schema && Object.keys(selectedTask.input_schema).length">
              <summary>Adapter input schema</summary><pre>{{ json(selectedTask.input_schema) }}</pre>
            </details><label>Options (JSON object)<textarea
              v-model="optionsText"
              data-testid="task-options"
              rows="5"
              spellcheck="false"
            /></label><template v-if="selectedTask.paid">
              <label>Maximum estimated cost (USD)<input
                v-model.number="maxUsd"
                data-testid="task-budget"
                type="number"
                min="0.01"
                step="0.01"
              ></label><label class="wb-check"><input
                v-model="acknowledgeCost"
                data-testid="task-consent"
                type="checkbox"
              >I authorize this paid run up to the configured budget.</label>
            </template><p
              v-if="selectedTask.requires_review"
              class="wb-notice"
            >
              A completed run still requires an independent evidence review.
            </p><div class="wb-actions">
              <button
                class="wb-primary"
                data-testid="start-run"
                :disabled="loading || busy || (selectedTask.paid && (!acknowledgeCost || !(maxUsd > 0)))"
                @click="start"
              >
                Start run
              </button><button
                v-if="activeRun(selectedRun)"
                :disabled="loading"
                @click="cancel"
              >
                Cancel current run
              </button>
            </div>
          </section>
          <section
            v-if="selectedRun"
            class="wb-panel"
            data-testid="run-evidence"
          >
            <div class="wb-section-head">
              <h2>Execution evidence</h2><strong :class="['wb-status', selectedRun.status]">{{ selectedRun.status }}</strong>
            </div><dl class="wb-facts">
              <div><dt>Run</dt><dd><code>{{ selectedRun.id }}</code></dd></div><div><dt>Structural checks</dt><dd>{{ evidence.structural }}</dd></div><div><dt>Semantic review</dt><dd>{{ evidence.semantic }}</dd></div><div><dt>Quality</dt><dd>{{ evidence.quality }}</dd></div><div><dt>Source revision</dt><dd>{{ evidence.revision }} <code>{{ selectedRun.source_sha || 'unknown' }}</code></dd></div><div><dt>Evidence kind</dt><dd>{{ selectedRun.evidence_kind || 'unknown' }}</dd></div>
            </dl><p
              v-if="evidence.revision !== 'current'"
              class="wb-notice"
            >
              This evidence does not establish the current release's quality.
            </p><ul v-if="selectedRun.gaps?.length">
              <li
                v-for="gap in selectedRun.gaps"
                :key="gap"
              >
                {{ gap }}
              </li>
            </ul><p
              v-if="selectedRun.error"
              role="alert"
            >
              {{ selectedRun.error }}
            </p><div class="wb-actions">
              <button @click="loadRun(selectedRun.id)">
                Refresh evidence
              </button><button
                :disabled="!selectedRun.report_available"
                @click="downloadReport"
              >
                Download report
              </button><button @click="showLogs = !showLogs">
                {{ showLogs ? 'Hide' : 'Show' }} logs
              </button>
            </div><pre
              v-if="showLogs"
              class="wb-log"
              tabindex="0"
              aria-label="Execution logs"
            >{{ logText || 'No captured output.' }}</pre><p
              v-if="logTruncated"
              class="wb-notice"
            >
              Log capture is truncated; the original report remains separate evidence.
            </p>
            <details
              v-if="selectedRun.report_available"
              class="wb-review"
            >
              <summary>Submit an evidence-bound review</summary><p>Use the exact report hash. Reviewer and reason must identify the actual review; structural completion alone is insufficient.</p><label>Reviewer<input
                v-model="reviewer"
                autocomplete="name"
              ></label><label>Evidence-based reason<textarea
                v-model="reviewReason"
                rows="3"
              /></label><label>Verdict<select v-model="reviewVerdict"><option value="failed">Failed</option><option value="passed">Passed</option></select></label><button
                :disabled="loading"
                @click="prepareReview"
              >
                Load exact row hashes for review
              </button><p
                v-if="reviewHash"
                class="wb-muted"
              >
                Report SHA-256: <code>{{ reviewHash }}</code>
              </p><label>Case reviews (JSON array of row_sha256, verdict, reason)<textarea
                v-model="reviewRows"
                rows="3"
                spellcheck="false"
              /></label><button
                :disabled="loading || !reviewer.trim() || !reviewReason.trim()"
                @click="review"
              >
                Submit review
              </button>
            </details>
          </section><section
            v-else
            class="wb-panel wb-empty"
          >
            <h2>No execution selected</h2><p>Task selection only opens settings. No run has started.</p>
          </section>
        </template>
        <template v-else-if="view === 'history'">
          <div class="wb-heading">
            <p class="wb-eyebrow">
              Persisted evidence
            </p><h1>Execution history</h1><p>Historical runs retain their original revision, report hashes and review state.</p>
          </div><section class="wb-panel">
            <p v-if="!history.length">
              No retained executions.
            </p><button
              v-for="run in history"
              :key="run.id"
              class="wb-history"
              @click="selectRun(run)"
            >
              <span><strong>{{ run.task_id }}</strong><small>{{ run.created_at }} · {{ run.id }}</small></span><span>{{ run.status }}<small>Structural: {{ run.structural_status || 'not_run' }} · Review: {{ run.semantic_status || 'pending_review' }}</small></span>
            </button>
          </section>
        </template>
        <template v-else>
          <div class="wb-heading">
            <p class="wb-eyebrow">
              Observed by the project adapter
            </p><h1>System health</h1><p>Absent observations remain unknown.</p>
          </div><section class="wb-panel">
            <pre>{{ health ? json(health) : 'No health observation.' }}</pre>
          </section>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { getQaAdapter } from './lib/runtime.js';
import { activeRun, createWorkbenchClient, runEvidence } from './lib/workbenchApi.js';
const props = defineProps({ client: Object });
const adapter = getQaAdapter();
const client = props.client || createWorkbenchClient({ apiBase: adapter.apiBase, request: adapter.fetch });
const project = ref({}), tasks = ref([]), history = ref([]), sourceSha = ref(null), selectedTaskId = ref(''), selectedRun = ref(null);
const optionsText = ref('{}'), maxUsd = ref(1), acknowledgeCost = ref(false), view = ref('task'), error = ref(''), loading = ref(false), health = ref(null);
const logText = ref(''), logOffset = ref(0), logTruncated = ref(false), showLogs = ref(true);
const reviewer = ref(''), reviewReason = ref(''), reviewVerdict = ref('failed'), reviewRows = ref('[]'), reviewHash = ref('');
const lifecycle = new AbortController();
let timer, selectionEpoch = 0;
const selectedTask = computed(() => tasks.value.find(task => task.id === selectedTaskId.value));
const busy = computed(() => history.value.some(activeRun));
const evidence = computed(() => runEvidence(selectedRun.value, sourceSha.value));
const json = value => JSON.stringify(value, null, 2);
const jobOf = value => value?.job || value;
function fail(failure) { if (!lifecycle.signal.aborted && failure?.name !== 'AbortError') error.value = failure.message || 'Request failed'; }
async function refresh() {
  loading.value = true; error.value = '';
  try { const [capabilities, runs] = await Promise.all([client.capabilities(lifecycle.signal), client.history(lifecycle.signal)]); if (lifecycle.signal.aborted) return; project.value = capabilities.project || {}; sourceSha.value = capabilities.source_sha || project.value.source_sha || null; tasks.value = capabilities.tasks || []; history.value = runs.runs || []; if (!selectedTaskId.value) selectedTaskId.value = tasks.value[0]?.id || ''; }
  catch (failure) { fail(failure); } finally { loading.value = false; }
}
function chooseTask(task) { selectionEpoch++; selectedTaskId.value = task.id; selectedRun.value = null; acknowledgeCost.value = false; optionsText.value = json(task.default_options || {}); logText.value = ''; logOffset.value = 0; view.value = 'task'; error.value = ''; }
function resetLogs() { logText.value = ''; logOffset.value = 0; logTruncated.value = false; reviewer.value = ''; reviewReason.value = ''; reviewRows.value = '[]'; reviewHash.value = ''; }
async function loadRun(id) {
  const epoch = selectionEpoch;
  try { const result = jobOf(await client.run(id, lifecycle.signal)); if (lifecycle.signal.aborted || epoch !== selectionEpoch || selectedRun.value?.id !== id) return; selectedRun.value = result; const logs = await client.logs(id, logOffset.value, lifecycle.signal); if (epoch !== selectionEpoch || selectedRun.value?.id !== id) return; logText.value += logs.text || ''; logOffset.value = logs.next_offset ?? logOffset.value; logTruncated.value = logs.truncated === true; }
  catch (failure) { fail(failure); }
}
async function selectRun(run) { selectionEpoch++; selectedTaskId.value = run.task_id; selectedRun.value = run; acknowledgeCost.value = false; resetLogs(); view.value = 'task'; await loadRun(run.id); }
async function start() {
  if (!selectedTask.value || loading.value || busy.value) return;
  loading.value = true; error.value = ''; const epoch = ++selectionEpoch;
  try { const options = JSON.parse(optionsText.value); const result = jobOf(await client.start(selectedTask.value, { options, acknowledgeCost: acknowledgeCost.value, maxUsd: maxUsd.value }, lifecycle.signal)); acknowledgeCost.value = false; if (epoch !== selectionEpoch || lifecycle.signal.aborted) return; selectedRun.value = result; resetLogs(); await refresh(); await loadRun(result.id); }
  catch (failure) { fail(failure); } finally { loading.value = false; }
}
async function cancel() { if (!selectedRun.value || !activeRun(selectedRun.value)) return; try { selectedRun.value = jobOf(await client.cancel(selectedRun.value.id, lifecycle.signal)); await refresh(); } catch (failure) { fail(failure); } }
function save(filename, value) { const url = URL.createObjectURL(new Blob([json(value)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
async function downloadReport() { const id = selectedRun.value?.id; if (!id) return; try { const report = await client.report(id, lifecycle.signal); save(adapter.id + '-run-' + id.replace(/[^a-z0-9-]/gi, '') + '.json', report); } catch (failure) { fail(failure); } }
async function prepareReview() { const id = selectedRun.value?.id; if (!id) return; loading.value = true; error.value = ''; try { const artifact = await client.report(id, lifecycle.signal); if (selectedRun.value?.id !== id) return; reviewHash.value = artifact.report_sha256; reviewRows.value = json((artifact.review_contract?.rows || []).map(row => ({ row_sha256: row.row_sha256, verdict: '', reason: '' }))); } catch (failure) { fail(failure); } finally { loading.value = false; } }
async function review() { const id = selectedRun.value?.id; if (!id) return; loading.value = true; error.value = ''; try { const artifact = await client.report(id, lifecycle.signal); if (selectedRun.value?.id !== id) return; const rows = JSON.parse(reviewRows.value); if (!Array.isArray(rows)) throw new TypeError('Case reviews must be a JSON array'); await client.review(id, { report_sha256: artifact.report_sha256, reviewer: reviewer.value.trim(), reason: reviewReason.value.trim(), verdict: reviewVerdict.value, rows }, lifecycle.signal); await loadRun(id); await refresh(); } catch (failure) { fail(failure); } finally { loading.value = false; } }
async function importEvidence(event) { const file = event.target.files?.[0]; if (!file) return; error.value = ''; loading.value = true; try { if (file.size > 8 * 1024 * 1024) throw new Error('Import exceeds 8 MiB'); const artifact = JSON.parse(await file.text()); const result = jobOf(await client.importRun(artifact, lifecycle.signal)); await refresh(); if (result?.id) await selectRun(result); } catch (failure) { fail(failure); } finally { loading.value = false; event.target.value = ''; } }
async function openHealth() { view.value = 'health'; error.value = ''; try { health.value = await client.health(lifecycle.signal); } catch (failure) { fail(failure); } }
async function poll() { if (lifecycle.signal.aborted) return; if (!loading.value && selectedRun.value && activeRun(selectedRun.value)) { await loadRun(selectedRun.value.id); await refresh(); } timer = setTimeout(poll, 2000); }
onMounted(async () => { await refresh(); if (!lifecycle.signal.aborted) timer = setTimeout(poll, 2000); });
onBeforeUnmount(() => { lifecycle.abort(); clearTimeout(timer); });
</script>
