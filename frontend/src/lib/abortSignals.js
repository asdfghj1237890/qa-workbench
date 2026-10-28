/** Compose request and identity cancellation on browsers without AbortSignal.any. */
export function combineAbortSignals(values) {
  const signals = values.filter(Boolean);
  if (typeof AbortSignal.any === 'function') return { signal: AbortSignal.any(signals), cleanup() {} };
  const controller = new AbortController();
  const cleanup = () => signals.forEach(signal => signal.removeEventListener('abort', abort));
  function abort() { controller.abort(); cleanup(); }
  if (signals.some(signal => signal.aborted)) abort();
  else signals.forEach(signal => signal.addEventListener('abort', abort, { once: true }));
  return { signal: controller.signal, cleanup };
}

/** Fetch resolves at headers; retain cancellation until its body is consumed. */
export function cleanupAfterResponse(response, cleanup) {
  if (!response.body) { cleanup(); return response; }
  const bodyMethods = new Set(['json', 'text', 'blob', 'arrayBuffer', 'formData']);
  return new Proxy(response, {
    get(target, key) {
      const value = Reflect.get(target, key, target);
      if (typeof value !== 'function') return value;
      if (!bodyMethods.has(key)) return value.bind(target);
      return async (...args) => { try { return await value.apply(target, args); } finally { cleanup(); } };
    },
  });
}
