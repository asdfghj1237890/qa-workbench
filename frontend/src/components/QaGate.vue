<template>
  <div v-if="session.status.value === 'ready'" class="qa-shell">
    <nav v-if="!observatoryRoute" class="qa-toolbar" aria-label="QA">
      <strong>QA</strong>
      <span>{{ session.user.value.email }}</span>
      <router-link class="qa-toolbar-link" to="/">{{ $t('observatory.back') }}</router-link>
      <router-link class="qa-toolbar-link" to="/observatory">{{ $t('observatory.navigation') }}</router-link>
      <button class="qa-button" @click="session.logout">{{ $t('qa.logout') }}</button>
    </nav>
    <router-view :key="session.generation.value" />
  </div>
  <main v-else class="qa-login ns" data-mode="light" data-font="editorial">
    <section class="qa-login-card" aria-labelledby="qa-title">
      <div class="qa-wordmark">{{ branding.name }}<b>QA</b></div>
      <p class="qa-eyebrow">{{ $t('qa.environment') }}</p>
      <h1 id="qa-title">{{ $t('qa.title') }}</h1>
      <p>{{ $t('qa.description') }}</p>
      <p v-if="session.status.value === 'unavailable'" role="alert">{{ $t('qa.unavailable') }}</p>
      <p v-else-if="session.status.value === 'loading'" role="status" aria-live="polite">{{ $t('qa.restoring') }}</p>
      <button v-else class="qa-button qa-google" :disabled="session.status.value === 'signing-in'" @click="session.login">
        {{ $t(session.status.value === 'signing-in' ? 'qa.signingIn' : 'qa.google') }}
      </button>
      <p v-if="session.error.value" class="qa-error" role="alert">{{ $t('qa.errors.' + session.error.value) }}</p>
      <a href="/">{{ $t('qa.publicSite') }}</a>
    </section>
  </main>
</template>
<script setup>
import { computed, inject, onMounted, provide } from "vue";
import { routeLocationKey } from "vue-router";
import { getQaSession } from "../lib/qaSession.js";
import { getQaAdapter } from "../lib/runtime.js";
const branding = getQaAdapter().branding;
const session = getQaSession();
const route = inject(routeLocationKey, null);
const observatoryRoute = computed(() => route?.path === "/observatory");
provide("qa-shell-controls", { user: session.user, logout: session.logout });
onMounted(session.start);
</script>
<style scoped>
.qa-shell { height: 100dvh; display: flex; flex-direction: column; }
.qa-shell :deep(.ns) { min-height: 0; flex: 1; }
.qa-shell :deep(.ns .app) { height: 100%; }
.qa-toolbar { display: flex; gap: 12px; align-items: center; padding: 7px 18px; background: #20251f; color: #f5f4eb; font: 12px "IBM Plex Mono", monospace; }
.qa-toolbar span { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.qa-toolbar .qa-toolbar-link { color: #f5f4eb; font-size: 12px; text-decoration: none; white-space: nowrap; }
.qa-toolbar .qa-toolbar-link:hover, .qa-toolbar .qa-toolbar-link.router-link-exact-active { text-decoration: underline; text-underline-offset: 4px; }
.qa-toolbar strong, .qa-wordmark b { background: #E4F0ED; color: #20251f; padding: 3px 6px; border-radius: 3px; }
.qa-login { min-height: 100dvh; display: grid; place-items: center; padding: 28px; background: #f5f4eb; color: #20251f; }
.qa-login-card { max-width: 460px; width: 100%; border: 1px solid #cbcbbf; padding: 38px; background: #fffef8; border-radius: 12px; }
.qa-wordmark { font: 900 30px "Noto Serif TC", serif; display: flex; gap: 0; align-items: center; }
.qa-wordmark span { color: #137567; }.qa-wordmark b { font: 600 12px "IBM Plex Mono", monospace; margin-left: 12px; }
.qa-eyebrow { text-transform: uppercase; font-size: 12px; color: #137567; letter-spacing: 2px; margin-top: 30px; }
h1 { font: 700 25px "Noto Serif TC", serif; margin: 12px 0; } p { line-height: 1.7; }
.qa-button { cursor: pointer; border: 1px solid #969c8c; padding: 8px 14px; border-radius: 6px; background: #fffef8; color: #20251f; font: inherit; }
.qa-google { width: 100%; padding: 13px; margin: 14px 0; font-weight: 600; }.qa-button:disabled { cursor: wait; opacity: .6; }
.qa-button:focus-visible, a:focus-visible { outline: 3px solid #137567; outline-offset: 3px; }.qa-error { color: #a13229; } a { color: #137567; font-size: 13px; }
@media (max-width: 600px) { .qa-toolbar { gap: 9px; padding: 7px 12px; flex-wrap: wrap; } .qa-toolbar span { flex-basis: calc(100% - 50px); } .qa-toolbar .qa-button { margin-left: auto; } }
</style>
