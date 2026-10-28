<template>
  <section v-if="workbench" class="qa-validation-workbench qa-guided-validation" :class="{ 'qa-guided-showing-result': workspacePhase !== 'settings' }" aria-labelledby="qa-testing-title" data-testid="qa-validation-panel">
    <header v-if="workspacePhase === 'settings'" class="qa-guided-heading">
      <div><h1 id="qa-testing-title">{{ $t('qaRunFlow.settings') }}</h1><p>{{ $t('qaFlowValidation.titles.' + mode) }} · {{ $t('qaValidation.modes.' + mode + '.scope') }}</p></div>
      <button class="qa-button" :disabled="loading" @click="load"><QaIcon name="refresh" aria-hidden="true" />{{ $t('qaValidation.refresh') }}</button>
    </header>
    <div v-if="workspacePhase === 'settings' && job" class="qa-guided-tabs">
      <button v-if="job" class="qa-button" :aria-pressed="workspacePhase !== 'settings'" data-testid="qa-validation-latest" @click="workspacePhase = runningJob ? 'execution' : 'evidence'">{{ $t(runningJob ? 'qaFlowValidation.viewProgress' : 'qaFlowValidation.viewLatest') }}</button>
    </div>
    <p v-if="error" class="qa-state qa-error" role="alert">{{ $t('qaValidation.errors.' + error) }}</p>
    <p v-if="busy && !runningJob" class="qa-state" role="status">{{ $t('qaValidation.busy') }}</p>

    <div class="qa-guided-layout">
      <div class="qa-guided-main">
        <form v-show="workspacePhase === 'settings'" class="qa-guided-card qa-guided-form" @submit.prevent="start(selectedSuite)">
          <div class="qa-guided-card-head"><div><h2>{{ $t('qaRunFlow.configuration') }}</h2><p>{{ $t(costRequired ? 'qaFlowValidation.paidHint' : 'qaFlowValidation.freeHint') }}</p></div></div>
          <div v-if="isOffline" class="qa-guided-field">
            <label for="qa-validation-suite">{{ $t('qaFlowValidation.scopeLabel') }}</label>
            <select id="qa-validation-suite" v-model="selectedSuite" data-testid="qa-validation-suite" :disabled="loading || Boolean(runningJob)"><option v-for="suite in selectedMode.suites" :key="suite" :value="suite">{{ $t('qaValidation.suites.' + suite) }}</option></select>
            <div class="qa-guided-scope-list"><details v-for="item in selectedEvidence" :key="item.id"><summary>{{ $t('observatory.evidence.' + item.id + '.title') }} <QaIcon name="expand_more" aria-hidden="true" /></summary><p>{{ $t('observatory.evidence.' + item.id + '.scope') }}</p><p class="qa-gap">{{ $t('observatory.evidence.' + item.id + '.gap') }}</p><div class="qa-evidence-links"><a v-for="link in item.links" :key="link.path" :href="repository + '/blob/main/' + link.path" target="_blank" rel="noopener noreferrer">{{ link.label }} ↗</a></div></details></div>
          </div>
          <div v-else class="qa-guided-plan"><h3>{{ $t('qaValidation.fixedPlan') }}</h3><ol><li v-for="stage in modeStages" :key="stage">{{ $t('qaValidation.stages.' + stage) }}</li></ol><p class="qa-gap">{{ $t('qaValidation.selectionIsNotEvidence') }}</p></div>
          <div v-if="costRequired" class="qa-validation-cost">
            <label for="qa-validation-budget">{{ $t('qaLive.budget') }}</label><input id="qa-validation-budget" v-model.number="budget" data-testid="qa-validation-budget" type="number" min="0.01" :max="budgetCeiling" step="0.01" inputmode="decimal" :disabled="loading || Boolean(runningJob)" :aria-invalid="!budgetValid" aria-describedby="qa-validation-budget-note" />
            <p id="qa-validation-budget-note" class="qa-small">{{ $t('qaValidation.budgetNote', { n: budgetCeiling || '—', reserve: money(selectedMode.pricing?.reserved_estimated_usd) }) }}</p>
            <details v-if="selectedMode.pricing" class="qa-guided-pricing"><summary>{{ $t('qaFlowValidation.pricingDetails') }}</summary><p>{{ $t('qaValidation.models', { main: selectedMode.pricing.model, judge: selectedMode.pricing.judge_model, embedding: selectedMode.pricing.embedding_model }) }}</p><p v-for="kind in ['main', 'judge', 'embedding']" :key="kind">{{ $t('qaValidation.pricing.' + kind) }} · {{ $t('qaValidation.rate', { input: money(selectedMode.pricing[kind]?.input_per_million), output: kind === 'embedding' ? '—' : money(selectedMode.pricing[kind]?.output_per_million) }) }}</p></details>
            <p v-if="selectedMode.limits.deadline_seconds" class="qa-small">{{ $t('qaValidation.executionLimits', { seconds: selectedMode.limits.deadline_seconds, turns: selectedMode.limits.turns || '—' }) }}</p>
            <label class="qa-validation-ack"><input v-model="acknowledged" data-testid="qa-validation-ack" type="checkbox" :disabled="loading || Boolean(runningJob)" /><span>{{ $t('qaValidation.acknowledge') }}</span></label>
            <div v-if="turnstileRequired" class="qa-validation-security"><p class="qa-small">{{ $t(tsSitekey ? 'qaValidation.turnstile' : 'qaValidation.turnstileUnavailable') }}</p><div ref="tsBox" class="qa-validation-turnstile"></div></div>
          </div>
          <div v-if="!available && !loading" class="qa-guided-blocked" role="status"><QaIcon name="info" aria-hidden="true" /><div><strong>{{ unavailableReason }}</strong><p>{{ $t('qaFlowValidation.unavailableHint') }}</p><details v-if="selectedMode.reason" data-testid="qa-validation-reason"><summary>{{ $t('qaFlowValidation.technicalDetails') }}</summary><code>{{ selectedMode.reason }}</code></details></div></div>
          <div class="qa-guided-start"><button class="qa-button qa-primary" type="submit" data-testid="qa-run-all" :disabled="cannotStart"><QaIcon name="play_arrow" aria-hidden="true" />{{ $t('qaFlowValidation.start.' + mode) }}</button><p v-if="startReason" class="qa-small" role="status" data-testid="qa-validation-start-reason">{{ startReason }}</p><p v-else class="qa-small">{{ $t('qaFlowValidation.explicitStart') }}</p></div>
        </form>

        <article v-if="job" v-show="workspacePhase !== 'settings'" class="qa-guided-result" data-testid="qa-validation-result" :aria-busy="runningJob && !syncIssue">
          <h1 v-if="workspacePhase !== 'settings'" id="qa-testing-title" class="qa-faithful-result-title">{{ $t(runningJob ? 'qaRunFlow.running' : 'qaRunFlow.results') }}</h1>
          <p class="qa-faithful-result-subtitle">{{ $t('qaFlowValidation.titles.' + mode) }}</p>
          <QaReleaseDecision v-if="!runningJob || syncIssue" :job="job" :source-sha="capabilities?.source_sha" :kind="mode" :capabilities="{ ...capabilities, recent }" :sync-issue="syncIssue" />
          <p v-else class="qa-small" role="status">{{ $t('qaRunFlow.summaries.running') }}</p>
          <div class="qa-run-actions"><span class="qa-run-execution-status" data-testid="qa-validation-execution-status">{{ $t('qaRunFlow.executionStatus') }} <strong role="status">{{ syncIssue ? 'UNKNOWN' : executionStatus }}</strong></span><button v-if="runningJob" class="qa-button" data-testid="qa-cancel-validation" :disabled="cancelling" @click="cancel">{{ $t('qaValidation.cancel') }}</button><button v-else class="qa-button" data-testid="qa-validation-settings" @click="workspacePhase = 'settings'"><QaIcon name="tune" aria-hidden="true" />{{ $t('qaRunFlow.backToSettings') }}</button></div>
          <p v-if="syncIssue" class="qa-state" data-testid="qa-validation-sync-issue" role="status"><strong>{{ $t('qaValidation.syncInterrupted') }}</strong><span>{{ $t(missingJob ? 'qaValidation.syncMissing' : 'qaValidation.syncRetry', { status: statusLabel(job.status, job.mode) }) }}</span></p>
          <p v-if="job.error" class="qa-state" role="alert">{{ $t('qaLive.executionError') }}: {{ logCaptureErrorKey(job.error) ? $t(logCaptureErrorKey(job.error)) : job.error }}</p>
          <button v-if="runningJob || syncIssue" class="qa-button qa-faithful-refresh" :disabled="loading" @click="load"><QaIcon name="refresh" aria-hidden="true" />{{ $t('qaValidation.refresh') }}</button>
          <div class="qa-faithful-run-metadata" :data-completed="finishedSteps" :data-total="job.total_steps"><span v-if="job.started_at || job.finished_at"><QaIcon name="calendar_today" aria-hidden="true" /><time :datetime="job.started_at || job.finished_at">{{ resultTimestamp(job.started_at || job.finished_at) }}</time> · QA</span><span><QaIcon name="format_list_bulleted" aria-hidden="true" />{{ $t('qaFaithfulValidation.stepsProgress', { n: finishedSteps, total: job.total_steps }) }} · {{ number(progressPercent) }}%</span><span v-if="measuredCounts" class="qa-faithful-visually-hidden">{{ $t('qaFlowValidation.totalTests', { n: number(measuredCounts.tests) }) }}</span></div>
          <div v-if="runningJob" class="qa-validation-progress"><progress :value="finishedSteps" :max="Math.max(1, job.total_steps)" :aria-label="$t('qaValidation.result')"></progress><span>{{ number(progressPercent) }}%</span></div>
          <div v-if="outcomeCounts" class="qa-guided-outcomes" :aria-label="$t('qaFlowValidation.observedCounts')"><div v-for="kind in ['passed', 'failed', 'errors', 'skipped']" :key="kind" :class="'qa-outcome-' + kind"><strong>{{ number(outcomeCounts[kind]) }}</strong><span>{{ { passed: 'PASS', failed: 'FAIL', errors: 'ERROR', skipped: 'SKIP' }[kind] }}</span></div></div>
          <p v-if="!isOffline && outcomeCounts" class="qa-small qa-guided-measurement">{{ $t('qaFlowValidation.observedCounts') }}</p>
          <QaExecutionLog ref="executionLog" family="validations" :job-id="job.id" :running="Boolean(runningJob)" :steps="job.steps" />
          <h3 class="qa-guided-evidence-title">{{ $t('qaEvidence.title') }}</h3>
          <p class="qa-evidence-intro">{{ $t('qaEvidence.intro') }} {{ $t('qaEvidence.resultMeaning') }}</p>
          <div class="qa-faithful-table-wrap" role="region" :aria-label="$t('qaEvidence.title')" tabindex="0">
            <table class="qa-guided-steps qa-faithful-evidence-table">
              <caption class="qa-faithful-visually-hidden">{{ $t('qaEvidence.title') }}</caption><colgroup><col class="qa-faithful-col-index" /><col class="qa-faithful-col-check" /><col class="qa-faithful-col-result" /><col class="qa-faithful-col-count" /><col class="qa-faithful-col-log" /></colgroup><thead><tr><th scope="col">#</th><th scope="col">{{ $t('qaEvidence.columns.item') }}</th><th scope="col">{{ $t('qaEvidence.columns.status') }}</th><th scope="col">{{ $t(isOffline ? 'qaFlowValidation.tests' : 'qaEvidence.columns.count') }}</th><th scope="col">{{ $t('qaEvidence.columns.details') }}</th></tr></thead>
              <tbody v-for="(step, index) in job.steps" :key="index">
                <tr class="qa-guided-step-row"><td class="qa-guided-step-index">{{ index + 1 }}</td><th scope="row">{{ stepTitle(step.name) }}</th><td><span class="qa-guided-step-status" :data-status="step.status"><QaIcon :name="step.status === 'completed' ? 'check_circle' : ['failed', 'timed_out'].includes(step.status) ? 'error' : 'pending'" aria-hidden="true" />{{ stepStatusLabel(step.status) }}</span></td><td>{{ isOffline ? (hasCounts(step) ? number(step.tests) : '—') : number(step.checks?.length) }}</td><td><button class="qa-faithful-log-button" :aria-expanded="expandedSteps.has(index)" :aria-controls="'qa-validation-step-' + index" :aria-label="$t('qaFlowValidation.viewEvidence') + ': ' + stepTitle(step.name)" @click="toggleStep(index)"><QaIcon name="description" aria-hidden="true" />{{ $t('qaEvidence.detailsAction') }}<QaIcon :name="expandedSteps.has(index) ? 'expand_more' : 'chevron_right'" aria-hidden="true" /></button></td></tr>
                <tr v-show="expandedSteps.has(index) || Boolean(runningJob && (step.progress || !hasCounts(step)))" class="qa-faithful-detail-row">
                  <td colspan="5">
                    <div :id="'qa-validation-step-' + index" class="qa-guided-step-details">
                      <p class="qa-evidence-explainer">{{ stepDescription(step.name) }}</p>
                      <p class="qa-evidence-result-note">{{ stepResultDescription(step.status) }}</p>
                      <div v-if="isOffline && step.progress" class="qa-pytest-progress" data-testid="qa-pytest-progress"><p>{{ $t('qaValidation.testPhase.' + step.progress.phase) }}<span v-if="step.progress.collected !== null"> · {{ $t('qaValidation.testProgress', { n: number(step.progress.completed), total: number(step.progress.collected) }) }}</span></p><p v-if="step.progress.current_test" class="qa-current-test">{{ $t('qaValidation.currentTest', { name: step.progress.current_test }) }}</p><p v-if="step.progress.completed || step.progress.errors">{{ $t('qaValidation.testOutcomes', { passed: number(step.progress.passed), failed: number(step.progress.failed), errors: number(step.progress.errors), skipped: number(step.progress.skipped) }) }}</p><p v-if="step.progress.collection_errors">{{ $t('qaValidation.collectionErrors', { n: number(step.progress.collection_errors) }) }}</p></div>
                      <p v-if="isOffline && !hasCounts(step)" class="qa-guided-step-detail">{{ $t(step.status === 'pending' ? 'qaValidation.stepPending' : 'qaValidation.unmeasured') }}</p>
                      <p v-if="isOffline && hasCounts(step)" class="qa-guided-step-detail">{{ $t('qaValidation.counts', { tests: number(step.tests), failed: number(step.failed + step.errors), skipped: number(step.skipped) }) }}</p>
                      <details class="qa-evidence-technical">
                        <summary>{{ $t('qaEvidence.technicalDetails') }}</summary>
                        <p class="qa-guided-raw-step"><span>{{ $t('qaFlowValidation.rawStepName') }}</span><code>{{ step.name }}</code></p>
                        <ul v-if="!isOffline && step.checks?.length" class="qa-measured-checks"><li v-for="(check, checkIndex) in step.checks" :key="checkIndex"><strong>{{ check.name }}</strong><span>{{ $t('qaValidation.checkStatus.' + check.status) }}</span><pre>{{ evidenceText(check.evidence) }}</pre></li></ul>
                        <details v-if="!isOffline && Object.keys(step.evidence || {}).length"><summary>{{ $t('qaValidation.stepEvidence') }}</summary><pre>{{ evidenceText(step.evidence) }}</pre></details>
                        <div v-if="step.log"><h4>{{ $t('qaLog.summary') }}</h4><pre>{{ step.log }}</pre><small v-if="step.log_truncated">{{ $t('qaValidation.truncated') }}</small></div>
                      </details>
                      <button class="qa-text-link" type="button" data-testid="qa-step-full-log" @click="executionLog?.openStep(step.name)">{{ $t('qaLog.stepOpen') }}</button>
                      <p v-if="!isOffline && !step.checks?.length" class="qa-small">{{ $t('qaValidation.noChecks') }}</p>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!isOffline && job.steps.length" class="qa-evidence-count-hint">{{ $t('qaEvidence.checkCountHint') }}</p>
          <p v-if="!job.steps.length" class="qa-state">{{ $t('qaFlowValidation.waitingForSteps') }}</p>
          <QaEvidenceScope v-if="!isOffline" :covered="job.covered" :gaps="job.gaps" />
        </article>
        <div v-else class="qa-guided-not-run"><QaIcon name="pending" aria-hidden="true" /><strong>NOT RUN</strong><span>{{ $t('qaFlowValidation.notRunHint') }}</span></div>
        <details v-if="modeHistory.length || historyRequested" ref="historyDetails" class="qa-guided-history" tabindex="-1"><summary>{{ $t('qaValidation.history') }} <span>{{ number(modeHistory.length) }}</span></summary><p v-if="!modeHistory.length" class="qa-small">{{ $t('qaFaithfulLive.notRunNote') }}</p><div v-else class="qa-validation-history"><button v-for="entry in modeHistory" :key="entry.id" class="qa-text-link" :class="{ 'qa-history-current': job?.id === entry.id }" :disabled="Boolean(runningJob) || loading" @click="show(entry)"><time v-if="entry.finished_at || entry.started_at" :datetime="entry.finished_at || entry.started_at">{{ timestamp(entry.finished_at || entry.started_at) }}</time><span>{{ $t(entry.mode === 'offline_regression' ? 'qaValidation.suites.' + entry.suite : 'qaValidation.modes.' + entry.mode + '.title') }}</span><strong>{{ statusLabel(entry.status, entry.mode) }}</strong></button></div></details>
      </div>
      <aside class="qa-guided-card qa-guided-aside">
        <template v-if="workspacePhase !== 'settings' && job"><h2>{{ $t(runningJob ? 'qaRunFlow.runningActions' : 'qaRunFlow.resultActions') }}</h2><div class="qa-guided-next-actions"><button class="qa-button qa-primary" data-testid="qa-validation-workbench" @click="emit('navigate', 'verification')"><QaIcon name="arrow_back" aria-hidden="true" />{{ $t('qaRunFlow.backToWorkbench') }}</button><button v-if="!runningJob && job.report_available" class="qa-button" data-testid="qa-validation-report" :disabled="downloading" @click="download"><QaIcon name="download" aria-hidden="true" />{{ $t('qaFlowValidation.downloadReport') }}</button><a v-if="reportDownload" class="qa-button" :href="reportDownload.url" :download="reportDownload.filename">{{ $t('qaLive.downloadAgain') }}</a></div><p class="qa-small">{{ $t(runningJob ? 'qaFlowLive.runningNote' : 'qaRunFlow.selectMissing') }}</p></template>
        <template v-else><h2>{{ $t('qaFlowValidation.whatYouGet') }}</h2><ul class="qa-guided-deliverables"><li v-for="item in ['progress', 'evidence', 'report']" :key="item"><QaIcon name="check_circle" aria-hidden="true" /><span>{{ $t('qaFlowValidation.deliverables.' + item) }}</span></li></ul></template>
        <div class="qa-guided-limits"><h3>{{ $t(workspacePhase === 'settings' ? 'qaFlowValidation.scopeLimits' : 'qaFaithfulValidation.scopeHeading') }}</h3><p>{{ $t(isOffline && workspacePhase !== 'settings' ? 'qaFaithfulValidation.offlineScope' : isOffline ? 'qaValidation.qualityLimit' : 'qaValidation.realQualityLimit') }}</p><span v-if="isOffline && workspacePhase !== 'settings'" class="qa-faithful-visually-hidden">{{ $t('qaValidation.qualityLimit') }}</span></div>
        <template v-if="workspacePhase === 'settings'"><a class="qa-text-link qa-guided-ci" :href="repository + '/actions/workflows/ci.yml'" target="_blank" rel="noopener noreferrer">{{ $t('observatory.openCi') }} ↗</a><button class="qa-text-link qa-guided-back" @click="emit('navigate', 'verification')">{{ $t('qaFlowValidation.chooseAnother') }}</button></template>
      </aside>
    </div>
  </section>
  <section v-else class="qa-testing" aria-labelledby="qa-testing-title" data-testid="qa-validation-panel">
    <div class="qa-testing-heading">
      <div><div v-if="!workbench" class="qa-eyebrow">{{ $t('observatory.testingEyebrow') }} <span>/ 03</span></div><component :is="workbench ? 'h1' : 'h2'" id="qa-testing-title">{{ $t(workbench ? 'qaValidation.workbenchTitle' : 'observatory.testingTitle') }}</component><p v-if="workbench" class="qa-testing-intro">{{ $t('qaValidation.scope') }}</p></div>
      <div class="qa-validation-heading-actions"><button class="qa-button" :class="{ 'qa-primary': workbench }" data-testid="qa-run-all" :disabled="cannotStart" @click="start('all')">{{ $t(isOffline ? 'qaValidation.runAll' : 'qaValidation.runMode') }}</button><button v-if="workbench" class="qa-button" :disabled="loading" @click="load">{{ $t('qaValidation.refresh') }}</button></div>
    </div>
    <p v-if="!workbench" class="qa-testing-intro">{{ $t('qaValidation.scope') }}</p>
    <div class="qa-validation-modes" data-testid="qa-validation-mode" role="group" :aria-label="$t('qaValidation.chooseMode')"><button v-for="entry in modes" :key="entry.id" class="qa-button" :data-mode="entry.id" :aria-pressed="mode === entry.id" :disabled="Boolean(runningJob) || loading" @click="selectMode(entry.id)">{{ $t('qaValidation.modes.' + entry.id + '.title') }}</button></div>
    <p class="qa-mode-scope">{{ $t('qaValidation.modes.' + mode + '.scope') }}</p>
    <p v-if="!available && !loading" class="qa-state" role="status">{{ $t('qaValidation.unavailable') }}</p>
    <p v-if="!available && selectedMode.reason && !loading" class="qa-small" data-testid="qa-validation-reason">{{ $t('qaValidation.modeReason', { reason: selectedMode.reason }) }}</p>
    <p v-if="error" class="qa-state qa-error" role="alert">{{ $t('qaValidation.errors.' + error) }}</p>
    <p v-if="busy && !runningJob" class="qa-state" role="status">{{ $t('qaValidation.busy') }}</p>
    <p v-if="retryAfter > 0" class="qa-small" role="status">{{ $t('qaValidation.cooldown', { n: retryAfter }) }}</p>

    <div class="qa-validation-layout">
      <div class="qa-validation-scope">
        <h2 v-if="workbench" class="qa-workbench-panel-title">{{ $t('qaValidation.validationScope') }}</h2>
        <div v-if="isOffline" class="qa-evidence-grid">
          <article v-for="(item, index) in evidence" :key="item.id" class="qa-panel qa-evidence">
            <span class="qa-evidence-number">0{{ index + 1 }}</span><h3>{{ $t('observatory.evidence.' + item.id + '.title') }}</h3>
            <span class="qa-pending">{{ latestFor(item.id) ? (latestFor(item.id).suite === 'all' ? $t('qaValidation.batchStatus', { status: $t('qaValidation.status.' + latestFor(item.id).status) }) : $t('qaValidation.status.' + latestFor(item.id).status)) : $t('qaValidation.notRun') }}</span>
            <p v-if="!workbench">{{ $t('observatory.evidence.' + item.id + '.scope') }}</p><p v-if="!workbench" class="qa-gap">{{ $t('observatory.evidence.' + item.id + '.gap') }}</p>
            <button class="qa-button" :data-testid="'qa-run-' + item.id" :disabled="cannotStart || !selectedMode.suites.includes(item.id)" @click="start(item.id)">{{ $t('qaValidation.runLayer') }}</button>
            <details v-if="workbench" class="qa-layer-details"><summary>{{ $t('qaValidation.scopeAndGaps') }}</summary><p>{{ $t('observatory.evidence.' + item.id + '.scope') }}</p><p class="qa-gap">{{ $t('observatory.evidence.' + item.id + '.gap') }}</p><div class="qa-evidence-links"><a v-for="link in item.links" :key="link.path" :href="repository + '/blob/main/' + link.path" target="_blank" rel="noopener noreferrer">{{ link.label }} ↗</a></div></details>
            <div v-else class="qa-evidence-links"><a v-for="link in item.links" :key="link.path" :href="repository + '/blob/main/' + link.path" target="_blank" rel="noopener noreferrer">{{ link.label }} ↗</a></div>
          </article>
        </div>
        <div v-else class="qa-real-configuration">
          <h3>{{ $t('qaValidation.fixedPlan') }}</h3><ol class="qa-mode-stages"><li v-for="stage in modeStages" :key="stage">{{ $t('qaValidation.stages.' + stage) }}</li></ol>
          <p class="qa-gap">{{ $t('qaValidation.selectionIsNotEvidence') }}</p>
          <div v-if="costRequired" class="qa-validation-cost">
            <label>{{ $t('qaLive.budget') }}<input v-model.number="budget" data-testid="qa-validation-budget" type="number" min="0.01" :max="budgetCeiling" step="0.01" inputmode="decimal" :disabled="loading || Boolean(runningJob)" :aria-invalid="!budgetValid" aria-describedby="qa-validation-budget-note" /></label>
            <p id="qa-validation-budget-note" class="qa-small">{{ $t('qaValidation.budgetNote', { n: budgetCeiling || '—', reserve: money(selectedMode.pricing?.reserved_estimated_usd) }) }}</p>
            <div v-if="selectedMode.pricing" class="qa-mode-pricing"><p>{{ $t('qaValidation.models', { main: selectedMode.pricing.model, judge: selectedMode.pricing.judge_model, embedding: selectedMode.pricing.embedding_model }) }}</p><p v-for="kind in ['main', 'judge', 'embedding']" :key="kind">{{ $t('qaValidation.pricing.' + kind) }} · {{ $t('qaValidation.rate', { input: money(selectedMode.pricing[kind]?.input_per_million), output: kind === 'embedding' ? '—' : money(selectedMode.pricing[kind]?.output_per_million) }) }}</p></div>
            <p v-if="selectedMode.limits.deadline_seconds" class="qa-small">{{ $t('qaValidation.executionLimits', { seconds: selectedMode.limits.deadline_seconds, turns: selectedMode.limits.turns || '—' }) }}</p>
            <label class="qa-validation-ack"><input v-model="acknowledged" data-testid="qa-validation-ack" type="checkbox" :disabled="loading || Boolean(runningJob)" /><span>{{ $t('qaValidation.acknowledge') }}</span></label>
            <div v-if="turnstileRequired" class="qa-validation-security"><p class="qa-small">{{ $t(tsSitekey ? 'qaValidation.turnstile' : 'qaValidation.turnstileUnavailable') }}</p><div ref="tsBox" class="qa-validation-turnstile"></div></div>
          </div>
        </div>
        <p class="qa-evidence-note">{{ $t('observatory.evidenceNote') }} <a :href="repository + '/actions/workflows/ci.yml'" target="_blank" rel="noopener noreferrer">{{ $t('observatory.openCi') }} ↗</a></p>
        <div v-if="modeHistory.length" class="qa-validation-history"><component :is="workbench ? 'h2' : 'span'">{{ $t('qaValidation.history') }}</component><button v-for="entry in modeHistory" :key="entry.id" class="qa-text-link" :class="{ 'qa-history-current': job?.id === entry.id }" :disabled="Boolean(runningJob) || loading" @click="show(entry)"><time v-if="entry.finished_at || entry.started_at" :datetime="entry.finished_at || entry.started_at">{{ timestamp(entry.finished_at || entry.started_at) }}</time><span>{{ $t(entry.mode === 'offline_regression' ? 'qaValidation.suites.' + entry.suite : 'qaValidation.modes.' + entry.mode + '.title') }}</span><strong>{{ statusLabel(entry.status, entry.mode) }}</strong></button></div>
      </div>

      <article v-if="job" class="qa-panel qa-validation-result" data-testid="qa-validation-result" :aria-busy="runningJob && !syncIssue">
        <div class="qa-panel-head"><component :is="workbench ? 'h2' : 'h3'">{{ $t('qaValidation.result') }}</component><strong v-if="!workbench" role="status">{{ syncIssue ? $t('qaValidation.syncInterrupted') : statusLabel(job.status, job.mode) }}</strong><button v-if="workbench && runningJob" class="qa-button" data-testid="qa-cancel-validation" :disabled="cancelling" @click="cancel">{{ $t('qaValidation.cancel') }}</button></div>
        <div v-if="workbench" class="qa-run-summary" :class="{ 'qa-run-active': runningJob && !syncIssue, 'qa-run-passed': job.mode === 'offline_regression' && job.status === 'completed' }"><QaIcon class="qa-run-indicator" aria-hidden="true" :name="syncIssue ? 'error' : runningJob ? 'progress_activity' : job.status === 'completed' ? (isOffline ? 'check_circle' : 'fact_check') : 'error'" /><strong role="status">{{ syncIssue ? $t('qaValidation.syncInterrupted') : statusLabel(job.status, job.mode) }}</strong></div>
        <p v-if="syncIssue" class="qa-small" data-testid="qa-validation-sync-issue" role="status">{{ $t(missingJob ? 'qaValidation.syncMissing' : 'qaValidation.syncRetry', { status: statusLabel(job.status, job.mode) }) }}</p>
        <p class="qa-small">{{ $t('qaValidation.progress', { n: finishedSteps, total: job.total_steps }) }} · {{ $t('qaValidation.modes.' + job.mode + '.title') }}</p>
        <div class="qa-validation-progress"><progress :value="finishedSteps" :max="Math.max(1, job.total_steps)" :aria-label="$t('qaValidation.result')"></progress><span v-if="workbench">{{ number(progressPercent) }}%</span></div>
        <p v-if="workbench && measuredCounts" class="qa-validation-total">{{ $t('qaValidation.counts', { tests: number(measuredCounts.tests), failed: number(measuredCounts.failed), skipped: number(measuredCounts.skipped) }) }}</p>
        <div v-if="!workbench" class="qa-validation-actions">
          <button v-if="runningJob" class="qa-button" data-testid="qa-cancel-validation" :disabled="cancelling" @click="cancel">{{ $t('qaValidation.cancel') }}</button>
          <button class="qa-button" :disabled="loading" @click="load">{{ $t('qaValidation.refresh') }}</button>
        </div>
        <ol class="qa-validation-steps">
          <li v-for="(step, index) in job.steps" :key="index">
            <div><strong>{{ step.name }}</strong><span>{{ statusLabel(step.status, job.mode) }}</span></div>
            <div v-if="isOffline && step.progress" class="qa-pytest-progress" data-testid="qa-pytest-progress">
              <p>{{ $t('qaValidation.testPhase.' + step.progress.phase) }}<span v-if="step.progress.collected !== null"> · {{ $t('qaValidation.testProgress', { n: number(step.progress.completed), total: number(step.progress.collected) }) }}</span></p>
              <p v-if="step.progress.current_test" class="qa-current-test">{{ $t('qaValidation.currentTest', { name: step.progress.current_test }) }}</p>
              <p v-if="step.progress.completed || step.progress.errors">{{ $t('qaValidation.testOutcomes', { passed: number(step.progress.passed), failed: number(step.progress.failed), errors: number(step.progress.errors), skipped: number(step.progress.skipped) }) }}</p>
              <p v-if="step.progress.collection_errors">{{ $t('qaValidation.collectionErrors', { n: number(step.progress.collection_errors) }) }}</p>
            </div>
            <p v-if="isOffline && hasCounts(step)">{{ $t('qaValidation.counts', { tests: number(step.tests), failed: number(step.failed + step.errors), skipped: number(step.skipped) }) }}</p>
            <p v-else-if="isOffline">{{ $t(step.status === 'pending' ? 'qaValidation.stepPending' : 'qaValidation.unmeasured') }}</p>
            <ul v-else-if="step.checks?.length" class="qa-measured-checks"><li v-for="(check, checkIndex) in step.checks" :key="checkIndex"><strong>{{ check.name }}</strong><span>{{ $t('qaValidation.checkStatus.' + check.status) }}</span><details><summary>{{ $t('qaValidation.evidence') }}</summary><pre>{{ evidenceText(check.evidence) }}</pre></details></li></ul>
            <p v-else>{{ $t('qaValidation.noChecks') }}</p>
            <details v-if="!isOffline && Object.keys(step.evidence || {}).length"><summary>{{ $t('qaValidation.stepEvidence') }}</summary><pre>{{ evidenceText(step.evidence) }}</pre></details>
            <details v-if="step.log"><summary>{{ $t('qaLog.summary') }}</summary><pre>{{ step.log }}</pre><small v-if="step.log_truncated">{{ $t('qaValidation.truncated') }}</small></details>
          </li>
        </ol>
        <QaEvidenceScope v-if="!isOffline" :covered="job.covered" :gaps="job.gaps" />
        <p v-if="job.error" class="qa-state" role="alert">{{ $t('qaLive.executionError') }}: {{ logCaptureErrorKey(job.error) ? $t(logCaptureErrorKey(job.error)) : job.error }}</p>
        <QaExecutionLog ref="executionLog" family="validations" :job-id="job.id" :running="Boolean(runningJob)" :steps="job.steps" />
        <div v-if="job.report_available" class="qa-validation-actions"><button class="qa-button" data-testid="qa-validation-report" :disabled="downloading" @click="download">{{ $t('qaLive.download') }}</button><a v-if="reportDownload" class="qa-button" :href="reportDownload.url" :download="reportDownload.filename">{{ $t('qaLive.downloadAgain') }}</a></div>
        <p class="qa-gap">{{ $t(isOffline ? 'qaValidation.qualityLimit' : 'qaValidation.realQualityLimit') }}</p>
      </article>
      <article v-else-if="workbench" class="qa-panel qa-validation-result qa-validation-empty"><h2>{{ $t('qaValidation.result') }}</h2><QaIcon class="qa-empty-indicator" aria-hidden="true" name="pending" /><h3>{{ $t('qaValidation.notRun') }}</h3><p>{{ $t('qaValidation.emptyResult') }}</p><p class="qa-gap">{{ $t(isOffline ? 'qaValidation.qualityLimit' : 'qaValidation.realQualityLimit') }}</p></article>
    </div>
  </section>
</template>

<script setup>
import { qaChallenge } from '../lib/runtime.js';
import { qaDownloadPrefix } from '../lib/runtime.js';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import QaIcon from "./QaIcon.vue";
import QaReleaseDecision from "./QaReleaseDecision.vue";
import QaExecutionLog from "./QaExecutionLog.vue";
import QaEvidenceScope from "./QaEvidenceScope.vue";
import { AGENT, TS_SITEKEY } from "../lib/runtime.js";
import { createCfToken } from "../lib/cfToken.js";
import { apiFetch } from "../lib/qaSession.js";
import { QA_EVIDENCE, QA_REPOSITORY } from "../lib/qa.js";
import { validValidationCapabilities, validValidationJob, validValidationPricing, validationModes } from "../lib/qaValidation.js";
import { logCaptureErrorKey } from "../lib/qaLogs.js";
import { getEvidenceStep } from "../lib/qaEvidence.js";

const props = defineProps({ workbench: { type: Boolean, default: false }, requestedMode: { type: String, default: "" } });
const emit = defineEmits(["status-change", "mode-change", "phase-change", "navigate", "observation-change"]);
const { locale, t } = useI18n();
const evidence = QA_EVIDENCE, repository = QA_REPOSITORY;
const busy = ref(false), loading = ref(false), cancelling = ref(false), downloading = ref(false);
const modes = ref(validationModes()), mode = ref("offline_regression"), budget = ref(null), acknowledged = ref(false), reportDownload = ref(null);
const workspacePhase = ref("settings"), selectedSuite = ref("all");
const expandedSteps = ref(new Set()), historyDetails = ref(null), historyRequested = ref(false);
const executionLog = ref(null);
watch(workspacePhase, (phase) => emit("phase-change", phase), { immediate: true });
function toggleStep(index) {
  const expanded = new Set(expandedSteps.value);
  if (expanded.has(index)) expanded.delete(index); else expanded.add(index);
  expandedSteps.value = expanded;
}
async function showHistory() {
  historyRequested.value = true;
  await nextTick();
  if (!historyDetails.value) return;
  historyDetails.value.open = true;
  historyDetails.value.focus({ preventScroll: true });
  historyDetails.value.scrollIntoView?.({ behavior: "smooth", block: "center" });
}
defineExpose({ showHistory, prepareRun, startFree, showJob, openLogs, refresh: load });
const tsBox = ref(null), tsSitekey = TS_SITEKEY, cfToken = createCfToken({ enabled: !!TS_SITEKEY });
let tsWidgetId = null;
const selectedMode = computed(() => modes.value.find((entry) => entry.id === mode.value));
const available = computed(() => selectedMode.value.available);
const isOffline = computed(() => mode.value === "offline_regression");
const costRequired = computed(() => mode.value === "real_es_llm_e2e" || selectedMode.value.cost_required);
const turnstileRequired = computed(() => mode.value === "real_es_llm_e2e" && selectedMode.value.turnstile_required === true);
const budgetCeiling = computed(() => Number(selectedMode.value.limits.max_budget_usd) || 0);
const money = (value) => typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat(locale.value, { maximumFractionDigits: 6 }).format(value) : "—";
const budgetValid = computed(() => typeof budget.value === "number" && Number.isFinite(budget.value) && budget.value >= 0.01
  && budget.value <= budgetCeiling.value && validValidationPricing(selectedMode.value.pricing)
  && budget.value >= selectedMode.value.pricing.reserved_estimated_usd);
const modeStages = computed(() => mode.value === "es_integration" ? ["isolatedEs", "api", "storage"] : ["isolatedEs", "realChain", "guard"]);
const statusLabel = (status, executionMode) => t('qaValidation.' + (executionMode === "offline_regression" ? "status." : "realStatus.") + status);
const evidenceText = (value) => JSON.stringify(value, null, 2);
const capabilities = ref(null), recent = ref([]), job = ref(null), error = ref(""), retryAfter = ref(0), syncIssue = ref(false), missingJob = ref(false);
const base = `${AGENT}/qa/validations`;
const isActive = (value) => value && ["queued", "running"].includes(value.status);
const runningJob = computed(() => Boolean(isActive(job.value)) && !missingJob.value);
const executionStatus = computed(() => ({ queued: 'QUEUED', running: 'RUNNING', completed: 'COMPLETED', failed: 'FAILED', cancelled: 'CANCELLED', timed_out: 'TIMED OUT', incomplete: 'INCOMPLETE' })[job.value?.status] || 'UNKNOWN');
const cannotStart = computed(() => !available.value || loading.value || busy.value || runningJob.value || retryAfter.value > 0 || (turnstileRequired.value && !tsSitekey)
  || (costRequired.value && (!budgetValid.value || !acknowledged.value)));
const modeHistory = computed(() => recent.value.filter((entry) => entry.mode === mode.value));
const selectedEvidence = computed(() => evidence.filter((entry) => selectedSuite.value === "all" || entry.id === selectedSuite.value));
const unavailableReason = computed(() => t(selectedMode.value.reason === "complete_chain_pricing_required" ? "qaFlowValidation.pricingRequired" : "qaFlowValidation.modeUnavailable"));
const startReason = computed(() => {
  if (loading.value) return t("qaFlowValidation.loading");
  if (runningJob.value) return t("qaFlowValidation.activeRun");
  if (!available.value) return unavailableReason.value;
  if (busy.value) return t("qaValidation.busy");
  if (retryAfter.value > 0) return t("qaValidation.cooldown", { n: retryAfter.value });
  if (turnstileRequired.value && !tsSitekey) return t("qaValidation.turnstileUnavailable");
  if (costRequired.value && !budgetValid.value) return t("qaFlowValidation.budgetRequired");
  if (costRequired.value && !acknowledged.value) return t("qaFlowValidation.consentRequired");
  return "";
});
const stepStatusLabel = (status) => ({ completed: "PASS", failed: "FAIL", pending: "NOT RUN", running: "RUNNING" })[status] || statusLabel(status, mode.value);
function evidenceStep(name) {
  // The explicit local fixture prefix is presentation-only; preserve the raw
  // backend value in technical details and step-scoped log requests.
  const fixturePrefix = "[OFFLINE FIXTURE] ";
  return getEvidenceStep(name.startsWith(fixturePrefix) ? name.slice(fixturePrefix.length) : name);
}
function stepTitle(name) {
  const step = evidenceStep(name);
  return step ? t("qaEvidence.stages." + step.key + ".title") : name;
}
function stepDescription(name) {
  const step = evidenceStep(name);
  return t(step ? "qaEvidence.stages." + step.key + ".description" : "qaEvidence.unknownStepDescription");
}
function stepResultDescription(status) {
  const key = { completed: "resultCompleted", failed: "resultFailed", running: "resultRunning", pending: "resultPending", queued: "resultPending", cancelled: "resultCancelled", timed_out: "resultTimedOut" }[status] || "resultIncomplete";
  return t("qaEvidence." + key);
}
const finishedSteps = computed(() => job.value?.steps.filter((step) => ["completed", "failed", "timed_out"].includes(step.status)).length || 0);
const number = (value) => new Intl.NumberFormat(locale.value).format(value || 0);
const hasCounts = (step) => [step.tests, step.failed, step.errors, step.skipped].every((value) => Number.isSafeInteger(value) && value >= 0);
const countsFor = (value) => {
  const measured = value?.steps.filter(hasCounts) || [];
  return measured.length ? measured.reduce((sum, step) => ({ tests: sum.tests + step.tests, failed: sum.failed + step.failed + step.errors, skipped: sum.skipped + step.skipped }), { tests: 0, failed: 0, skipped: 0 }) : null;
};
const measuredCounts = computed(() => countsFor(job.value));
const outcomeCounts = computed(() => {
  if (!job.value) return null;
  if (isOffline.value) {
    const measured = job.value.steps.filter(hasCounts);
    return measured.length ? measured.reduce((sum, step) => ({ passed: sum.passed + Math.max(0, step.tests - step.failed - step.errors - step.skipped), failed: sum.failed + step.failed, errors: sum.errors + step.errors, skipped: sum.skipped + step.skipped }), { passed: 0, failed: 0, errors: 0, skipped: 0 }) : null;
  }
  const checks = job.value.steps.flatMap((step) => step.checks || []);
  return checks.length ? { passed: checks.filter((check) => check.status === "passed").length, failed: checks.filter((check) => check.status === "failed").length, errors: 0, skipped: 0 } : null;
});
const progressPercent = computed(() => job.value?.total_steps ? Math.round(finishedSteps.value / job.value.total_steps * 100) : 0);
const summaryJob = computed(() => {
  if (isActive(job.value)) return job.value;
  const active = recent.value.find(isActive);
  if (active && active.id !== job.value?.id) return active;
  return recent.value[0]?.id === job.value?.id ? job.value : recent.value[0] || job.value;
});
watch(() => ({ status: summaryJob.value?.status || "not_run", mode: summaryJob.value?.mode || mode.value, tests: countsFor(summaryJob.value)?.tests ?? null, active: Boolean(isActive(summaryJob.value)) && !(missingJob.value && summaryJob.value?.id === job.value?.id), available: available.value, error: error.value || null }), (value) => emit("status-change", value), { immediate: true });
watch(() => ({ capabilities: capabilities.value ? { ...capabilities.value, recent: recent.value, busy: busy.value, retry_after_seconds: retryAfter.value } : null, job: job.value, loading: loading.value, error: error.value }), (value) => emit("observation-change", JSON.parse(JSON.stringify(value))), { immediate: true, deep: true });
const timestamp = (value) => new Intl.DateTimeFormat(locale.value, { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Taipei" }).format(new Date(value));
const resultTimestamp = (value) => new Intl.DateTimeFormat(locale.value, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "Asia/Taipei" }).format(new Date(value));
const latestFor = (suite) => isActive(job.value) && job.value.mode === mode.value && [suite, "all"].includes(job.value.suite) ? job.value : recent.value.find((entry) => entry.mode === mode.value && (entry.suite === suite || entry.suite === "all"));
let controller = new AbortController(), pollTimer, cooldownTimer, refreshNeeded = false, observationRevision = 0;
function clearReportDownload() { if (reportDownload.value) URL.revokeObjectURL(reportDownload.value.url); reportDownload.value = null; }
function clearSecurityWidget() { if (qaChallenge.widget && tsWidgetId !== null) qaChallenge.widget.remove?.(tsWidgetId); tsWidgetId = null; cfToken.clear(); }
watch(() => job.value?.id, () => { clearReportDownload(); expandedSteps.value = new Set(); });
function selectMode(id) {
  if (loading.value) return;
  if (!modes.value.some((entry) => entry.id === id) || runningJob.value) { emit("mode-change", mode.value); return; }
  workspacePhase.value = "settings";
  if (mode.value === id) { emit("mode-change", mode.value); return; }
  clearSecurityWidget(); mode.value = id; acknowledged.value = false; error.value = ""; syncIssue.value = false; missingJob.value = false; clearReportDownload();
  selectedSuite.value = "all";
  job.value = recent.value.find((entry) => entry.mode === id) || null;
  if (costRequired.value) budget.value = selectedMode.value.limits.default_budget_usd ?? null;
}
function prepareRun(id = mode.value) {
  if (loading.value || runningJob.value || !modes.value.some((entry) => entry.id === id)) return false;
  selectMode(id);
  acknowledged.value = false; selectedSuite.value = "all"; clearSecurityWidget(); workspacePhase.value = "settings";
  return mode.value === id;
}
async function startFree(id) {
  if (!["offline_regression", "es_integration"].includes(id) || !prepareRun(id)) return false;
  return start("all");
}
async function openLogs() {
  if (!job.value) return false;
  workspacePhase.value = runningJob.value ? "execution" : "evidence";
  await nextTick();
  if (!executionLog.value) return false;
  await executionLog.value.openStep(""); return true;
}
async function showJob(id, { logs = false } = {}) {
  if (loading.value || !/^[a-zA-Z0-9-]{1,64}$/.test(id) || (runningJob.value && job.value.id !== id)) return false;
  const revision = observationRevision;
  loading.value = true;
  try {
    const value = await request("/" + encodeURIComponent(id));
    if (controller.signal.aborted || revision !== observationRevision) return false;
    if (!validValidationJob(value.job) || value.job.id !== id) throw new Error("schema");
    if (runningJob.value && job.value.id !== id) return false;
    clearTimeout(pollTimer); clearSecurityWidget(); acknowledged.value = false;
    mode.value = value.job.mode; remember(value.job); error.value = ""; syncIssue.value = false;
    workspacePhase.value = isActive(value.job) ? "execution" : "evidence"; schedule();
    if (logs) await openLogs();
    return true;
  } catch (failure) { failed(failure); return false; }
  finally { loading.value = false; }
}
watch([() => props.requestedMode, loading], ([value]) => { if (value && value !== mode.value) selectMode(value); }, { immediate: true });
watch(mode, (value) => emit("mode-change", value), { immediate: true });
watch(() => selectedMode.value.suites, (suites) => { if (!suites.includes(selectedSuite.value)) selectedSuite.value = suites.includes("all") ? "all" : suites[0]; }, { immediate: true });
watch(() => job.value?.status, (status, previous) => {
  if (["queued", "running"].includes(status)) workspacePhase.value = "execution";
  else if (["queued", "running"].includes(previous)) workspacePhase.value = "evidence";
});
async function securityToken() {
  if (!turnstileRequired.value) return undefined;
  await nextTick();
  if (!TS_SITEKEY || !tsBox.value) throw new Error("turnstile");
  cfToken.clear();
  await qaChallenge.load(controller.signal);
  if (tsWidgetId !== null) qaChallenge.widget.reset(tsWidgetId);
  else tsWidgetId = qaChallenge.widget.render(tsBox.value, { sitekey: TS_SITEKEY, size: "compact", callback: (token) => cfToken.set(token), "expired-callback": () => cfToken.clear() });
  const token = await cfToken.get();
  if (!token || controller.signal.aborted) throw new Error("turnstile");
  return token;
}
function schedule() {
  clearTimeout(pollTimer);
  if (controller.signal.aborted) return;
  if (runningJob.value) pollTimer = setTimeout(poll, 1000);
  else if (busy.value || refreshNeeded) pollTimer = setTimeout(load, 2000);
}
function setCooldown(seconds) {
  clearInterval(cooldownTimer); retryAfter.value = Math.max(0, Math.ceil(Number(seconds) || 0));
  if (retryAfter.value) cooldownTimer = setInterval(() => { retryAfter.value = Math.max(0, retryAfter.value - 1); if (!retryAfter.value) { clearInterval(cooldownTimer); load(); } }, 1000);
}
async function responseFor(path = "", init = {}) {
  const response = await apiFetch(base + path, { ...init, cache: "no-store", signal: init.signal || controller.signal });
  if (!response.ok) {
    if (response.status === 429) setCooldown(response.headers?.get("Retry-After") || 60);
    throw new Error(response.status === 409 ? "busy" : response.status === 429 ? "cooldown" : response.status === 503 ? "unavailable" : response.status === 404 ? "missing" : "request");
  }
  return response;
}
async function request(path = "", init = {}) {
  if (controller.signal.aborted) throw new DOMException("Cancelled", "AbortError");
  if (init.method && init.method !== "GET") return (await responseFor(path, init)).json();
  const readController = new AbortController();
  const abort = () => readController.abort();
  controller.signal.addEventListener("abort", abort, { once: true });
  let timer;
  try {
    return await Promise.race([
      (async () => (await responseFor(path, { ...init, signal: readController.signal })).json())(),
      new Promise((_, reject) => { timer = setTimeout(() => { readController.abort(); reject(new Error("request")); }, 15000); }),
    ]);
  } finally { clearTimeout(timer); controller.signal.removeEventListener("abort", abort); readController.abort(); }
}
function failed(failure) { if (!controller.signal.aborted) error.value = ["busy", "cooldown", "unavailable", "missing", "turnstile"].includes(failure.message) ? failure.message : "request"; }
function remember(value) {
  if (job.value?.id === value.id && !isActive(job.value) && isActive(value)) return false;
  observationRevision += 1; job.value = value; missingJob.value = false;
  recent.value = [value, ...recent.value.filter((entry) => entry.id !== value.id)].slice(0, 20);
  return true;
}
async function load() {
  clearTimeout(pollTimer); loading.value = true;
  const revision = observationRevision;
  try {
    const value = await request();
    if (controller.signal.aborted || revision !== observationRevision) return;
    if (!validValidationCapabilities(value)) throw new Error("schema");
    const observed = value.recent.filter(validValidationJob).map((entry) => entry.id === job.value?.id && !isActive(job.value) && isActive(entry) ? job.value : entry).slice(0, 20);
    if (value.active_job_id && value.recent.some((entry) => entry.id === value.active_job_id) && !observed.some((entry) => entry.id === value.active_job_id)) throw new Error("schema");
    if (job.value && value.recent.some((entry) => entry.id === job.value.id) && !observed.some((entry) => entry.id === job.value.id)) throw new Error("schema");
    capabilities.value = value; modes.value = validationModes(value); busy.value = value.busy === true;
    if (costRequired.value && budget.value === null) budget.value = selectedMode.value.limits.default_budget_usd ?? null;
    recent.value = observed; refreshNeeded = false; error.value = ""; syncIssue.value = false; missingJob.value = false;
    observationRevision += 1;
    setCooldown(value.retry_after_seconds);
    const active = recent.value.find((entry) => entry.id === value.active_job_id && isActive(entry));
    if (active) { mode.value = active.mode; job.value = active; if (costRequired.value && budget.value === null) budget.value = selectedMode.value.limits.default_budget_usd ?? null; }
    else {
      const current = recent.value.find((entry) => entry.id === job.value?.id);
      if (current) job.value = current;
      else if (isActive(job.value)) { missingJob.value = true; syncIssue.value = true; error.value = "missing"; }
      else if (!job.value && modeHistory.value.length) { job.value = modeHistory.value[0]; workspacePhase.value = "evidence"; }
    }
    schedule();
  } catch (failure) { if (revision === observationRevision) { failed(failure); syncIssue.value = Boolean(runningJob.value); refreshNeeded = true; schedule(); } } finally { loading.value = false; }
}
async function start(suite) {
  if (cannotStart.value || !selectedMode.value.suites.includes(suite)) return false;
  loading.value = true; error.value = "";
  let submitted = false;
  try {
    const payload = { mode: mode.value, suite, ...(costRequired.value ? { max_usd: budget.value, acknowledge_cost: true } : {}) };
    const token = await securityToken();
    if (controller.signal.aborted) return;
    if (token) payload.cf_token = token;
    submitted = true;
    const value = await request("", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!validValidationJob(value.job) || value.job.mode !== mode.value) throw new Error("schema");
    remember(value.job); busy.value = Boolean(isActive(value.job)); syncIssue.value = false; acknowledged.value = false; schedule(); return true;
  } catch (failure) { failed(failure); if (submitted) { refreshNeeded = true; schedule(); } return false; } finally { loading.value = false; }
}
async function poll() {
  if (!runningJob.value) return;
  const jobId = job.value.id;
  const revision = observationRevision;
  try {
    const value = await request("/" + encodeURIComponent(jobId));
    if (controller.signal.aborted || job.value?.id !== jobId || revision !== observationRevision) return;
    if (!validValidationJob(value.job)) throw new Error("schema");
    if (value.job.id !== jobId) throw new Error("schema");
    if (!remember(value.job)) { refreshNeeded = true; schedule(); return; }
    busy.value = Boolean(isActive(value.job)); error.value = ""; syncIssue.value = false;
    if (!isActive(job.value)) await load();
    else schedule();
  } catch (failure) { if (revision === observationRevision) { failed(failure); syncIssue.value = Boolean(runningJob.value); schedule(); } }
}
async function cancel() {
  if (!job.value || cancelling.value) return;
  cancelling.value = true; error.value = ""; observationRevision += 1;
  try {
    const value = await request("/" + encodeURIComponent(job.value.id) + "/cancel", { method: "POST" });
    if (!validValidationJob(value.job)) throw new Error("schema");
    remember(value.job); busy.value = Boolean(isActive(value.job)); syncIssue.value = false; if (isActive(job.value)) schedule(); else await load();
  } catch (failure) { failed(failure); syncIssue.value = Boolean(isActive(job.value)); schedule(); } finally { cancelling.value = false; }
}
function show(entry) { clearTimeout(pollTimer); job.value = entry; workspacePhase.value = isActive(entry) ? "execution" : "evidence"; schedule(); }
async function download() {
  if (!job.value?.report_available || downloading.value) return;
  const jobId = job.value.id; downloading.value = true; error.value = ""; clearReportDownload();
  try {
    const response = await responseFor("/" + encodeURIComponent(jobId) + "/report");
    const blob = await response.blob();
    if (controller.signal.aborted || job.value?.id !== jobId) return;
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = qaDownloadPrefix() + "-validation-" + jobId + ".json";
    reportDownload.value = { url, filename: link.download }; document.body.append(link);
    try { link.click(); } finally { link.remove(); }
  } catch (failure) { clearReportDownload(); failed(failure); } finally { downloading.value = false; }
}
onMounted(load);
onBeforeUnmount(() => { controller.abort(); cfToken.set(""); clearSecurityWidget(); clearTimeout(pollTimer); clearInterval(cooldownTimer); clearReportDownload(); });
</script>

<style scoped>
.qa-validation-modes { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 12px; }
.qa-validation-modes .qa-button { flex: 1 1 180px; min-width: 0; white-space: normal; }
.qa-validation-modes [aria-pressed="true"] { color: var(--accent); border-color: var(--accent); background: var(--surface-2); }
.qa-mode-scope { font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); margin-bottom: 24px; color: var(--ink-2); }
.qa-mode-scope, .qa-mode-pricing, .qa-validation-observations, .qa-state { overflow-wrap: anywhere; min-width: 0; }
.qa-real-configuration h3 { font: 500 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); margin: 22px 0 12px; }
.qa-mode-stages { padding-left: 20px; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); color: var(--ink-2); }
.qa-mode-stages li { padding: 5px 0; }
.qa-validation-cost { margin-top: 22px; border-top: 1px solid var(--border); padding-top: 22px; }
.qa-validation-cost label:not(.qa-validation-ack) { display: flex; flex-direction: column; gap: 10px; font-size: var(--qa-type-meta); }
.qa-validation-cost input[type="number"] { display: block; width: 100%; min-width: 0; box-sizing: border-box; padding: 11px 13px; border: 1px solid var(--border); border-radius: 5px; background: var(--surface-2); color: var(--ink); font: var(--qa-type-control)/var(--qa-leading-body) var(--font-mono); }
.qa-validation-cost input:focus-visible, .qa-validation-ack input:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-validation-ack { display: flex; gap: 12px; align-items: flex-start; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); margin-top: 18px; }
.qa-validation-ack input { flex: none; margin-top: 5px; accent-color: var(--accent); }
.qa-mode-pricing { padding: 12px; margin-top: 14px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 5px; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-mode-pricing p { margin: 6px 0; }
.qa-measured-checks { padding: 0; list-style: none; }
.qa-validation-steps .qa-measured-checks > li { margin: 8px 0; padding: 10px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 5px; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-measured-checks > li > strong, .qa-measured-checks > li > span { display: block; overflow-wrap: anywhere; }
.qa-validation-observations { margin: 18px 0; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-validation-turnstile { max-width: 100%; overflow: hidden; }
.qa-validation-result a { overflow-wrap: anywhere; }
.qa-validation-result { margin-top: 24px; }
.qa-validation-result progress { width: 100%; height: 8px; accent-color: var(--accent); }
.qa-validation-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.qa-validation-steps { padding-left: 22px; }
.qa-validation-steps li { margin: 16px 0; }
.qa-validation-steps li > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
.qa-validation-steps p, .qa-validation-steps details { font-size: var(--qa-type-meta); }
.qa-validation-steps pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 240px; overflow: auto; font-size: var(--qa-type-code); }
.qa-validation-history { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 20px; font-size: var(--qa-type-meta); }
.qa-validation-history button { text-align: left; }
.qa-validation-heading-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.qa-validation-progress { display: flex; align-items: center; gap: 12px; }
.qa-validation-progress progress { min-width: 0; }
.qa-validation-progress > span { flex: none; font: var(--qa-type-meta)/var(--qa-leading-body) var(--font-mono); }
.qa-validation-history button { display: flex; flex-wrap: wrap; gap: 8px; }
.qa-validation-history strong { font-weight: 500; }
.qa-validation-workbench { margin: 0; padding: 0; border: 0; }
.qa-validation-workbench .qa-testing-heading { align-items: flex-start; gap: 24px; margin-bottom: 24px; }
.qa-validation-workbench .qa-testing-heading > div:first-child { flex: 1; min-width: 0; }
.qa-validation-workbench h1 { margin: 0; font: 500 var(--qa-type-page-title)/var(--qa-leading-title) var(--font-sans); letter-spacing: .025em; }
.qa-validation-workbench .qa-testing-intro { max-width: 850px; margin: 12px 0 0; color: var(--ink-2); font-size: var(--qa-type-lead); line-height: var(--qa-leading-body); }
.qa-validation-workbench .qa-validation-heading-actions { flex-direction: column; flex: none; min-width: 156px; }
.qa-validation-workbench .qa-validation-heading-actions > .qa-button:first-child:disabled { opacity: .5; }
.qa-validation-workbench .qa-validation-layout { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-items: start; gap: 16px; }
.qa-validation-workbench .qa-validation-scope, .qa-validation-workbench .qa-validation-result { background: var(--surface); border: 1px solid var(--border); border-radius: 7px; padding: 24px; min-width: 0; margin: 0; }
.qa-validation-workbench .qa-workbench-panel-title, .qa-validation-workbench .qa-panel-head h2, .qa-validation-workbench .qa-validation-history h2, .qa-validation-workbench .qa-validation-empty h2 { font: 500 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); margin: 0; }
.qa-validation-workbench .qa-workbench-panel-title { padding-bottom: 18px; border-bottom: 1px solid var(--border); }
.qa-validation-workbench .qa-evidence-grid { display: block; margin: 0; }
.qa-validation-workbench .qa-evidence { display: grid; grid-template-columns: 54px minmax(0, 1fr) auto; column-gap: 16px; align-items: start; margin: 0; padding: 25px 0; border: 0; border-bottom: 1px solid var(--border); border-radius: 0; box-shadow: none; background: transparent; }
.qa-validation-workbench .qa-evidence-number { grid-row: 1 / 4; margin: 0; font: 400 var(--qa-type-metric)/var(--qa-leading-title) var(--font-mono); color: var(--ink-3); }
.qa-validation-workbench .qa-evidence h3 { grid-column: 2; margin: 0; font: 500 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); }
.qa-validation-workbench .qa-pending { grid-column: 2; margin: 7px 0 12px; color: var(--ink-2); font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-validation-workbench .qa-evidence > .qa-button { grid-column: 3; grid-row: 1 / 3; margin: 0; padding: 8px 11px; white-space: nowrap; font-size: var(--qa-type-control); }
.qa-validation-workbench .qa-layer-details { grid-column: 2 / 4; min-width: 0; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-validation-workbench .qa-layer-details summary, .qa-validation-workbench .qa-validation-steps summary { cursor: pointer; color: var(--ink-2); }
.qa-validation-workbench .qa-layer-details p { margin: 9px 0; }
.qa-validation-workbench .qa-evidence-links { margin-top: 10px; gap: 6px; }
.qa-validation-workbench .qa-evidence-links a { overflow-wrap: anywhere; font-size: var(--qa-type-meta); }
.qa-validation-workbench .qa-evidence-note { padding: 18px 0; margin: 0; border-bottom: 1px solid var(--border); font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-validation-workbench .qa-validation-history { display: block; margin-top: 20px; }
.qa-validation-workbench .qa-validation-history h2 { margin-bottom: 15px; }
.qa-validation-workbench .qa-validation-history button { appearance: none; background: transparent; border: 0; border-radius: 0; width: 100%; display: grid; grid-template-columns: 1fr 1.05fr 1fr; align-items: center; gap: 8px; padding: 13px 0; border-bottom: 1px solid var(--border-2); font: var(--qa-type-meta)/var(--qa-leading-body) var(--font-sans); color: var(--ink-2); text-decoration: none; cursor: pointer; }
.qa-validation-workbench .qa-validation-history button strong { color: var(--ink); }
.qa-validation-workbench .qa-validation-history button:not(:disabled):hover, .qa-validation-workbench .qa-validation-history .qa-history-current { color: var(--accent); }
.qa-validation-workbench .qa-validation-history button:not(:disabled):hover { background: var(--surface-2); }
.qa-validation-workbench .qa-validation-history button:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-validation-workbench .qa-validation-history button:disabled { cursor: default; opacity: .7; }
.qa-validation-workbench .qa-panel-head { align-items: center; padding-bottom: 18px; border-bottom: 1px solid var(--border); gap: 12px; }
.qa-validation-workbench .qa-run-summary { display: flex; align-items: center; gap: 18px; padding-top: 27px; }
.qa-validation-workbench .qa-run-summary > strong { font: 500 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); }
.qa-validation-workbench .qa-run-indicator { display: grid; flex: none; place-items: center; width: 54px; height: 54px; font-size: 54px; line-height: 1; color: var(--ink-2); }
.qa-validation-workbench .qa-run-passed .qa-run-indicator { color: var(--accent); }
.qa-validation-workbench .qa-run-active .qa-run-indicator { color: var(--accent); animation: qa-validation-spin 1.4s linear infinite; }
.qa-validation-workbench .qa-validation-result > .qa-small { margin: 12px 0 20px; }
.qa-validation-workbench progress { height: 12px; }
.qa-validation-workbench .qa-validation-total { padding: 20px 0; margin: 20px 0 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); font: var(--qa-type-body)/var(--qa-leading-body) var(--font-mono); }
.qa-validation-workbench .qa-validation-steps { list-style: none; padding: 0; margin: 0; }
.qa-validation-workbench .qa-validation-steps li { padding: 17px 0; margin: 0; border-bottom: 1px solid var(--border-2); }
.qa-validation-workbench .qa-validation-steps li > div { font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-validation-workbench .qa-validation-steps li > div > strong { font-weight: 500; overflow-wrap: anywhere; }
.qa-validation-workbench .qa-validation-steps li > div > span { color: var(--ink-2); font-size: var(--qa-type-meta); }
.qa-validation-workbench .qa-validation-steps p { color: var(--ink-2); font: var(--qa-type-meta)/var(--qa-leading-body) var(--font-mono); }
.qa-validation-steps .qa-pytest-progress { display: block; min-width: 0; }
.qa-validation-steps .qa-current-test { overflow-wrap: anywhere; }
.qa-validation-workbench .qa-validation-steps details { margin-top: 12px; font-size: var(--qa-type-meta); }
.qa-validation-workbench .qa-validation-steps pre { padding: 13px; background: var(--bg); border: 1px solid var(--border); border-radius: 5px; font: var(--qa-type-code)/var(--qa-leading-body) var(--font-mono); }
.qa-validation-workbench .qa-validation-result > .qa-gap { margin-top: 22px; padding: 15px; border: 1px solid var(--border); border-radius: 5px; color: var(--ink-2); font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-validation-workbench .qa-validation-empty { min-height: 380px; }
.qa-validation-workbench .qa-empty-indicator { display: block; margin-top: 42px; font-size: 42px; color: var(--ink-3); }
.qa-validation-workbench .qa-validation-empty h3 { font: 500 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); margin: 15px 0 8px; }
.qa-validation-workbench .qa-validation-empty > p:not(.qa-gap) { font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); color: var(--ink-2); }
@keyframes qa-validation-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .qa-validation-workbench .qa-run-active .qa-run-indicator { animation: none; } }
@media (max-width: 1120px) { .qa-validation-workbench .qa-validation-layout { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 600px) {
  .qa-validation-workbench .qa-testing-heading { flex-direction: column; gap: 16px; }
  .qa-validation-workbench .qa-validation-heading-actions { width: 100%; flex-direction: row; }
  .qa-validation-workbench .qa-validation-heading-actions .qa-button { flex: 1; }
  .qa-validation-workbench .qa-validation-scope, .qa-validation-workbench .qa-validation-result { padding: 18px; }
  .qa-validation-workbench .qa-evidence { grid-template-columns: 35px minmax(0, 1fr); column-gap: 12px; }
  .qa-validation-workbench .qa-evidence-number { font-size: var(--qa-type-metric); }
  .qa-validation-workbench .qa-evidence h3 { font-size: var(--qa-type-subsection-title); }
  .qa-validation-workbench .qa-evidence > .qa-button { grid-column: 2; grid-row: auto; justify-self: start; margin-bottom: 12px; }
  .qa-validation-workbench .qa-layer-details { grid-column: 2; }
  .qa-validation-workbench .qa-validation-history button { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .qa-validation-workbench .qa-validation-history button time { grid-column: 1 / 3; }
}
.qa-guided-validation { color: var(--ink); }
.qa-guided-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 28px; }
.qa-guided-heading > div { min-width: 0; }
.qa-guided-eyebrow { margin: 0 0 10px; color: var(--accent); font: var(--qa-type-meta)/var(--qa-leading-body) var(--font-sans); letter-spacing: .12em; }
.qa-guided-heading h1 { margin: 0; font: 500 var(--qa-type-page-title)/var(--qa-leading-title) var(--font-sans); }
.qa-guided-heading > div > p:last-child { max-width: 790px; margin: 12px 0 0; font: var(--qa-type-body)/var(--qa-leading-body) var(--font-sans); color: var(--ink-2); }
.qa-guided-heading > .qa-button { flex: none; }
.qa-guided-validation .qa-button { display: inline-flex; justify-content: center; align-items: center; gap: 8px; min-height: 44px; font-size: var(--qa-type-control); line-height: var(--qa-leading-body); }
.qa-guided-validation .qa-button .q-icon { font-size: 21px; }
.qa-guided-tabs { display: flex; gap: 8px; margin: 26px 0 20px; }
.qa-guided-tabs .qa-button { min-height: 38px; background: transparent; }
.qa-guided-tabs [aria-pressed="true"] { color: var(--accent); border-color: var(--accent); background: var(--surface-2); }
.qa-guided-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(250px, .39fr); align-items: start; gap: 24px; }
.qa-guided-main { min-width: 0; }
.qa-guided-card { min-width: 0; padding: 28px; background: var(--surface); border: 1px solid var(--border); border-radius: 9px; }
.qa-guided-card-head { display: flex; gap: 17px; padding-bottom: 24px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
.qa-guided-number { display: flex; justify-content: center; align-items: center; flex: none; width: 37px; height: 37px; color: var(--accent); border: 1px solid var(--accent); border-radius: 50%; font: var(--qa-type-body)/var(--qa-leading-body) var(--font-mono); }
.qa-guided-validation h2 { margin: 0; font: 500 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); }
.qa-guided-card-head p { margin: 7px 0 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-field > label, .qa-guided-validation .qa-validation-cost > label:first-child { display: block; margin: 0 0 10px; font-size: var(--qa-type-control); }
.qa-guided-field select { display: block; width: 100%; min-height: 48px; padding: 12px 14px; border: 1px solid var(--border); border-radius: 5px; color: var(--ink); background: var(--surface-2); font: var(--qa-type-control)/var(--qa-leading-body) var(--font-sans); }
.qa-guided-field select:focus-visible, .qa-guided-validation summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-guided-scope-list { margin-top: 18px; }
.qa-guided-scope-list > details { border-bottom: 1px solid var(--border-2); padding: 17px 0; }
.qa-guided-scope-list summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; cursor: pointer; font-size: var(--qa-type-body); }
.qa-guided-scope-list summary > .q-icon { color: var(--ink-2); font-size: 20px; }
.qa-guided-scope-list p, .qa-guided-pricing p { color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); margin: 12px 0 0; }
.qa-guided-plan h3 { margin: 0 0 10px; font-size: var(--qa-type-subsection-title); font-weight: 500; }
.qa-guided-plan ol { padding-left: 22px; margin: 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-plan li { padding: 5px 0; }
.qa-guided-plan > .qa-gap { margin: 18px 0 0; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-validation .qa-validation-cost { margin-top: 24px; padding-top: 24px; }
.qa-guided-validation .qa-validation-cost input[type="number"] { min-height: 48px; max-width: 280px; }
.qa-guided-validation .qa-small { margin: 12px 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); overflow-wrap: anywhere; }
.qa-guided-pricing { padding: 15px 0; margin-top: 15px; border-top: 1px solid var(--border-2); font-size: var(--qa-type-body); }
.qa-guided-pricing summary { cursor: pointer; color: var(--ink-2); }
.qa-guided-validation .qa-validation-ack { padding: 17px; border: 1px solid var(--border); border-radius: 5px; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); background: var(--surface-2); }
.qa-guided-blocked { display: flex; align-items: flex-start; gap: 13px; margin-top: 24px; padding: 18px; border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 5px; background: var(--surface-2); color: var(--ink-2); }
.qa-guided-blocked > .q-icon { color: var(--accent); font-size: 22px; }
.qa-guided-blocked strong { color: var(--ink); font-size: var(--qa-type-body); font-weight: 500; line-height: var(--qa-leading-body); }
.qa-guided-blocked p, .qa-guided-blocked details { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); margin: 8px 0 0; }
.qa-guided-blocked summary { cursor: pointer; }
.qa-guided-blocked code { display: block; margin-top: 10px; overflow-wrap: anywhere; font-size: var(--qa-type-code); }
.qa-guided-start { padding-top: 25px; margin-top: 25px; border-top: 1px solid var(--border); }
.qa-guided-start > .qa-primary { width: 100%; min-height: 52px; font-size: var(--qa-type-body); }
.qa-guided-start > .qa-small { margin: 12px 0 0; }
.qa-guided-aside { padding: 26px; }
.qa-guided-deliverables { list-style: none; padding: 0; margin: 22px 0 0; }
.qa-guided-deliverables li { display: flex; align-items: flex-start; gap: 11px; padding: 10px 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-deliverables .q-icon { margin-top: 3px; color: var(--accent); font-size: 20px; }
.qa-guided-limits { margin-top: 26px; padding-top: 24px; border-top: 1px solid var(--border); }
.qa-guided-limits h3 { font-size: var(--qa-type-subsection-title); font-weight: 500; margin: 0 0 13px; }
.qa-guided-limits p { color: var(--ink-2); margin: 0; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-ci, .qa-guided-back { display: block; margin-top: 22px; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-back { padding: 0; border: 0; background: transparent; cursor: pointer; text-align: left; }
.qa-guided-next-actions { display: flex; flex-direction: column; gap: 12px; margin-top: 24px; }
.qa-guided-next-actions > .qa-button { width: 100%; white-space: normal; }
.qa-guided-not-run { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 18px; padding: 18px 20px; border: 1px solid var(--border); border-radius: 7px; color: var(--ink-2); font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-guided-not-run .q-icon { font-size: 23px; }
.qa-guided-not-run strong { font: var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-mono); }
.qa-guided-result { min-width: 0; }
.qa-guided-run-hero { display: flex; gap: 18px; align-items: center; margin-bottom: 24px; }
.qa-guided-run-hero > .q-icon { flex: none; font-size: 66px; color: var(--ink-2); }
.qa-guided-run-hero h2 { font: 500 var(--qa-type-result)/var(--qa-leading-title) var(--font-sans); overflow-wrap: anywhere; }
.qa-guided-run-hero > div { flex: 1; min-width: 0; }
.qa-guided-run-hero p { margin: 12px 0 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-run-passed > .q-icon, .qa-guided-run-passed h2 { color: var(--accent); }
.qa-guided-run-failed > .q-icon { color: #e87672; }
.qa-guided-validation .qa-validation-progress { gap: 14px; margin: 0 0 24px; }
.qa-guided-validation .qa-validation-progress progress { min-width: 0; height: 8px; accent-color: var(--accent); flex: 1; }
.qa-guided-outcomes { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); padding: 23px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
.qa-guided-outcomes > div { display: flex; flex-direction: column; align-items: center; gap: 7px; border-right: 1px solid var(--border); }
.qa-guided-outcomes > div:last-child { border-right: 0; }
.qa-guided-outcomes strong { font: 500 var(--qa-type-metric)/var(--qa-leading-title) var(--font-mono); }
.qa-guided-outcomes span { font: var(--qa-type-body)/var(--qa-leading-body) var(--font-mono); }
.qa-outcome-passed { color: var(--accent); }.qa-outcome-failed { color: #e87672; }.qa-outcome-errors { color: #c49035; }.qa-outcome-skipped { color: var(--ink-2); }
.qa-guided-validation .qa-guided-measurement { font-size: var(--qa-type-meta); margin-bottom: 25px; }
.qa-guided-evidence-title { margin: 28px 0 16px; font: 500 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); }
.qa-guided-step-head, .qa-guided-step-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) 110px 70px; align-items: start; gap: 12px; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-step-head { padding: 13px 16px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 7px 7px 0 0; color: var(--ink-2); }
.qa-guided-steps { padding: 0; margin: 0; list-style: none; background: var(--surface); border: 1px solid var(--border); border-top: 0; border-radius: 0 0 7px 7px; }
.qa-guided-steps > li { padding: 16px; border-bottom: 1px solid var(--border-2); min-width: 0; }
.qa-guided-steps > li:last-child { border-bottom: 0; }
.qa-guided-step-row strong { font-weight: 500; overflow-wrap: anywhere; }
.qa-guided-step-index, .qa-guided-step-row > span:last-child { color: var(--ink-2); font-family: var(--font-mono); }
.qa-guided-step-status { font: var(--qa-type-meta)/var(--qa-leading-body) var(--font-mono); overflow-wrap: anywhere; color: var(--accent); }
.qa-guided-step-status[data-status="failed"], .qa-guided-step-status[data-status="timed_out"] { color: #e87672; }
.qa-guided-step-status[data-status="pending"], .qa-guided-step-status[data-status="cancelled"], .qa-guided-step-status[data-status="incomplete"] { color: var(--ink-2); }
.qa-guided-validation .qa-guided-step-detail { margin: 8px 0 0 40px; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-steps .qa-pytest-progress { display: block; margin: 12px 0 0 40px; color: var(--ink-2); font: var(--qa-type-code)/var(--qa-leading-body) var(--font-mono); }
.qa-guided-steps .qa-pytest-progress p { margin: 7px 0; overflow-wrap: anywhere; }
.qa-guided-step-details { margin: 12px 0 0 40px; min-width: 0; }
.qa-guided-step-details > summary { display: flex; align-items: center; gap: 7px; color: var(--accent); cursor: pointer; width: fit-content; min-height: 32px; font-size: var(--qa-type-body); }
.qa-guided-step-details summary .q-icon { font-size: 18px; }
.qa-guided-step-details pre { padding: 14px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg); max-height: 280px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: var(--qa-type-code)/var(--qa-leading-body) var(--font-mono); }
.qa-guided-step-details h4, .qa-guided-step-details small { font-size: var(--qa-type-subsection-title); font-weight: 400; color: var(--ink-2); }
.qa-guided-step-details details { font-size: var(--qa-type-body); margin-top: 15px; }
.qa-guided-raw-step { display: flex; flex-wrap: wrap; gap: 6px 12px; margin: 15px 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-raw-step code { font: var(--qa-type-code)/var(--qa-leading-body) var(--font-mono); overflow-wrap: anywhere; }
.qa-guided-history { margin-top: 24px; border: 1px solid var(--border); border-radius: 7px; padding: 17px 20px; background: var(--surface); }
.qa-guided-history > summary { color: var(--ink-2); cursor: pointer; font-size: var(--qa-type-body); }
.qa-guided-history > summary > span { font: var(--qa-type-meta)/var(--qa-leading-body) var(--font-mono); margin-left: 10px; }
.qa-guided-validation .qa-guided-history .qa-validation-history { margin-top: 12px; }
.qa-guided-spin { animation: qa-validation-spin 1.4s linear infinite; }
.qa-guided-evidence-column { display: none; }
.qa-guided-showing-result .qa-guided-heading { margin-bottom: 10px; align-items: center; }
.qa-guided-showing-result .qa-guided-heading h1 { font-size: var(--qa-type-page-title); line-height: var(--qa-leading-title); }
.qa-guided-showing-result :deep(.qa-flow-steps) { margin: 10px 0 14px; }
.qa-guided-showing-result .qa-guided-tabs { margin: 12px 0 16px; }
.qa-guided-showing-result .qa-guided-run-hero { margin-bottom: 12px; }
.qa-guided-showing-result .qa-guided-run-hero h2 { font-size: var(--qa-type-result); }
.qa-guided-showing-result .qa-guided-run-hero > .q-icon { font-size: 56px; }
.qa-guided-showing-result .qa-guided-run-hero p { margin-top: 6px; line-height: 1.65; }
.qa-guided-showing-result .qa-validation-progress { margin-bottom: 18px; }
.qa-guided-showing-result .qa-guided-outcomes { padding: 12px 10px; }
.qa-guided-showing-result .qa-guided-outcomes > div { gap: 5px; }
.qa-guided-showing-result .qa-guided-outcomes strong { font-size: var(--qa-type-metric); }
.qa-guided-showing-result .qa-guided-measurement { margin-bottom: 14px; }
.qa-guided-showing-result .qa-guided-evidence-title { margin: 16px 0 12px; font-size: var(--qa-type-section-title); line-height: var(--qa-leading-title); }
.qa-guided-step-details .qa-guided-step-detail { margin-left: 0; }
.qa-guided-validation .qa-guided-history .qa-validation-history button { font-size: var(--qa-type-body); }
@media (min-width: 1181px) {
  .qa-guided-step-head, .qa-guided-step-row { grid-template-columns: 24px minmax(0, 1fr) 70px 54px 190px; }
  .qa-guided-evidence-column { display: block; }
  .qa-guided-steps > li { padding: 10px 16px; }
  .qa-guided-step-details:not([open]) { width: 190px; margin: -27px 0 0 auto; }
  .qa-guided-step-details:not([open]) > summary { font-size: var(--qa-type-body); }
}
@media (prefers-reduced-motion: reduce) { .qa-guided-spin { animation: none; } }
@media (max-width: 1100px) { .qa-guided-layout { grid-template-columns: minmax(0, 1fr) minmax(230px, .43fr); gap: 18px; }.qa-guided-card { padding: 22px; }.qa-guided-step-head, .qa-guided-step-row { grid-template-columns: 22px minmax(0, 1fr) 85px 45px; gap: 8px; } }
@media (max-width: 850px) { .qa-guided-layout { grid-template-columns: minmax(0, 1fr); }.qa-guided-heading { flex-wrap: wrap; }.qa-guided-aside { display: block; }.qa-guided-deliverables { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 15px; }.qa-guided-next-actions { max-width: 440px; } }
@media (max-width: 600px) { .qa-guided-heading { gap: 18px; margin-bottom: 22px; }.qa-guided-heading h1 { font-size: var(--qa-type-page-title); }.qa-guided-heading > div > p:last-child { font-size: var(--qa-type-body); }.qa-guided-card { padding: 19px; }.qa-guided-card-head { gap: 12px; }.qa-guided-validation h2 { font-size: var(--qa-type-section-title); }.qa-guided-deliverables { display: block; }.qa-guided-run-hero { gap: 12px; flex-wrap: wrap; }.qa-guided-run-hero > .q-icon { font-size: 46px; }.qa-guided-run-hero h2 { font-size: var(--qa-type-result); }.qa-guided-run-hero > .qa-button { margin-left: 58px; }.qa-guided-step-head { display: none; }.qa-guided-steps { border-top: 1px solid var(--border); border-radius: 7px; }.qa-guided-step-row { grid-template-columns: 22px minmax(0, 1fr) auto; gap: 8px; }.qa-guided-step-row > span:last-child { grid-column: 2 / 4; font-size: var(--qa-type-meta); }.qa-guided-step-status { max-width: 95px; }.qa-guided-validation .qa-guided-step-detail, .qa-guided-steps .qa-pytest-progress, .qa-guided-step-details { margin-left: 30px; }.qa-guided-outcomes { padding: 19px 6px; }.qa-guided-outcomes strong { font-size: var(--qa-type-metric); }.qa-guided-outcomes span { font-size: var(--qa-type-meta); }.qa-guided-tabs { flex-wrap: wrap; }.qa-guided-history { padding: 16px; } }
@media (max-width: 600px) {
  .qa-guided-step-row > span:last-child, .qa-guided-outcomes span { font-size: var(--qa-type-body); }
  .qa-guided-showing-result .qa-guided-heading h1 { font-size: var(--qa-type-page-title); }
  .qa-guided-showing-result .qa-guided-run-hero > .q-icon { font-size: 46px; }
  .qa-guided-showing-result .qa-guided-outcomes strong { font-size: var(--qa-type-metric); }
}
.qa-faithful-visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
.qa-run-actions { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
.qa-run-execution-status { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 8px; color: var(--ink-2); font-size: var(--qa-type-meta); }
.qa-run-execution-status strong { color: var(--ink); font-weight: 600; }
.qa-guided-showing-result .qa-guided-layout { grid-template-columns: minmax(0, 1fr) 330px; gap: 25px; }
.qa-guided-showing-result .qa-faithful-result-title { margin: 0; font: 600 var(--qa-type-page-title)/var(--qa-leading-title) var(--font-sans); letter-spacing: -.025em; }
.qa-guided-showing-result .qa-guided-run-hero { gap: 22px; min-height: 84px; margin: 6px 0 0; }
.qa-guided-showing-result .qa-guided-run-hero > .q-icon { font-size: 80px; }
.qa-guided-showing-result .qa-guided-run-hero h2 { flex: 1; font: 500 var(--qa-type-result)/var(--qa-leading-title) var(--font-sans); letter-spacing: -.025em; }
.qa-guided-showing-result .qa-guided-run-hero:not(.qa-guided-run-passed) h2 { font-size: var(--qa-type-section-title); line-height: var(--qa-leading-title); }
.qa-guided-showing-result .qa-guided-run-hero .qa-button { min-height: 44px; padding: 8px 16px; font-size: var(--qa-type-control); }
.qa-guided-showing-result .qa-guided-run-hero .qa-button .q-icon { font-size: 26px; }
.qa-guided-showing-result .qa-faithful-rerun { margin-left: auto; }
.qa-faithful-result-subtitle { margin: 8px 0 20px; font: 400 var(--qa-type-lead)/var(--qa-leading-body) var(--font-sans); }
.qa-guided-showing-result :deep(.qa-flow-steps) { min-height: 40px; margin: 23px 0 0; }
.qa-faithful-run-metadata { display: flex; align-items: center; gap: 24px; min-height: 36px; margin-top: 16px; color: var(--ink-2); font: 400 var(--qa-type-meta)/var(--qa-leading-body) var(--font-sans); }
.qa-faithful-run-metadata > span:not(.qa-faithful-visually-hidden) { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.qa-faithful-run-metadata > span + span:not(.qa-faithful-visually-hidden) { border-left: 1px solid var(--ink-3); padding-left: 24px; }
.qa-faithful-run-metadata .q-icon { font-size: 27px; color: var(--ink); }
.qa-guided-showing-result .qa-validation-progress { margin-top: 14px; }
.qa-guided-showing-result .qa-guided-outcomes { box-sizing: border-box; min-height: 92px; margin-top: 20px; padding: 16px 10px; border-radius: 8px; }
.qa-guided-showing-result .qa-guided-outcomes > div { gap: 0; justify-content: center; }
.qa-guided-showing-result .qa-guided-outcomes strong { font: 600 var(--qa-type-metric)/var(--qa-leading-title) var(--font-sans); }
.qa-guided-showing-result .qa-guided-outcomes span { font: 500 var(--qa-type-body)/var(--qa-leading-body) var(--font-sans); }
.qa-guided-showing-result .qa-outcome-failed { color: #f45e5e; }
.qa-guided-showing-result .qa-outcome-errors { color: #ffba4a; }
.qa-guided-showing-result .qa-guided-evidence-title { margin: 34px 0 9px; font: 500 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); }
.qa-evidence-intro { margin: 0 0 12px; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-evidence-explainer { margin: 0 0 8px; color: var(--ink); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-evidence-result-note, .qa-evidence-count-hint { color: var(--ink-2); font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-evidence-count-hint { margin: 8px 0 0; }
.qa-evidence-technical { min-width: 0; margin: 12px 0; border-top: 1px solid var(--border); padding-top: 10px; }
.qa-evidence-technical > summary { width: fit-content; cursor: pointer; color: var(--ink-2); font-size: var(--qa-type-control); }
.qa-evidence-technical > summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-faithful-table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
.qa-faithful-table-wrap:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.qa-guided-validation .qa-faithful-evidence-table { width: 100%; min-width: 740px; margin: 0; padding: 0; border: 0; border-collapse: collapse; table-layout: fixed; border-radius: 0; font: 400 var(--qa-type-body)/var(--qa-leading-body) var(--font-sans); }
/* Keep status/count/actions readable; give identifiers the remaining width. */
.qa-faithful-col-index { width: 56px; }.qa-faithful-col-check { width: auto; }.qa-faithful-col-result { width: 160px; }.qa-faithful-col-count { width: 84px; }.qa-faithful-col-log { width: 200px; }
.qa-faithful-evidence-table thead { background: var(--surface-2); color: var(--ink-2); }
.qa-faithful-evidence-table th, .qa-faithful-evidence-table td { box-sizing: border-box; text-align: left; padding: 9px 16px; font-size: inherit; font-weight: 400; vertical-align: middle; border-bottom: 1px solid var(--border); }
.qa-faithful-evidence-table th[scope="row"] { white-space: normal; overflow-wrap: anywhere; word-break: normal; }
.qa-faithful-evidence-table thead tr { height: 49px; }
.qa-faithful-evidence-table .qa-guided-step-row { display: table-row; height: 49px; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-faithful-evidence-table .qa-guided-step-row > th, .qa-faithful-evidence-table .qa-guided-step-row > td { height: 49px; padding-top: 7px; padding-bottom: 7px; }
.qa-faithful-evidence-table tbody:last-child .qa-guided-step-row > * { border-bottom: 0; }
.qa-faithful-evidence-table .qa-guided-step-index { color: var(--ink-2); font-family: var(--font-serif); }
.qa-faithful-evidence-table .qa-guided-step-status { display: inline-flex; align-items: center; gap: 14px; vertical-align: middle; font: inherit; white-space: nowrap; }
.qa-faithful-evidence-table .qa-guided-step-status .q-icon { font-size: 28px; }
.qa-faithful-evidence-table .qa-faithful-log-button { display: inline-flex; align-items: center; justify-content: flex-start; gap: 10px; min-height: 30px; padding: 0; border: 0; background: transparent; color: var(--accent); vertical-align: middle; font: 400 var(--qa-type-control)/var(--qa-leading-body) var(--font-sans); cursor: pointer; white-space: nowrap; }
.qa-faithful-log-button .q-icon { font-size: 24px; }.qa-faithful-log-button .q-icon:last-child { font-size: 22px; }
.qa-faithful-log-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
.qa-faithful-evidence-table .qa-faithful-detail-row > td { padding: 0 28px; background: var(--bg); }
.qa-guided-validation .qa-faithful-detail-row .qa-guided-step-details { width: auto; margin: 0; padding: 12px 0; }
.qa-guided-validation .qa-faithful-detail-row .qa-guided-step-detail, .qa-faithful-detail-row .qa-pytest-progress { margin-left: 0; }
.qa-guided-showing-result .qa-guided-aside { box-sizing: border-box; min-height: 0; margin-top: 27px; padding: 26px 25px; border-radius: 8px; }
.qa-guided-showing-result .qa-guided-aside h2 { font: 500 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); }
.qa-guided-showing-result .qa-guided-next-actions { gap: 16px; margin-top: 13px; }
.qa-guided-showing-result .qa-guided-next-actions > .qa-button { min-height: 44px; padding: 10px 14px; font-size: var(--qa-type-control); gap: 13px; }
.qa-guided-showing-result .qa-guided-next-actions .q-icon { font-size: 28px; }
.qa-guided-showing-result .qa-guided-limits { margin-top: 34px; padding-top: 27px; }
.qa-guided-showing-result .qa-guided-limits h3 { margin: 0 0 12px; font: 500 var(--qa-type-subsection-title)/var(--qa-leading-title) var(--font-sans); }
.qa-guided-showing-result .qa-guided-limits p { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-guided-showing-result .qa-guided-history:not([open]) { display: none; }
.qa-guided-showing-result .qa-guided-history:not([open]) > summary { width: fit-content; font-size: var(--qa-type-body); }
@media (max-width: 1250px) {
  .qa-guided-showing-result .qa-guided-layout { grid-template-columns: minmax(0, 1fr) 285px; gap: 24px; }
  .qa-faithful-evidence-table th, .qa-faithful-evidence-table td { padding-right: 15px; padding-left: 15px; }
  .qa-faithful-evidence-table .qa-guided-step-status { gap: 7px; }
  .qa-faithful-evidence-table .qa-faithful-log-button { gap: 5px; }
  .qa-guided-showing-result .qa-guided-next-actions > .qa-button { font-size: var(--qa-type-control); }
}
@media (max-width: 1400px) {
  .qa-guided-showing-result .qa-guided-layout { grid-template-columns: minmax(0, 1fr); }
  .qa-guided-showing-result .qa-guided-aside { min-height: 0; margin-top: 0; }
  .qa-guided-showing-result .qa-guided-next-actions { max-width: none; }
  .qa-guided-showing-result .qa-guided-limits { margin-top: 26px; }
}
@media (max-width: 650px) {
  .qa-guided-showing-result .qa-faithful-result-title { font-size: var(--qa-type-page-title); line-height: var(--qa-leading-title); }
  .qa-guided-showing-result .qa-guided-run-hero { gap: 14px; min-height: 65px; }
  .qa-guided-showing-result .qa-guided-run-hero > .q-icon { font-size: 60px; }
  .qa-guided-showing-result .qa-guided-run-hero h2 { font-size: var(--qa-type-result); line-height: var(--qa-leading-title); }
  .qa-guided-showing-result .qa-guided-run-hero:not(.qa-guided-run-passed) h2 { font-size: var(--qa-type-section-title); }
  .qa-guided-showing-result .qa-guided-run-hero .qa-button { margin-left: 0; min-height: 44px; padding: 8px 14px; font-size: var(--qa-type-control); }
  .qa-faithful-result-subtitle { font-size: var(--qa-type-lead); line-height: var(--qa-leading-body); }
  .qa-faithful-run-metadata { gap: 8px 16px; flex-wrap: wrap; margin-top: 24px; font-size: var(--qa-type-meta); line-height: var(--qa-leading-body); }
  .qa-faithful-run-metadata > span + span:not(.qa-faithful-visually-hidden) { padding-left: 0; border-left: 0; }
  .qa-guided-showing-result .qa-guided-outcomes { height: 104px; padding: 14px 4px; margin-top: 20px; }
  .qa-guided-showing-result .qa-guided-outcomes strong { font-size: var(--qa-type-metric); line-height: var(--qa-leading-title); }
  .qa-guided-showing-result .qa-guided-outcomes span { font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
  .qa-guided-showing-result .qa-guided-evidence-title { margin-top: 24px; font-size: var(--qa-type-section-title); }
  .qa-faithful-evidence-table .qa-guided-step-row { display: table-row; font-size: var(--qa-type-body); }
  .qa-guided-showing-result .qa-guided-aside { padding: 22px; }
}
</style>
