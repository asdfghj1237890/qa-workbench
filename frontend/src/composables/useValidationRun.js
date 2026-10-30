/** Compatibility facade for existing flat consumers. New views use useValidationPanel. */
import { useValidationPanel } from './useValidationPanel.js';
import { legacyPanelBindings } from './legacyPanelBindings.js';
export function useValidationRun(props, emit, options) { return legacyPanelBindings(useValidationPanel(props, emit, options)); }
