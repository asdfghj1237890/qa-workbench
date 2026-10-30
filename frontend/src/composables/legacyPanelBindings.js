/** Compatibility for the original flat composable API; new views use groups. */
import { isRef, toRef } from 'vue';

export function legacyPanelBindings(panel) {
  const bindings = {};
  for (const group of [panel.state, panel.form, panel.ui, panel.dom, panel.actions]) {
    for (const key of Object.keys(group || {})) {
      const value = group[key];
      bindings[key] = typeof value === 'function' || isRef(value) ? value : toRef(group, key);
    }
  }
  return bindings;
}
