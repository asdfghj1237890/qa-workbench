<template>
  <ol class="qa-flow-steps" :class="'qa-flow-steps-' + variant" :aria-label="$t('qaFlow.journey')">
    <li v-for="(label, index) in labels" :key="label" :class="{ current: step === index, done: step > index }" :aria-current="step === index ? 'step' : undefined">
      <span class="qa-flow-step-number"><QaIcon v-if="step > index" name="check" aria-hidden="true" /><span v-else>{{ index + 1 }}</span></span>
      <span class="qa-flow-step-copy"><strong>{{ $t(variant === 'model' ? 'qaFaithfulFlow.modelSteps.' + label + '.title' : variant === 'evidence' ? 'qaFaithfulFlow.evidenceSteps.' + label : 'qaFlow.steps.' + label) }}</strong><small v-if="variant === 'model'">{{ $t('qaFaithfulFlow.modelSteps.' + label + '.hint') }}</small></span>
    </li>
  </ol>
</template>

<script setup>
import QaIcon from "./QaIcon.vue";
defineProps({ step: { type: Number, default: 0 }, variant: { type: String, default: 'default' } });
const labels = ["choose", "configure", "run", "evidence"];
</script>

<style scoped>
.qa-flow-steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); list-style: none; margin: 28px 0 30px; padding: 0; gap: 20px; }
.qa-flow-steps li { position: relative; display: flex; align-items: center; gap: 18px; color: var(--ink-2); font-size: var(--qa-type-body); line-height: var(--qa-leading-body); min-width: 0; }
.qa-flow-step-copy { display: grid; gap: 3px; min-width: 0; }
.qa-flow-step-copy strong { font-weight: 500; white-space: nowrap; }
.qa-flow-step-copy small { font-size: var(--qa-type-meta); font-weight: 400; white-space: nowrap; }
.qa-flow-step-number { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border: 2px solid #62625d; border-radius: 50%; flex: none; background: var(--surface-2); font: var(--qa-type-body)/var(--qa-leading-body) var(--font-sans); box-shadow: inset 0 0 0 3px rgba(255,255,255,.03); }
.qa-flow-steps .current { color: var(--accent); }
.current .qa-flow-step-number, .done .qa-flow-step-number { background: var(--accent); color: var(--bg); border-color: var(--accent); }
.qa-flow-step-number .qa-icon { font-size: 25px; }
.qa-flow-steps-chooser { height: 82px; margin: 14px 0 34px; gap: 0; }
.qa-flow-steps-chooser li { flex-direction: column; gap: 10px; align-items: center; font-size: var(--qa-type-body); }
.qa-flow-steps-chooser li::after { content: ''; position: absolute; left: calc(50% + 36px); top: 19px; height: 2px; width: calc(100% - 72px); background: var(--border); }
.qa-flow-steps-chooser li:last-child::after { display: none; }
.qa-flow-steps-chooser li:first-child { transform: translateX(-28px); }.qa-flow-steps-chooser li:nth-child(2) { transform: translateX(-12px); }.qa-flow-steps-chooser li:nth-child(3) { transform: translateX(16px); }.qa-flow-steps-chooser li:last-child { transform: translateX(32px); }
.qa-flow-steps-model { grid-template-columns: 1.11fr 1.035fr 1.035fr .82fr; min-height: 62px; margin: 12px 0 22px; gap: 26px; }
.qa-flow-steps-model li { align-items: flex-start; gap: 20px; font-size: var(--qa-type-body); }
.qa-flow-steps-model .qa-flow-step-copy { gap: 5px; }
.qa-flow-steps-model .qa-flow-step-copy strong, .qa-flow-steps-model .qa-flow-step-copy small { white-space: normal; overflow-wrap: anywhere; }
.qa-flow-steps-model .qa-flow-step-number { margin-top: 1px; }
.qa-flow-steps-model li:not(:last-child)::after { content:''; position:absolute; height:2px; background:var(--border); top:19px; left:calc(100% - 104px); width:110px; }
.qa-flow-steps-evidence { grid-template-columns:1.11fr 1.025fr 1.11fr .755fr; gap: 26px; margin: 29px 0 28px; }
.qa-flow-steps-evidence li { font-size: var(--qa-type-body); gap: 17px; }
.qa-flow-steps-evidence li:not(:last-child)::after { content:''; position:absolute; height:1px; background:var(--accent); width:32px; top:19px; right:-21px; }
@media (max-width: 1100px) { .qa-flow-steps-model, .qa-flow-steps-evidence { grid-template-columns:repeat(4,minmax(0,1fr)); }.qa-flow-steps-model li::after { display:none; }.qa-flow-steps-model .qa-flow-step-copy small { white-space: normal; font-size:var(--qa-type-meta); }.qa-flow-steps-model li { gap:10px; font-size:var(--qa-type-body); }.qa-flow-steps-evidence li { gap:9px; font-size:var(--qa-type-body); } }
@media (max-width: 760px) { .qa-flow-steps { gap:8px; margin:20px 0 24px; height:auto; }.qa-flow-steps li { flex-direction:column; align-items:flex-start; gap:8px; font-size:var(--qa-type-meta); transform:none !important; }.qa-flow-step-copy strong { white-space:normal; }.qa-flow-step-copy small { display:none; }.qa-flow-step-number { width:30px; height:30px; font-size:var(--qa-type-body); }.qa-flow-steps li::after { display:none; }.qa-flow-steps-evidence li { font-size:var(--qa-type-meta); } }
</style>
