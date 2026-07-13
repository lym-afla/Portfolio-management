# Phase 2 — Frontend Tooling Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Vue 3 frontend from vue-cli/webpack + Vuex 4 + Options API to Vite + Pinia + `<script setup>`. No new features — purely tooling modernization.

**Architecture:** Three sequential migrations: (1) build tool vue-cli→Vite, (2) state Vuex→Pinia, (3) component style Options→`<script setup>`. Each is independently testable.

**Tech Stack:** Vue 3.4+, Vite 5+, Pinia 2+, Vuetify 3, vue-chartjs, axios, vee-validate + yup. Jest replaced by Vitest (Vite-native).

## Global Constraints

- **Frontend dir:** `frontend/` (renamed in Phase 0). All commands: `cd frontend && npm <cmd>`.
- **No behavior changes:** The app must work identically after each migration. Same routes, same API calls, same UI.
- **Backend untouched:** Phase 2 is frontend-only. No changes to `backend/`.
- **Branch:** `phase2/frontend-modernization`. Merges to `main` only at the end of all phases.
- **Env var migration:** `VUE_APP_*` → `VITE_*` (Vite convention). `process.env` → `import.meta.env`.
- **Vuetify:** Replace `webpack-plugin-vuetify` with `vite-plugin-vuetify`. Full component registration stays (not tree-shaking yet).
- **Testing:** Jest + `@vue/cli-plugin-unit-jest` → Vitest. The 4 existing spec files migrate.
- **Phase 3 overlap:** TypeScript adoption (Phase 3) can begin in parallel with late Task 3 — but `.js` files are not renamed to `.ts` in Phase 2.

---

## Task 1: vue-cli → Vite

**Files:**
- Create: `frontend/vite.config.js`
- Delete: `frontend/vue.config.js`, `frontend/babel.config.js`
- Modify: `frontend/package.json` (scripts, deps)
- Modify: `frontend/src/main.js` (entry adjustments if needed)
- Modify: `frontend/src/config/axiosConfig.js` (env var)
- Modify: `frontend/src/services/api.js` (env var)
- Modify: `frontend/src/utils/logger.js` (env var)
- Modify: `frontend/src/router/index.js` (env var, base URL)
- Rename: `frontend/.env.development` → update var name
- Modify: `frontend/index.html` (if needed for Vite entry)

**Interfaces:** none (build tooling change)

- [ ] **Step 1: Install Vite + vite-plugin-vuetify, remove vue-cli**

```bash
cd frontend
npm install --save-dev vite @vitejs/plugin-vue vite-plugin-vuetify
npm uninstall @vue/cli-service @vue/cli-plugin-babel @vue/cli-plugin-eslint @vue/cli-plugin-unit-jest webpack-plugin-vuetify @babel/core @babel/eslint-parser @babel/plugin-transform-modules-commonjs
```

- [ ] **Step 2: Create vite.config.js**

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 8080,
  },
})
```

- [ ] **Step 3: Delete vue-cli config files**

```bash
rm vue.config.js babel.config.js
```

- [ ] **Step 4: Update package.json scripts**

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint src/",
    "format": "prettier --write \"src/**/*.{js,vue,json,css,scss}\""
  }
}
```

Note: `test:unit` scripts are handled in the Vitest migration below. If the test runner isn't ready yet, temporarily remove test scripts and note it.

- [ ] **Step 5: Update env vars (VUE_APP_ → VITE_)**

In `frontend/.env.development`:
```
VITE_API_URL=http://localhost:8000
```

In `frontend/.env.example`:
```
VITE_API_URL=http://localhost:8000
```

In `src/config/axiosConfig.js`:
```javascript
baseURL: import.meta.env.VITE_API_URL,
```

In `src/services/api.js` (line ~607):
```javascript
`${import.meta.env.VITE_API_URL}/database/api/update-account-performance/sse/?session_id=${sessionId}&token=${token}`,
```

In `src/utils/logger.js`:
```javascript
const isProduction = import.meta.env.PROD
```

In `src/router/index.js`:
```javascript
import.meta.env.DEV  // instead of process.env.NODE_ENV !== 'production'
import.meta.env.BASE_URL  // instead of process.env.BASE_URL
```

In `src/main.js`:
```javascript
if (import.meta.env.DEV) {  // instead of process.env.NODE_ENV !== 'production'
```

- [ ] **Step 6: Ensure index.html is at frontend root (Vite convention)**

Vite expects `index.html` at the project root, not in `public/`. Check if `public/index.html` exists and move it to `frontend/index.html`. Update the script tag to use ES modules:

```html
<script type="module" src="/src/main.js"></script>
```

Remove any `<%= BASE_URL %>` or `<%= htmlWebpackPlugin.options.title %>` vue-cli template syntax — replace with literal values.

- [ ] **Step 7: Install Vitest (replaces Jest)**

```bash
npm install --save-dev vitest @vue/test-utils @vitest/coverage-v8 jsdom
```

Add to `vite.config.js`:
```javascript
export default defineConfig({
  // ... existing config ...
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

- [ ] **Step 8: Migrate test files to Vitest**

The 4 spec files use Jest globals (`describe`, `it`, `expect`, `jest`). Vitest provides the same API. Update:
- Replace `jest.fn()` → `vi.fn()`, `jest.mock()` → `vi.mock()` etc.
- Add `import { describe, it, expect, vi } from 'vitest'` at the top of each spec (or use `globals: true` in config which avoids this).
- Update `jest.config.js` → delete it (Vitest config is in `vite.config.js`).

Add test script to package.json:
```json
"test:unit": "vitest run",
"test:unit:watch": "vitest"
```

- [ ] **Step 9: Verify dev server works**

```bash
cd frontend && npm run dev
```
Expected: Vite dev server starts on `127.0.0.1:8080`, app loads in browser.

- [ ] **Step 10: Verify build works**

```bash
cd frontend && npm run build
```
Expected: build completes, `dist/` produced.

- [ ] **Step 11: Verify tests work**

```bash
cd frontend && npm run test:unit
```
Expected: all 4 specs pass.

- [ ] **Step 12: Commit**

```bash
git add -A && git commit -m "build: migrate vue-cli/webpack to Vite + Vitest

- Replace @vue/cli-service with Vite + @vitejs/plugin-vue
- Replace webpack-plugin-vuetify with vite-plugin-vuetify
- Migrate Jest to Vitest (same API, Vite-native)
- Update env vars: VUE_APP_* → VITE_*, process.env → import.meta.env
- Move index.html to project root (Vite convention)
- Update all scripts (serve→dev, build→vite build)"
```

---

## Task 2: Vuex 4 → Pinia

**Files:**
- Create: `frontend/src/stores/auth.js` (auth store)
- Create: `frontend/src/stores/app.js` (UI/app state store)
- Delete: `frontend/src/store/index.js`
- Modify: `frontend/src/main.js` (swap Vuex for Pinia)
- Modify: ~24 files that import `useStore` from Vuex

**Interfaces:** Pinia stores expose the same data/actions as the current Vuex store.

- [ ] **Step 1: Read the current Vuex store**

Read `frontend/src/store/index.js` thoroughly. Document every state field, mutation, action, and getter. Identify logical groupings (auth vs app state).

- [ ] **Step 2: Install Pinia**

```bash
cd frontend && npm install pinia && npm uninstall vuex
```

- [ ] **Step 3: Create Pinia stores**

Based on the Vuex store structure, create:
- `src/stores/auth.js` — `accessToken`, `refreshToken`, `user`, login/logout/refresh actions
- `src/stores/app.js` — `pageTitle`, `loading`, `error`, `accountSelection`, `dataRefreshTrigger`, `effectiveCurrentDate`, `selectedCurrency`, `tableSettings`

Use Composition API stores (`defineStore('auth', () => { ... })`) since we're modernizing. Preserve localStorage persistence.

- [ ] **Step 4: Update main.js**

```javascript
import { createPinia } from 'pinia'
// ...
const app = createApp(App)
app.use(createPinia())
app.use(router)
// Remove: app.use(store)
```

- [ ] **Step 5: Update all useStore consumers**

Grep: `grep -rn "useStore\|from 'vuex'\|from 'vuex'" src/ --include='*.vue' --include='*.js'`

For each file, replace:
```javascript
// Old (Vuex)
import { useStore } from 'vuex'
const store = useStore()
store.state.accessToken
store.commit('SET_ACCESS_TOKEN', token)
store.dispatch('login', credentials)

// New (Pinia)
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
const authStore = useAuthStore()
const appStore = useAppStore()
authStore.accessToken
authStore.setAccessToken(token)
authStore.login(credentials)
```

- [ ] **Step 6: Delete old Vuex store**

```bash
rm src/store/index.js
# If src/store/ is now empty, remove it
rmdir src/store/ 2>/dev/null
```

- [ ] **Step 7: Verify dev server + build + tests**

```bash
cd frontend && npm run dev   # app loads, auth works
npm run build                # build succeeds
npm run test:unit            # tests pass
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "refactor: migrate Vuex 4 to Pinia

- Create stores/auth.js and stores/app.js (Composition API style)
- Migrate all 24 useStore consumers to useStore from Pinia
- Delete src/store/index.js (Vuex)
- Preserve localStorage persistence for tokens and account selection"
```

---

## Task 3: Options API → `<script setup>`

**Files:**
- Modify: 63 `.vue` SFCs in `src/`

This is the largest task by file count but the most mechanical. Each component converts from:
```vue
<script>
import { ref } from 'vue'
export default {
  setup() {
    const count = ref(0)
    return { count }
  },
}
</script>
```
to:
```vue
<script setup>
import { ref } from 'vue'
const count = ref(0)
</script>
```

- [ ] **Step 1: Convert the 19 components with setup() first**

These already use Composition API — the conversion is simplest. For each:
- Replace `<script>` + `export default { setup() { ... return { ... } } }` with `<script setup>`
- Remove the `return` statement (script setup auto-exposes top-level bindings)
- Convert `defineProps` / `defineEmits` if the component uses props/emits
- Remove `export default` wrapper

- [ ] **Step 2: Convert Options API components in batches**

Convert in groups: views first, then dialogs, then components, then charts. For each Options API component:
- `data()` → top-level `ref()` / `reactive()`
- `computed: {}` → `computed()`
- `methods: {}` → plain functions
- `watch: {}` → `watch()`
- `mounted()` / `created()` → `onMounted()` / direct calls
- `props` → `defineProps()`
- `emits` → `defineEmits()`

- [ ] **Step 3: Verify after each batch**

```bash
cd frontend && npm run build
npm run test:unit
```

- [ ] **Step 4: Final commit**

```bash
git add -A && git commit -m "refactor: migrate all SFCs to <script setup>

Convert 63 SFCs from Options API (export default {}) to <script setup>.
The 19 components that already used setup() were converted first (simplest),
followed by the Options API components in batches (views → dialogs → components).
All Composition API primitives (ref, computed, watch, onMounted) now use
top-level script setup syntax."
```

---

## Final Verification

- [ ] **Step 1: Dev server**
```bash
cd frontend && npm run dev
```
App loads, navigation works, login works, data displays.

- [ ] **Step 2: Build**
```bash
cd frontend && npm run build
```
Build completes without errors.

- [ ] **Step 3: Tests**
```bash
cd frontend && npm run test:unit
```
All specs pass.

- [ ] **Step 4: Verify no vuex/cli/webpack remnants**
```bash
grep -rn "vuex\|vue-cli\|webpack\|process.env" src/ --include='*.vue' --include='*.js'
```
Expected: no output (all migrated).

- [ ] **Step 5: Verify <script setup> count**
```bash
grep -rl "<script setup" src/ --include='*.vue' | wc -l
```
Expected: ~63 (all SFCs).

---

## Risk notes

- **Task 1 (Vite)** is the foundational swap. Expect env var issues and index.html placement to be the main friction points.
- **Task 2 (Pinia)** is moderate — 24 callers to update, but the store logic is straightforward.
- **Task 3 (script setup)** is the largest by file count but lowest risk per file — it's mechanical refactoring.
- **Vuetify auto-import** via `vite-plugin-vuetify` should work seamlessly, but verify all Vuetify components render correctly after the swap.
- **vee-validate + yup** should be unaffected by the Vite migration.
- **chart.js + vue-chartjs** should work fine with Vite — they're framework-agnostic.
