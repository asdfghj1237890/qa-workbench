<template>
  <div class="wb-app">
    <header class="wb-top">
      <a
        class="wb-brand"
        href="./"
      >{{ state.project.name || ui.adapter.branding.name }}</a><span>QA Workbench</span><code
        v-if="state.sourceSha"
        :title="state.sourceSha"
      >{{ state.sourceSha.slice(0, 12) }}</code><button
        :disabled="state.loading"
        @click="actions.refresh"
      >
        Refresh
      </button>
    </header>
    <div
      v-if="state.error"
      class="wb-error"
      role="alert"
    >
      {{ state.error }}
    </div>
    <div class="wb-layout">
      <aside class="wb-sidebar">
        <h2>Tasks</h2><p class="wb-muted">
          Choose a task, configure it, then explicitly start.
        </p><button
          v-for="task in state.tasks"
          :key="task.id"
          :data-testid="'task-' + task.id"
          :aria-pressed="state.selectedTaskId === task.id"
          @click="actions.chooseTask(task)"
        >
          <span>{{ task.title || task.id }}</span><small>{{ task.paid ? 'Paid · consent required' : 'Offline / configured adapter' }}</small>
        </button><p v-if="!state.loading && !state.tasks.length">
          No tasks provided by this adapter.
        </p><hr><button @click="ui.view = 'history'">
          Execution history <small>{{ state.history.length }} retained runs</small>
        </button><button @click="actions.openHealth">
          System health
        </button><label class="wb-import">Import execution evidence<input
          type="file"
          accept="application/json,.json"
          @change="actions.importEvidence"
        ></label>
      </aside>
      <main class="wb-main">
        <template v-if="ui.view === 'task'">
          <WorkbenchTaskSettings

            v-model:options-text="form.optionsText"
            v-model:max-usd="form.maxUsd"
            v-model:acknowledge-cost="form.acknowledgeCost"
            :selected-task="state.selectedTask"
            :selected-run="state.selectedRun"
            :loading="state.loading"
            :busy="state.busy"
            @start="actions.start" @cancel="actions.cancel"
          />
          <WorkbenchRunEvidence

            v-model:show-logs="ui.showLogs"
            v-model:reviewer="form.reviewer"
            v-model:review-reason="form.reviewReason"
            v-model:review-verdict="form.reviewVerdict"
            v-model:review-rows="form.reviewRows"
            :selected-run="state.selectedRun"
            :evidence="state.evidence"
            :loading="state.loading"
            :log-text="state.logText"
            :log-truncated="state.logTruncated"
            :review-hash="state.reviewHash"
            @refresh="actions.loadRun" @download="actions.downloadReport" @prepare-review="actions.prepareReview" @review="actions.review"
          />
        </template>
        <WorkbenchRunHistory v-else-if="ui.view === 'history'" :history="state.history" @select="actions.selectRun" />
        <WorkbenchSystemHealth v-else :health="state.health" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { useWorkbenchPanel } from './composables/useWorkbenchPanel.js';
import WorkbenchTaskSettings from './components/workbench/WorkbenchTaskSettings.vue';
import WorkbenchRunEvidence from './components/workbench/WorkbenchRunEvidence.vue';
import WorkbenchRunHistory from './components/workbench/WorkbenchRunHistory.vue';
import WorkbenchSystemHealth from './components/workbench/WorkbenchSystemHealth.vue';
const props = defineProps({ client: Object });
const { state, form, ui, actions } = useWorkbenchPanel(props);
</script>
