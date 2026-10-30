/** Presentation adapter for the host's browser challenge widget. */
import { nextTick, onScopeDispose, ref } from 'vue';
import { createCfToken } from '../lib/cfToken.js';

export function useValidationChallenge({ sitekey, provider }) {
  const element = ref(null), cfToken = createCfToken({ enabled: !!sitekey });
  let widgetId = null;
  function clear() {
    if (provider.widget && widgetId !== null) provider.widget.remove?.(widgetId);
    widgetId = null; cfToken.clear();
  }
  onScopeDispose(() => { cfToken.set(''); clear(); });
  async function token(signal) {
    await nextTick();
    if (!sitekey || !element.value) throw new Error('turnstile');
    cfToken.clear();
    await provider.load(signal);
    if (widgetId !== null) provider.widget.reset(widgetId);
    else widgetId = provider.widget.render(element.value, {
      sitekey, size: 'compact', callback: value => cfToken.set(value), 'expired-callback': () => cfToken.clear(),
    });
    const value = await cfToken.get();
    if (!value || signal.aborted) throw new Error('turnstile');
    return value;
  }
  return { element, available: !!sitekey, token, clear };
}
