import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import PortfolioMetrics from '@/components/dashboard/PortfolioMetrics.vue'
import { summaryMetrics } from '@/components/dashboard/summaryMetrics'
import { decodeDashboardSummary } from '@/services/api/dashboard'
import DashboardPage from '@/views/DashboardPage.vue'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'

// Fixtures pass through the real API decoder so branded display types are
// honored instead of being cast away in test setup.
const populatedSummary = decodeDashboardSummary({
  'Current NAV': '$0.00',
  Invested: '$100.00',
  'Cash-out': '($100.00)',
  total_return: '−2.40%',
  irr: 'N/A',
})

describe('summaryMetrics display adapter', () => {
  it('maps every actual summary key to the five explicit metric ids in order', () => {
    expect(summaryMetrics(populatedSummary).map((metric) => metric.id)).toEqual([
      'nav',
      'invested',
      'cash-out',
      'total-return',
      'irr',
    ])
  })

  it('uses domain labels and preserves the lifetime horizon meaning', () => {
    const metrics = summaryMetrics(populatedSummary)
    expect(metrics.map((metric) => metric.label)).toEqual([
      'Total NAV',
      'Invested',
      'Cash out',
      'Total return',
      'IRR since inception',
    ])
    expect(metrics.find((metric) => metric.id === 'total-return')?.explanation).toBe('Since inception')
    expect(metrics.find((metric) => metric.id === 'irr')?.explanation).toBeUndefined()
  })

  it('keeps zero, negative, signed and unavailable display strings verbatim', () => {
    const values = summaryMetrics(populatedSummary).map((metric) => metric.value)
    expect(values).toEqual(['$0.00', '$100.00', '($100.00)', '−2.40%', 'N/A'])
  })

  it('maps null fields to the established unavailable marker instead of a blank', () => {
    const metrics = summaryMetrics(
      decodeDashboardSummary({
        'Current NAV': '$1.00',
        Invested: null,
        'Cash-out': 'N/R',
        total_return: null,
        irr: 'N/R',
      })
    )
    const wrapper = mount(PortfolioMetrics, {
      props: { contextLabel: 'All accounts · 2026-10-01 · USD', metrics },
    })
    expect(wrapper.get('[data-metric="invested"] dd').text()).toBe('N/R')
    expect(wrapper.get('[data-metric="cash-out"] dd').text()).toBe('N/R')
    expect(wrapper.get('[data-metric="total-return"] dd').text()).toBe('N/R')
    expect(wrapper.get('[data-metric="irr"] dd').text()).toBe('N/R')
    wrapper.unmount()
  })
})

describe('PortfolioMetrics presentation', () => {
  const mountMetrics = (metrics: readonly ReturnType<typeof summaryMetrics>[number][]) =>
    mount(PortfolioMetrics, {
      props: { contextLabel: 'Brokerage A · 2026-09-08 · USD', metrics },
    })

  it('renders a semantic definition list with one dt/dd pair per metric', () => {
    const wrapper = mountMetrics(summaryMetrics(populatedSummary))
    const list = wrapper.get('dl.portfolio-metrics')
    expect(list.findAll('div').length).toBe(5)
    expect(wrapper.findAll('dt').length).toBe(5)
    expect(wrapper.findAll('dd').length).toBe(5)
    wrapper.unmount()
  })

  it('renders the supplied display values exactly without adding currency decoration', () => {
    const wrapper = mountMetrics(summaryMetrics(populatedSummary))
    expect(wrapper.get('[data-metric="nav"] dd').text()).toBe('$0.00')
    expect(wrapper.get('[data-metric="invested"] dd').text()).toBe('$100.00')
    expect(wrapper.get('[data-metric="cash-out"] dd').text()).toBe('($100.00)')
    expect(wrapper.get('[data-metric="total-return"] dd').text()).toBe('−2.40%')
    expect(wrapper.get('[data-metric="irr"] dd').text()).toBe('N/A')
    // The committed context carries the currency; values must not repeat it.
    expect(wrapper.get('[data-metric="invested"] dd').text()).not.toContain('USD')
    wrapper.unmount()
  })

  it('shows the committed context label and makes the NAV entry dominant', () => {
    const wrapper = mountMetrics(summaryMetrics(populatedSummary))
    expect(wrapper.get('[data-testid="portfolio-context-label"]').text()).toContain('Brokerage A · 2026-09-08 · USD')
    expect(wrapper.get('[data-metric="nav"]').classes()).toContain('portfolio-metrics__primary')
    expect(wrapper.get('[data-metric="invested"]').classes()).not.toContain('portfolio-metrics__primary')
    wrapper.unmount()
  })
})

const api = vi.hoisted(() => ({
  getDashboardSummary: vi.fn(),
  getDashboardSummaryOverTime: vi.fn(),
}))
vi.mock('@/services/api', () => api)

// C4: the breakdown request negotiates chart contract v2 through the shared
// chart transport (one request still feeds all three cards).
const chartApi = vi.hoisted(() => ({
  fetchNavChart: vi.fn(),
  fetchBreakdownChart: vi.fn(),
  ChartApiError: class ChartApiError extends Error {},
  ChartContextMismatchError: class ChartContextMismatchError extends Error {},
}))
vi.mock('@/features/charts/chartApi', () => chartApi)

const summaryFixture = decodeDashboardSummary({
  'Current NAV': '$1,000.00',
  Invested: '$900.00',
  'Cash-out': '$0.00',
  total_return: '11.11%',
  irr: 'N/R',
})

const vuetify = createVuetify({ components, directives })

async function mountDashboard() {
  const pinia = createPinia()
  await usePortfolioContextStore(pinia).reconcileContext()
  const wrapper = mount(DashboardPage, {
    global: {
      plugins: [vuetify, pinia],
      provide: { showError: vi.fn(), clearErrors: vi.fn() },
      stubs: {
        UpdateAccountPerformanceDialog: true,
        BreakdownChart: { props: ['title'], template: '<div class="allocation-content">{{ title }}</div>' },
        NAVChart: { name: 'NAVChart', props: ['chartData'], template: '<div class="nav-content">{{ JSON.stringify(chartData.labels) }}</div>' },
        SummaryOverTimeTable: true,
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
  chartApi.fetchBreakdownChart.mockResolvedValue({
    capability: 'legacy_only',
    legacy: {
      assetType: { data: { Stocks: '$1,000.00' }, percentage: { Stocks: '100%' } },
      assetClass: { data: { Equity: '$1,000.00' }, percentage: { Equity: '100%' } },
      currency: { data: { USD: '$1,000.00' }, percentage: { USD: '100%' } },
      totalNAV: '$1,000.00',
    },
  })
  api.getDashboardSummaryOverTime.mockResolvedValue({
    lines: [{ name: 'EoP NAV', data: { YTD: '$1,000.00', 'All-time': '$1,000.00' } }],
    years: [2026],
    currentYear: 2026,
  })
  chartApi.fetchNavChart.mockResolvedValue({
    capability: 'legacy_only',
    legacy: { labels: ['2026-09-08'], currency: 'USDk', datasets: [{ label: 'NAV', type: 'bar', data: [1000] }] },
  })
})

describe('DashboardPage NAV-first composition', () => {
  it('renders portfolio values, NAV trajectory, allocation and history in reading order', async () => {
    const wrapper = await mountDashboard()
    const regions = [
      wrapper.get('[data-testid="summary-card"]').element,
      wrapper.get('[data-testid="nav-chart"]').element,
      wrapper.get('[data-testid="allocation-assetType-card"]').element,
      wrapper.get('[data-testid="history-section"]').element,
    ]
    for (let index = 1; index < regions.length; index++) {
      expect(regions[index - 1].compareDocumentPosition(regions[index]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
    wrapper.unmount()
  })

  it('carries the committed account, date and currency with the portfolio values', async () => {
    const wrapper = await mountDashboard()
    const label = wrapper.get('[data-testid="summary-card"]').text()
    expect(label).toContain('All accounts')
    expect(label).toContain('2026-09-08')
    expect(label).toContain('USD')
    wrapper.unmount()
  })

  it('offers Account Performance as a secondary action of the history section', async () => {
    const wrapper = await mountDashboard()
    const section = wrapper.get('[data-testid="history-section"]')
    expect(section.get('h2').text()).toBe('Historical reconciliation')
    const action = section.get('.workspace-actions button')
    expect(action.text()).toBe('Update Account Performance')
    wrapper.unmount()
  })
})
