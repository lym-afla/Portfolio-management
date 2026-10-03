// Isolated synthetic harness for the C3 NAV pilot (dev/acceptance only).
// Mounts the real NavChartPanel with explicit fixtures and scenario
// controls; no production router or app shell is imported. The pilot
// renderer requires VITE_NAV_ECHARTS_ENABLED=true at build/dev time.
import { createApp, h, ref } from 'vue'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as vuetifyComponents from 'vuetify/components'
import * as vuetifyDirectives from 'vuetify/directives'
import NavChartPanel from '../../NavChartPanel.vue'
import { parseNavEnvelope } from '../../parseChartEnvelope'
import type { NavResult } from '../../contracts'
import { navEmptyWireFixture, navWireFixture, type FixtureFrequency, type FixtureMode } from '../navFixtures'

const vuetify = createVuetify({ components: vuetifyComponents, directives: vuetifyDirectives })

const result = ref<NavResult | null>(null)
const loading = ref(false)
const error = ref<string | undefined>(undefined)
const scenarioName = ref('v2 (complete/partial/signed synthetic)')

const modes: FixtureMode[] = [
  'none', 'account', 'asset_type', 'asset_class', 'currency',
  'value_contributions', 'value_contributions_cumulative',
]
const frequencies: FixtureFrequency[] = ['D', 'W', 'M', 'Q', 'Y']
const mode = ref<FixtureMode>('asset_type')
const frequency = ref<FixtureFrequency>('M')

function applyV2(): void {
  const parsed = parseNavEnvelope(navWireFixture(mode.value, frequency.value))
  if (parsed.capability !== 'v2') throw new Error('harness fixture must parse as v2')
  result.value = parsed
  error.value = undefined
  scenarioName.value = `v2 ${mode.value}/${frequency.value}`
}

function applyLegacyOnly(): void {
  result.value = {
    capability: 'legacy_only',
    legacy: {
      labels: ['Jan-26', 'Feb-26'],
      currency: 'USDk',
      datasets: [
        { label: 'NAV', type: 'bar', yAxisID: 'y', data: [100, 110] },
        { label: 'IRR (RHS)', type: 'line', yAxisID: 'y1', data: [0.12, 0.13] },
      ],
    },
  }
  error.value = undefined
  scenarioName.value = 'legacy_only'
}

function applyEmpty(): void {
  const parsed = parseNavEnvelope(navEmptyWireFixture())
  if (parsed.capability !== 'v2') throw new Error('harness fixture must parse as v2')
  result.value = parsed
  error.value = undefined
  scenarioName.value = 'v2 empty'
}

function applyInvalidContract(): void {
  result.value = null
  error.value = 'Invalid chartV2 document: Unsupported chart contract version: 3'
  scenarioName.value = 'invalid v2 contract (error state)'
}

applyV2()

const initialParams = {
  frequency: 'Q',
  breakdown: 'none',
  dateRange: 'ytd',
  dateFrom: '2026-01-01',
  dateTo: '2026-09-08',
}

const harness = createApp({
  setup() {
    return () =>
      h('main', { class: 'harness' }, [
        h('h1', 'C3 NAV pilot render harness (synthetic data only)'),
        h('p', { class: 'harness__scenario' }, `Scenario: ${scenarioName.value}`),
        h('div', { class: 'harness__controls' }, [
          h('label', [
            'Mode ',
            h('select', {
              value: mode.value,
              onChange: (event: Event) => {
                mode.value = (event.target as HTMLSelectElement).value as FixtureMode
                applyV2()
              },
            }, modes.map((entry) => h('option', { value: entry, selected: entry === mode.value }, entry))),
          ]),
          h('label', [
            'Frequency ',
            h('select', {
              value: frequency.value,
              onChange: (event: Event) => {
                frequency.value = (event.target as HTMLSelectElement).value as FixtureFrequency
                applyV2()
              },
            }, frequencies.map((entry) => h('option', { value: entry, selected: entry === frequency.value }, entry))),
          ]),
          h('button', { type: 'button', onClick: applyV2 }, 'Reload v2'),
          h('button', { type: 'button', onClick: applyLegacyOnly }, 'Legacy only'),
          h('button', { type: 'button', onClick: applyEmpty }, 'Empty v2'),
          h('button', { type: 'button', onClick: applyInvalidContract }, 'Invalid contract'),
          h('button', {
            type: 'button',
            onClick: () => {
              loading.value = !loading.value
            },
          }, loading.value ? 'Stop loading' : 'Simulate loading'),
        ]),
        h('div', { class: 'harness__panel' }, [
          h(NavChartPanel, {
            result: result.value as NavResult | null,
            loading: loading.value,
            error: error.value,
            initialParams,
            effectiveCurrentDate: '2026-09-08',
            'onUpdate-params': () => undefined,
            onRetry: () => applyV2(),
          }),
        ]),
      ])
  },
})

harness.use(createPinia())
harness.use(vuetify)

// Cold frontend render timing for the pilot composition (no API involved):
// script evaluation start to the first painted pilot canvas frame.
declare global {
  interface Window {
    __harnessTiming?: { scriptStart: number; chartReadyAt: number | null }
  }
}
const timing = (window.__harnessTiming = { scriptStart: performance.now(), chartReadyAt: null as number | null })
const recordChartReady = () => {
  if (timing.chartReadyAt !== null) return
  if (document.querySelector('[data-testid="nav-echarts-pilot"] canvas, [data-testid="nav-chart"] canvas')) {
    requestAnimationFrame(() => {
      if (timing.chartReadyAt === null) timing.chartReadyAt = performance.now()
    })
  }
}
const chartObserver = new MutationObserver(recordChartReady)
chartObserver.observe(document.documentElement, { childList: true, subtree: true })
recordChartReady()

harness.mount('#harness')
