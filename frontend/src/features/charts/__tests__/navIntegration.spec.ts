// C3 Task 4: dashboard integration of the gated pilot. Both flag states,
// legacy-only notice, malformed v2 errors, historical ranges, render
// failure/fallback without extra API requests, loading transitions,
// context invalidation, one-request-per-action ownership, and the C2
// reconciliation-loop regression — all through the real DashboardPage and
// the C2 request boundary (only the lazy renderer and flag are stubbed).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { configureContextFixture } from '../../../../tests/unit/context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import DashboardPage from '@/views/DashboardPage.vue'
import type { NavQuery, NavResult } from '../contracts'
import { navWireFixture } from './navFixtures'

const api = vi.hoisted(() => ({
  getDashboardSummary: vi.fn(),
  getDashboardBreakdown: vi.fn(),
  getDashboardSummaryOverTime: vi.fn(),
}))
vi.mock('@/services/api', () => api)

const chartApi = vi.hoisted(() => {
  class ChartApiError extends Error {
    readonly status?: number
    readonly code?: string
    readonly retryable: boolean
    constructor(message: string, status?: number, code?: string, retryable = false) {
      super(message)
      this.name = 'ChartApiError'
      this.status = status
      this.code = code
      this.retryable = retryable
    }
  }
  class ChartContextMismatchError extends Error {
    constructor(message: string) {
      super(message)
      this.name = 'ChartContextMismatchError'
    }
  }
  return { fetchNavChart: vi.fn(), ChartApiError, ChartContextMismatchError }
})
vi.mock('@/features/charts/chartApi', () => chartApi)

const pilot = vi.hoisted(() => ({ enabled: false }))
vi.mock('../rendererPolicy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../rendererPolicy')>()
  return { ...actual, pilotRequested: () => pilot.enabled }
})

vi.mock('../EChartsNav.vue', async () => {
  const { h } = await import('vue')
  return {
    // __esModule lets Vue's async-component interop pick .default instead of
    // treating this namespace itself as the component.
    __esModule: true,
    default: {
      name: 'EChartsNav',
      props: ['document', 'interaction'],
      emits: ['update:interaction', 'render-error'],
      render() {
        return h('div', { class: 'echarts-stub', 'data-testid': 'echarts-canvas' })
      },
    },
  }
})

import EChartsNavStub from '../EChartsNav.vue'

const summaryFixture = { 'Current NAV': '$1,000.00', Invested: '$900.00', 'Cash-out': '$0.00', total_return: '11.11%', irr: 'N/R' }
const breakdownFixture = {
  assetType: { data: { Stocks: '$1,000.00' }, percentage: { Stocks: '100%' } },
  assetClass: { data: { Equity: '$1,000.00' }, percentage: { Equity: '100%' } },
  currency: { data: { USD: '$1,000.00' }, percentage: { USD: '100%' } },
  totalNAV: '$1,000.00',
}
const historyFixture = { lines: [{ name: 'EoP NAV', data: { YTD: '$1,000.00' } }], years: [2026], currentYear: 2026 }

/** A validated v2 result matching the fixture effective date (historical range). */
function v2Result(outcomeDocument = navWireFixture('asset_type', 'M')): NavResult {
  const parsed = JSON.parse(JSON.stringify(outcomeDocument))
  const { chartV2: document, ...legacy } = parsed
  return { capability: 'v2', legacy, document }
}

function legacyOnlyResult(): NavResult {
  return { capability: 'legacy_only', legacy: { labels: ['Jan-26'], currency: 'USDk', datasets: [{ label: 'NAV', type: 'bar', data: [1000] }] } }
}

const vuetify = createVuetify({ components, directives })

// The store instance the mounted page will use, created explicitly so tests
// can spy before the first request fires (mounting installs this pinia).
let activeContext: ReturnType<typeof usePortfolioContextStore> | null = null

async function mountDashboard(beforeMount?: (context: ReturnType<typeof usePortfolioContextStore>) => void) {
  const pinia = createPinia()
  activeContext = usePortfolioContextStore(pinia)
  await activeContext.reconcileContext()
  beforeMount?.(activeContext)
  const wrapper = mount(DashboardPage, {
    global: {
      plugins: [vuetify, pinia],
      provide: { showError: vi.fn(), clearErrors: vi.fn() },
      stubs: {
        UpdateAccountPerformanceDialog: true,
        BreakdownChart: { props: ['title'], template: '<div class="allocation-content">{{ title }}</div>' },
        SummaryOverTimeTable: true,
        'v-skeleton-loader': { template: '<div class="skeleton-stub" />' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  configureContextFixture('2026-09-08')
  pilot.enabled = false
  api.getDashboardSummary.mockResolvedValue(summaryFixture)
  api.getDashboardBreakdown.mockResolvedValue(breakdownFixture)
  api.getDashboardSummaryOverTime.mockResolvedValue(historyFixture)
  chartApi.fetchNavChart.mockResolvedValue(v2Result())
})

describe('flag-off dashboard (default)', () => {
  it('renders the incumbent Chart.js renderer with no pilot artifacts and one request', async () => {
    const wrapper = await mountDashboard()
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(1)
    const query = chartApi.fetchNavChart.mock.calls[0][0] as NavQuery
    // Historical range accepted: query end date is the chart's toDate while
    // the committed effective date stays authoritative elsewhere.
    expect(query.toDate).toBe('2026-09-08')
    expect(query.fromDate).toBe('2026-01-01')
    expect(wrapper.find('[data-testid="nav-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-echarts-pilot"]').exists()).toBe(false)
    expect(wrapper.find('.echarts-stub').exists()).toBe(false)
    expect(wrapper.find('[data-testid="nav-capability-notice"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('flag-on dashboard (pilot)', () => {
  beforeEach(() => {
    pilot.enabled = true
  })

  it('renders the pilot composition for a validated v2 result', async () => {
    const wrapper = await mountDashboard()
    expect(wrapper.find('[data-testid="nav-echarts-pilot"]').exists()).toBe(true)
    expect(wrapper.find('.echarts-stub').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-capability-notice"]').exists()).toBe(false)
    const legendText = wrapper.find('[role="group"][aria-label="Chart series visibility"]').text()
    expect(legendText).toContain('Since-inception IRR (annualized)')
    expect(legendText).toContain('Interval IRR (annualized)')
    expect(wrapper.find('caption').text()).toBe('Exact values by period')
    wrapper.unmount()
  })

  it('keeps legacy_only on the incumbent renderer with the honest notice', async () => {
    chartApi.fetchNavChart.mockResolvedValue(legacyOnlyResult())
    const wrapper = await mountDashboard()
    expect(wrapper.get('[data-testid="nav-capability-notice"]').text()).toContain('legacy response')
    expect(wrapper.find('[data-testid="nav-echarts-pilot"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="nav-chart"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('surfaces malformed v2 as the Dashboard error state, never a pilot or notice', async () => {
    chartApi.fetchNavChart.mockRejectedValue(new Error('Invalid chartV2 document: unsupported version'))
    const wrapper = await mountDashboard()
    expect(wrapper.get('[data-testid="nav-error"]').text()).toContain('Invalid chartV2 document')
    expect(wrapper.find('[data-testid="nav-echarts-pilot"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="nav-capability-notice"]').exists()).toBe(false)
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('offers the known-data fallback after a rendering failure without any extra request', async () => {
    const wrapper = await mountDashboard()
    expect(wrapper.find('.echarts-stub').exists()).toBe(true)
    wrapper.findComponent(EChartsNavStub).vm.$emit('render-error', new Error('canvas exploded'))
    await flushPromises()
    expect(wrapper.get('[data-testid="chart-render-error"]').text()).toContain('canvas exploded')
    await wrapper.get('[data-testid="chart-render-fallback"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="nav-fallback-notice"]').text()).toContain('previous chart')
    expect(wrapper.find('[data-testid="nav-chart"]').exists()).toBe(true)
    expect(wrapper.find('.echarts-stub').exists()).toBe(false)
    // The fallback is renderer-only: still exactly one chart request.
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('issues exactly one request per parameter event and per context refresh', async () => {
    const wrapper = await mountDashboard()
    const chart = wrapper.getComponent({ name: 'NAVChart' })
    chart.vm.$emit('update-params', {
      frequency: 'M', breakdown: 'none', dateRange: 'ytd',
      dateFrom: '2026-01-01', dateTo: '2026-09-08',
    })
    await flushPromises()
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(2)
    expect(api.getDashboardSummary).toHaveBeenCalledTimes(1)
    const context = usePortfolioContextStore()
    context.triggerDataRefresh()
    await flushPromises()
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(3)
    wrapper.unmount()
  })

  it('clears the old chart on a context transition before the new one applies', async () => {
    const wrapper = await mountDashboard()
    expect(wrapper.find('[data-testid="nav-chart"]').exists()).toBe(true)
    const context = usePortfolioContextStore()
    const change = context.changeContext({ effectiveCurrentDate: '2025-12-31' })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="nav-chart"]').exists()).toBe(false)
    await change
    await flushPromises()
    expect(wrapper.find('[data-testid="nav-chart"]').exists()).toBe(true)
    const query = chartApi.fetchNavChart.mock.calls.at(-1)![0] as NavQuery
    expect(query.toDate).toBe('2025-12-31')
    wrapper.unmount()
  })

  it('keeps the C2 reconciliation loop bounded (one reconcile per episode)', async () => {
    chartApi.fetchNavChart.mockRejectedValue(new chartApi.ChartContextMismatchError('effective date does not match'))
    let spy: ReturnType<typeof vi.spyOn> | null = null
    const wrapper = await mountDashboard((context) => {
      spy = vi.spyOn(context, 'reconcileContext')
    })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 0))
    // The initial mismatch reconciled exactly once during mount; the
    // reconciliation refresh refetched and still mismatched, so the episode
    // suppression holds: no second reconciliation, error stays visible.
    expect(spy!).toHaveBeenCalledTimes(1)
    const settled = chartApi.fetchNavChart.mock.calls.length
    expect(settled).toBeGreaterThanOrEqual(2)
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(chartApi.fetchNavChart.mock.calls.length).toBeLessThanOrEqual(settled + 1)
    expect(spy!).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-testid="nav-error"]').exists()).toBe(true)
    wrapper.unmount()
  })
})

describe('loading transitions (flag on)', () => {
  beforeEach(() => {
    pilot.enabled = true
  })

  it('shows the initial skeleton, then retains the mounted pilot under same-context loading', async () => {
    let release!: (result: NavResult) => void
    chartApi.fetchNavChart.mockReturnValueOnce(new Promise((resolve) => { release = resolve }))
    const wrapper = await mountDashboard()
    expect(wrapper.find('.skeleton-stub').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-chart"]').exists()).toBe(false)
    release(v2Result())
    await flushPromises()
    const chartElement = wrapper.get('[data-testid="nav-chart"]').element
    let refresh!: (result: NavResult) => void
    chartApi.fetchNavChart.mockReturnValueOnce(new Promise((resolve) => { refresh = resolve }))
    wrapper.getComponent({ name: 'NAVChart' }).vm.$emit('update-params', {
      frequency: 'M', breakdown: 'none', dateRange: 'ytd',
      dateFrom: '2026-01-01', dateTo: '2026-09-08',
    })
    await flushPromises()
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="nav-chart"]').element).toBe(chartElement)
    refresh(v2Result())
    await flushPromises()
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
