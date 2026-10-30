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
          <WorkbenchTaskSettings

            v-model:options-text="optionsText"
            v-model:max-usd="maxUsd"
            v-model:acknowledge-cost="acknowledgeCost"
            :selected-task="selectedTask"
            :selected-run="selectedRun"
            :loading="loading"
            :busy="busy"
            @start="start" @cancel="cancel"
          />
          <WorkbenchRunEvidence

            v-model:show-logs="showLogs"
            v-model:reviewer="reviewer"
            v-model:review-reason="reviewReason"
            v-model:review-verdict="reviewVerdict"
            v-model:review-rows="reviewRows"
            :selected-run="selectedRun"
            :evidence="evidence"
            :loading="loading"
            :log-text="logText"
            :log-truncated="logTruncated"
            :review-hash="reviewHash"
            @refresh="loadRun" @download="downloadReport" @prepare-review="prepareReview" @review="review"
          />
        </template>
        <WorkbenchRunHistory v-else-if="view === 'history'" :history="history" @select="selectRun" />
        <WorkbenchSystemHealth v-else :health="health" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { useWorkbench } from './composables/useWorkbench.js';
import WorkbenchTaskSettings from './components/workbench/WorkbenchTaskSettings.vue';
import WorkbenchRunEvidence from './components/workbench/WorkbenchRunEvidence.vue';
import WorkbenchRunHistory from './components/workbench/WorkbenchRunHistory.vue';
import WorkbenchSystemHealth from './components/workbench/WorkbenchSystemHealth.vue';
const props = defineProps({ client: Object });
const {
  adapter, project, sourceSha, loading, refresh,
  error, tasks, selectedTaskId, chooseTask, view,
  history, openHealth, importEvidence, optionsText, maxUsd,
  acknowledgeCost, selectedTask, selectedRun, busy, start,
  cancel, showLogs, reviewer, reviewReason, reviewVerdict,
  reviewRows, evidence, logText, logTruncated, reviewHash,
  loadRun, downloadReport, prepareReview, review, selectRun,
  health
} = useWorkbench(props);
</script>
