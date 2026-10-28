import { getQaAdapter } from './runtime.js';
export const QA_OTHER_CATEGORY = '__other__';
export const qaCategoryGroup = value => getQaAdapter().categories.group(value);
export const qaCategoryColor = value => getQaAdapter().categories.color(value);
export const qaCategoryLabelKey = value => getQaAdapter().categories.labelKey(value);
export const qaCategoryDistribution = rows => getQaAdapter().categories.distribution(rows);
