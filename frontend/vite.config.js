import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  plugins: [vue()],
  resolve: { dedupe: ['vue', 'vue-router', 'vue-i18n', 'quasar', '@quasar/extras'], alias: [
    { find: /^quasar$/, replacement: fileURLToPath(new URL('./node_modules/quasar/dist/quasar.client.js', import.meta.url)) },
    { find: 'src', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
  ] },
  server: { proxy: { '/api': { target: process.env.QA_API_PROXY || 'http://127.0.0.1:8765', changeOrigin: false } } },
  build: { outDir: 'dist', emptyOutDir: true },
  test: { exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'] },
});
