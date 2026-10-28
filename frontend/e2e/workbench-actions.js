import { browserWorkbench, browserHealthHistory, browserAuthenticatedWorkbench } from './workbench-physical.js';
export const openWorkbench = page => browserWorkbench(page);
export const openHealthHistory = page => browserHealthHistory(page);
export const openAuthenticatedWorkbench = page => browserAuthenticatedWorkbench(page);
