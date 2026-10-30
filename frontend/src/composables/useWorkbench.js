/** Compatibility facade for existing flat consumers. New views use useWorkbenchPanel. */
import { useWorkbenchPanel } from './useWorkbenchPanel.js';
import { legacyPanelBindings } from './legacyPanelBindings.js';
export function useWorkbench(options) { return legacyPanelBindings(useWorkbenchPanel(options)); }
