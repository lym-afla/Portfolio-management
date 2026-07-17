// defineConfig imported from vitest/config so the `test` block is recognized
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { fileURLToPath, URL } from 'node:url'

// Vitest sets process.env.VITEST when running. We disable vite-plugin-vuetify's
// auto-import transform during tests because the unit tests stub all Vuetify
// components (they don't use real ones), and auto-import would pull in real
// Vuetify components whose setup() requires the Vuetify plugin's provide()
// (DefaultsSymbol) — causing "[Vuetify] Could not find defaults instance".
const isTest = !!process.env.VITEST

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    ...(!isTest ? [vuetify({ autoImport: true })] : []),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1', // IPv4 only — consistent with backend bind address and CORS
    port: 8080,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    pool: 'threads',
    setupFiles: ['./tests/unit/setup.js'],
    server: {
      deps: {
        // Vuetify ships per-component .css files that Node cannot load directly.
        // Inlining vuetify forces Vite's CSS pipeline to process them, avoiding
        // "Unknown file extension .css" errors when tests transitively import
        // Vuetify components (e.g. via composables or plugins).
        inline: ['vuetify'],
      },
    },
  },
})
