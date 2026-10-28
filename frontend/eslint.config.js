import pluginVue from 'eslint-plugin-vue';
// Match the host's recommended Vue correctness rules and compact-template style.
// No host-specific v-html or filename exceptions are carried into this project.
export default [
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['src/**/*.{js,vue}', 'tests/**/*.js', 'e2e/**/*.js'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'module', globals: { window: 'readonly', document: 'readonly', localStorage: 'readonly', sessionStorage: 'readonly', fetch: 'readonly', console: 'readonly', navigator: 'readonly' } },
    rules: {
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/require-default-prop': 'off',
    },
  },
  { ignores: ['dist/**', 'node_modules/**', 'test-results/**', 'test-results-independent/**', 'playwright-report/**', '.yarn/**'] },
];
