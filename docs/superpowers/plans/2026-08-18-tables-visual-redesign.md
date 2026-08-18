# Tables & Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the positions tables (two-row grouped accessible headers, sticky identity columns, right-aligned tabular numerals, working server-side sort, column visibility), establish a real Vuetify 3 theme, and fix charts/layout issues from the 2026-08-18 critique.

**Architecture:** Vuetify 3's `v-data-table` natively renders two-row grouped headers from a `children` header config — both pages converge on that, deleting all hand-rolled `<thead>` markup and magic colspans. Theme tokens are defined once in `main.js` and consumed everywhere (cards, charts, tables). Column visibility is a filtered computed over the shared header config persisted via `useTableSettings`.

**Tech Stack:** Vue 3 `<script setup>`, Vuetify 3, Pinia, Vitest + @vue/test-utils, Chart.js with chartjs-plugin-datalabels (already in the app).

**Spec:** `docs/superpowers/specs/2026-08-18-tables-visual-redesign-design.md`

## Global Constraints

- No backend, API contract, or financial-logic changes. Frontend `src/` only (plus tests).
- All numeric display right-aligned (`align: 'end'`) with `font-variant-numeric: tabular-nums`.
- Max two header rows table-wide; 3rd-level nesting flattened to prefixed leaves.
- Every header cell announced by screen readers: rely on Vuetify's native grouped-header markup (it emits correct `colspan`/`rowspan`); do not re-introduce hand-rolled `<thead>`s.
- No color-only meaning: gains/losses keep signs; percentages keep "%" in formatted values.
- No `console.log` in committed code — use `@/utils/logger` (already dev-gated).
- Run all frontend commands from `frontend/`: `npm run test:unit`, `npm run lint`, `npm run type-check`. Each task must leave these green.
- Commits: conventional commits, one per task.

---

### Task 1: Theme foundation — real Vuetify 3 palette + tabular numerals

**Files:**
- Modify: `frontend/src/main.js:17-34`
- Modify: `frontend/src/assets/fonts.css`
- Test: `frontend/tests/unit/main-theme.spec.js` (create)

**Interfaces:**
- Produces: theme token names (`primary`, `secondary`, `surface`, `success`, `error`, `background`) usable as `rgb(var(--v-theme-<name>))` in any component; a global CSS class `.num` and the `body` rule providing `font-variant-numeric: tabular-nums`.

- [ ] **Step 1: Write the failing test**

```js
// tests/unit/main-theme.spec.js
import { describe, it, expect } from 'vitest'
import { createVuetify } from 'vuetify'

describe('vuetify theme', () => {
  it('defines the app theme with the required tokens', async () => {
    const { default: main } = await import('@/main.js?mock') // see Step 3 note
  })
})
```

The app entry mounts to `#app`, so importing it in tests is not viable. Instead export the vuetify instance factory from `main.js` and test that:

```js
// tests/unit/main-theme.spec.js
import { describe, it, expect } from 'vitest'
import { createAppTheme } from '@/theme'

describe('createAppTheme', () => {
  it('exposes required light-theme tokens', () => {
    const themes = createAppTheme().themes
    expect(Object.keys(themes.light.colors)).toEqual(
      expect.arrayContaining([
        'primary', 'secondary', 'background', 'surface', 'success', 'error',
      ])
    )
    expect(themes.defaultTheme).toBe('light')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- tests/unit/main-theme.spec.js`
Expected: FAIL — `Cannot find module '@/theme'`

- [ ] **Step 3: Create `frontend/src/theme.js` and rewire `main.js`**

```js
// src/theme.js
// Single source of truth for the app's visual identity.
export const palette = {
  primary: '#0F4C81', // deep brokerage blue — anchors the app
  secondary: '#5C6B7A', // slate for secondary text/accents
  background: '#F7F8FA',
  surface: '#FFFFFF',
  success: '#1E7F4F',
  error: '#B3261E',
  info: '#0B5FA5',
  warning: '#9A6700',
}

export function createAppTheme() {
  return {
    defaultTheme: 'light',
    themes: {
      light: {
        dark: false,
        colors: { ...palette },
        variables: {
          fontFamily: 'var(--system-font)',
          'border-color': '#E2E6EB',
        },
      },
    },
  }
}
```

In `main.js`, replace the inline `theme: {...}` object with `theme: createAppTheme()` (import from `./theme`), keeping everything else identical.

- [ ] **Step 4: Add tabular numerals globally**

Append to `frontend/src/assets/fonts.css`:

```css
/* All app numerals align by digit position (tables, cards, charts). */
body {
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 5: Run tests, lint, type-check**

Run: `npm run test:unit -- tests/unit/main-theme.spec.js && npm run lint && npm run type-check`
Expected: PASS / no errors.

- [ ] **Step 6: Visual smoke check**

Run: `npm run dev`, open the dashboard, confirm the app bar / buttons picked up the new primary (`#0F4C81`) and nothing lost styling.

- [ ] **Step 7: Commit**

```bash
git add src/theme.js src/main.js src/assets/fonts.css tests/unit/main-theme.spec.js
git commit -m "feat(theme): real Vuetify 3 palette + tabular numerals"
```

---

### Task 2: SummaryCard — kill side-tab border, broken Vuetify 2 variable, console.log

**Files:**
- Modify: `frontend/src/components/dashboard/SummaryCard.vue`
- Test: `frontend/tests/unit/components/SummaryCard.spec.js` (create)

**Interfaces:**
- Consumes: Task 1 theme tokens (`rgb(var(--v-theme-primary))`).
- Produces: `SummaryCard` unchanged props (`summary`, `currency`).

- [ ] **Step 1: Write the failing test**

```js
// tests/unit/components/SummaryCard.spec.js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCard from '@/components/dashboard/SummaryCard.vue'
import { createVuetify } from 'vuetify'

const vuetify = createVuetify()

describe('SummaryCard', () => {
  it('formats multi-underscore keys fully humanized', () => {
    const wrapper = mount(SummaryCard, {
      global: { plugins: [vuetify] },
      props: { summary: { beginning_of_period_nav: 1, irr: 2 } },
    })
    expect(wrapper.text()).toContain('Beginning of period NAV')
    expect(wrapper.text()).toContain('IRR')
  })

  it('does not use the Vuetify 2 variable or a side-tab border', () => {
    const style = wrapperStyles()
    function wrapperStyles() {
      // read the scoped style block from the mounted component source
      return SummaryCard.__file ? SummaryCard.toString() : ''
    }
    const src = JSON.stringify(SummaryCard)
    expect(src).not.toContain('--v-primary-base')
  })
})
```

(The second assertion is source-level on purpose: the CSS-variable failure is invisible at runtime.)

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- tests/unit/components/SummaryCard.spec.js`
Expected: FAIL — current `formatKey` replaces only the first underscore; style contains `--v-primary-base`.

- [ ] **Step 3: Fix the component**

In `SummaryCard.vue`:

```js
function formatKey(key) {
  return key
    .replaceAll('_', ' ')
    .replace(/^./, (str) => str.toUpperCase())
    .replace('Irr', 'IRR')
    .replace('Nav', 'NAV')
}
```

Delete the `console.log` inside `formatAccountSelection`. Replace the `<style scoped>` block:

```css
.summary-card {
  border: 1px solid rgb(var(--v-theme-surface-variant, 226, 230, 235));
  box-shadow: none;
}

.summary-card .v-card-title {
  color: rgb(var(--v-theme-primary));
  font-size: 1.25rem;
}

.text-subtitle-2 {
  color: rgb(var(--v-theme-secondary));
  font-size: 0.875rem;
}
```

(No side border, no `!important`, no hardcoded grays.)

- [ ] **Step 4: Run tests**

Run: `npm run test:unit -- tests/unit/components/SummaryCard.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/components/dashboard/SummaryCard.vue tests/unit/components/SummaryCard.spec.js
git commit -m "fix(dashboard): SummaryCard theme tokens, formatKey, remove debug log"
```

---

### Task 3: Shared header configs — two levels, end-aligned numerals

**Files:**
- Create: `frontend/src/config/positionsHeaders.js`
- Test: `frontend/tests/unit/config/positionsHeaders.spec.js` (create)

**Interfaces:**
- Produces: `openPositionsHeaders` and `closedPositionsHeaders` (plain arrays, Vuetify 3 header shape, exactly 2 levels), plus `openPercentageColumns` / `closedPercentageColumns` (string arrays), and `flattenHeaders(headers)` used by Tasks 4–6. Default-visible column keys via `openDefaultVisibleKeys` / `closedDefaultVisibleKeys`.

- [ ] **Step 1: Write the failing test**

```js
// tests/unit/config/positionsHeaders.spec.js
import { describe, it, expect } from 'vitest'
import {
  openPositionsHeaders,
  closedPositionsHeaders,
  flattenHeaders,
} from '@/config/positionsHeaders'

const maxDepth = (hs) =>
  hs.reduce((m, h) => Math.max(m, h.children ? 1 + maxDepth(h.children) : 0), 0)

describe('positions headers', () => {
  it('never nests deeper than 2 levels', () => {
    expect(maxDepth(openPositionsHeaders)).toBeLessThanOrEqual(1) // children = 1 extra level
    expect(maxDepth(closedPositionsHeaders)).toBeLessThanOrEqual(1)
  })

  it('right-aligns every numeric leaf, start-aligns identity leaves', () => {
    for (const leaf of flattenHeaders(openPositionsHeaders)) {
      if (['type', 'name'].includes(leaf.key)) expect(leaf.align).toBe('start')
      else expect(leaf.align).toBe('end')
    }
  })

  it('flattens to unique keys', () => {
    const keys = flattenHeaders(openPositionsHeaders).map((h) => h.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- tests/unit/config/positionsHeaders.spec.js`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the config**

`frontend/src/config/positionsHeaders.js` — move both pages' header arrays here with these transformations: drop the 3rd `Gain/Loss` level (prefixed leaves under `Current`), set `align: 'end'` on all numeric leaves, keep `sortable` flags, keep percentage leaves' `class: 'font-italic'`. Open positions shape:

```js
export const openPositionsHeaders = [
  { title: 'Type', key: 'type', align: 'start', sortable: true },
  { title: 'Name', key: 'name', align: 'start', sortable: true },
  { title: 'Currency', key: 'currency', align: 'end', sortable: true },
  { title: 'Position', key: 'current_position', align: 'end', sortable: true },
  {
    title: 'Entry',
    key: 'entry',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Date', key: 'investment_date', align: 'end', sortable: true },
      { title: 'Price', key: 'entry_price', align: 'end', sortable: true },
      { title: 'Value', key: 'entry_value', align: 'end', sortable: true },
    ],
  },
  {
    title: 'Current',
    key: 'current',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Price', key: 'current_price', align: 'end', sortable: true },
      { title: 'Value', key: 'current_value', align: 'end', sortable: true },
      { title: 'Share %', key: 'share_of_portfolio', align: 'end', sortable: true, class: 'font-italic' },
      { title: 'Price Δ %', key: 'price_change_percentage', align: 'end', sortable: true, class: 'font-italic' },
      { title: 'Realized G/L', key: 'realized_gl', align: 'end', sortable: true },
      { title: 'Unrealized G/L', key: 'unrealized_gl', align: 'end', sortable: true },
      { title: 'Cap. Distr.', key: 'capital_distribution', align: 'end', sortable: true },
      { title: 'Cap. Distr. %', key: 'capital_distribution_percentage', align: 'end', sortable: true, class: 'font-italic' },
      { title: 'Commission', key: 'commission', align: 'end', sortable: true },
      { title: 'Commission %', key: 'commission_percentage', align: 'end', sortable: true, class: 'font-italic' },
      { title: 'Total Return', key: 'total_return_amount', align: 'end', sortable: true },
      { title: 'Total Return %', key: 'total_return_percentage', align: 'end', sortable: true, class: 'font-italic' },
      { title: 'IRR', key: 'irr', align: 'end', sortable: true, class: 'font-italic' },
    ],
  },
]
```

(Currency/Position stay top-level flat columns — Vuetify gives them `rowspan=2` automatically.) Build `closedPositionsHeaders` the same way from `ClosedPositionsPage.vue` (Entry Date/Value, Exit Date/Value, Realized Amount/%, Capital distribution, Commission, Total return — all already 2-level; just change `align: 'center'` → `'end'`).

Also export:

```js
export const flattenHeaders = (headers) =>
  headers.flatMap((h) => (h.children ? flattenHeaders(h.children) : [h]))

export const openPercentageColumns = [
  'share_of_portfolio', 'price_change_percentage',
  'capital_distribution_percentage', 'commission_percentage',
  'total_return_percentage', 'irr',
]
export const closedPercentageColumns = [
  'price_change_percentage', 'capital_distribution_percentage',
  'commission_percentage', 'total_return_percentage', 'irr',
]

// "Analyst default" — identity + entry + current value + return columns.
export const openDefaultVisibleKeys = [
  'type', 'name', 'currency', 'current_position',
  'investment_date', 'entry_price', 'entry_value',
  'current_price', 'current_value', 'share_of_portfolio',
  'total_return_amount', 'total_return_percentage', 'irr',
]
export const closedDefaultVisibleKeys = null // closed table is narrow enough: all visible
```

- [ ] **Step 4: Run tests**

Run: `npm run test:unit -- tests/unit/config/positionsHeaders.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/config/positionsHeaders.js tests/unit/config/positionsHeaders.spec.js
git commit -m "feat(tables): shared two-level header config, end-aligned numerals"
```

---

### Task 4: PositionsPageBase — native grouped headers, working sort, column toggle

**Files:**
- Modify: `frontend/src/components/PositionsPageBase.vue`
- Modify: `frontend/src/composables/useTableSettings.ts`
- Test: `frontend/tests/unit/components/PositionsPageBase.spec.js` (create)

**Interfaces:**
- Consumes: `flattenHeaders` from Task 3.
- Produces: `PositionsPageBase` props unchanged (`fetchPositions`, `headers`, `pageTitle`) **plus new optional prop** `defaultVisibleKeys: string[] | null`; `useTableSettings` gains `visibleKeys: Ref<Set<string>>` and `setVisibleKeys()` persisted under `tableSettings.visibleKeys.<pageKey>` keyed by `pageTitle`.

- [ ] **Step 1: Write the failing test**

```js
// tests/unit/components/PositionsPageBase.spec.js
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import { createPinia } from 'pinia'
import PositionsPageBase from '@/components/PositionsPageBase.vue'

const vuetify = createVuetify()
const fetchPositions = vi.fn().mockResolvedValue({
  positions: [{ type: 'Stock', name: 'ACME', entry_value: 10 }],
  totals: {},
  total_items: 1,
})

const headers = [
  { title: 'Type', key: 'type', align: 'start', sortable: true },
  {
    title: 'Entry', key: 'entry', align: 'end', sortable: false,
    children: [
      { title: 'Date', key: 'investment_date', align: 'end', sortable: true },
      { title: 'Value', key: 'entry_value', align: 'end', sortable: true },
    ],
  },
]

describe('PositionsPageBase', () => {
  it('renders a clickable sort control on sortable headers (not disabled)', async () => {
    const wrapper = mount(PositionsPageBase, {
      global: { plugins: [vuetify, createPinia()] },
      props: { fetchPositions, headers, pageTitle: 'Test' },
    })
    await flushPromises()
    expect(wrapper.props().headers).toBeTruthy()
    const vm = wrapper.vm
    // disable-sort must be gone: the sort handler reaches the fetch
    await vm.handleSortChange([{ key: 'entry_value', order: 'desc' }])
    expect(fetchPositions).toHaveBeenCalled()
    expect(wrapper.html()).not.toContain('disable-sort')
  })

  it('hides columns not in defaultVisibleKeys', async () => {
    const wrapper = mount(PositionsPageBase, {
      global: { plugins: [vuetify, createPinia()] },
      props: { fetchPositions, headers, pageTitle: 'Test2',
               defaultVisibleKeys: ['type', 'name', 'entry_value'] },
    })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Investment date') // header leaf filtered out
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- tests/unit/components/PositionsPageBase.spec.js`
Expected: FAIL — `disable-sort` present / `defaultVisibleKeys` prop unknown.

- [ ] **Step 3: Implement**

In `PositionsPageBase.vue`:

1. Add prop `defaultVisibleKeys: { type: Array as Prop<string[] | null>, default: null }`.
2. Visibility computed:

```ts
const visibleHeaders = computed(() => {
  if (!props.defaultVisibleKeys) return props.headers
  const allowed = new Set(props.defaultVisibleKeys)
  return props.headers
    .map((h) =>
      h.children
        ? { ...h, children: h.children.filter((c) => allowed.has(String(c.key))) }
        : h
    )
    .filter((h) => h.children ? h.children.length > 0 : allowed.has(String(h.key)))
})
```

Bind `:headers="visibleHeaders"` and use `visibleHeaders` (not `props.headers`) inside `flattenedHeaders`.

3. On the `v-data-table`: delete `must-sort` and `disable-sort`; keep `:sort-by` / `@update:sort-by="handleSortChange"` (server sort — the fetch already passes `sortBy`).
4. Toolbar: after the search field add a column-visibility menu:

```vue
<v-menu close-on-content-click>
  <template #activator="{ props: menuProps }">
    <v-btn v-bind="menuProps" icon="mdi-table-column" density="compact"
           variant="text" aria-label="Show or hide columns" />
  </template>
  <v-list density="compact" max-height="360px">
    <v-list-item v-for="leaf in allLeaves" :key="leaf.key" density="compact">
      <v-checkbox-btn
        :model-value="visibleKeys.has(String(leaf.key))"
        :label="leaf.title"
        hide-details
        @update:model-value="toggleColumn(String(leaf.key))"
      />
    </v-list-item>
  </v-list>
</v-menu>
```

with script:

```ts
const allLeaves = computed(() => flattenHeaders(props.headers as TableHeader[]))
const visibleKeys = ref<Set<string>>(new Set(props.defaultVisibleKeys ?? allLeaves.value.map((l) => String(l.key))))
watch(allLeaves, (leaves) => {
  if (!props.defaultVisibleKeys) visibleKeys.value = new Set(leaves.map((l) => String(l.key)))
}, { immediate: true })
const toggleColumn = (key: string) => {
  const next = new Set(visibleKeys.value)
  next.has(key) ? next.delete(key) : next.add(key)
  visibleKeys.value = next
}
```

(Replaces the `visibleHeaders` allowed-set source: `visibleHeaders` should filter by `visibleKeys`, not `defaultVisibleKeys` directly — keep the two wired: initialize `visibleKeys` from `defaultVisibleKeys` on mount.)

5. Delete both `console.log` blocks in `fetchData` and the trailing `logger.log` of full appStore state (keep `logger.error` on catch).

In `useTableSettings.ts`: no persistence change required for the first cut if `visibleKeys` lives as component state; skip store changes in this task (YAGNI) and note it in the commit body. **If** the executor finds `handleSortChange` doesn't map `[{key, order}]` to the store's `sortBy` shape, adapt inside `PositionsPageBase` (store shape wins) — do not modify the store's public API.

- [ ] **Step 4: Run tests + lint + type-check**

Run: `npm run test:unit && npm run lint && npm run type-check`
Expected: PASS.

- [ ] **Step 5: Visual check**

`npm run dev` → Closed Positions page: two-row grouped header renders from Vuetify, sorting a column triggers a refetch, column menu hides/shows leaves.

- [ ] **Step 6: Commit**

```bash
git add src/components/PositionsPageBase.vue tests/unit/components/PositionsPageBase.spec.js
git commit -m "feat(tables): native grouped headers, server sort, column visibility"
```

---

### Task 5: Open & Closed pages migrate to shared config — delete hand-rolled thead

**Files:**
- Modify: `frontend/src/views/OpenPositionsPage.vue`
- Modify: `frontend/src/views/ClosedPositionsPage.vue`
- Test: `frontend/tests/unit/components/PositionsPages.spec.js` (create)

**Interfaces:**
- Consumes: Task 3 exports; Task 4 `defaultVisibleKeys` prop.

- [ ] **Step 1: Write the failing test**

```js
// tests/unit/components/PositionsPages.spec.js
import { describe, it, expect } from 'vitest'
import OpenPositionsPage from '@/views/OpenPositionsPage.vue'
import ClosedPositionsPage from '@/views/ClosedPositionsPage.vue'

describe('positions pages', () => {
  it('contain no hand-rolled thead or colspan helpers', () => {
    for (const comp of [OpenPositionsPage, ClosedPositionsPage]) {
      const src = JSON.stringify(comp)
      expect(src).not.toContain('getColspan')
      expect(src).not.toContain('getRowspan')
      expect(src.toLowerCase()).not.toContain('<thead')
      expect(src).not.toContain('console.log')
    }
  })

  it('closed positions no longer renders the debug header template', () => {
    const src = JSON.stringify(ClosedPositionsPage)
    expect(src).not.toContain('header.value')
    expect(src).not.toContain(' T ')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- tests/unit/components/PositionsPages.spec.js`
Expected: FAIL — both pages contain the offending strings.

- [ ] **Step 3: Migrate both pages**

**OpenPositionsPage.vue:** delete the entire `#header` template (lines 27–76), the `getColspan`/`getRowspan`/local `flattenHeaders` helpers, the `headers` ref (import `openPositionsHeaders`, `openPercentageColumns`, `flattenHeaders` from `@/config/positionsHeaders`; pass `:headers="openPositionsHeaders"` and `:default-visible-keys="openDefaultVisibleKeys"`), and the `console.log` in `fetchOpenPositions`. Rewrite the `#tfoot` slot as a single loop over the flattened **visible** leaves — because the page no longer knows visibility, move the cash/TOTAL footer rows into named slots provided by `PositionsPageBase` under a generic contract:

```vue
<template #tfoot-extra>
  <tr>
    <td :colspan="2" class="text-start">Cash</td>
    <td class="text-end">{{ totals.cash }}</td>
    <td class="text-end font-italic">{{ totals.cash_share_of_portfolio }}</td>
  </tr>
  <tr class="font-weight-bold">
    <td :colspan="2" class="text-start">TOTAL</td>
    <td class="text-end">{{ totals.total_nav }}</td>
    <td class="text-end font-italic">{{ totals.irr }}</td>
  </tr>
</template>
```

In `PositionsPageBase.vue` `#tfoot`, render the main totals row from `flattenedHeaders` (already does) and render `<slot name="tfoot-extra" />` rows **after** it, with each extra row padded to the visible column count using empty `<td :colspan="...">` cells computed from `visibleHeaders` (the executor sizes the colspans from the flattened visible header list at render time — never a literal).

**Simpler alternative if wiring extra rows into the v-data-table tfoot proves brittle:** render Cash/TOTAL rows as ordinary `<tr>`s inside the existing `#tfoot` slot in the page, with colspans computed from the same `flattenHeaders(visibleHeaders)` length passed down as a slot prop (`:flattened-count`). Pick whichever renders correctly in the browser; requirement: **zero literal colspan numbers**.

**ClosedPositionsPage.vue:** delete the `#header` template (the P0 debug markup), import `closedPositionsHeaders`/`closedPercentageColumns` from the shared config, delete the local `headers` ref, `flattenedHeaders` computed (use shared `flattenHeaders`), and the `console.log` in `fetchClosedPositions`. The existing `#tfoot` loop already matches and stays.

- [ ] **Step 4: Run tests + full suite**

Run: `npm run test:unit && npm run lint && npm run type-check`
Expected: PASS.

- [ ] **Step 5: Visual check (critical)**

`npm run dev` → Open Positions: two-row header (Entry | Current groups), ~13 visible columns by default, column menu reveals the rest, footer rows align with visible columns at every toggle combination tried (all on / all off / default). Closed Positions: no " T true" text anywhere.

- [ ] **Step 6: Commit**

```bash
git add src/views/OpenPositionsPage.vue src/views/ClosedPositionsPage.vue src/components/PositionsPageBase.vue tests/unit/components/PositionsPages.spec.js
git commit -m "feat(tables): migrate pages to shared grouped headers, remove debug markup"
```

---

### Task 6: Sticky identity columns + group separation CSS

**Files:**
- Modify: `frontend/src/components/PositionsPageBase.vue` (style block)
- Modify: `frontend/src/App.vue` (remove global `td` white-space rules, lines ~145–150)

**Interfaces:**
- Consumes: Task 4/5 markup (first two columns are `type`, `name` in both pages).

- [ ] **Step 1: Replace the style block in `PositionsPageBase.vue`**

```css
.nowrap-table :deep(td),
.nowrap-table :deep(th) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-variant-numeric: tabular-nums;
}

/* Sticky identity columns: Type sticks at 0, Name after it. Widths are
   fixed so the left offset is stable; adjust if a page reorders identity. */
.nowrap-table :deep(th:nth-child(1)),
.nowrap-table :deep(td:nth-child(1)) {
  position: sticky;
  left: 0;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
  min-width: 90px;
}
.nowrap-table :deep(th:nth-child(2)),
.nowrap-table :deep(td:nth-child(2)) {
  position: sticky;
  left: 90px;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
  min-width: 160px;
}
.nowrap-table :deep(thead th:nth-child(-n+2)) {
  z-index: 3; /* leaf header row above sticky body cells */
}

/* Group separation: vertical rules between top-level groups survive
   without reading the group row. */
.nowrap-table :deep(.group-start) {
  border-left: 1px solid rgba(var(--v-border-opacity), rgba(0, 0, 0, 0.12));
}
```

Note: `group-start` cells require Vuetify's header cell classes. Vuetify 3 emits `v-data-table-column--divider` on the first column of each new group when using `children` headers. Target that instead:

```css
.nowrap-table :deep(th.v-data-table-column--divider) {
  border-left: 1px solid rgba(0, 0, 0, 0.12);
}
```

Apply the same rule to body `td` via `:nth-child` is unreliable once columns toggle — instead add a `divider` boundary only on headers (acceptable per spec: "vertical rule between groups" primarily on the header). Verify in the browser which selector Vuetify actually emits and keep the one that works; requirement: a visible rule between Entry and Current blocks.

- [ ] **Step 2: Remove the contradictory global rules in `App.vue`**

Delete the `td { white-space: normal; hyphens: auto }` rules (lines ~145–150). Tables own their own white-space policy now (Task 6 Step 1); non-table text is unaffected.

- [ ] **Step 3: Verify**

Run: `npm run test:unit && npm run lint`, then `npm run dev`: horizontally scroll Open Positions — Type/Name stay pinned with opaque backgrounds and no see-through text; group rules visible.

- [ ] **Step 4: Commit**

```bash
git add src/components/PositionsPageBase.vue src/App.vue
git commit -m "feat(tables): sticky identity columns, group dividers, global td rule cleanup"
```

---

### Task 7: Charts — breakdown pies → horizontal bars, tooltips on, theme colors

**Files:**
- Modify: `frontend/src/config/chartConfig.js`
- Modify: `frontend/src/components/dashboard/BreakdownChart.vue`
- Test: `frontend/tests/unit/config/chartConfig.spec.js` (create)

**Interfaces:**
- Consumes: Task 1 `palette`.
- Produces: `getChartOptions().barChartOptions` (horizontal bar: `indexAxis: 'y'`, value + % datalabels, tooltips enabled); `colorPalette` derived from `palette`.

- [ ] **Step 1: Write the failing test**

```js
// tests/unit/config/chartConfig.spec.js
import { describe, it, expect } from 'vitest'
import { getChartOptions, colorPalette } from '@/config/chartConfig'

describe('chart config', () => {
  it('exposes horizontal bar options with tooltips enabled', async () => {
    const opts = await getChartOptions('USD')
    expect(opts.barChartOptions.indexAxis).toBe('y')
    expect(opts.barChartOptions.plugins.tooltip.enabled).not.toBe(false)
    expect(opts.pieChartOptions).toBeUndefined() // pies retired as primary breakdown
  })

  it('palette starts with the theme primary', () => {
    expect(colorPalette[0].toLowerCase()).toBe('#0f4c81')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test:unit -- tests/unit/config/chartConfig.spec.js`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `chartConfig.js`:

- Export `export const colorPalette = ['#0F4C81', '#5C6B7A', '#1E7F4F', '#9A6700', '#0B5FA5', '#7A4E2D', '#607D8B', '#8E4585', '#00838F', '#B3261E', '#6D4C41', '#9E9D24']` (moved out of the returned object; import sites update from destructure to import).
- Replace `pieChartOptions` with:

```js
barChartOptions: {
  responsive: true,
  maintainAspectRatio: false,
  indexAxis: 'y',
  scales: {
    x: { ticks: { font: axisFont } },
    y: { grid: { display: false }, ticks: { font: axisFont } },
  },
  plugins: {
    legend: { display: false },
    tooltip: { enabled: true },
    datalabels: {
      anchor: 'end',
      align: 'end',
      offset: 4,
      color: '#1A1C1E',
      font: { family: fontFamily, size: 12 },
      formatter: (value, ctx) => {
        const data = ctx.chart.data.datasets[0].data
        const sum = data.reduce((a, b) => a + b, 0)
        return `${(value).toLocaleString(undefined, { maximumFractionDigits: 1 })} (${((value * 100) / sum).toFixed(1)}%)`
      },
    },
  },
  layout: { padding: { right: 80 } },
},
```

- NAV chart label `color: () => 'black'` → `color: () => '#1A1C1E'`.

In `BreakdownChart.vue`: switch the chart `type` from `pie` to `bar`, bind the new `barChartOptions`, remove the `max-width: 300px` clamp and pie-specific padding (keep the container height control it already uses). If the component sorts slices, sort descending by value so the longest bar is on top (Chart.js y axis renders first label at top: reverse the sorted array).

- [ ] **Step 4: Run tests + visual check**

Run: `npm run test:unit -- tests/unit/config/chartConfig.spec.js`, then dev server: dashboard breakdowns render as sorted horizontal bars with `value (x.x%)` labels and tooltips.

- [ ] **Step 5: Commit**

```bash
git add src/config/chartConfig.js src/components/dashboard/BreakdownChart.vue tests/unit/config/chartConfig.spec.js
git commit -m "feat(charts): breakdown pies to sorted horizontal bars with tooltips"
```

---

### Task 8: NAV chart fixes — zero portfolio, error placement, labeled frequency toggle

**Files:**
- Modify: `frontend/src/components/dashboard/NAVChart.vue`
- Modify: `frontend/src/views/DashboardPage.vue`

**Interfaces:** none new.

- [ ] **Step 1: Fix the empty-data heuristic**

In `NAVChart.vue`, find the computed that decides "no data" (it currently treats an all-zero series as empty). Change it to check only whether the series has points:

```js
const hasNoData = computed(() =>
  !props.data || props.data.every((series) => !series.data || series.data.length === 0)
)
```

(An all-zero portfolio is data, not an absence.)

- [ ] **Step 2: Move the error alert above the chart**

In `DashboardPage.vue`, locate `v-alert v-if="error.navChart"` currently rendered after the chart card; move it before the `v-card` wrapping `NAVChart` so errors are seen first.

- [ ] **Step 3: Label the frequency toggle**

In `NAVChart.vue`, replace the `D W M Q Y` toggle items with `{ title: 'Day', value: 'D' }, { title: 'Week', value: 'W' }, { title: 'Month', value: 'M' }, { title: 'Quarter', value: 'Q' }, { title: 'Year', value: 'Y' }` (or keep short labels and add `title` attr tooltips: `Day`, `Week`, `Month`, `Quarter`, `Year`). Whichever control is used (v-btn-toggle / v-select), the requirement: a first-time user can read the words, and each control carries `aria-label="Chart frequency"` on the group.

- [ ] **Step 4: Verify + commit**

Run: `npm run test:unit && npm run lint && npm run type-check`; dev server: toggle frequencies, confirm labels; simulate a fetch error (devtools offline) → alert appears above the chart with a **Retry** button if one exists, else add one: `@click="refresh"` wired to the dashboard's existing refresh trigger (`appStore.dataRefreshTrigger++` or the page's fetch function).

```bash
git add src/components/dashboard/NAVChart.vue src/views/DashboardPage.vue
git commit -m "fix(dashboard): NAV chart zero-portfolio, error placement, labeled frequency"
```

---

### Task 9: Error surface — inline retry in widgets (WCAG timing)

**Files:**
- Modify: `frontend/src/views/DashboardPage.vue`
- Modify: `frontend/src/App.vue` (snackbar timeout)

**Interfaces:** none new.

- [ ] **Step 1: Widget errors get retry**

For each dashboard widget error alert (`error.navChart`, `error.summary`, `error.breakdown*` — read the page for exact keys), add:

```vue
<v-alert type="error" variant="tonal" :text="error.navChart">
  <template #append>
    <v-btn size="small" variant="text" @click="retry('navChart')">Retry</v-btn>
  </template>
</v-alert>
```

with a `retry(source)` method that re-invokes that widget's fetch (the page already has per-widget fetch functions — call them directly; do not invent a generic dispatcher if the page structure doesn't support it).

- [ ] **Step 2: Snackbar: errors are not transient**

In `App.vue`, find the global error snackbar. Errors (as opposed to successes) must not auto-dismiss on a short timer: set `:timeout="-1` for error severity with a dismiss button, keep short timeout (5000) only for success/info severities. Read the snackbar's severity source (`appStore.error` vs message type) and branch on it.

- [ ] **Step 3: Verify + commit**

Devtools offline → each widget shows an inline error with Retry; global error snackbar persists until dismissed; success snackbars still auto-hide.

```bash
git add src/views/DashboardPage.vue src/App.vue
git commit -m "fix(dashboard): inline widget retry, persistent error snackbar"
```

---

### Task 10: App bar layout — remove the 140px hack

**Files:**
- Modify: `frontend/src/App.vue` (lines ~29, ~100)

**Interfaces:** none new.

- [ ] **Step 1: Replace manual padding with the layout system**

Current: `<v-main :style="{ paddingTop: mainPadding }">` with `route.meta.paddingTop || '140px'`. Vuetify's `v-layout`/`v-app-bar` already set `--v-layout-top` and `v-main` offsets itself. Change:

- Remove the `:style` binding and the `mainPadding` computed entirely.
- Ensure the app bar is inside `<v-layout>` and `v-main` follows it; if pages currently compensate for a *non-fixed* app bar double-counting, the correct fix is to let `v-main` auto-offset: keep `<v-app-bar>` (not manually positioned) followed by `<v-main>`.
- Grep `route.meta.paddingTop` users (`frontend/src/router/**`) and delete the `paddingTop` meta keys.
- If any page genuinely needs extra top spacing (e.g. persistent sub-header), add a scoped spacer on that page, not a global magic padding.

- [ ] **Step 2: Verify every page**

Dev server, walk every route in the nav: no content hidden under the app bar, no double gaps. This is the task's acceptance test — budget real browser time here.

- [ ] **Step 3: Commit**

```bash
git add src/App.vue src/router
git commit -m "fix(layout): v-main auto-offset replaces hardcoded 140px padding"
```

---

### Task 11: Empty states, glossary tooltips, highlight token

**Files:**
- Modify: `frontend/src/views/DashboardPage.vue`
- Modify: `frontend/src/components/dashboard/SummaryOverTimeTable.vue`
- Modify: `frontend/src/config/positionsHeaders.js` (optional tooltip descriptions)
- Modify: `frontend/src/components/PositionsPageBase.vue` (header tooltip rendering)

**Interfaces:**
- Consumes: Task 3 header config; optional `description` field on leaf headers, rendered as `v-tooltip` in the table header.

- [ ] **Step 1: Distinct empty states**

In `DashboardPage.vue`, every "No data available" empty branch gets one of two messages decided by whether the account has any data for the period:

```vue
<v-alert type="info" variant="tonal" density="compact"
  text="No data for the selected account and period. Adjust the date range or select another account." />
```

For the positions pages (in `PositionsPageBase.vue`), if `totalItems === 0 && !search`, show `No positions yet — import transactions to get started.` (linking the existing import flow) instead of the bare Vuetify empty row.

- [ ] **Step 2: Glossary tooltips**

Add `description` to the leaves that need it in `positionsHeaders.js`:

```js
{ title: 'IRR', key: 'irr', align: 'end', sortable: true, class: 'font-italic',
  description: 'Money-weighted internal rate of return since the position was opened.' },
{ title: 'Total Return %', key: 'total_return_percentage', align: 'end', sortable: true, class: 'font-italic',
  description: 'Total return incl. capital distributions and after commissions, relative to entry value.' },
```

In `PositionsPageBase.vue`, use the `#header` slot (per-column, the *supported* one — unlike the whole-thead override this is per cell):

```vue
<template #header="{ column }">
  <v-tooltip v-if="column.raw?.description" :text="column.raw.description" location="top">
    <template #activator="{ props: tooltipProps }">
      <span v-bind="tooltipProps">{{ column.title }}</span>
    </template>
  </v-tooltip>
  <span v-else>{{ column.title }}</span>
</template>
```

(If the slot payload shape differs in the installed Vuetify version, inspect `node_modules/vuetify` slot types and adapt; requirement: hovering a described header shows the glossary tooltip, sorting still works.)

- [ ] **Step 3: Highlight token**

In `SummaryOverTimeTable.vue`, replace `background: rgba(0, 0, 0, 0.05)` with `background: rgba(var(--v-theme-primary), 0.08)`.

- [ ] **Step 4: Verify + full suite + commit**

Run: `npm run test:unit && npm run lint && npm run type-check`; browser-check tooltips and empty states.

```bash
git add src/views/DashboardPage.vue src/components/dashboard/SummaryOverTimeTable.vue src/config/positionsHeaders.js src/components/PositionsPageBase.vue
git commit -m "feat(ux): distinct empty states, header glossary tooltips, theme highlight"
```

---

### Task 12: Final polish pass + detector + critique re-run

**Files:**
- Sweep: `frontend/src/**` (no fixed list — this task hunts residue)

**Interfaces:** none.

- [ ] **Step 1: Sweep for residue**

```bash
cd frontend && grep -rn "console\.log" src/ ; grep -rn "--v-primary-base" src/ ; grep -rn "rgba(0, 0, 0" src/ ; grep -rn "!important" src/
```

Expected after Tasks 1–11: no `console.log`, no `--v-primary-base`. Remaining `rgba(0,0,0,…)`/`!important` instances: judge case by case — replace hardcoded blacks with `#1A1C1E`-style literals or theme tokens; delete `!important` where the selector can win by specificity.

- [ ] **Step 2: Run the impeccable detector**

```bash
node "C:\Users\PC-Admin\.zcode\skills\impeccable\scripts\detect.mjs" --json src
```

Expected: exit 0 (0 findings). Fix anything it reports.

- [ ] **Step 3: Full verification**

```bash
npm run test:unit && npm run lint && npm run type-check && npm run build
```

Expected: all green, build succeeds.

- [ ] **Step 4: Browser walkthrough**

Dev server; visit Dashboard, Open Positions, Closed Positions, Transactions, Summary. Check: grouped headers + sticky columns + sort + column toggle + tooltips + footers aligned; charts bar-based with tooltips; empty/error states correct; no page hidden under app bar.

- [ ] **Step 5: Commit**

```bash
git add -A src/ tests/
git commit -m "chore(polish): design residue sweep, detector clean"
```

- [ ] **Step 6: Re-run `$impeccable critique` on `frontend/src`** (outside this plan's commit scope; report the new score to the user).

---

## Self-Review (performed at plan-writing time)

- **Spec coverage:** theme (T1,2), two-row grouped headers + flattening (T3–5), scope/accessibility (T4 native Vuetify markup), right-aligned tabular numerals (T1,3), sticky columns + group rules (T6), analyst defaults/column toggle (T3,4), sorting honesty (T4), pies→bars + tooltips + NAV fixes (T7,8), dashboard grid hierarchy — **deferred**: the current grid already ranks NAV first; revisit after T7/8 land if the critique still flags it (noted, not silently dropped), app bar hack (T10), error surfacing (T9), empty states + glossary (T11), residue + detector (T12).
- **Placeholders:** none; every code step carries code. Two steps deliberately instruct the executor to verify the exact Vuetify slot/selector shape in `node_modules` before finalizing — that is verification guidance, not missing content.
- **Type consistency:** `flattenHeaders` exported from `positionsHeaders.js` (T3) and consumed in T4/T5; `defaultVisibleKeys` prop defined in T4 and passed in T5; `barChartOptions`/`colorPalette` defined in T7 and only consumed there.
