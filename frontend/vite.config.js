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
let deliveryRoot = null

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    {
      name: 'route-delivery-membership',
      configResolved(config) {
        deliveryRoot = config.mode === 'browser-test' ? config.root.replaceAll('\\', '/') : null
      },
      generateBundle(_options, bundle) {
        if (!deliveryRoot) return
        const membership = Object.fromEntries(Object.values(bundle)
          .filter((entry) => entry.type === 'chunk')
          .map((entry) => [entry.fileName, Object.keys(entry.modules).map((path) => path.replaceAll('\\', '/').replace(deliveryRoot, ''))]))
        this.emitFile({ type: 'asset', fileName: '.vite/module-membership.json', source: JSON.stringify(membership) })
      },
    },
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
  build: { manifest: true },
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
