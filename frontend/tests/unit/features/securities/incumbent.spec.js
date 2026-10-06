// D7 task 0 — characterization of the incumbent security detail page with
// populated stock/bond/crypto wire shapes, exact per-trigger request counts
// and verbatim display strings (SecurityDetailPage.vue stays the route/title
// compatibility entrypoint after extraction, so these pins must keep passing
// unchanged). All values are synthetic server display strings; none pass
// through Number on their way to the DOM.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'
import { createPinia } from 'pinia'
import { configureContextFixture } from '../../context-fixture'
import { deferred } from '../../helpers/deferred'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import SecurityDetailPage from '@/views/database/SecurityDetailPage.vue'

const mocks = vi.hoisted(() => ({
  getSecurityDetail: vi.fn(),
  getSecurityPriceHistory: vi.fn(),
  getSecurityPositionHistory: vi.fn(),
  getSecurityTransactions: vi.fn(),
  getAccountChoices: vi.fn(),
}))
let route
vi.mock('vue-router', () => ({
  useRoute: () => route, useRouter: () => ({ push: vi.fn() }),
  createRouter: () => ({ beforeEach() {}, afterEach() {}, onError() {} }), createWebHistory: () => ({}),
}))
vi.mock('@/services/api', () => ({ ...mocks }))
vi.mock('@/config/chartConfig', () => ({
  getChartOptions: vi.fn().mockResolvedValue({ navChartOptions: { responsive: true } }),
  colorPalette: ['#0F4C81', '#5C6B7A'],
}))
vi.mock('chartjs-adapter-date-fns', () => ({}))

const flush = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

const securityPageStubs = () => ({
  'v-skeleton-loader': true,
  'v-table': { template: '<table class="v-table"><slot /></table>' },
  'v-data-table': { template: '<div class="v-data-table"><slot name="bottom" /></div>' },
  'v-pagination': true,
  'v-list-subheader': { template: '<div class="v-list-subheader"><slot /></div>' },
  TimelineSelector: {
    props: ['modelValue', 'effectiveCurrentDate'],
    emits: ['update:modelValue'],
    template: `<div class="timeline-selector">
      <button type="button" class="period" v-for="p in ['7d','1m','3m','6m','ytd','1Y','3Y','5Y','All']"
        :key="p" @click="$emit('update:modelValue', p)">{{ p }}</button>
    </div>`,
  },
  TransactionRow: { props: ['transaction'], template: '<tr class="transaction-row-stub">{{ transaction.id }}</tr>' },
  LineChart: { props: ['chartData', 'options'], template: '<div class="line-chart-stub" />' },
})

const stockDetail = () => ({
  id: 1,
  instrument_type: 'Stock',
  ISIN: 'US0000000001',
  name: 'Fixture Stock',
  currency: 'USD',
  first_investment: '08-Sep-26',
  open_position: '10.000000000',
  buy_in_price: '101.50',
  current_price: '102.25',
  current_value: '$1,022.50',
  realized: '$12.50',
  unrealized: '$7.50',
  capital_distribution: '$0.00',
  irr: '1.25%',
})

const bondDetail = () => ({
  id: 2,
  instrument_type: 'Bond',
  ISIN: 'US0000000002',
  name: 'Fixture Bond',
  currency: 'USD',
  first_investment: '01-Feb-24',
  open_position: '2.000000000',
  buy_in_price: '99.125000%',
  current_value: '$1,982.50',
  realized: '($17.50)',
  unrealized: '–',
  capital_distribution: '$87.50',
  irr: 'NA',
  bond_data: {
    current_notional: '2,000.00',
    is_amortizing: true,
    initial_notional: '2,400.00',
    issue_date: '2024-02-01',
    maturity_date: '2031-02-01',
    coupon_type: 'Fixed',
    credit_rating: 'AA-',
    coupon_amount: '43.75',
    coupon_rate: '4.375000%',
    coupon_frequency: 2,
    next_coupon_date: '2027-02-01',
    current_aci: { aci_amount: '2.19', aci_days: 90, total_days: 181 },
    total_aci: '25.00',
    ytm: '4.51%',
  },
})

const sparseBondDetail = () => ({
  ...bondDetail(),
  bond_data: {
    current_notional: null,
    is_amortizing: false,
    coupon_type: null,
    credit_rating: null,
    coupon_amount: null,
    coupon_rate: null,
    coupon_frequency: null,
    next_coupon_date: null,
    total_aci: '–',
    ytm: null,
  },
})

const cryptoDetail = () => ({
  id: 3,
  instrument_type: 'Crypto',
  ISIN: 'CRYPTO:BTC',
  name: 'Fixture Coin',
  currency: 'USD',
  first_investment: '01-Jan-26',
  open_position: '9007199254740993.123456789',
  current_value: '$500.00',
  realized: '–',
  unrealized: '–',
  capital_distribution: '$500.00',
  irr: 'NA',
  crypto_reward_native_quantity: '9007199254740993.123456789',
  crypto_reward_fiat_value: '500.00',
})

const transactionsPage = (total, page = 1) => ({
  transactions: Array.from({ length: Math.min(10, total) }, (_, index) => ({ id: index + 1 })),
  total_items: total,
  page,
})

async function mountPage() {
  const pinia = createPinia()
  await usePortfolioContextStore(pinia).reconcileContext()
  useAppStore(pinia)
  const wrapper = mount(SecurityDetailPage, {
    shallow: false,
    global: { plugins: [pinia], stubs: securityPageStubs() },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  route = reactive({ params: { id: 1 } })
  configureContextFixture('2026-01-02')
  mocks.getAccountChoices.mockResolvedValue({ options: [] })
  mocks.getSecurityDetail.mockImplementation((id) => {
    if (id === 1) return Promise.resolve(stockDetail())
    if (id === 2) return Promise.resolve(bondDetail())
    return Promise.resolve(cryptoDetail())
  })
  mocks.getSecurityPriceHistory.mockResolvedValue([{ date: '2025-06-01', price: '100' }])
  mocks.getSecurityPositionHistory.mockResolvedValue([{ date: '2025-06-01', position: '1' }])
  mocks.getSecurityTransactions.mockImplementation((_id, pagination) =>
    Promise.resolve(transactionsPage(23, pagination.page)))
})

describe('security detail characterization (incumbent surface)', () => {
  it('fetches exactly the five characterized resources on mount and renders the stock page', async () => {
    const wrapper = await mountPage()
    expect(mocks.getSecurityDetail).toHaveBeenCalledTimes(1)
    expect(mocks.getSecurityPriceHistory).toHaveBeenCalledTimes(1)
    expect(mocks.getSecurityPositionHistory).toHaveBeenCalledTimes(1)
    expect(mocks.getSecurityTransactions).toHaveBeenCalledTimes(1)
    expect(mocks.getAccountChoices).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('update-page-title').at(-1)).toEqual(['Fixture Stock'])
    const text = wrapper.text()
    expect(text).toContain('Fixture Stock')
    expect(text).toContain('US0000000001 · Stock · USD')
    expect(text).toContain('Basic Information')
    expect(text).toContain('Current Position:')
    expect(text).toContain('10.000000000')
    expect(text).toContain('Buy-in Price:')
    expect(text).toContain('101.50')
    expect(text).toContain('Current Price:')
    expect(text).toContain('102.25')
    expect(text).toContain('Current Value:')
    expect(text).toContain('$1,022.50')
    expect(text).toContain('Realized Gain/Loss:')
    expect(text).toContain('$12.50')
    expect(text).toContain('IRR:')
    expect(text).toContain('1.25%')
    expect(text).not.toContain('Crypto Rewards')
    expect(text).not.toContain('Bond Information')
    expect(text).toContain('Price History')
    expect(text).toContain('Position History')
    expect(text).toContain('Showing 1-10 of 23 entries')
    wrapper.unmount()
  })

  it('renders the populated bond page with verbatim percentage and bond-only rows', async () => {
    route.params.id = 2
    const wrapper = await mountPage()
    const text = wrapper.text()
    expect(text).toContain('99.125000%')
    expect(text).toContain('Total Accrued Interest:')
    expect(text).toContain('25.00')
    expect(text).toContain('(net of ACI paid at acquisition)')
    expect(text).toContain('YTM at Acquisition:')
    expect(text).toContain('4.51%')
    expect(text).toContain('Bond Information')
    expect(text).toContain('Current Nominal:')
    expect(text).toContain('2,000.00')
    expect(text).toContain('Initial Nominal:')
    expect(text).toContain('2,400.00')
    expect(text).toContain('(Amortizing)')
    expect(text).toContain('Coupon per Bond:')
    expect(text).toContain('43.75')
    expect(text).toContain('Coupon Rate:')
    expect(text).toContain('4.375000%')
    expect(text).toContain('2x per year')
    expect(text).toContain('90 / 181 days')
    expect(text).toContain('($17.50)')
    expect(wrapper.emitted('update-page-title').at(-1)).toEqual(['Fixture Bond'])
    wrapper.unmount()
  })

  it('keeps the bond section visible with explicit gaps when bond metadata is missing', async () => {
    mocks.getSecurityDetail.mockImplementation((id) =>
      id === 2 ? Promise.resolve(sparseBondDetail()) : Promise.resolve(stockDetail()))
    route.params.id = 2
    const wrapper = await mountPage()
    const text = wrapper.text()
    expect(text).toContain('Bond Information')
    expect(text).toContain('Bond Type:')
    expect(text).toContain('Standard')
    // Missing values suppress only their own rows.
    expect(text).not.toContain('Current Nominal:')
    expect(text).not.toContain('Coupon per Bond:')
    expect(text).not.toContain('Credit Rating:')
    expect(text).not.toContain('Total Accrued Interest:')
    expect(text).not.toContain('YTM at Acquisition:')
    wrapper.unmount()
  })

  it('renders crypto rewards with beyond-safe-integer quantities verbatim', async () => {
    route.params.id = 3
    const wrapper = await mountPage()
    const text = wrapper.text()
    expect(text).toContain('Crypto Rewards')
    expect(text).toContain('Native rewards')
    expect(text).toContain('9007199254740993.123456789')
    expect(text).toContain('Fiat reward value')
    expect(text).toContain('500.00')
    expect(wrapper.emitted('update-page-title').at(-1)).toEqual(['Fixture Coin'])
    wrapper.unmount()
  })

  it('counts period changes as price+position+transactions refetches with the page reset', async () => {
    const wrapper = await mountPage()
    // Move to page 2 first: the deep transactionOptions watch refetches once.
    wrapper.vm.transactionOptions.page = 2
    await flush()
    expect(mocks.getSecurityTransactions).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityTransactions.mock.calls.at(-1)[1]).toEqual({ page: 2, itemsPerPage: 10 })
    await wrapper.find('.timeline-selector button.period:nth-child(9)').trigger('click')
    await flush()
    expect(mocks.getSecurityPriceHistory).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityPriceHistory.mock.calls.at(-1)[1]).toBe('All')
    expect(mocks.getSecurityPositionHistory).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityPositionHistory.mock.calls.at(-1)[1]).toBe('All')
    // Page reset back to 1 on the period change — one transactions fetch.
    expect(mocks.getSecurityTransactions).toHaveBeenCalledTimes(3)
    expect(mocks.getSecurityTransactions.mock.calls.at(-1)[1]).toEqual({ page: 1, itemsPerPage: 10 })
    expect(mocks.getSecurityDetail).toHaveBeenCalledTimes(1)
    expect(mocks.getAccountChoices).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Showing 1-10 of 23 entries')
    wrapper.unmount()
  })

  it('counts account changes as detail+price+position+transactions refetches, never accounts', async () => {
    const wrapper = await mountPage()
    wrapper.vm.selectedAccount = { type: 'account', id: 7 }
    await flush()
    expect(mocks.getSecurityDetail).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityDetail.mock.calls.at(-1)[1]).toBe(7)
    expect(mocks.getSecurityPriceHistory.mock.calls.at(-1)).toHaveLength(3)
    expect(mocks.getSecurityPriceHistory.mock.calls.at(-1)[1]).toBe('1Y')
    expect(mocks.getSecurityPositionHistory).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityPositionHistory.mock.calls.at(-1)[2]).toBe(7)
    expect(mocks.getSecurityTransactions).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityTransactions.mock.calls.at(-1)[3]).toBe(7)
    expect(mocks.getAccountChoices).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps the rendered page on the newer security when the older detail lands last', async () => {
    const stale = deferred()
    mocks.getSecurityDetail.mockImplementation((id) =>
      id === 1 ? stale.promise : Promise.resolve(bondDetail()))
    const wrapper = await mountPage()
    route.params.id = 2
    await flushPromises()
    stale.resolve(stockDetail())
    await flushPromises()
    expect(wrapper.text()).toContain('Fixture Bond')
    expect(wrapper.text()).toContain('99.125000%')
    expect(wrapper.emitted('update-page-title').at(-1)).toEqual(['Fixture Bond'])
    wrapper.unmount()
  })

  it('refetches all five resources on a data refresh trigger', async () => {
    const wrapper = await mountPage()
    const context = usePortfolioContextStore()
    context.triggerDataRefresh()
    await nextTick()
    await flush()
    expect(mocks.getSecurityDetail).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityPriceHistory).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityPositionHistory).toHaveBeenCalledTimes(2)
    expect(mocks.getSecurityTransactions).toHaveBeenCalledTimes(2)
    expect(mocks.getAccountChoices).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
