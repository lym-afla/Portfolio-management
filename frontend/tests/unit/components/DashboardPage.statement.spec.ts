import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import DashboardPage from '@/views/DashboardPage.vue'
import { ApiError } from '@/services/http/errors'
import { amount, statementFixture } from './statement-fixture'

const api = vi.hoisted(() => ({
  getDashboardSummaryV2: vi.fn(),
  getDashboardSummaryOverTime: vi.fn(),
}))
vi.mock('@/services/api', () => api)

const chartApi = vi.hoisted(() => ({
  fetchNavChart: vi.fn(),
  fetchBreakdownChart: vi.fn(),
  ChartApiError: class ChartApiError extends Error {},
  ChartContextMismatchError: class ChartContextMismatchError extends Error {},
}))
vi.mock('@/features/charts/chartApi', () => chartApi)

const legacyFive = {
  'Current NAV': '$112,500.00',
  Invested: '$100,000.00',
  'Cash-out': '($5,000.00)',
  total_return: '17.5%',
  irr: '8.4%',
}

const vuetify = createVuetify({ components, directives })

async function mountPage() {
  const pinia = createPinia()
  await usePortfolioContextStore(pinia).reconcileContext()
  const wrapper = mount(DashboardPage, {
    global: {
      plugins: [vuetify, pinia],
      provide: { showError: vi.fn(), clearErrors: vi.fn() },
      stubs: {
        UpdateAccountPerformanceDialog: true,
        BreakdownChart: true,
        NAVChart: true,
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
  configureContextFixture('2026-10-15')
  api.getDashboardSummaryV2.mockRejectedValue(new Error('summary temporarily failed'))
  api.getDashboardSummaryOverTime.mockRejectedValue(new Error('history temporarily failed'))
  chartApi.fetchNavChart.mockRejectedValue(new Error('nav temporarily failed'))
  chartApi.fetchBreakdownChart.mockRejectedValue(new Error('breakdown temporarily failed'))
})

describe('DashboardPage reconciled statement', () => {
  it('renders the approved statement composition from a v2 response', async () => {
    api.getDashboardSummaryV2.mockResolvedValue({
      capability: 'v2',
      legacy: legacyFive,
      statement: statementFixture(),
    })
    const wrapper = await mountPage()
    expect(wrapper.find('[data-testid="portfolio-statement-section"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Invested')
    expect(wrapper.text()).toContain('$100,000.00')
    expect(wrapper.text()).toContain('($5,000.00)')
    expect(wrapper.text()).toContain('Net invested capital')
    expect(wrapper.text()).toContain('$95,000.00')
    expect(wrapper.text()).toContain('Net result')
    expect(wrapper.text()).toContain('Total NAV')
    expect(wrapper.text()).toContain('$112,500.00')
    // Returns card, separated from the statement.
    expect(wrapper.find('[data-testid="total-return"]').text()).toContain('17.5%')
    expect(wrapper.find('[data-testid="irr-since-inception"]').text()).toContain('8.4%')
    // Expanded by default per the approved image; exact server display strings.
    expect(wrapper.find('[data-testid="net-result-breakdown"]').isVisible()).toBe(true)
    expect(wrapper.text()).toContain('Realized gains / losses')
    expect(wrapper.text()).toContain('Dividends & interest')
    expect(wrapper.text()).toContain('Price gains exclude FX; FX shown separately.')
    wrapper.unmount()
  })

  it('toggles the breakdown without issuing any request', async () => {
    api.getDashboardSummaryV2.mockResolvedValue({
      capability: 'v2',
      legacy: legacyFive,
      statement: statementFixture(),
    })
    const wrapper = await mountPage()
    const breakdownDisplay = () =>
      wrapper.find('[data-testid="net-result-breakdown"]').element.style.display
    expect(wrapper.find('[data-testid="breakdown-toggle"]').attributes('aria-expanded')).toBe('true')
    await wrapper.find('[data-testid="breakdown-toggle"]').trigger('click')
    expect(breakdownDisplay()).toBe('none')
    expect(wrapper.find('[data-testid="breakdown-toggle"]').attributes('aria-expanded')).toBe('false')
    expect(api.getDashboardSummaryV2).toHaveBeenCalledTimes(1)
    // The status line stays outside the collapsible: reconciliation state is
    // never concealable by collapsing.
    await wrapper.find('[data-testid="breakdown-toggle"]').trigger('click')
    expect(breakdownDisplay()).toBe('')
    expect(wrapper.find('[data-testid="statement-status"]').exists()).toBe(false)
    expect(api.getDashboardSummaryV2).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('announces unreconciled and partial states outside the collapsible', async () => {
    api.getDashboardSummaryV2.mockResolvedValue({
      capability: 'v2',
      legacy: legacyFive,
      statement: statementFixture({
        status: 'partial',
        reasons: ['missing_fx', 'unexplained_difference'],
        netResult: {
          nav: amount('$112,500.00', { raw: '112500', status: 'ok' }),
          controlTotal: amount('$17,500.00', { raw: '17500' }),
          components: {
            realizedPrice: amount('$8,000.00', { raw: '8000' }),
            unrealizedPrice: amount('$7,000.00', { raw: '7000' }),
            income: amount('$3,500.00', { raw: '3500' }),
            fees: amount('($1,000.00)', { raw: '-1000' }),
            taxes: amount('($500.00)', { raw: '-500' }),
            fx: amount('$500.00', { raw: '500' }),
            otherFlows: amount('–', { raw: '0' }),
          },
          fxDetail: { security: amount('$500.00', { raw: '500' }), cashFlows: amount('–', { raw: '0' }) },
          attributedSum: amount('$18,000.00', { raw: '18000' }),
          unexplainedDifference: amount('($500.00)', { raw: '-500' }),
          toleranceRaw: '0.04',
          toleranceBasis: 'half-ULP budget',
          reconciliation: 'unreconciled',
        },
      }),
    })
    const wrapper = await mountPage()
    const status = wrapper.find('[data-testid="statement-status"]')
    expect(status.exists()).toBe(true)
    expect(status.text()).toContain('Unreconciled difference')
    expect(status.text()).toContain('($500.00)')
    // Collapse cannot hide the reconciliation state.
    await wrapper.find('[data-testid="breakdown-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="statement-status"]').isVisible()).toBe(true)
    wrapper.unmount()
  })

  it('keeps the five legacy metrics plus an honest notice for a legacy-only response', async () => {
    api.getDashboardSummaryV2.mockResolvedValue({ capability: 'legacy_only', legacy: legacyFive })
    const wrapper = await mountPage()
    expect(wrapper.find('[data-testid="summary-card"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('$112,500.00')
    expect(wrapper.find('[data-testid="statement-capability-notice"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="portfolio-statement-section"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('fails visibly when the negotiated request itself fails', async () => {
    // A rejected negotiation (network, invalid document — the decoder
    // boundary itself is pinned in DashboardStatement.boundary.spec) keeps
    // the incumbent error + retry contract.
    api.getDashboardSummaryV2.mockRejectedValue(
      new ApiError('Invalid dashboard statement response: netResult.components.income.status'),
    )
    const wrapper = await mountPage()
    expect(wrapper.find('[data-testid="summary-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Invalid dashboard statement response')
    expect(wrapper.find('[data-testid="portfolio-statement-section"]').exists()).toBe(false)
    api.getDashboardSummaryV2.mockResolvedValue({
      capability: 'v2',
      legacy: legacyFive,
      statement: statementFixture(),
    })
    await wrapper.find('[data-testid="summary-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="portfolio-statement-section"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
