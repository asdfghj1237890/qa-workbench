<template>
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
        @click="$emit('start')"
      >
        Start run
      </button><button
        v-if="activeRun(selectedRun)"
        :disabled="loading"
        @click="$emit('cancel')"
      >
        Cancel current run
      </button>
    </div>
  </section>
</template>

<script setup>
import { activeRun } from '../../lib/workbenchApi.js';
defineProps({ selectedTask: Object, selectedRun: Object, loading: Boolean, busy: Boolean });
defineEmits(['start', 'cancel']);
const optionsText = defineModel('optionsText', { type: String, default: '{}' });
const maxUsd = defineModel('maxUsd', { type: [Number, String], default: 1 });
const acknowledgeCost = defineModel('acknowledgeCost', { type: Boolean, default: false });
const json = value => JSON.stringify(value, null, 2);
</script>
