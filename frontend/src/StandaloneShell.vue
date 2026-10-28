<template>
  <div class="wb-standalone">
    <div
      v-if="status === 'ready'"
      class="wb-identity"
    >
      <span>{{ identityLabel }}</span><button
        data-testid="auth-signout"
        @click="signOut"
      >
        Sign out / change identity
      </button>
    </div>
    <WorkbenchApp
      v-if="status === 'ready'"
      :key="generation"
      :client="client"
    />
    <main
      v-else
      class="wb-auth"
      aria-labelledby="auth-title"
    >
      <section>
        <p class="wb-auth-eyebrow">
          {{ adapter.branding.name }}
        </p><h1 id="auth-title">
          Sign in to QA Workbench
        </h1><p>The configured API requires an authorized identity.</p><p
          v-if="rejected"
          role="alert"
        >
          Credentials were rejected. Enter a valid bearer token.
        </p>
        <form @submit.prevent="signIn">
          <label for="workbench-token">Bearer token</label><input
            id="workbench-token"
            v-model="credential"
            data-testid="auth-token"
            type="password"
            autocomplete="off"
            autocapitalize="off"
            spellcheck="false"
          ><p class="wb-auth-hint">
            Kept in memory for this page only. Signing out or reloading clears it.
          </p><button
            data-testid="auth-signin"
            type="submit"
            :disabled="!credential.trim()"
          >
            Sign in
          </button>
        </form>
        <button
          v-if="tokenProvider || injectedIdentity"
          class="wb-auth-provider"
          @click="continueWithProvider"
        >
          Continue with host identity
        </button>
      </section>
    </main>
  </div>
</template>
<script setup>
import { computed, onBeforeUnmount, ref } from 'vue';
import WorkbenchApp from './App.vue';
import { getQaAdapter } from './lib/runtime.js';
import { createWorkbenchClient } from './lib/workbenchApi.js';
import { combineAbortSignals, cleanupAfterResponse } from './lib/abortSignals.js';
const props = defineProps({ config: { type: Object, default: () => ({}) }, request: Function });
const adapter = getQaAdapter(), baseRequest = props.request || props.config.request || adapter.fetch;
const tokenProvider = typeof props.config.tokenProvider === 'function' ? props.config.tokenProvider : typeof props.config.token === 'function' ? props.config.token : null;
const injectedIdentity = typeof props.config.request === 'function';
const status = ref('ready'), rejected = ref(false), credential = ref(''), generation = ref(0), manualIdentity = ref(false);
let token = '', identityController = new AbortController();
const identityLabel = computed(() => manualIdentity.value ? 'Bearer identity · memory only' : tokenProvider || injectedIdentity ? 'Host identity provider' : 'Adapter session');
function reset(next, invalid = false) {
  identityController.abort(); identityController = new AbortController();
  token = ''; credential.value = ''; manualIdentity.value = false;
  generation.value++; rejected.value = invalid; status.value = next;
}
function signIn() {
  const candidate = credential.value.trim();
  if (!candidate || candidate.length > 16384 || /[\r\n]/.test(candidate)) { reset('required', true); return; }
  reset('ready'); token = candidate; manualIdentity.value = true;
}
function signOut() { reset('required'); }
function continueWithProvider() { reset('ready'); }
async function authenticatedRequest(url, options = {}) {
  const epoch = generation.value, owned = identityController;
  const bearer = token || (tokenProvider ? await tokenProvider() : '');
  if (epoch !== generation.value || owned.signal.aborted) throw new DOMException('Identity changed', 'AbortError');
  const { signal, cleanup } = combineAbortSignals([owned.signal, options.signal]);
  let response;
  try { response = await baseRequest(url, { ...options, signal, headers: { ...options.headers, ...(bearer ? { Authorization: 'Bearer ' + bearer } : {}) } }); }
  catch (failure) {
    cleanup();
    if (epoch !== generation.value || owned.signal.aborted) throw new DOMException('Identity changed', 'AbortError');
    throw failure;
  }
  if (epoch !== generation.value || owned.signal.aborted) { cleanup(); throw new DOMException('Identity changed', 'AbortError'); }
  if (response.status === 401) { reset('required', Boolean(bearer)); cleanup(); throw new DOMException('Authentication required', 'AbortError'); }
  return cleanupAfterResponse(response, cleanup);
}
const client = createWorkbenchClient({ apiBase: props.config.apiBase || adapter.apiBase, request: authenticatedRequest });
onBeforeUnmount(() => reset('disposed'));
</script>
