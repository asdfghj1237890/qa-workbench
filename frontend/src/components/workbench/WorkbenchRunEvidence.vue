<template>
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
      <button @click="$emit('refresh', selectedRun.id)">
        Refresh evidence
      </button><button
        :disabled="!selectedRun.report_available"
        @click="$emit('download')"
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
        @click="$emit('prepare-review')"
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
        @click="$emit('review')"
      >
        Submit review
      </button>
    </details>
  </section>
  <section
    v-else
    class="wb-panel wb-empty"
  >
    <h2>No execution selected</h2><p>Task selection only opens settings. No run has started.</p>
  </section>
</template>

<script setup>
defineProps({ selectedRun: Object, evidence: { type: Object, required: true }, loading: Boolean, logText: String, logTruncated: Boolean, reviewHash: String });
defineEmits(['refresh', 'download', 'prepare-review', 'review']);
const showLogs = defineModel('showLogs', { type: Boolean, default: true });
const reviewer = defineModel('reviewer', { type: String, default: '' });
const reviewReason = defineModel('reviewReason', { type: String, default: '' });
const reviewVerdict = defineModel('reviewVerdict', { type: String, default: 'failed' });
const reviewRows = defineModel('reviewRows', { type: String, default: '[]' });
</script>
