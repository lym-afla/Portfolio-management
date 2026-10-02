// C2 Task 5: DashboardPage compatibility wiring. The dashboard NAV chart now
// requests through the typed v2 boundary while the incumbent Chart.js
// renderer keeps rendering the validated legacy payload; one request per
// initial/context/explicit/parameter trigger, honest capability notice for
// legacy_only only, and retained validated state immune to renderer-side
// mutation.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import { h } from 'vue'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { configureContextFixture } from '../../../../tests/unit/context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import DashboardPage from '@/views/DashboardPage.vue'
import type { NavQuery, NavResult } from '../contracts'
import { navSeriesFixture } from './fixtures'

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

const summaryFixture = { 'Current NAV': '$1,000.00', Invested: '$900.00', 'Cash-out': '$0.00', total_return: '11.11%', irr: 'N/R' }
const breakdownFixture = {
  assetType: { data: { Stocks: '$1,000.00' }, percentage: { Stocks: '100%' } },
  assetClass: { data: { Equity: '$1,000.00' }, percentage: { Equity: '100%' } },
  currency: { data: { USD: '$1,000.00' }, percentage: { USD: '100%' } },
  totalNAV: '$1,000.00',
}
const historyFixture = {
  lines: [{ name: 'EoP NAV', data: { YTD: '$1,000.00', 'All-time': '$1,000.00' } }],
  years: [2026],
  currentYear: 2026,
}

/** A validated v2 result mirroring the fixture document and its legacy twin. */
function v2Result(): NavResult {
  const envelope = structuredClone(navSeriesFixture())
  const { chartV2: _document, ...legacy } = envelope
  return { capability: 'v2', legacy, document: _document }
}
function legacyOnlyResult(labels: string[] = ['2026-09-08']): NavResult {
  return { capability: 'legacy_only', legacy: { labels, currency: 'USDk', datasets: [{ label: 'NAV', type: 'bar', data: [1000] }] } }
}

const vuetify = createVuetify({ components, directives })

const plainNavStub = {
  name: 'NAVChart',
  props: ['chartData', 'loading', 'initialParams', 'effectiveCurrentDate'],
  template: '<div class="nav-content" data-testid="nav-chart">{{ JSON.stringify(chartData.labels) }}</div>',
}
// Mutates its payload exactly like a hostile renderer would.
const mutatingNavStub = {
  name: 'NAVChart',
  props: ['chartData'],
  setup(props: { chartData?: { datasets?: { label: string; data: number[] }[] } }) {
    return () => {
      const dataset = props.chartData?.datasets?.[0]
      if (dataset) {
        dataset.data.push(999)
        dataset.label = 'mutated by renderer'
      }
      return h('div', { class: 'nav-content', 'data-testid': 'nav-chart' }, JSON.stringify(props.chartData.datasets[0].data))
    }
  },
}

async function mountDashboard(navStub: typeof plainNavStub = plainNavStub) {
  const pinia = createPinia()
  await usePortfolioContextStore(pinia).reconcileContext()
  const wrapper = mount(DashboardPage, {
    global: {
      plugins: [vuetify, pinia],
      provide: { showError: vi.fn(), clearErrors: vi.fn() },
      stubs: {
        UpdateAccountPerformanceDialog: true,
        BreakdownChart: { props: ['title'], template: '<div class="allocation-content">{{ title }}</div>' },
        SummaryOverTimeTable: true,
        NAVChart: navStub,
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
  api.getDashboardSummary.mockResolvedValue(summaryFixture)
  api.getDashboardBreakdown.mockResolvedValue(breakdownFixture)
  api.getDashboardSummaryOverTime.mockResolvedValue(historyFixture)
  chartApi.fetchNavChart.mockResolvedValue(v2Result())
})

describe('DashboardPage NAV chart wiring', () => {
  it('issues exactly one NAV request on initial load with the mapped query', async () => {
    const wrapper = await mountDashboard()
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(1)
    const query = chartApi.fetchNavChart.mock.calls[0][0] as NavQuery
    expect(query.mode).toBe('none')
    expect(query.frequency).toBe('Q')
    expect(query.fromDate).toBe('2026-01-01')
    expect(query.toDate).toBe('2026-09-08')
    expect(query.context.currency).toBe('USD')
    expect(wrapper.get('[data-testid="nav-chart"]').text()).toContain('Jan-26')
    expect(wrapper.find('[data-testid="nav-capability-notice"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps incumbent labels, datasets and both IRR lines deeply equal', async () => {
    const result = v2Result()
    const before = structuredClone(result.legacy)
    chartApi.fetchNavChart.mockResolvedValue(result)
    const wrapper = await mountDashboard()
    expect(wrapper.get('[data-testid="nav-chart"]').text()).toContain('Jan-26')
    // The retained validated legacy payload is untouched by rendering.
    expect(result.legacy).toEqual(before)
    expect(result.legacy.datasets).toHaveLength(4)
    expect(result.legacy.datasets.map((dataset) => dataset.label)).toEqual(
      ['NAV', 'IRR (RHS)', 'Rolling IRR (RHS)', 'Stock'],
    )
    wrapper.unmount()
  })

  it('renders the concise compatibility notice only for legacy_only', async () => {
    chartApi.fetchNavChart.mockResolvedValue(legacyOnlyResult())
    const wrapper = await mountDashboard()
    expect(wrapper.get('[data-testid="nav-capability-notice"]').text()).toContain('legacy response')
    expect(wrapper.get('[data-testid="nav-chart"]').text()).toContain('2026-09-08')
    wrapper.unmount()
  })

  it('surfaces invalid v2 as an error, never a capability notice, retrying only on demand', async () => {
    chartApi.fetchNavChart.mockRejectedValueOnce(new Error('Invalid chartV2 document: unsupported version'))
    const wrapper = await mountDashboard()
    expect(wrapper.get('[data-testid="nav-error"]').text()).toContain('Invalid chartV2 document')
    expect(wrapper.find('[data-testid="nav-capability-notice"]').exists()).toBe(false)
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(1)
    await wrapper.get('[data-testid="nav-retry"]').trigger('click')
    await flushPromises()
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="nav-error"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="nav-chart"]').text()).toContain('Jan-26')
    wrapper.unmount()
  })

  it('honors a non-retryable C1 error without any automatic retry', async () => {
    chartApi.fetchNavChart.mockRejectedValue(
      new chartApi.ChartApiError('Unsupported chart frequency.', 400, 'INVALID_CHART_QUERY', false),
    )
    const wrapper = await mountDashboard()
    expect(wrapper.get('[data-testid="nav-error"]').text()).toContain('Unsupported chart frequency.')
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('issues one request per child parameter event and keeps the chart mounted', async () => {
    const wrapper = await mountDashboard()
    const chart = wrapper.getComponent({ name: 'NAVChart' })
    const element = wrapper.get('[data-testid="nav-chart"]').element
    let release!: (result: NavResult) => void
    chartApi.fetchNavChart.mockReturnValueOnce(new Promise((resolve) => { release = resolve }))
    chart.vm.$emit('update-params', {
      frequency: 'M', breakdown: 'none', dateRange: 'ytd',
      dateFrom: '2026-01-01', dateTo: '2026-09-08',
    })
    await flushPromises()
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(2)
    expect((chartApi.fetchNavChart.mock.calls[1][0] as NavQuery).frequency).toBe('M')
    expect(api.getDashboardSummary).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="nav-chart"]').element).toBe(element)
    release(legacyOnlyResult(['Feb-26']))
    await flushPromises()
    expect(wrapper.get('[data-testid="nav-chart"]').text()).toContain('Feb-26')
    wrapper.unmount()
  })

  it('re-reads the NAV chart and every other widget once per data refresh', async () => {
    const wrapper = await mountDashboard()
    const context = usePortfolioContextStore(wrapper.vm.$pinia as never)
    context.triggerDataRefresh()
    await flushPromises()
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(2)
    expect(api.getDashboardSummary).toHaveBeenCalledTimes(2)
    expect(api.getDashboardBreakdown).toHaveBeenCalledTimes(2)
    expect(api.getDashboardSummaryOverTime).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('queries the new committed context after an effective-date change', async () => {
    const wrapper = await mountDashboard()
    const context = usePortfolioContextStore()
    await context.changeContext({ effectiveCurrentDate: '2025-12-31' })
    await flushPromises()
    expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(2)
    const query = chartApi.fetchNavChart.mock.calls[1][0] as NavQuery
    expect(query.toDate).toBe('2025-12-31')
    expect(query.fromDate).toBe('2025-01-01')
    wrapper.unmount()
  })

  it('keeps other widgets independent of a NAV failure', async () => {
    chartApi.fetchNavChart.mockRejectedValue(new Error('nav chart failed'))
    const wrapper = await mountDashboard()
    expect(wrapper.get('[data-testid="nav-error"]').text()).toContain('nav chart failed')
    expect(wrapper.find('[data-testid="summary-card"]').exists()).toBe(true)
    expect(wrapper.get('.allocation-content').text()).toBe('Asset Type')
    expect(wrapper.find('[data-testid="history-table"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('protects the retained validated result from renderer-side dataset mutation', async () => {
    const first = v2Result()
    const second = v2Result()
    const pristine = structuredClone(first.legacy)
    let call = 0
    chartApi.fetchNavChart.mockImplementation(() => {
      call += 1
      return Promise.resolve(call === 1 ? first : second)
    })
    const wrapper = await mountDashboard(mutatingNavStub as never)
    // The renderer mutated the copy it received...
    expect(wrapper.get('[data-testid="nav-chart"]').text()).toContain('999')
    // ...but the retained validated legacy payload survived untouched.
    expect(first.legacy).toEqual(pristine)
    const chart = wrapper.getComponent({ name: 'NAVChart' })
    chart.vm.$emit('update-params', {
      frequency: 'M', breakdown: 'none', dateRange: 'ytd',
      dateFrom: '2026-01-01', dateTo: '2026-09-08',
    })
    await flushPromises()
    // The next render mutated its own fresh copy; both retained results stay pristine.
    expect(wrapper.get('[data-testid="nav-chart"]').text()).toContain('999')
    expect(first.legacy).toEqual(pristine)
    expect(second.legacy).toEqual(pristine)
    wrapper.unmount()
  })
})
