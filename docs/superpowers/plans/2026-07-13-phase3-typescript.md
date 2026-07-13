# Phase 3 — TypeScript Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TypeScript to the Vue 3 frontend with OpenAPI-generated API types. New code is strictly typed from day one; existing code migrates opportunistically. API responses become fully type-safe.

**Architecture:** (1) TS infrastructure (tsconfig, vue-tsc, build integration), (2) drf-spectacular on backend + openapi-typescript codegen for API types, (3) type the Pinia stores and composables, (4) convert api.js → api.ts with generated types, (5) gradual component migration.

**Tech Stack:** TypeScript 5.x, vue-tsc, Vite (already from Phase 2), drf-spectacular (backend), openapi-typescript (codegen).

## Global Constraints

- **Frontend dir:** `frontend/`. Commands: `cd frontend && npm <cmd>`.
- **Backend dir:** `backend/`. Commands: `cd backend && uv run <cmd>`.
- **Branch:** `phase3/typescript` (from integration/pre-phase3 which includes Phase 1 + Phase 2).
- **Gradual typing:** Do NOT flip `strict: true` globally yet. Use `allowJs: true` + `checkJs: false` so JS files coexist. Type new/converted code strictly.
- **No behavior changes:** The app works identically. TS is additive.
- **Backend: drf-spectacular is non-protected** (adds a DRF extension, doesn't touch financial logic).

---

## Task 1: TS Infrastructure

**Files:**
- Create: `frontend/tsconfig.json`, `frontend/tsconfig.node.json`
- Modify: `frontend/vite.config.js` (rename to `.ts`)
- Modify: `frontend/package.json` (add typescript, vue-tsc, type-check script)
- Modify: `frontend/env.d.ts` (Vite client types + import.meta.env typing)

- [ ] **Step 1: Install TypeScript + vue-tsc**

```bash
cd frontend
npm install --save-dev typescript vue-tsc
```

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": false,
    "jsx": "preserve",
    "allowJs": true,
    "checkJs": false,
    "noEmit": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "useDefineForClassFields": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "types": ["vite/client"]
  },
  "include": ["src/**/*", "src/**/*.vue", "env.d.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Key: `strict: false` + `allowJs: true` = gradual typing. JS files keep working.

- [ ] **Step 3: Create tsconfig.node.json**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.js"]
}
```

- [ ] **Step 4: Create env.d.ts**

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

- [ ] **Step 5: Add vue-tsc type-check script to package.json**

```json
{
  "scripts": {
    "type-check": "vue-tsc --noEmit"
  }
}
```

- [ ] **Step 6: Rename vite.config.js → vite.config.ts**

This is optional but idiomatic. If the rename causes issues, leave as `.js` (tsconfig.node.json handles it).

- [ ] **Step 7: Verify build + dev + tests still work**

```bash
cd frontend && npm run dev     # dev server
npm run build                  # build
npm run test:unit              # tests
npm run type-check             # type check (should pass — no strict mode yet)
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "build: add TypeScript infrastructure (tsconfig, vue-tsc, env.d.ts)

Gradual typing: strict=false, allowJs=true. JS files continue to work.
New code is typed; existing code migrates opportunistically."
```

---

## Task 2: drf-spectacular + OpenAPI Type Generation

**Files:**
- Modify: `backend/pyproject.toml` (add drf-spectacular)
- Modify: `backend/portfolio_management/settings.py` (INSTALLED_APPS, REST_FRAMEWORK schema class)
- Modify: `backend/portfolio_management/urls.py` (schema endpoint)
- Create: `frontend/src/types/api.d.ts` (generated)
- Modify: `frontend/package.json` (add openapi-typescript)
- Create: `frontend/scripts/generate-api-types.sh` (codegen script)

- [ ] **Step 1: Install drf-spectacular on backend**

```bash
cd backend
# Add to [project.dependencies] in pyproject.toml
uv add drf-spectacular
```

- [ ] **Step 2: Configure drf-spectacular in settings.py**

```python
INSTALLED_APPS = [
    # ...
    'drf_spectacular',
]

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # ... existing settings ...
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Portfolio Management API',
    'DESCRIPTION': 'Investment portfolio management system',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}
```

- [ ] **Step 3: Add schema endpoint to urls.py**

```python
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    # ... existing ...
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
]
```

- [ ] **Step 4: Generate the OpenAPI schema and fix any issues**

```bash
cd backend && uv run python manage.py spectacular --color --file openapi-schema.yml
```

This will likely surface issues — some serializers/views may need `@extend_schema` decorators for proper typing. Fix the most impactful ones; the goal is a usable schema, not perfection.

- [ ] **Step 5: Install openapi-typescript on frontend**

```bash
cd frontend && npm install --save-dev openapi-typescript
```

- [ ] **Step 6: Create codegen script**

Create `frontend/scripts/generate-api-types.sh`:
```bash
#!/bin/bash
# Generate TypeScript types from the backend OpenAPI schema
cd /d/Developing/Portfolio-management/backend
uv run python manage.py spectacular --format openapi-json > /tmp/openapi-schema.json
cd /d/Developing/Portfolio-management/frontend
npx openapi-typescript /tmp/openapi-schema.json -o src/types/api.d.ts
```

- [ ] **Step 7: Generate the types**

```bash
bash frontend/scripts/generate-api-types.sh
```

- [ ] **Step 8: Verify the generated types are usable**

Check that `src/types/api.d.ts` has proper interfaces for the main API responses (securities, transactions, positions, etc.).

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: add OpenAPI type generation (drf-spectacular + openapi-typescript)

Backend: drf-spectacular generates OpenAPI schema from DRF serializers.
Frontend: openapi-typescript generates TypeScript types from the schema.
98 API functions now have auto-generated types that stay in sync with
the backend."
```

---

## Task 3: Type the Pinia Stores and Composables

**Files:**
- Rename + modify: `frontend/src/stores/auth.js` → `auth.ts`
- Rename + modify: `frontend/src/stores/app.js` → `app.ts`
- Modify: `frontend/src/composables/*.js` → `.ts` (4 files)
- Modify: `frontend/src/config/axiosConfig.js` → `.ts`
- Modify: `frontend/src/utils/logger.js` → `.ts`

- [ ] **Step 1: Convert auth store to TypeScript**

Rename `src/stores/auth.js` → `src/stores/auth.ts`. Add types:
- Type the User interface (match backend CustomUser fields)
- Type the return values of login/logout/refresh
- Use the generated API types for user data

- [ ] **Step 2: Convert app store to TypeScript**

Rename `src/stores/app.js` → `src/stores/app.ts`. Add types:
- Type the AccountSelection interface
- Type the TableSettings interface
- Type all state refs and actions

- [ ] **Step 3: Convert composables to TypeScript**

Rename each composable (`.js` → `.ts`):
- `src/composables/useErrorHandler.ts` — type error state and handler
- `src/composables/useImportState.ts` — type import progress state
- `src/composables/useTableSettings.ts` — type table settings + handlers
- `src/composables/useWebSocket.ts` — type WebSocket message payloads

- [ ] **Step 4: Convert config + utils to TypeScript**

- `src/config/axiosConfig.ts` — type the axios instance + interceptors
- `src/utils/logger.ts` — type the log levels and methods

- [ ] **Step 5: Verify**

```bash
cd frontend && npm run type-check && npm run build && npm run test:unit
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor: type Pinia stores, composables, and core utilities

Convert auth store, app store, 4 composables, axios config, and logger
to TypeScript with proper interfaces and type annotations."
```

---

## Task 4: Convert api.js → api.ts with Generated Types

**Files:**
- Rename + modify: `frontend/src/services/api.js` → `api.ts`

This is the highest-value typing target — 98 API functions become fully typed.

- [ ] **Step 1: Read the current api.js**

Read `frontend/src/services/api.js` thoroughly. Document the return shapes of each function (most return axios response data).

- [ ] **Step 2: Convert to TypeScript**

Rename to `api.ts`. For each function:
- Add parameter types (using generated API types where applicable)
- Add return type annotations
- Type the response shapes using the generated `api.d.ts` types

For example:
```typescript
import type { components } from '@/types/api'

type SecurityDetail = components['schemas']['SecurityDetail']

export const getSecurityDetail = async (id: number): Promise<SecurityDetail> => {
  const response = await apiClient.get(`/database/api/securities/${id}/`)
  return response.data
}
```

Not all 98 functions need perfect types immediately. Prioritize:
1. Functions used by the most components (getOpenPositions, getDashboard, getTransactions)
2. Functions with complex return shapes (security detail, NAV, performance)
3. Auth functions (login, refreshToken)

- [ ] **Step 3: Verify**

```bash
cd frontend && npm run type-check && npm run build && npm run test:unit
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "refactor: convert api.js to TypeScript with OpenAPI-generated types

All 98 API functions now have typed parameters and return values.
Response types are generated from the backend OpenAPI schema via
drf-spectacular + openapi-typescript."
```

---

## Task 5: Gradual Component Migration (Optional / Opportunistic)

This task is the open-ended "migrate on touch" policy from the spec. It doesn't have a fixed scope — the goal is to establish the pattern and convert a few representative components.

- [ ] **Step 1: Convert a few representative SFCs from `.vue` (JS) to `.vue` (TS)**

Pick 3-5 high-traffic components:
- `App.vue` — root component
- `Navigation.vue` — nav bar
- `DashboardPage.vue` — main dashboard view
- `PositionsPageBase.vue` — positions table base

For each: add `<script setup lang="ts">`, type props/emits, type reactive state, type API calls using the generated types.

- [ ] **Step 2: Verify**

```bash
cd frontend && npm run type-check && npm run build && npm run test:unit
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "refactor: convert 5 representative SFCs to <script setup lang=\"ts\">

Establishes the TypeScript component pattern. Remaining components migrate
opportunistically (any file touched for another reason gets typed)."
```

---

## Final Verification

- [ ] **Step 1: Type check**

```bash
cd frontend && npm run type-check
```

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Tests**

```bash
cd frontend && npm run test:unit
```

- [ ] **Step 4: Backend tests (verify drf-spectacular didn't break anything)**

```bash
cd backend && uv run python -m pytest -q --no-cov
```

- [ ] **Step 5: API type generation works end-to-end**

```bash
bash frontend/scripts/generate-api-types.sh
# Verify src/types/api.d.ts is regenerated with current schema
```

---

## Risk notes

- **drf-spectacular schema generation** may surface serializer issues (untyped fields, missing serializers for some views). Fix the impactful ones; accept `any` for edge cases.
- **Gradual typing means type-check passes even with untyped code** — `strict: false`. The value is in the typed code, not in enforcing coverage. Don't rush to `strict: true`.
- **openapi-typescript output** may need manual adjustments for complex nested types. The generated file is a starting point, not always perfect.
- **Renaming `.js` to `.ts`** can break imports if some files use extension-explicit imports (`import x from './y.js'`). Vite handles `.ts` extensions transparently, but check for any explicit extensions.
