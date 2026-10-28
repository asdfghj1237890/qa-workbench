// Browser test entry: all runtime and presentation dependencies are independent.
import { createApp, h } from 'vue';
import { createI18n } from 'vue-i18n';
import { Quasar } from 'quasar';
import 'quasar/dist/quasar.css';
import QaHealthWorkspace from '../src/components/QaHealthWorkspace.vue';
import { configureQaAdapter } from '../src/lib/runtime.js';
import zhTW from '../src/i18n/zh-TW.json';
import '../src/css/panel-base.css';
import '../src/css/qa.css';
import '../src/css/qa-fonts.css';
import '../src/css/qa-typography.css';
import '../src/css/qa-workbench.css';
configureQaAdapter({ id: 'health-fixture', apiBase: '/api', fetch: (...args) => fetch(...args) });
const i18n = createI18n({ legacy: false, globalInjection: true, locale: 'zh-TW', messages: { 'zh-TW': zhTW } });
createApp({ render: () => h('div', { class: 'ns qa-page qa-workbench qa-release-shell', 'data-mode': 'dark', style: 'display:block;overflow:auto;height:auto;' }, [h('main', { class: 'qa-workspace' }, [h('div', { class: 'qa-wrap', style: 'padding:28px 0;' }, [h(QaHealthWorkspace, { dark: true })])])]) }).use(i18n).use(Quasar).mount('#app');
