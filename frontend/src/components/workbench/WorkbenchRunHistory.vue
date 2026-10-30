<template>
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
      @click="$emit('select', run)"
    >
      <span><strong>{{ run.task_id }}</strong><small>{{ run.created_at }} · {{ run.id }}</small></span><span>{{ run.status }}<small>Structural: {{ run.structural_status || 'not_run' }} · Review: {{ run.semantic_status || 'pending_review' }}</small></span>
    </button>
  </section>
</template>

<script setup>
defineProps({ history: { type: Array, required: true } });
defineEmits(['select']);
</script>
