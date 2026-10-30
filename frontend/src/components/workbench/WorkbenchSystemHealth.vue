<template>
  <div class="wb-heading">
    <p class="wb-eyebrow">
      Observed by the project adapter
    </p><h1>System health</h1><p>Absent observations remain unknown.</p>
  </div><section class="wb-panel">
    <pre>{{ health ? json(health) : 'No health observation.' }}</pre>
  </section>
</template>

<script setup>
defineProps({ health: Object });
const json = value => JSON.stringify(value, null, 2);
</script>
