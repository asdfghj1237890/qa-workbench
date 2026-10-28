<template>
  <section class="qa-flow-chooser" aria-labelledby="qa-flow-title" data-testid="qa-verification-chooser">
    <header class="qa-flow-intro"><h1>{{ $t('qaFaithfulFlow.landingTitle') }}</h1><p>{{ $t('qaFaithfulFlow.landingIntro') }}</p></header>
    <div class="qa-flow-question"><h2 id="qa-flow-title">{{ $t('qaFlow.chooseTitle') }}</h2><p>{{ $t('qaFaithfulFlow.chooseHint') }}</p></div>
    <div class="qa-flow-task-grid" role="group" :aria-label="$t('qaFlow.chooseTitle')">
      <button v-for="task in tasks" :key="task.id" class="qa-flow-task" :class="{ selected: selected === task.id }" :aria-pressed="selected === task.id" :data-testid="'qa-choose-' + task.id" @click="selected = task.id">
        <QaIcon :name="task.icon" aria-hidden="true" />
        <QaIcon v-if="selected === task.id" class="qa-flow-selection-check" name="check" aria-hidden="true" />
        <span class="qa-flow-task-copy"><strong>{{ $t('qaFlow.tasks.' + task.id + '.title') }}</strong><span>{{ $t('qaFaithfulFlow.descriptions.' + task.id) }}</span></span>
        <span class="qa-flow-cost" :class="{ paid: task.paid }">{{ $t(task.paid ? 'qaFlow.costConsent' : 'qaFlow.noModelCost') }}</span>
      </button>
    </div>
    <section class="qa-flow-selection" aria-live="polite">
      <div class="qa-flow-scope"><h2>{{ $t('qaFlow.selected', { name: $t('qaFlow.tasks.' + selected + '.title') }) }}</h2><p>{{ $t('qaFaithfulFlow.scopeIntro') }}</p><ol><li v-for="index in 3" :key="index"><span class="qa-flow-scope-number">{{ index }}</span><div><strong>{{ $t('qaFaithfulFlow.scopes.' + selected + '.' + (index - 1) + '.title') }}</strong><p>{{ $t('qaFaithfulFlow.scopes.' + selected + '.' + (index - 1) + '.body') }}</p></div></li></ol></div>
      <div class="qa-flow-selection-actions"><button class="qa-button qa-primary" data-testid="qa-configure-selected" @click="$emit('navigate', selected)">{{ $t('qaFlow.configure') }}<QaIcon name="arrow_forward" aria-hidden="true" /></button><small><QaIcon name="info" aria-hidden="true" />{{ $t('qaFlow.noAutoStart') }}</small><button class="qa-flow-recent" data-testid="qa-open-recent" @click="$emit('navigate', 'history')"><QaIcon name="history" aria-hidden="true" />{{ $t('qaFaithfulFlow.recent') }}<QaIcon name="arrow_forward" aria-hidden="true" /></button></div>
    </section>
    <div v-if="validation.active || live.active" class="qa-flow-active" role="status"><QaIcon name="pending" aria-hidden="true" />{{ $t('qaFlow.activeNotice') }}</div>
  </section>
</template>

<script setup>
import { ref } from "vue";
import QaIcon from "./QaIcon.vue";
defineProps({ validation: { type: Object, default: () => ({}) }, live: { type: Object, default: () => ({}) } });
defineEmits(["navigate"]);
const selected = ref("offline_regression");
const tasks = [
  { id: "offline_regression", icon: "fact_check", paid: false },
  { id: "es_integration", icon: "link", paid: false },
  { id: "real_es_llm_e2e", icon: "database", paid: true },
  { id: "model_evaluation", icon: "smart_toy", paid: true },
  { id: "real_corpus_quality", icon: "find_in_page", paid: true },
];
</script>

<style scoped>
.qa-flow-intro { padding-top: 0; }
.qa-flow-intro h1 { margin: 0; font: 400 var(--qa-type-page-title)/var(--qa-leading-title) var(--font-sans); letter-spacing: -.035em; }
.qa-flow-intro > p:last-child { margin: 12px 0 0; color: var(--ink-2); font-size: var(--qa-type-lead); line-height: var(--qa-leading-body); }
.qa-flow-question { margin-bottom: 21px; }
.qa-flow-question h2 { margin: 0; font: 400 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); letter-spacing: -.02em; }
.qa-flow-question p { margin: 10px 0 0; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-flow-task-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.qa-flow-task { display: flex; align-items: flex-start; gap: 32px; position: relative; min-height: 120px; padding: 18px 22px; background: var(--surface); color: var(--ink); border: 1px solid var(--border); border-radius: 9px; text-align: left; cursor: pointer; }
.qa-flow-task:hover { border-color: var(--accent); }
.qa-flow-task.selected { background: var(--accent-soft); border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.qa-flow-task:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.qa-flow-task > .qa-icon { font-size: 44px; margin-top: 10px; color: var(--ink-2); }
.qa-flow-task.selected > .qa-icon { color: var(--accent); }
.qa-flow-task > .qa-flow-selection-check { position: absolute; top: 25px; right: 22px; font-size: 34px; margin: 0; }
.qa-flow-task.selected > .qa-flow-selection-check { background: var(--accent); color: var(--bg); border-radius:50%; padding:3px; }
.qa-flow-task-copy { display: grid; gap: 9px; min-width: 0; padding-right: 16px; }
.qa-flow-task-copy strong { font: 400 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); }
.qa-flow-task-copy > span { color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); white-space: pre-line; }
.qa-flow-cost { position: absolute; right: 23px; top: 26px; color: var(--accent); border: 1px solid #285d53; border-radius: 5px; padding: 4px 11px; font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-flow-task.selected .qa-flow-cost { top: auto; bottom: 28px; }
.qa-flow-cost.paid { color: var(--warning, #b9aa69); border-color: color-mix(in srgb, var(--warning, #b9aa69) 60%, var(--border)); }
.qa-flow-selection { display: grid; grid-template-columns: minmax(0, 580px) minmax(0, 1fr); align-items: center; gap: 0; padding: 20px 36px; margin-top: 20px; min-height: 260px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }
.qa-flow-selection h2 { margin: 0 0 12px; font: 400 var(--qa-type-section-title)/var(--qa-leading-title) var(--font-sans); }
.qa-flow-scope > p { margin: 6px 0 10px; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-flow-scope ol { list-style: none; padding:0; margin:0; display:grid; gap:12px; }
.qa-flow-scope li { display:flex; align-items:flex-start; gap:22px; }
.qa-flow-scope-number { display:inline-flex; align-items:center; justify-content:center; width:38px; height:38px; flex:none; border-radius:50%; background:var(--surface-2); font:var(--qa-type-body)/var(--qa-leading-body) var(--font-sans); }
.qa-flow-scope li strong { display:block; font-size:var(--qa-type-subsection-title); font-weight:500; line-height: var(--qa-leading-title); }
.qa-flow-scope li p { margin:0; color:var(--ink-2); font-size:var(--qa-type-body); line-height: var(--qa-leading-body); }
.qa-flow-selection-actions { display: flex; flex-direction:column; justify-content:center; gap:16px; padding:20px 0 8px 50px; min-height:200px; border-left:1px solid var(--border); }
.qa-flow-selection-actions .qa-button { justify-content: center; width: 100%; min-height:48px; font-size:var(--qa-type-control); font-weight:600; gap:16px; }
.qa-flow-selection-actions small { display:flex; align-items:flex-start; gap:9px; color:var(--ink-2); font-size:var(--qa-type-meta); line-height: var(--qa-leading-body); }
.qa-flow-selection-actions small .qa-icon { font-size:var(--qa-type-meta); margin-top:3px; }
.qa-flow-recent { display:flex; align-items:center; gap:11px; background:transparent; border:0; border-top:1px solid var(--border); padding:26px 0 0; margin-top:12px; color:var(--accent); font-size:var(--qa-type-control); text-align:left; text-decoration:underline; text-underline-offset:5px; cursor:pointer; }
.qa-flow-recent .qa-icon { font-size:25px; }
.qa-flow-active { display: flex; align-items: center; gap: 10px; margin-top: 18px; color: var(--accent); font-size: var(--qa-type-meta); }
@media (max-width: 1200px) { .qa-flow-task { gap:18px; padding:23px; }.qa-flow-cost { font-size:var(--qa-type-meta); }.qa-flow-task-copy > span { font-size:var(--qa-type-body); }.qa-flow-task-copy strong { font-size:var(--qa-type-section-title); }.qa-flow-selection { grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr); }.qa-flow-selection-actions { padding-left:28px; }.qa-flow-scope li { gap:14px; }.qa-flow-scope li p { font-size:var(--qa-type-body); } }
@media (max-width: 1400px) {
  .qa-flow-task { display:grid; grid-template-columns:44px minmax(0,1fr); gap:12px 24px; }
  .qa-flow-task > .qa-icon:not(.qa-flow-selection-check) { grid-column:1; grid-row:1; }
  .qa-flow-task-copy { grid-column:2; grid-row:1; padding-right:0; }
  .qa-flow-task-copy strong { padding-right:38px; overflow-wrap:anywhere; }
  .qa-flow-task .qa-flow-cost { position:static; grid-column:2; grid-row:2; justify-self:start; max-width:100%; margin:0; }
}
@media (max-width: 1000px) { .qa-flow-selection { grid-template-columns:1fr; gap:22px; }.qa-flow-selection-actions { border-left:0; border-top:1px solid var(--border); padding:24px 0 0; min-height:0; } }
@media (max-width: 760px) { .qa-flow-intro h1 { font-size:var(--qa-type-page-title); }.qa-flow-question h2 { font-size:var(--qa-type-section-title); }.qa-flow-intro p, .qa-flow-question p { font-size:var(--qa-type-body); }.qa-flow-task-grid { grid-template-columns:1fr; gap:12px; }.qa-flow-task { min-height:150px; padding:20px; gap:14px; }.qa-flow-task-copy strong { font-size:var(--qa-type-section-title); }.qa-flow-selection { padding:22px; }.qa-flow-selection h2 { font-size:var(--qa-type-section-title); }.qa-flow-scope li strong { font-size:var(--qa-type-subsection-title); }.qa-flow-selection-actions .qa-button { font-size:var(--qa-type-control); }.qa-flow-recent { font-size:var(--qa-type-control); } }
</style>
