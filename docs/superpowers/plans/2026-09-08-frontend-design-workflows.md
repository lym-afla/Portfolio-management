# Frontend Design and Workflows Implementation Plan

## Scope amendment — 5 October 2026

The owner has removed dedicated screen-reader support work and real assistive-technology audits (NVDA, JAWS, VoiceOver or equivalent) from the modernization scope. They are not acceptance criteria, release blockers or deferred D8 work. This amendment supersedes earlier screen-reader requirements and historical references assigning their audit to D8, including prior handoffs and evidence records. Past statements that no such audit was performed remain historically accurate; do not present them as outstanding acceptance gaps.

Retain keyboard navigation, focus entry/return, readable labels, contrast, responsive layouts, native 200% zoom, visible/hittable controls, semantic HTML and exact-value chart tables. Preserve existing ARIA/semantic markup and tests; this scope change does not request application-code removal. D8 still verifies visual quality, keyboard usability, responsive behavior and workflow correctness. General accessibility references in these plans apply to those retained checks, not a screen-reader certification or dedicated compatibility project.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every existing application page a coherent, accessible financial-workspace design while preserving its routes, calculations, data and established workflows.

**Architecture:** Retain Vue, Vuetify and Pinia. Introduce a small presentational workspace component set, then migrate route families incrementally; extract the import, broker-connection and security-detail responsibilities where their current components mix unrelated state and UI. The R workstream owns committed portfolio context and request correctness; the C workstream owns ECharts rendering, chart adapters and chart data alternatives.

**Tech Stack:** Existing locked Vue 3, Vuetify 3, Pinia, TypeScript, Vue Router, VeeValidate/Yup, Vitest and Vue Test Utils; agent-browser for real browser review. This workstream adds no UI framework or production dependency.

**Spec:** [Accepted 8 September frontend audit](../../audits/2026-09-08-frontend-audit.md), supplemented by the already approved [tables and visual redesign design](../specs/2026-08-18-tables-visual-redesign-design.md). Read both before execution. The September audit identifies current defects; the August spec remains authoritative for table behavior already implemented.

**Subsequent direction:** Read the [focused table/pie review](../../audits/2026-09-08-grouped-tables-and-allocation-pies.md). The user explicitly requires three solid allocation pies. Its hybrid table recommendation updates the proposed D3/D4 pilot: simple Overview, grouped comparison and Full ledger; preserve the August financial/column invariants without freezing its header-row count in every view. The pilot still establishes the reviewed visual result before rollout.

## Global Constraints

- This document is an implementation plan only. Its creation does not implement, commit, deploy or run the proposed work.
- Keep Vue, Vite, Pinia and Vuetify. Keep existing route paths, route names, redirects, authentication guards and API endpoints.
- Keep brokerage blue `#0F4C81` and the current system font stack. Implement the light theme now; use semantic tokens that can support a future dark theme without adding a theme toggle.
- Preserve grouped metric meanings, numeric end alignment, sticky row identity, complete column availability, meaningful totals and functional sorting. Pilot a single-row Overview and two-row grouped comparison/Full ledger, with no third tier. Current positions already have two structural rows; the new work is task-based views, clearer group membership and durable column identity rather than another third-tier removal.
- Financial values remain server-authoritative. Render the existing Decimal/string API values and approved formatters; never add NAV, return, cash, FX, price, bond, quantity or tax calculations in a UI component.
- Preserve zero, negative/short values, missing values, currency distinctions, bond percentage-price labels, effective notional behavior and `CustomUser.digits`. Missing is not zero; a return is not the same thing as a change in NAV.
- Do not add new metrics, benchmark comparisons, CSV export, dark mode, i18n, route-wide URL sharing, onboarding tours or custom keyboard shortcuts. Standard keyboard operation and equivalent chart data tables are required.
- D owns appearance, layout composition, labels, controls and extracted workflow presentation. R owns the shell's basic non-overlap fix, committed context, request cancellation/acceptance and mutation invalidation. C owns all chart rendering and numeric chart adapters under `frontend/src/features/charts/`.
- Follow `AGENTS.md` and `.memory-bank/Rules for AI Coding Agent.md`. Any unexpected protected-code or financial-output change belongs in a separately reviewed PR with the required regression evidence and `needs-approval` label; do not hide it inside a design commit.
- Run commands from `backend/` as required by the repository. Frontend command prefixes below deliberately use `../frontend`.
- Use isolated local synthetic fixtures or an explicitly configured development account for visual review. Never attach real account data or credentials to screenshots or broker-token test fixtures.
- Complete a rendered desktop/mobile design review at D3 before propagating visual defaults across all pages. This is an implementation quality milestone, not a new permission request for the already accepted direction.

## Boundaries and shared contracts

R provides `frontend/src/types/portfolioContext.ts` and `frontend/src/stores/portfolioContext.ts`. `usePortfolioContextStore()` exposes:

```ts
committed: Readonly<PortfolioContext>
isTransitioning: boolean
isReady: boolean
transitionError: Error | null
changeContext(patch: ContextPatch): Promise<void>
reconcileContext(): Promise<void>
```

`PortfolioContext` contains `revision`, `accountSelection`, `effectiveCurrentDate`, `currency` and `digits`. R exports `ContextPatch` as `{ accountSelection: AccountSelection } | { effectiveCurrentDate: string; currency: string; digits: number }`. Reuse R's selection union unchanged, including all existing broker/group/account selection variants. D must not narrow saved selections to the examples in a component test. Date, currency and precision persistence remain coordinated by R; a failed mutation leaves the displayed committed context unchanged. Committed date/currency may be null before readiness; show `Unavailable` and disable mutation controls until ready.

D creates `frontend/src/components/workspace/types.ts`:

```ts
import type { PortfolioContext } from '@/types/portfolioContext'

export type ContextIntent =
  | { accountSelection: PortfolioContext['accountSelection'] }
  | Partial<{ effectiveCurrentDate: string; currency: string; digits: number }>

export interface WorkspaceContextView {
  committed: Readonly<PortfolioContext>
  accountLabel: string
  pendingLabel: string | null
  isReady: boolean
  isTransitioning: boolean
  errorMessage: string | null
}

export interface WorkspaceAction {
  id: string
  label: string
  icon?: string
  disabled?: boolean
  destructive?: boolean
}

export interface MetricDisplay {
  id: string
  label: string
  value: string
  unitLabel?: string
  explanation?: string
}

export interface TableQueryView {
  search: string
  page: number
  itemsPerPage: number
  totalItems: number
}

export interface ConfirmationSubject {
  title: string
  details: ReadonlyArray<{ label: string; value: string }>
  confirmLabel: string
}
```

`WorkspaceContextStrip` consumes `WorkspaceContextView`, emits `request-change(ContextIntent)` and `open-preferences()`, and owns no network requests or committed selection. The App adapter converts each settings intent into R's complete ready settings tuple before calling `changeContext`; account intents use R's separate account variant. `WorkspaceTableToolbar` consumes `TableQueryView` plus action definitions and emits a query patch or action ID; R's existing route/controller owns request identity, debounce and page reset rules. `WorkspaceActions` emits action IDs, never calls API functions. C components retain their documented chart props/events; D provides surrounding sections and layout, not a parallel chart-control API.

## File responsibility map

| Files | Responsibility |
|---|---|
| `frontend/src/theme.js`, `frontend/src/theme/defaults.ts`, `frontend/src/assets/workspace.css`, `frontend/src/assets/fonts.css` | Existing palette plus semantic surface/text/border/spacing/type tokens; scoped component defaults and numeric presentation |
| `frontend/src/components/workspace/{types.ts,WorkspacePage.vue,WorkspaceSection.vue,WorkspaceActions.vue,WorkspaceContextStrip.vue,WorkspaceTableToolbar.vue,WorkspaceEmptyState.vue,ConfirmActionDialog.vue}` | Small presentational components with explicit props/events/slots |
| `frontend/src/components/{Navigation.vue,AccountSelection.vue,SettingsDialog.vue}`, `frontend/src/App.vue` | Integrate visible committed context and responsive navigation after R's shell repair |
| `frontend/src/views/DashboardPage.vue`, `frontend/src/components/dashboard/{SummaryCard.vue,SummaryOverTimeTable.vue}` | NAV-first page composition and existing summary values; C retains chart ownership |
| `frontend/src/components/PositionsPageBase.vue`, `frontend/src/components/transactions/TransactionRow.vue`, existing route views/dialogs | Shared table, action, form and confirmation patterns without changing data contracts |
| `frontend/src/features/imports/{types.ts,legacyImportProtocol.ts,useTransactionImport.ts,ImportMethodStep.vue,ImportSourceStep.vue,ImportReviewStep.vue,ImportResult.vue}` | Typed import state and transport boundary, existing mapping/confirmation workflow, focused step presentation |
| `frontend/src/features/brokers/{types.ts,useBrokerConnections.ts,BrokerConnectionList.vue,BrokerConnectionForm.vue}` | Broker-token state/API boundary and provider-specific form/list presentation |
| `frontend/src/features/securities/{types.ts,useSecurityDetail.ts,SecurityOverview.vue,SecurityMetadata.vue,SecurityActivity.vue}` | Security response ownership, identity/metadata/activity composition; chart content supplied through slots |
| `frontend/tests/unit/workspace/`, `frontend/tests/unit/features/`, existing component tests | Behavioral regressions for shared contracts and extracted workflows |
| `docs/design/{frontend-workspace.md,frontend-route-review.md}`, `.memory-bank/Tech details/frontend.md` | Implemented design conventions, route evidence, state/component ownership |

Folders listed in this map that do not yet exist are **proposed**. Current components remain compatibility entrypoints until their callers are migrated; no duplicate live implementations remain after the relevant task.

## Sequence and review units

`D1 → D2 → D3 → D4 → D5 → D8`. D2 integrates only after R context/shell contracts are available. D3 is renderer-neutral and can use the existing `NAVChart` after R's fixes; D5's visual rollout does not wait for financial C1 or the ECharts migration. D6 and D7 can be reviewed independently after D4, then D8 integrates all route families. C3 replaces the renderer and repeats the same visual captures, adding its mandatory HTML legend/table/tooltip/zoom acceptance; C4 migrates allocations/security charts and C5 gates cutover/removal. C owns chart implementation commits even when a D task edits the surrounding page. Avoid simultaneous edits of App, Dashboard, SecurityDetail or transaction/import entrypoints; agree which workstream lands first and rebase the other.

### D1: Establish restrained tokens and pilot component defaults

**Files**

- Modify: `frontend/src/theme.js`, `frontend/src/assets/fonts.css`, `frontend/src/main.js`.
- Create: `frontend/src/theme/defaults.ts`, `frontend/src/assets/workspace.css`, `frontend/src/components/workspace/types.ts`, `frontend/src/components/workspace/WorkspacePage.vue`, `frontend/src/components/workspace/WorkspaceSection.vue`.
- Test: `frontend/tests/unit/workspace/WorkspaceSection.spec.ts`; retain `frontend/tests/unit/main-theme.spec.js` and `frontend/tests/unit/components/SummaryCard.spec.js`.

**Interfaces**

- `WorkspacePage`: props `{ title: string; description?: string }`; slots `actions`, `context`, default. Exactly one page `<h1>` per route; App stops duplicating the same title when this component is used.
- `WorkspaceSection`: props `{ headingId: string; title: string; description?: string }`; slots `actions`, default. Renders a named `<section>` and `<h2>`.
- Export `workspaceDefaults` from `theme/defaults.ts` for a scoped `VDefaultsProvider`. Do not apply all defaults globally before D3.

- [ ] Add semantic theme colors `text-primary`, `text-secondary`, `border`, `surface-muted`, `focus`, preserving all existing `palette` keys consumed by chart code. Use current primary `#0F4C81`, secondary `#5C6B7A`, canvas `#F7F8FA`, surface `#FFFFFF`; choose readable dark text and restrained borders. Add this initial scoped style/default definition:

```ts
// frontend/src/theme/defaults.ts
export const workspaceDefaults = {
  VCard: { elevation: 0, rounded: 'lg', border: true },
  VBtn: { rounded: 'sm', elevation: 0 },
  VTextField: { variant: 'outlined', density: 'compact' },
  VSelect: { variant: 'outlined', density: 'compact' },
  VAutocomplete: { variant: 'outlined', density: 'compact' },
  VDataTable: { density: 'compact' },
} as const
```

```css
/* frontend/src/assets/workspace.css */
.workspace-ui {
  --workspace-gap: 24px;
  --workspace-section-gap: 16px;
  --workspace-radius: 8px;
  --workspace-page-title: 1.5rem;
  --workspace-metric: clamp(1.75rem, 3vw, 2.25rem);
  color: rgb(var(--v-theme-text-primary));
}
.workspace-ui .workspace-number { text-align: right; font-variant-numeric: tabular-nums; }
.workspace-ui .workspace-meta { color: rgb(var(--v-theme-text-secondary)); }
.workspace-ui :focus-visible { outline: 2px solid rgb(var(--v-theme-focus)); outline-offset: 3px; }
.workspace-ui .workspace-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.workspace-ui .workspace-table-region { max-width: 100%; overflow-x: auto; }
@media (max-width: 599px) {
  .workspace-ui { --workspace-gap: 16px; --workspace-section-gap: 12px; }
  .workspace-ui .workspace-touch-action { min-width: 44px; min-height: 44px; }
}
```

- [ ] Implement the section boundary without decorative icons or hardcoded visual colors. Keep the default system font and tabular numerals; replace the blanket descendant font override only after checking MDI icons and form controls, so icon fonts remain intact.

```vue
<!-- frontend/src/components/workspace/WorkspaceSection.vue -->
<script setup lang="ts">
defineProps<{ headingId: string; title: string; description?: string }>()
</script>
<template>
  <section :aria-labelledby="headingId" class="workspace-section">
    <header class="workspace-section__header">
      <div>
        <h2 :id="headingId">{{ title }}</h2>
        <p v-if="description" class="workspace-meta">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="workspace-actions"><slot name="actions" /></div>
    </header>
    <slot />
  </section>
</template>
```

- [ ] Add a meaningful naming/content regression; do not snapshot CSS strings. The test must fail before the new component exists, then pass with its real template.

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'

describe('WorkspaceSection', () => {
  it('names the section from its visible heading and preserves its content', () => {
    const wrapper = mount(WorkspaceSection, {
      props: { headingId: 'allocation', title: 'Allocation' },
      slots: { default: '<p>Cash is included</p>' },
    })
    expect(wrapper.get('section').attributes('aria-labelledby')).toBe('allocation')
    expect(wrapper.get('#allocation').text()).toBe('Allocation')
    expect(wrapper.text()).toContain('Cash is included')
  })
})
```

- [ ] Run `npm --prefix ../frontend run test:unit -- tests/unit/workspace/WorkspaceSection.spec.ts tests/unit/main-theme.spec.js tests/unit/components/SummaryCard.spec.js`, then `npm --prefix ../frontend run type-check`. Expected: all targeted tests pass; existing palette consumers still type-check. Record unrelated baseline failures instead of deleting assertions.
- [ ] Review the token values at 100% zoom in the D3 pilot, with no global route restyling yet. Prepare one reviewable commit containing the foundation and its contracts; use the repository's required commit-message format and scope `frontend`.

### D2: Show committed context and responsive labeled navigation

**Files**

- Modify: `frontend/src/App.vue`, `frontend/src/components/Navigation.vue`, `frontend/src/components/AccountSelection.vue`, `frontend/src/components/SettingsDialog.vue`.
- Create: `frontend/src/components/workspace/WorkspaceContextStrip.vue`, `frontend/src/components/workspace/useWorkspaceContextView.ts`, `frontend/src/components/workspace/contextIntent.ts`, `frontend/src/components/workspace/navigation.ts`.
- Test: `frontend/tests/unit/workspace/WorkspaceContextStrip.spec.ts`, `frontend/tests/unit/workspace/Navigation.spec.ts`; retain R's context and App-layout tests.

**Interfaces**

- Consume R's committed store and `ContextIntent`/`WorkspaceContextView` above. `useWorkspaceContextView` receives the store and already loaded account-label lookup; it returns a computed display view and does not fetch or persist anything. `toContextPatch(intent, committed, isReady)` converts only UI intents into R's exported `ContextPatch` and rejects pre-ready commands.
- Preserve `AccountSelection` as an entrypoint if R already refactors it. Its selected value is committed; intent and pending labels are distinct.
- `navigation.ts` exports `workspaceNavigation: ReadonlyArray<{ label: string; to: string; icon: string; section: 'portfolio' | 'data' | 'personal' }>` using current paths.

- [ ] Add tests for committed-label persistence while pending, accessible names, failed transitions and the settings precision field. Use R's existing deterministic context fixtures; do not create a second context store.

```ts
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import WorkspaceContextStrip from '@/components/workspace/WorkspaceContextStrip.vue'
import type { WorkspaceContextView } from '@/components/workspace/types'

it('keeps committed account and date visible while another choice is saving', () => {
  const view: WorkspaceContextView = {
    committed: { revision: 4, accountSelection: { type: 'account', id: 1 },
      effectiveCurrentDate: '2026-09-08', currency: 'USD', digits: 2 },
    accountLabel: 'Brokerage A', pendingLabel: 'Brokerage B',
    isReady: true, isTransitioning: true, errorMessage: null,
  }
  const wrapper = mount(WorkspaceContextStrip, { props: { view } })
  expect(wrapper.get('[data-testid="committed-account"]').text()).toBe('Brokerage A')
  expect(wrapper.get('[role="status"]').text()).toContain('Brokerage B')
  expect(wrapper.text()).toContain('2026-09-08')
  expect(wrapper.text()).toContain('USD')
})
```

- [ ] Implement a compact context strip. The selected account occupies the available width; desktop cycling buttons have `Previous account`/`Next account` names. Below 600px, use a full-width account control on the first line and valuation-date/currency controls on the second; remove cycling arrows from that layout. Precision stays in the named `Display preferences` dialog. Existing values stay visible while pending; announce the pending label through one polite status region.

```vue
<script setup lang="ts">
import type { ContextIntent, WorkspaceContextView } from './types'
defineProps<{ view: WorkspaceContextView }>()
defineEmits<{
  'request-change': [patch: ContextIntent]
  'open-preferences': []
}>()
</script>
<template>
  <div class="workspace-context" aria-label="Portfolio context">
    <div data-testid="committed-account">{{ view.accountLabel }}</div>
    <span>Valuation date: {{ view.committed.effectiveCurrentDate ?? 'Unavailable' }}</span>
    <span>Reporting currency: {{ view.committed.currency ?? 'Unavailable' }}</span>
    <slot name="controls" />
    <p v-if="view.isTransitioning" role="status">Updating to {{ view.pendingLabel }}…</p>
    <p v-if="view.errorMessage" role="alert">{{ view.errorMessage }}</p>
  </div>
</template>
```

The skeleton defines the display contract; move the existing account/date/currency input controls into its `controls` slot. Keep their existing backend choices and validation; disable them when `!view.isReady`. At the App boundary, convert settings edits into the complete R settings tuple and render errors from `transitionError`; do not pass partial settings directly to `changeContext` or mutate the compatibility app store a second time.

```ts
// frontend/src/components/workspace/contextIntent.ts
import type { ContextPatch, PortfolioContext } from '@/types/portfolioContext'
import type { ContextIntent } from './types'

export function toContextPatch(
  intent: ContextIntent, committed: Readonly<PortfolioContext>, isReady: boolean,
): ContextPatch {
  if (!isReady || !committed.effectiveCurrentDate || !committed.currency) {
    throw new Error('Portfolio context is not ready.')
  }
  if ('accountSelection' in intent) return { accountSelection: intent.accountSelection }
  return {
    effectiveCurrentDate: intent.effectiveCurrentDate ?? committed.effectiveCurrentDate,
    currency: intent.currency ?? committed.currency,
    digits: intent.digits ?? committed.digits,
  }
}
```

App's `requestContextChange(intent: ContextIntent): Promise<void>` awaits
`contextStore.changeContext(toContextPatch(intent, contextStore.committed, contextStore.isReady))`.
Add assertions that a currency-only intent retains committed date/digits, digits `0` is retained, an account intent has no settings fields, and pre-ready state sends no mutation. These checks protect the shared tuple contract rather than testing styling.

- [ ] Make desktop navigation labeled by default from Vuetify's `md` breakpoint (960px). An optional user collapse preference may retain the rail on desktop. Below 960px use a temporary drawer closed on selection and Escape; restore focus to `Open navigation`. Use a visible current-page heading and `aria-current="page"`. Keep `/dashboard`, `/summary`, `/open-positions`, `/closed-positions`, `/transactions`, `/database/*` and `/profile/*` unchanged. Clarify labels to `Overview` for Dashboard and `Performance` for Summary; group both existing position links under `Positions`, and display `Data` for Database. Preserve child route links and existing active-state matching.
- [ ] Integrate only after R's shell non-overlap fix. Keep R's intrinsic header measurement and use the new strip's actual measured height; do not add a fixed main padding or suppress page horizontal overflow to hide clipping.
- [ ] Run `npm --prefix ../frontend run test:unit -- tests/unit/workspace/WorkspaceContextStrip.spec.ts tests/unit/workspace/Navigation.spec.ts tests/unit/AppLayout.spec.js`, then `npm --prefix ../frontend run type-check`. Add a failed-save interaction assertion to R's test suite only through the R owner if its contract needs additional coverage.
- [ ] Produce desktop/mobile screenshots at D3, including a long broker/group name and failed change. Commit this integration separately from token propagation; reviewers must be able to assess whether displayed context still matches data.

### D3: Build and review the NAV-first desktop/mobile pilot

**Files**

- Modify: `frontend/src/views/DashboardPage.vue`, `frontend/src/components/dashboard/SummaryCard.vue`, `frontend/src/components/dashboard/SummaryOverTimeTable.vue`.
- Pilot integration only: `frontend/src/components/PositionsPageBase.vue` receives D1's scoped defaults/classes without rebuilding its toolbar/header implementation.
- Create: `frontend/src/components/dashboard/PortfolioMetrics.vue`, `frontend/src/components/dashboard/summaryMetrics.ts`, `frontend/tests/unit/workspace/DashboardComposition.spec.ts`.
- Coordinate: C's `frontend/src/features/charts/` pilot and chart-control/data-table contracts; do not change its adapters in this task.
- Create evidence: `docs/design/assets/frontend-workspace/pilot-desktop.png`, `pilot-mobile.png`, `pilot-mobile-nav.png`, `pilot-positions-desktop.png`, `pilot-positions-mobile.png`; document decisions in `docs/design/frontend-workspace.md`.

**Interfaces**

- `PortfolioMetrics` consumes `{ metrics: readonly MetricDisplay[]; contextLabel: string }`. It does not accept numeric primitives and does not calculate or reformat money. `SummaryCard` remains a compatibility adapter until its callers switch.
- `summaryMetrics.ts` consumes R6/R8's typed **direct summary dictionary** from `getDashboardSummary`: `Current NAV`, `Invested`, `Cash-out`, `total_return`, `irr`. It produces all five `MetricDisplay` entries in explicit order. The stale generated `metrics` envelope and audit fixture keys such as `total_nav`/`cash` are not the runtime contract.
- Dashboard consumes R's accepted widget results. Initially use the existing `NAVChart` through a renderer-neutral section/slot with its current props/events; no ECharts or financial-contract task is a prerequisite to the layout milestone. C3 supplies its own chart props/events at the later renderer integration. C owns chart-table/legend/tooltip/zoom functionality; D places the surrounding controls so they remain usable.

- [ ] Recompose the page in this exact reading order: visible committed context; dominant Total NAV mapped from `Current NAV`, with Invested, Cash out, Total return and IRR as the four existing secondary values; Value and return over time; Allocation; historical reconciliation. Keep the backend's signs, formatting and return horizons. Do not invent a Cash balance metric from `Cash-out`, and do not call lifetime IRR a YTD return. If the API does not provide an additional requested period metric, omit that additional metric rather than derive it from NAV or relabel lifetime data.
- [ ] Add this explicit display-only adapter against R8's actual typed return value. R8 validates all five required fields; malformed payloads remain errors rather than silently dropping a metric. Values already include server formatting, so the adapter does not append a second currency symbol, parse amounts or recalculate percentages. Reporting currency remains visible in the committed context.

```ts
// frontend/src/components/dashboard/summaryMetrics.ts
import type { getDashboardSummary } from '@/services/api'
import type { MetricDisplay } from '@/components/workspace/types'

type DashboardSummaryData = Awaited<ReturnType<typeof getDashboardSummary>>

export function summaryMetrics(summary: DashboardSummaryData): readonly MetricDisplay[] {
  return [
    { id: 'nav', label: 'Total NAV', value: summary['Current NAV'] },
    { id: 'invested', label: 'Invested', value: summary.Invested },
    { id: 'cash-out', label: 'Cash out', value: summary['Cash-out'] },
    { id: 'total-return', label: 'Total return', value: summary.total_return,
      explanation: 'Since inception' },
    { id: 'irr', label: 'IRR since inception', value: summary.irr },
  ]
}
```
- [ ] Replace equal-weight bold summary rows with a semantic definition list. Keep source order explicit rather than iterating arbitrary backend keys. Hide neither losses nor zeroes; show missing values as the established unavailable marker. The representative component can render the supplied display strings as follows:

```vue
<script setup lang="ts">
import type { MetricDisplay } from '@/components/workspace/types'
defineProps<{ metrics: readonly MetricDisplay[]; contextLabel: string }>()
</script>
<template>
  <section aria-label="Portfolio values">
    <p class="workspace-meta">{{ contextLabel }}</p>
    <dl class="portfolio-metrics">
      <div v-for="metric in metrics" :key="metric.id" :data-metric="metric.id">
        <dt>{{ metric.label }}</dt>
        <dd class="workspace-number">{{ metric.value }} <span>{{ metric.unitLabel }}</span></dd>
        <p v-if="metric.explanation" class="workspace-meta">{{ metric.explanation }}</p>
      </div>
    </dl>
  </section>
</template>
```

- [ ] Use one full-width trajectory region, with three allocation cards below it at desktop and stacked on mobile: Asset Type, Asset Class and Currency. Their required final presentation is solid pies with visible category/value/% inspection and Table access. This D3 geometry pilot may temporarily render incumbent bars; record that transitional state and repeat the captures when C4 supplies accepted pies. Historical reconciliation retains all rows and its table alternative; reduce `Update Account Performance` to an explicit secondary section action. On narrow screens, the existing frequency controls must fit a labeled select or wrapping layout, then use C3's compact control mode at integration. A scoped wrapper can make incumbent chart height responsive for this layout pilot; leave its data adapter untouched. C3 owns removal of dense canvas point labels and its full accessible data alternative.
- [ ] Add a regression demonstrating that missing/zero/negative display strings survive and financial values are not reinterpreted:

```ts
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import PortfolioMetrics from '@/components/dashboard/PortfolioMetrics.vue'
import { summaryMetrics } from '@/components/dashboard/summaryMetrics'

it('maps every actual summary key without losing cash-out, return or display values', () => {
  const metrics = summaryMetrics({
    'Current NAV': '$0.00', Invested: '$100.00', 'Cash-out': '($100.00)',
    total_return: '−2.40%', irr: 'N/A',
  })
  const wrapper = mount(PortfolioMetrics, {
    props: { contextLabel: 'Brokerage A · 2026-09-08 · USD', metrics },
  })
  expect(metrics.map(metric => metric.id)).toEqual(['nav', 'invested', 'cash-out', 'total-return', 'irr'])
  expect(wrapper.get('[data-metric="nav"] dd').text()).toBe('$0.00')
  expect(wrapper.get('[data-metric="invested"] dd').text()).toBe('$100.00')
  expect(wrapper.get('[data-metric="cash-out"] dd').text()).toBe('($100.00)')
  expect(wrapper.get('[data-metric="total-return"] dd').text()).toBe('−2.40%')
  expect(wrapper.get('[data-metric="irr"] dd').text()).toBe('N/A')
})
```

The fixture checks string preservation and key mapping only; its figures are not a calculated portfolio scenario. R's endpoint decoder tests establish the actual direct-dictionary contract separately.

- [ ] Run `npm --prefix ../frontend run test:unit -- tests/unit/workspace/DashboardComposition.spec.ts tests/unit/components/DashboardPage.retry.spec.js tests/unit/components/SummaryCard.spec.js`, then `npm --prefix ../frontend run type-check` and `npm --prefix ../frontend run build`. Preserve C's accessible table and R's failure → retry → recovered-widget tests.
- [ ] Start the local dev server for actual browser review using `npm --prefix ../frontend run dev -- --host 127.0.0.1 --port 5189`. Run it through an execution session that yields a session ID, record that ID, and stop it with Ctrl-C when finished. Use R/C's sanitized fixture harness, with every displayed endpoint contract complete; fixture errors are review failures to repair, not app findings to accept.
- [ ] Read the installed agent-browser skill, run `npx --no-install agent-browser --help`, then create a fresh session: `npx --no-install agent-browser --session design-pilot open http://127.0.0.1:5189`. At `1440 1000`, `1024 768`, `390 844` and `768 1024`, inspect the real rendered components and save screenshots. Commands use `set viewport`, `snapshot -i`, quoted refs such as `click '@e4'`, and `screenshot` with absolute paths. No image mockup can substitute for this milestone.
- [ ] Review both the populated Dashboard and one dense Open Positions table at desktop and mobile before accepting the pilot. The positions fixture includes long names, at least two currencies, zero/negative/missing values and enough columns to require horizontal scrolling; verify sticky identity, grouped headings and totals. Save both additional positions screenshots listed above. Do not substitute an empty table or a screenshot mockup.
- [ ] Accept the pilot only when the first card is below the header; account/date/currency are readable; no page-level horizontal clipping occurs; all chart controls remain visible or reachable; navigation opens/closes by keyboard; the trajectory dominates; existing allocation table access remains obvious; and 200% zoom does not hide actions. Inspect actual computed foreground/background contrast for normal text and focus, aiming for WCAG AA text contrast, rather than inferring accessibility from blue/white tokens. Record the incumbent NAV's missing equivalent table as an assigned C3 issue, not a passed accessibility gate; C3's accessible NAV table is mandatory before final release and its renderer replacement repeats these captures.
- [ ] Record the selected sizes, spacing, density, action placement and any corrected pilot issues in `docs/design/frontend-workspace.md`. Close `design-pilot`, stop the dev-server session, and commit the reviewed pilot. **Only after this milestone passes may D5 propagate defaults to other routes.**

### D4: Consolidate table controls, actions and dialog accessibility

**Files**

- Create: `frontend/src/components/workspace/WorkspaceActions.vue`, `WorkspaceTableToolbar.vue`, `WorkspaceEmptyState.vue`, `ConfirmActionDialog.vue`.
- Modify: `frontend/src/components/PositionsPageBase.vue`, `frontend/src/config/positionsHeaders.js`, `frontend/src/composables/useTableSettings.ts`, `frontend/src/views/{OpenPositionsPage.vue,ClosedPositionsPage.vue,TransactionsPage.vue}`, `frontend/src/components/transactions/TransactionRow.vue`, `frontend/src/components/dialogs/TransactionFormDialog.vue`, `frontend/src/components/dialogs/FXTransactionFormDialog.vue`.
- Create: `frontend/tests/unit/components/PositionsTableViews.spec.ts` for preset, grouping, column-label, sort-state and footer behavior; extend browser fixtures for horizontal/vertical scrolling, key-based pinning and actual header semantics.
- Test: `frontend/tests/unit/workspace/TableToolbar.spec.ts`, `frontend/tests/unit/workspace/ConfirmActionDialog.spec.ts`, `frontend/tests/unit/components/TransactionRow.actions.spec.ts`; retain positions, pagination and formatting regressions.

**Interfaces**

- `WorkspaceActions`: props `{ primary?: WorkspaceAction; secondary: readonly WorkspaceAction[]; overflow: readonly WorkspaceAction[] }`; emit `action(id: string)`.
- `WorkspaceTableToolbar`: props `{ query: TableQueryView; searchLabel: string; searchPlaceholder?: string; rowsPerPageOptions: readonly number[] }`; emit `update:query(Partial<Pick<TableQueryView, 'search' | 'page' | 'itemsPerPage'>>)`; slots `filters`, `actions`, `columns`. It is a layout/input component, not a data table or query controller.
- `WorkspaceEmptyState`: props `{ title: string; description: string; action?: WorkspaceAction }`; emit `action(id: string)`.
- `ConfirmActionDialog`: props `{ modelValue: boolean; subject: ConfirmationSubject; busy: boolean; error: string | null }`; emits `update:modelValue(boolean)`, `confirm()`. On success its parent closes it. On failure retain subject and error. Cancel never emits confirm.

- [ ] Move table filters into a wrapping CSS grid: primary search/filter area, optional column/action area, then pagination footer. Keep rows-per-page in one place. Wide financial columns remain in their own named horizontal scroll region; do not compress them into unreadable cards. Reuse the existing table and declarative header model where practical, preserving totals and backend-supported sort mappings.
- [ ] Implement the focused table recommendation as the D3/D4 pilot. Open Overview: Security (Type as secondary identity), Currency, Entry value, Current value, Portfolio share %, Total return amount, Total return %, IRR. Closed Overview: Security (Type as secondary identity), Currency, Entry value, Exit value, Total return amount, Total return %, IRR. These are presentation presets over existing keys; all 20 open and 16 closed fields remain in Full ledger/Columns. Keep amounts and percentages independently sortable columns rather than silently selecting a sort basis inside a composite cell.
- [ ] Add Entry & valuation / Entry & exit comparison presets with both sides visible together. Full ledger uses two header levels: Identity, Entry, Current/Exit and Performance. For open positions, move realized/unrealized G/L, price change, distributions, commissions and returns out of the broad Current group into Performance. Flatten redundant closed Amount/% labels into qualified Performance leaves. Reuse unchanged backend keys; closed positions do not acquire invented Entry/Exit price fields.
- [ ] Extend existing column metadata with stable group ID, short visible title, full chooser/accessible title, unit/description and identity/pinning status. Group labels are left-aligned quiet section bands; numeric leaves remain end-aligned. Apply subtle group-start boundaries to header, body and footer from the same filtered metadata. Generate spans only from visible leaves; remove empty groups. Two lines of wrapping text are not a third structural header tier.
- [ ] Qualify every Columns checkbox (Entry price, Current price, Realized G/L amount, Commission %) and keep the menu open for multiple choices with a clear Done action. Persist preset and visible keys per table, migrate/filter invalid keys and always retain a security identity. Pin by column key with measured offsets, never nth-child; Type is separately available in Full ledger. When hiding a sorted column retain a visible full-name sort summary and Clear sort action; never silently change server order. Coordinate this state with R5's per-query ownership.
- [ ] Generate proper caption, colgroup/group/leaf and row associations, unique header IDs where needed, and aria-sort for the actual active leaf; use fully qualified sort names in flat and grouped views. Verify the installed Vuetify DOM rather than assuming it supplies these attributes. Both header tiers stay together during vertical scroll below the app bar; identity stays visible during horizontal scroll. At narrow widths use the compact view plus contained horizontal scrolling, without automatically overwriting a user's saved Full ledger choice.
- [ ] Test all keys remain reachable across presets; labels distinguish repeated Date/Value/Price/Amount/%; column hiding never pins Currency by accident or removes Assets/Cash/TOTAL labels; footer cells remain under the correct leaf after reorder/hide; active hidden sort remains intelligible; returning to the route restores that table's choice. Test changed reporting currency updates all header units through committed context. Verify the server component/pipeline does not re-sort only a loaded page as a presentation side effect; coordinate any data-lifecycle repair with R5.
- [ ] Keep search/column labels visible and glossary triggers focusable. Use `WorkspaceActions` on Transactions: primary `Add transaction`, secondary `Import transactions`, overflow `Add FX transaction`, `Transfer asset`, `Record merger`. Every action remains reachable; no financial flow is removed. Resolve active action IDs in TransactionsPage against existing handlers.
- [ ] Convert row icons to Vuetify buttons with accessible names that include row identity; use `Edit transaction on 2026-09-08` when no unique description is available, and include account/security text where available. Keep signed amounts as text and preserve transaction event payloads exactly.

```vue
<v-btn icon="mdi-pencil" variant="text" class="workspace-touch-action"
  :aria-label="`Edit ${transaction.date} transaction`"
  @click="$emit('edit', transaction)" />
<v-btn icon="mdi-delete" variant="text" class="workspace-touch-action"
  :aria-label="`Delete ${transaction.date} transaction`"
  @click="$emit('delete', transaction)" />
```

- [ ] Replace generic `OK` deletion confirmation with the exact selected transaction: date, broker/account, security or cash/FX description, type, and displayed amount/quantity with currency. When current list data lacks these fields, fetch through the existing transaction-detail API and show loading before enabling deletion. Keep the selected transaction ID fixed until the dialog closes; filter or account changes cannot silently retarget it. Use `Delete transaction` and `Cancel`; never create an undo promise when the API has no undo endpoint.
- [ ] Verify real dialog behavior with a real Vuetify test plugin, not the generic `v-dialog` div stub. Put initial focus on Cancel for destructive actions; Escape cancels while idle, busy submission does not submit twice, and close returns focus to the invoking row/menu control. Give forms visible section labels and inline field errors; preserve entered data on rejected saves. Use existing Yup rules and server validation, including bond `%` price hints.

```ts
import { mount, flushPromises } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { expect, it } from 'vitest'
import ConfirmActionDialog from '@/components/workspace/ConfirmActionDialog.vue'

it('keeps the identified transaction visible after a failed delete', async () => {
  const wrapper = mount(ConfirmActionDialog, {
    attachTo: document.body,
    props: { modelValue: true, busy: false, error: null, subject: {
      title: 'Delete transaction', confirmLabel: 'Delete transaction',
      details: [{ label: 'Account', value: 'Brokerage A' },
        { label: 'Date', value: '2026-09-08' },
        { label: 'Amount', value: '100.00 USD' }],
    } },
    global: { plugins: [createVuetify({ components, directives })] },
  })
  await wrapper.setProps({ error: 'The transaction could not be deleted. Try again.' })
  await flushPromises()
  const dialog = document.querySelector('[role="dialog"]')!
  expect(dialog.textContent).toContain('Brokerage A')
  expect(dialog.textContent).toContain('100.00 USD')
  expect(dialog.textContent).toContain('Try again')
  expect(wrapper.emitted('confirm')).toBeUndefined()
  wrapper.unmount()
})
```

- [ ] Run `npm --prefix ../frontend run test:unit -- tests/unit/workspace/TableToolbar.spec.ts tests/unit/workspace/ConfirmActionDialog.spec.ts tests/unit/components/TransactionRow.actions.spec.ts tests/unit/components/PositionsPageBase.spec.js tests/unit/components/PositionsTableViews.spec.ts tests/unit/config/positionsHeaders.spec.js`, then `npm --prefix ../frontend run type-check`. Verify keyboard/focus in the real browser during D5; jsdom alone cannot establish rendered geometry or complete focus behavior.
- [ ] Commit shared patterns and their first consumers as one review unit. R retains query/data logic; request-generation changes must not appear accidentally in this diff.

### D5: Roll the reviewed system across every existing route family

**Files**

- Modify: `frontend/src/views/SummaryPage.vue`, `OpenPositionsPage.vue`, `ClosedPositionsPage.vue`, `TransactionsPage.vue`, `DatabasePage.vue`, `LoginPage.vue`, `RegisterPage.vue`.
- Modify: `frontend/src/views/database/{BrokersPage.vue,AccountsPage.vue,PricesPage.vue,SecuritiesPage.vue,FXPage.vue}` and `frontend/src/views/profile/{ProfileLayout.vue,ProfilePage.vue,ProfileEdit.vue,ProfileSettings.vue}`.
- Modify: `frontend/src/components/{LoginForm.vue,RegisterForm.vue,AccountGroupManager.vue}` and existing `dialogs/{AccountFormDialog.vue,BrokerFormDialog.vue,SecurityFormDialog.vue,PriceFormDialog.vue,FXDialog.vue,PriceImportDialog.vue,FXImportDialog.vue,AssetTransferDialog.vue,MergerDialog.vue,UpdateAccountPerformanceDialog.vue}`.
- Modify: `frontend/src/main.js` only now to apply reviewed defaults app-wide, retaining targeted density overrides where functional forms require them.
- Test: `frontend/tests/unit/workspace/RoutePatterns.spec.ts`; retain existing page, authentication and transaction-description tests.

**Interfaces**

- Each route composes D1/D4 components and existing API/controller events. No universal schema-driven page builder is introduced.
- Preserve each existing dialog's `modelValue` and completion event names so callers and invalidation remain compatible. `ConfirmActionDialog` supplies the shared destructive UI where current routes have hand-written confirmation markup.

- [ ] Migrate route families in the order below. Complete the table's acceptance checks for each row before proceeding; this is the definition of all-pages coverage, not a dashboard-only restyle.

| Route family | Required design delta | Behavior preserved and reviewed |
|---|---|---|
| `/summary` | Clear Performance heading; reactive units; single-period account table for compact review plus explicit multi-period comparison/full-history view; keep metrics-as-rows option as a later extension | Public/restricted groups, every period, subtotals, BoP/EoP/TSR/Fee per AuM meanings and year filter; no hidden removal of history |
| `/open-positions`, `/closed-positions` | Shared toolbar; compact Overview; Entry & valuation/exit comparison; quiet grouped Full ledger; key-based sticky identity; unambiguous Columns labels | All 20/16 leaves, cash/total footers, sorting, paging, quantity/short/missing values and financial meanings |
| `/transactions` | Action hierarchy and exact confirmation from D4; search/date filters fit mobile; accessible row actions | FX, transfer, merger and import entrypoints; per-currency flow/balance columns; server event payloads |
| `/database` + `/database/brokers` | Named Data navigation, meaningful landing links; concise broker inventory and primary create action | Existing child navigation, broker details/edit/delete, connected-broker behavior |
| `/database/accounts` | Shared table/search/action patterns and descriptive account form sections | Broker association, currencies, totals, account groups, account deletion constraints |
| `/database/securities` | Search/identity-first ledger and clear metadata form groups | Security types/identifiers, bond/crypto fields, existing detail links and sharing/mapping behavior |
| `/database/prices` | Clear security/date context, price unit labels and import action | Existing price source/date filters, bond percentage-of-par values, all decimal display precision |
| `/database/fx` | Calm pivot/table layout, pair/date labels and scoped scroll region | Existing FX pivot mapping, source currencies, orientation and server values |
| `/database/securities/:id` | Apply page/context shell now; detailed section extraction in D7 | Current ID route, account scope and price/position/activity access; C owns migrated charts |
| `/profile`, `/profile/edit`, `/profile/settings` | Consistent page/section hierarchy; forms grouped into identity, display defaults, account defaults and broker connections | Existing profile/account settings, saved choices, group manager; context-affecting saves through R |
| `/login`, `/register` | Restrained narrow form surface, one heading/primary submit, visible error summary and field labels | Existing auth flow, password autocomplete semantics, validation, redirects, and session handling |
| `/debug-auth` (development only) | Retain development-only availability; readable with shared typography | Never expose the route or debug controls in production |

- [ ] Complete remaining column-visibility persistence only if R/earlier table work has not already done so. Persist visible leaf keys per table/page through the existing table-settings owner; filter removed keys against current headers, retain the analyst defaults on invalid/empty stored data, and keep all original columns selectable. Do not persist a combined global column list across unrelated tables.
- [ ] Replace literal colors, inconsistent blue variants, uppercase group-label noise and gratuitous percentage italics in migrated views with tokens and standard classes. Right-align money/quantity/percentage cells without altering their strings. Use sentence-case action labels. Keep form layouts one column on mobile and grouped two columns only when labels remain readable.
- [ ] Add route-level contract tests for the actual common controls, avoiding blanket stubs that erase labels or events. This example confirms an action's routing intent while keeping API work outside the component:

```ts
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import WorkspaceActions from '@/components/workspace/WorkspaceActions.vue'

it('emits the original import action without executing an API request', async () => {
  const wrapper = mount(WorkspaceActions, {
    props: { primary: { id: 'add', label: 'Add transaction' },
      secondary: [{ id: 'import', label: 'Import transactions' }], overflow: [] },
    global: { stubs: { VBtn: {
      props: ['disabled'], emits: ['click'],
      template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    } } },
  })
  const importButton = wrapper.findAll('button').find(b => b.text() === 'Import transactions')!
  await importButton.trigger('click')
  expect(wrapper.emitted('action')).toEqual([['import']])
})
```

- [ ] Run `npm --prefix ../frontend run test:unit -- tests/unit/workspace/RoutePatterns.spec.ts tests/unit/components/PositionsPages.spec.js tests/unit/components/TransactionDescription.crypto.spec.js tests/unit/utils/formatUtils.spec.js`, then `npm --prefix ../frontend run lint`, `npm --prefix ../frontend run type-check`, and `npm --prefix ../frontend run build`. Keep a baseline failure list and require changed-route failures to be fixed before continuing.
- [ ] Perform actual desktop/mobile review of one populated, empty, filtered-empty and error state for each route family. Follow real links and confirm no route names or URLs changed; tab through primary actions, open/close one representative form, inspect 200% zoom. Do not mark a family reviewed from screenshots of a different page.
- [ ] Record route results in `docs/design/frontend-route-review.md` as each family passes. Commit the rollout in family-sized changes using the same shared contracts; broker-connection internals and security-detail internals remain D7's separate review unit.

### D6: Extract the transaction import workflow into typed, testable units

**Files**

- Modify: `frontend/src/components/dialogs/TransactionImportDialog.vue`, `frontend/src/composables/useImportState.ts`.
- Create: `frontend/src/features/imports/{types.ts,legacyImportProtocol.ts,useTransactionImport.ts,ImportMethodStep.vue,ImportSourceStep.vue,ImportReviewStep.vue,ImportResult.vue}`.
- Retain/integrate: `frontend/src/components/dialogs/{SecurityMappingDialog.vue,SecurityFormDialog.vue,AccountMatchingDialog.vue,ProgressDialog.vue}` and `frontend/src/components/TransactionImportProgress.vue`.
- Test: `frontend/tests/unit/features/imports/protocol.spec.ts`, `workflow.spec.ts`; retain `frontend/tests/unit/components/TransactionImportDialog.spec.js` and `TransactionImportDialog.warnings.spec.js`.

**Interfaces**

- Preserve entrypoint props `{ modelValue: boolean }` and emits `update:modelValue`, `import-completed`.
- Evolve the existing `useImportState` into the sole discriminated state owner; `useTransactionImport` composes it and owns transport/orchestration, not a second state ref. Keep the legacy `isIdle`/`isAnalyzing`/`isImporting`/`isMapping`/`isComplete`/`isError` names as computed compatibility projections until their callers are migrated. Child steps own only field editing and emit typed intents.
- Keep `useWebSocket('/ws/transactions/')` and `analyzeFile` as current transport mechanisms. Transport envelopes, confirmation flags, account/security mapping payloads and completion semantics remain byte-for-byte equivalent for the same input. No new backend protocol or retry/restart behavior is introduced.

- [ ] Create characterization fixtures from the current dialog handlers before moving them: file analyze/account choice/start; API broker/date start; account matching; security mapping/create/skip; per-transaction confirm/skip; stop request/acknowledgment; completion with warnings; disconnected/error state. Fixtures must be synthetic, and counts/amounts must not assert invented financial outcomes.
- [ ] Define the typed state and exact existing start-command boundary. Existing incoming handlers remain behind a validated decoder; unknown input creates a recoverable protocol error without fabricating success.

```ts
// frontend/src/features/imports/types.ts
export type ImportMethod = 'file' | 'api'
export type ImportDecision = 'accounts' | 'security' | 'transaction'
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
export interface ImportWarning { endpoint: string; error: string }
export interface ImportResultData {
  totalTransactions: number
  importedTransactions: number
  skippedTransactions: number
  duplicateTransactions: number
  importErrors: number
  warnings: readonly ImportWarning[]
}
export type TransactionImportState =
  | { kind: 'choose-method' }
  | { kind: 'configure'; method: ImportMethod }
  | { kind: 'analyzing'; method: 'file' }
  | { kind: 'review'; method: ImportMethod; accountLabel: string }
  | { kind: 'running'; method: ImportMethod; current: number; total: number; message: string }
  | { kind: 'decision'; method: ImportMethod; decision: ImportDecision; payload: unknown }
  | { kind: 'stopping'; method: ImportMethod }
  | { kind: 'complete'; result: ImportResultData }
  | { kind: 'error'; message: string; canReturnToConfiguration: boolean }

export interface FileStartInput {
  fileId: string | number
  accountId: number
  confirmEvery: boolean
  isGalaxy: boolean
  galaxyType: string
  currency: string | null
}
export interface ApiStartInput {
  brokerId: number
  confirmEvery: boolean
  dateFrom: string | null
}
export interface AccountMatchPair {
  tinkoff_account_id: string | number
  db_account_id: string | number
  [key: string]: JsonValue
}
export type ImportCommand =
  | { type: 'start_file_import'; file_id: string | number; account_id: number;
      confirm_every: boolean; is_galaxy: boolean; galaxy_type: string | null; currency: string | null }
  | { type: 'start_api_import'; data: { broker_id: number;
      confirm_every_transaction: boolean; date_from: string | null } }
  | { type: 'stop_import' }
  | { type: 'security_mapped'; action: 'map'; security_id: number }
  | { type: 'security_mapped'; action: 'skip'; security_id: null }
  | { type: 'transaction_confirmed'; confirmed: boolean }
  | { type: 'security_confirmation'; security_id: number; security_created?: true;
      security_data?: { name: string; id: number } }
  | { type: 'security_confirmation'; security_id: null; skip_transaction: true }
  | { type: 'select_account'; data: { account_id: number; confirm_every_transaction: boolean;
      date_from?: string | null; date_to?: string | null } }
  | { type: 'accounts_matched' | 'use_existing_matches'; data: { pairs: readonly AccountMatchPair[] } }
  | { type: 'create_account'; data: { tinkoff_account: JsonValue; name: string; comment: string } }
export interface ImportTransport {
  connect(): Promise<boolean>
  send(command: ImportCommand): boolean
  disconnect(): void
}
```

`ImportCommand` covers the existing start/stop/mapping/confirmation/account commands. Characterization fixtures must verify the optional full objects retained in existing account matches and the distinction between API-start dates and account-selection dates; do not widen `send` to `any` or discard provider-specific fields. The API start currently transmits `date_from` only: preserve that behavior here and track any requested `date_to` change separately, since the visible field alone is not authorization to change backend import semantics. `ImportResultData` preserves all five existing counters and structured endpoint/error warnings; the compatibility entrypoint still emits the original result payload to its parent.

- [ ] Replace the current state implementation in place and make all UI booleans computed views of it. The orchestration methods below call `transition`; no second `ref<TransactionImportState>` is created in `useTransactionImport`.

```ts
// frontend/src/composables/useImportState.ts
import { computed, readonly, shallowRef } from 'vue'
import type { TransactionImportState } from '@/features/imports/types'

export function useImportState() {
  const state = shallowRef<TransactionImportState>({ kind: 'choose-method' })
  const transition = (next: TransactionImportState) => { state.value = next }
  return {
    state: readonly(state), transition,
    isIdle: computed(() => ['choose-method', 'configure', 'review'].includes(state.value.kind)),
    isAnalyzing: computed(() => state.value.kind === 'analyzing'),
    isImporting: computed(() => ['running', 'stopping'].includes(state.value.kind)),
    isMapping: computed(() => state.value.kind === 'decision'),
    isComplete: computed(() => state.value.kind === 'complete'),
    isError: computed(() => state.value.kind === 'error'),
  }
}
```

- [ ] Implement the protocol seam first and assert the existing asymmetric confirmation flag names. The decimal/string payload for transaction decisions must pass through unchanged; progress counters may use ordinary integers because they are UI counts, not money.

```ts
// frontend/src/features/imports/legacyImportProtocol.ts
import type { ApiStartInput, FileStartInput, ImportCommand } from './types'

export function fileStartCommand(input: FileStartInput): ImportCommand {
  return { type: 'start_file_import', file_id: input.fileId, account_id: input.accountId,
    confirm_every: input.confirmEvery, is_galaxy: input.isGalaxy,
    galaxy_type: input.isGalaxy ? input.galaxyType : null,
    currency: input.isGalaxy ? input.currency : null }
}
export function apiStartCommand(input: ApiStartInput): ImportCommand {
  return { type: 'start_api_import', data: { broker_id: input.brokerId,
    confirm_every_transaction: input.confirmEvery, date_from: input.dateFrom } }
}
```

```ts
import { expect, it } from 'vitest'
import { apiStartCommand, fileStartCommand } from '@/features/imports/legacyImportProtocol'

it('preserves the existing wire names for API and file confirmation', () => {
  expect(apiStartCommand({ brokerId: 7, confirmEvery: true, dateFrom: null })).toEqual({
    type: 'start_api_import', data: { broker_id: 7, confirm_every_transaction: true, date_from: null },
  })
  expect(fileStartCommand({ fileId: 'fixture-1', accountId: 3, confirmEvery: false,
    isGalaxy: false, galaxyType: 'transactions', currency: 'USD' })).toEqual({
    type: 'start_file_import', file_id: 'fixture-1', account_id: 3,
    confirm_every: false, is_galaxy: false, galaxy_type: null, currency: null,
  })
})
```

- [ ] Move orchestration into `useTransactionImport`: exposed methods `selectMethod(method: ImportMethod): void`, `back(): void`, `analyze(file: File): Promise<void>`, `startFile(input: FileStartInput): Promise<void>`, `startApi(input: ApiStartInput): Promise<void>`, `requestStop(): void`, `receive(raw: unknown): void`, `reset(): void`; expose the readonly state returned by `useImportState` and editable configuration separately. Implement `requestStop()` so it sends once, enters `stopping`, and waits for the existing stopped acknowledgment rather than declaring cancellation immediately. Cleanup removes the message watcher and disconnects only the connection owned by this workflow. Reuse the existing `useWebSocket` through an adapter that normalizes `connect()`'s current resolved value with `Boolean(await connect())`; do not create another socket/reconnect implementation. Reuse R's request safety for analyzer/lookups without altering import command order.
- [ ] Replace modal booleans with state-derived visibility and typed step events. Method selection is two keyboard-operable choices; configuration shows the relevant inputs only; review repeats selected account/source before start; results retain total/imported/skipped/duplicate/error counts and structured endpoint/error warnings. Existing account/security/transaction decision dialogs remain first-class states and preserve the current selection after a rejected confirmation. Keep one polite progress announcement region instead of repeated modal announcements. Delete the old independent state/boolean authority after its last caller is migrated; compatibility getters are projections, not synchronized duplicate storage.
- [ ] Extend workflow tests with: duplicate start click sends once; failed connect does not enter running; unknown messages cannot complete a run; all warnings survive completion; stop is pending until acknowledgment; close/reopen does not retain the previous file or token; mapping preserves the supplied transaction display data. Keep existing public dialog event tests and remove obsolete internal-boolean assertions only when equivalent external behavior is covered.
- [ ] Run `npm --prefix ../frontend run test:unit -- tests/unit/features/imports tests/unit/components/TransactionImportDialog.spec.js tests/unit/components/TransactionImportDialog.warnings.spec.js`, then `npm --prefix ../frontend run type-check` and `npm --prefix ../frontend run build`. Review a synthetic file and API path in the browser, including decision, stop and warning-result states, before committing the extraction.

### D7: Decompose broker connections and security detail without changing their capabilities

**Files**

- Modify: `frontend/src/components/BrokerTokenManager.vue`, `frontend/src/views/database/SecurityDetailPage.vue`.
- Create: `frontend/src/features/brokers/{types.ts,useBrokerConnections.ts,BrokerConnectionList.vue,BrokerConnectionForm.vue}`.
- Create: `frontend/src/features/securities/{types.ts,useSecurityDetail.ts,SecurityOverview.vue,SecurityMetadata.vue,SecurityActivity.vue}`.
- Test: `frontend/tests/unit/features/brokers/connections.spec.ts`, `frontend/tests/unit/features/securities/detail.spec.ts`; retain `frontend/tests/unit/components/BrokerTokenManager.spec.js` and `SecurityDetailPage.crypto.spec.js`.

**Interfaces**

- `BrokerTokenManager` keeps emits `error`, `success`, `info`. `useBrokerConnections` owns lookup/list/API state; `BrokerConnectionList` consumes safe display models and emits `(provider, tokenId)` for test/revoke/delete. `BrokerConnectionForm` owns unsaved secret input only for its open lifetime and emits a provider-specific draft directly to the current API adapter; no credential is stored in Pinia, localStorage, fixtures, logs or display models.
- `useSecurityDetail` accepts reactive `securityId: number`, existing account/period inputs and R context revision. It consumes current `getSecurityDetail`, `getSecurityPriceHistory`, `getSecurityPositionHistory`, `getSecurityTransactions` signatures and returns accepted response resources through R's latest-request lifecycle. C owns chart series/formatting; section components receive their content through named `price-chart` and `position-chart` slots.

- [ ] Extract the broker list/form/API responsibilities in separate files while preserving Tinkoff, IB, Bybit and OKX field requirements and behavior. Keep test, revoke and delete as distinct commands; a provider without a supported test operation must not gain a misleading test button. Display connection status as both text and icon, with per-row busy/error state rather than a full-page modal.

```ts
// frontend/src/features/brokers/types.ts
export type BrokerProvider = 'tinkoff' | 'ib' | 'bybit' | 'okx'
export interface BrokerConnectionDisplay {
  provider: BrokerProvider
  tokenId: number
  label: string
  statusLabel: string
  createdAtLabel: string
  canTest: boolean
  canRevoke: boolean
  busy: boolean
}
export interface BrokerConnectionKey { provider: BrokerProvider; tokenId: number }
```

- [ ] Verify credential forms keep existing API-specific draft shapes, reset on success/cancel/unmount and show field errors without echoing secrets into alerts. Confirmation names the broker/connection and says `Delete connection` or the existing precise revocation action; it must not imply deleting portfolio transactions. Broker token displays never receive secret fields.
- [ ] Extract security identity/metadata/activity while preserving server-backed bond and crypto-specific sections, all units, historical price/position views and account scope. Do not put API calls in `SecurityOverview`, `SecurityMetadata` or `SecurityActivity`. Define response types from the current API/schema plus the existing fixtures; render unknown/missing metadata explicitly rather than dropping an entire section.

```ts
// frontend/src/features/securities/types.ts
export interface DetailField { label: string; value: string; explanation?: string }
export interface SecurityOverviewView {
  securityId: number
  name: string
  identifier: string
  instrumentType: string
  currency: string
  fields: readonly DetailField[]
}
```

```vue
<!-- SecurityOverview.vue keeps rendering and calculations separate. -->
<script setup lang="ts">
import type { SecurityOverviewView } from './types'
defineProps<{ view: SecurityOverviewView }>()
</script>
<template>
  <section aria-label="Security overview">
    <h2>{{ view.name }}</h2>
    <p>{{ view.identifier }} · {{ view.instrumentType }} · {{ view.currency }}</p>
    <dl><div v-for="field in view.fields" :key="field.label">
      <dt>{{ field.label }}</dt><dd>{{ field.value }}</dd>
    </div></dl>
    <slot name="price-chart" /><slot name="position-chart" />
  </section>
</template>
```

- [ ] Add behavioral tests for provider action identity and security-value preservation. Use this security fixture alongside the existing crypto/bond regressions:

```ts
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import SecurityOverview from '@/features/securities/SecurityOverview.vue'

it('keeps bond percentage prices and missing metadata as supplied', () => {
  const wrapper = mount(SecurityOverview, { props: { view: {
    securityId: 9, name: 'Example Bond', identifier: 'TEST-9', instrumentType: 'Bond', currency: 'USD',
    fields: [{ label: 'Price (% of nominal)', value: '99.125000%' },
      { label: 'Maturity', value: '–' }],
  } } })
  expect(wrapper.text()).toContain('99.125000%')
  expect(wrapper.text()).toContain('Maturity')
  expect(wrapper.text()).toContain('–')
})
```

- [ ] Run `npm --prefix ../frontend run test:unit -- tests/unit/features/brokers tests/unit/features/securities tests/unit/components/BrokerTokenManager.spec.js tests/unit/components/SecurityDetailPage.crypto.spec.js`, then `npm --prefix ../frontend run type-check`. Review one broker create/error/cancel path with fake inputs and one populated bond/crypto security page at desktop/mobile sizes; do not send fake credentials to a live broker service.
- [ ] Commit broker extraction and security extraction separately. Preserve compatibility entrypoints and remove old duplicate handler bodies after their extraction is tested; coordinate SecurityDetail integration with C's chart migration to avoid parallel chart implementations.

### D8: Close all-page visual and behavior QA and document the implemented system

**Files**

- Create/update: `docs/design/frontend-workspace.md`, `docs/design/frontend-route-review.md`, `docs/design/assets/frontend-workspace/`.
- Update: `.memory-bank/Tech details/frontend.md` and `.memory-bank/index.md` only to index implemented repository documentation; do not edit personal Codex memories.
- Update tests only for actual defects discovered during this review, in the owning D/R/C workstream; do not add snapshots that merely repeat component source.

**Interfaces**

- D hands R/C stable component contracts and the route review record. Final release readiness requires all three workstreams' tests and numeric/API contracts, not just screenshot approval.

- [ ] Write `docs/design/frontend-workspace.md` with the implemented values and ownership. Include this explicit policy text, updating only concrete implementation paths if agreed by the other workstream owners:

```markdown
## Financial workspace conventions

The visible context identifies the committed account/group, valuation date and reporting currency.
Pending context changes are announced separately. Financial display values come from accepted server
responses and retain their units, precision, missing-value markers and sign semantics.

Use a page heading, compact context strip, one primary action and named analytical sections.
Tables retain grouped headers, numeric end alignment, row identity while scrolling and access to
the complete set of columns. Allocation and timeline charts provide equivalent data tables.

R owns committed context, request acceptance and invalidation. D owns workspace controls and layouts.
C owns chart adapters, renderers and chart accessibility. Child presentational components do not fetch.
```

- [ ] Populate `docs/design/frontend-route-review.md` with columns `Route`, `Fixture/account`, `Viewport`, `State`, `Keyboard/focus`, `Context/data match`, `Screenshot`, `Result`, `Remaining issue`. Cover every D5 row plus import mapping/stop/warnings, broker form failure, security bond/crypto views and authentication forms. Record failed cases explicitly; no row can pass on source inspection alone.
- [ ] Use fresh `agent-browser` sessions to review actual rendered pages at 1440×1000, 1024×768, 390×844 and 768×1024, plus 200% browser zoom. Check header rectangles, complete account names, accessible control names, keyboard traversal, dialog focus return, defined table overflow, empty/error recovery and C chart/table access. Review on light theme; future dark readiness is semantic-token inspection, not an unrequested dark-mode release gate.
- [ ] Capture clean screenshots with realistic synthetic long names, multiple currencies, signed values, missing prices and at least one dense populated table. Label them synthetic. Compare the result with the accepted audit images and D3 pilot, not with an empty-state screenshot that conceals layout problems.
- [ ] Run the complete required checks once after the integrated changes stabilize:

```powershell
npm --prefix ../frontend run test:unit
npm --prefix ../frontend run test:browser
npm --prefix ../frontend run type-check
npm --prefix ../frontend run type-check:reliability
npm --prefix ../frontend run lint
npm --prefix ../frontend run build
uv run python -m pytest
```

Expected: all checks pass. Record command exit status and failing tests precisely. The backend suite is required by repository policy even when D's diff is presentational; it must not be silently replaced by frontend tests. Do not keep rerunning healthy checks unless a new change/failure warrants it.

- [ ] Review the final diff for route/API changes, new arithmetic, financial formatter drift, backend/protected files, secret inputs in persisted state, unscoped style overrides and duplicate state owners. Return any such issue to the relevant workstream before declaring D complete.
- [ ] Close all audit browser sessions and stop every dev-server session started for visual QA. Publish the final route evidence and concise implementation notes in the PR. D is complete only when all route families pass and the visual hierarchy matches the pilot; remaining future ideas go into a follow-up list rather than being hidden as completed work.

## Completion checklist for this plan

- [x] D1 tokens/defaults preserve the palette/system font and existing numeric formatting.
- [x] D2 displays R's committed context and keeps labels/navigation usable at narrow widths.
- [ ] D3 desktop/mobile rendered pilot is reviewed before global propagation.
- [ ] D4 shared table/action/dialog patterns preserve financial table utility and improve keyboard operation.
- [ ] D5 covers every route family, including profile/auth and all database pages.
- [ ] D6 preserves import commands, mapping/confirmation/stop semantics and warning results through typed extraction.
- [ ] D7 preserves all broker-provider and bond/crypto security-detail capabilities through focused components.
- [ ] D8 records actual route-level visual evidence and complete required checks, with R/C ownership respected.

## Plan self-review

The accepted audit's design/system/mobile/context findings map to D1–D5; long import and broker/security components map to D6–D7; route-wide verification/documentation maps to D8. The August table requirements are preserved as existing behavior, with only their remaining persistence/alignment/accessibility delta included. R remains responsible for state correctness and the initial overlap repair, C for all chart rendering/adapters and equivalent data access, and the separate financial workstream for any server numeric fixes. No whole-route renaming, new metrics, dark-mode release, custom shortcut system or CSV feature is required by this plan.
