/** Compatibility facade for existing flat consumers. New views use useLivePanel. */
import { useLivePanel } from './useLivePanel.js';
import { legacyPanelBindings } from './legacyPanelBindings.js';
export function useLiveEvaluation(emit, options) { return legacyPanelBindings(useLivePanel(emit, options)); }
