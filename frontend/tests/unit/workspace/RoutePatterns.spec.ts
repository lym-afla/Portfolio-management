// D5 — route-family contract tests for the actual common controls of each
// migrated route. No blanket stubs: real components mount with the real
// stores and mocked API boundary, so labels, events and request behavior
// stay observable. Financial strings are asserted verbatim — never parsed.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { configureContextFixture } from '../context-fixture'
import { configureApiTransport } from '@/services/http/client'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import SummaryPage from '@/views/SummaryPage.vue'

const api = vi.hoisted(() => ({
  getAccountPerformanceSummary: vi.fn(),
  getPortfolioBreakdownSummary: vi.fn(),
  getYearOptions: vi.fn(),
}))
vi.mock('@/services/api', () => api)

const vuetify = createVuetify({ components, directives })

// Backend-faithful synthetic response (services/summary.py shape): server
// period order YTD, calendar years descending, All-time; eight metric keys
// per period; a Sub-total line inside each group's lines; a TOTAL line.
const performanceFixture = (value: (period: string) => string) => {
  const periods = ['YTD', '2025', '2024', 'All-time']
  const metricData = () =>
    Object.fromEntries(
      periods.map((period) => [
        period,
        {
          'BoP NAV': value(period),
          'Cash-in/out': value(period),
          Return: value(period),
          FX: value(period),
          'TSR percentage': value(period),
          'EoP NAV': value(period),
          Commission: value(period),
          'Fee per AuM (percentage)': value(period),
        },
      ]),
    )
  return {
    public_markets_context: {
      years: periods,
      lines: [
        { name: 'Broker — Main', data: metricData() },
        { name: 'Sub-total', data: metricData() },
      ],
      subtotal: metricData(),
    },
    restricted_investments_context: {
      years: periods,
      lines: [{ name: 'Restricted — One', data: metricData() }, { name: 'Sub-total', data: metricData() }],
      subtotal: metricData(),
    },
    total_context: { line: { name: 'TOTAL', data: metricData() }, years: periods },
  }
}

const breakdownFixture = {
  consolidated_context: [
    { name: 'Stocks', cost: '$10,000.00', unrealized: '$1,000.00', unrealized_percent: '10%', market_value: '$11,000.00', portfolio_percent: '55%', realized: '$0.00', realized_percent: '0%', capital_distribution: '$0.00', capital_distribution_percent: '0%', commission: '($10.00)', commission_percent: '0.1%', total: '$1,000.00', total_percent: '10%' },
    { name: 'TOTAL', cost: '$10,000.00', unrealized: '$1,000.00', unrealized_percent: '10%', market_value: '$11,000.00', portfolio_percent: '55%', realized: '$0.00', realized_percent: '0%', capital_distribution: '$0.00', capital_distribution_percent: '0%', commission: '($10.00)', commission_percent: '0.1%', total: '$1,000.00', total_percent: '10%' },
  ],
  unrestricted_context: [],
  restricted_context: [],
}

const emptyPerformance = {
  public_markets_context: { lines: [], subtotal: null, years: [] },
  restricted_investments_context: { lines: [], subtotal: null, years: [] },
  total_context: { line: {}, years: [] },
}

async function mountSummary() {
  const pinia = createPinia()
  await usePortfolioContextStore(pinia).reconcileContext()
  const wrapper = mount(SummaryPage, {
    global: {
      plugins: [vuetify, pinia],
      provide: { showError: vi.fn(), clearErrors: vi.fn() },
    },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  configureContextFixture('2026-09-08')
  api.getAccountPerformanceSummary.mockResolvedValue(
    performanceFixture(() => '$10,000.00'),
  )
  api.getPortfolioBreakdownSummary.mockResolvedValue(breakdownFixture)
  api.getYearOptions.mockResolvedValue([2026])
})

describe('/summary route patterns', () => {
  it('renders one workspace-owned Performance heading', async () => {
    const wrapper = await mountSummary()
    const headings = wrapper.findAll('h1')
    expect(headings).toHaveLength(1)
    expect(headings[0].attributes('data-testid')).toBe('workspace-page-heading')
    expect(headings[0].text()).toBe('Performance')
  })

  it('defaults to the returned YTD period with all eight flat qualified leaves', async () => {
    const wrapper = await mountSummary()
    await flushPromises()
    const headerCells = wrapper.findAll('.account-performance-table thead th')
    const headerText = headerCells.map((cell) => cell.text())
    expect(headerText).toContain('Account')
    expect(headerText).toContain('BoP NAV (YTD)')
    expect(headerText).toContain('Cash-in/(out) (YTD)')
    expect(headerText).toContain('Return (YTD)')
    expect(headerText).toContain('FX (YTD)')
    expect(headerText).toContain('TSR (YTD)')
    expect(headerText).toContain('EoP NAV (YTD)')
    expect(headerText).toContain('Commissions (YTD)')
    expect(headerText).toContain('Fee per AuM (YTD)')
    // Exactly one period's worth of leaves: 8 qualified labels + Account.
    expect(headerCells).toHaveLength(9)
  })

  it('keeps both groups, their lines, sub-totals, the TOTAL row and exact strings', async () => {
    const wrapper = await mountSummary()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('Public Markets')
    expect(text).toContain('Restricted Investments')
    expect(text).toContain('Broker — Main')
    expect(text).toContain('Restricted — One')
    expect(text).toContain('Sub-total')
    expect(text).toContain('TOTAL')
    expect(text).toContain('$10,000.00')
  })

  it('single-period view changes are presentation-only: no additional request', async () => {
    const wrapper = await mountSummary()
    await flushPromises()
    api.getAccountPerformanceSummary.mockClear()
    const periodSelect = wrapper
      .findAllComponents({ name: 'VSelect' })
      .find((c) => c.props('label') === 'Period')
    expect(periodSelect).toBeTruthy()
    await periodSelect!.vm.$emit('update:modelValue', '2024')
    await flushPromises()
    expect(api.getAccountPerformanceSummary).not.toHaveBeenCalled()
    const headerText = wrapper.findAll('.account-performance-table thead th').map((c) => c.text())
    expect(headerText).toContain('BoP NAV (2024)')
  })

  it('comparison mode groups selected periods under accessible bands', async () => {
    const wrapper = await mountSummary()
    await flushPromises()
    const viewSelect = wrapper
      .findAllComponents({ name: 'VSelect' })
      .find((c) => c.props('label') === 'View')
    await viewSelect!.vm.$emit('update:modelValue', 'comparison')
    await flushPromises()
    const bands = wrapper.findAll('.account-performance-table thead .period-band')
    // Default comparison selection is the single-period default period.
    expect(bands.map((b) => b.text())).toEqual(['YTD'])
    const periodsSelect = wrapper
      .findAllComponents({ name: 'VSelect' })
      .find((c) => c.props('label') === 'Periods')
    expect(periodsSelect).toBeTruthy()
    await periodsSelect!.vm.$emit('update:modelValue', ['YTD', '2024'])
    await flushPromises()
    const bandsAfter = wrapper.findAll('.account-performance-table thead .period-band')
    expect(bandsAfter.map((b) => b.text())).toEqual(['YTD', '2024'])
    expect(
      bandsAfter.every((band) => band.attributes('scope') === 'colgroup'),
    ).toBe(true)
  })

  it('full history shows every returned period in server order', async () => {
    const wrapper = await mountSummary()
    await flushPromises()
    const viewSelect = wrapper
      .findAllComponents({ name: 'VSelect' })
      .find((c) => c.props('label') === 'View')
    await viewSelect!.vm.$emit('update:modelValue', 'history')
    await flushPromises()
    const bands = wrapper.findAll('.account-performance-table thead .period-band')
    expect(bands.map((b) => b.text())).toEqual(['YTD', '2025', '2024', 'All-time'])
  })

  it('keeps the breakdown-year filter as its own request owner with reactive currency units', async () => {
    // EUR must be a valid reporting choice for the store's serialized
    // context change; extend the synthetic transport before mounting.
    configureApiTransport({
      get: async (url) =>
        url.includes('get_account_choices')
          ? { data: { options: [['All accounts', { type: 'all', id: null }]] } }
          : { data: { choices: { default_currency: [['USD', 'US Dollar'], ['EUR', 'Euro']] } } },
    })
    const pinia = createPinia()
    await usePortfolioContextStore(pinia).reconcileContext()
    const wrapper = mount(SummaryPage, {
      global: {
        plugins: [vuetify, pinia],
        provide: { showError: vi.fn(), clearErrors: vi.fn() },
      },
    })
    await flushPromises()
    expect(api.getPortfolioBreakdownSummary).toHaveBeenCalledWith(
      String(new Date().getFullYear()),
      expect.anything(),
    )
    const yearSelect = wrapper
      .findAllComponents({ name: 'VSelect' })
      .find((c) => c.props('label') === 'Year')
    expect(yearSelect).toBeTruthy()
    api.getPortfolioBreakdownSummary.mockClear()
    await yearSelect!.vm.$emit('update:modelValue', '2025')
    await flushPromises()
    expect(api.getPortfolioBreakdownSummary).toHaveBeenCalledWith('2025', expect.anything())
    const breakdownText = wrapper.find('.portfolio-breakdown-table').text()
    expect(breakdownText).toContain('(USD)')
    expect(breakdownText).toContain('$10,000.00')
    // Reporting-currency change re-labels the breakdown units.
    await usePortfolioContextStore(pinia).changeContext({
      currency: 'EUR',
      digits: 2,
      accountSelection: { type: 'all', id: null },
      effectiveCurrentDate: '2026-09-08',
    })
    await flushPromises()
    expect(wrapper.find('.portfolio-breakdown-table').text()).toContain('(EUR)')
  })

  it('disables period controls and keeps the page usable for empty data', async () => {
    api.getAccountPerformanceSummary.mockResolvedValue(emptyPerformance)
    const wrapper = await mountSummary()
    await flushPromises()
    const periodSelect = wrapper
      .findAllComponents({ name: 'VSelect' })
      .find((c) => c.props('label') === 'Period')
    expect(periodSelect!.props('disabled')).toBe(true)
    const viewSelect = wrapper
      .findAllComponents({ name: 'VSelect' })
      .find((c) => c.props('label') === 'View')
    expect(viewSelect!.props('disabled')).toBe(true)
  })

  it('surfaces a readable error when a summary resource fails', async () => {
    api.getAccountPerformanceSummary.mockRejectedValue(new Error('boom'))
    const wrapper = await mountSummary()
    await flushPromises()
    expect(wrapper.text()).toContain('Unable to load part of the summary')
  })
})
