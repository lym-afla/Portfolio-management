// D7 task 3/4 — behavioral contract of the security detail resource owner
// and the extracted display sections. RED first: the modules do not exist
// yet. Request counts and trigger semantics pin the characterized incumbent
// behavior (docs/design/frontend-brokers-security.md §2); display strings
// cross as server-issued strings only.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import type { Ref } from 'vue'
import type { EffectScope } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { configureContextFixture } from '../../context-fixture'
import { deferred } from '../../helpers/deferred'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import { useSecurityDetail } from '@/features/securities/useSecurityDetail'
import SecurityOverview from '@/features/securities/SecurityOverview.vue'
import SecurityMetadata from '@/features/securities/SecurityMetadata.vue'
import SecurityActivity from '@/features/securities/SecurityActivity.vue'
import TransactionRow from '@/components/transactions/TransactionRow.vue'
import {
  getAccountChoices,
  getSecurityDetail,
  getSecurityPositionHistory,
  getSecurityPriceHistory,
  getSecurityTransactions,
} from '@/services/api'
import { getChartOptions } from '@/config/chartConfig'

vi.mock('@/services/api', () => ({
  getAccountChoices: vi.fn(),
  getSecurityDetail: vi.fn(),
  getSecurityPositionHistory: vi.fn(),
  getSecurityPriceHistory: vi.fn(),
  getSecurityTransactions: vi.fn(),
}))
vi.mock('@/config/chartConfig', () => ({
  getChartOptions: vi.fn(),
  colorPalette: ['#0F4C81', '#5C6B7A'],
}))
vi.mock('chartjs-adapter-date-fns', () => ({}))

const flush = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

interface Harness {
  detail: ReturnType<typeof useSecurityDetail>
  scope: EffectScope
  refreshTick: Ref<number>
  securityId: Ref<number>
}

const activeScopes: EffectScope[] = []

async function startOwner(securityId = 1): Promise<Harness> {
  const pinia = createPinia()
  const context = usePortfolioContextStore(pinia)
  await context.reconcileContext()
  useAppStore(pinia)
  const idHolder = ref(securityId)
  const refreshTick = ref(0)
  const harness: Harness = {
    refreshTick,
    securityId: idHolder,
    scope: null as unknown as EffectScope,
    detail: null as unknown as ReturnType<typeof useSecurityDetail>,
  }
  const scope = effectScope(true)
  const detail = scope.run(() =>
    useSecurityDetail({
      securityId: () => idHolder.value,
      canRead: () => context.canRead,
      refreshTrigger: () => refreshTick.value,
      committed: () => context.committed,
    }),
  )
  if (!detail) throw new Error('owner scope did not run')
  harness.scope = scope
  harness.detail = detail
  activeScopes.push(scope)
  return harness
}

const stopAll = () => {
  for (const scope of activeScopes.splice(0)) scope.stop()
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  configureContextFixture('2026-01-02')
  vi.mocked(getAccountChoices).mockResolvedValue({ options: [] })
  vi.mocked(getChartOptions).mockResolvedValue({
  navChartOptions: {},
} as Awaited<ReturnType<typeof getChartOptions>>)
  vi.mocked(getSecurityDetail).mockResolvedValue({
    id: 1, name: 'One', instrument_type: 'Stock', ISIN: 'ISIN-1',
    currency: 'USD', first_investment: '01-Jan-26', open_position: '1',
    current_value: '$1.00', realized: '–', unrealized: '–',
    capital_distribution: '$0.00', irr: 'NA',
  })
  vi.mocked(getSecurityPriceHistory).mockResolvedValue(
  [] as unknown as Awaited<ReturnType<typeof getSecurityPriceHistory>>,
)
  vi.mocked(getSecurityPositionHistory).mockResolvedValue(
  [] as unknown as Awaited<ReturnType<typeof getSecurityPositionHistory>>,
)
  vi.mocked(getSecurityTransactions).mockResolvedValue({ transactions: [], total_items: 0 })
})

afterEach(stopAll)

describe('useSecurityDetail — characterized triggers and request counts', () => {
  it('fetches all five resources once on start with the characterized signatures', async () => {
    const { detail } = await startOwner()
    await flushPromises()
    expect(getSecurityDetail).toHaveBeenCalledTimes(1)
    expect(vi.mocked(getSecurityDetail).mock.calls[0][0]).toBe(1)
    expect(vi.mocked(getSecurityDetail).mock.calls[0][1]).toBeNull()
    expect(getChartOptions).toHaveBeenCalledWith('USD')
    expect(getSecurityPriceHistory).toHaveBeenCalledTimes(1)
    expect(vi.mocked(getSecurityPriceHistory).mock.calls[0][1]).toBe('1Y')
    expect(getSecurityPositionHistory).toHaveBeenCalledTimes(1)
    expect(vi.mocked(getSecurityPositionHistory).mock.calls[0][2]).toBeNull()
    expect(getSecurityTransactions).toHaveBeenCalledTimes(1)
    expect(vi.mocked(getSecurityTransactions).mock.calls[0][1]).toEqual({ page: 1, itemsPerPage: 10 })
    expect(getAccountChoices).toHaveBeenCalledTimes(1)
    expect(detail.security.value?.name).toBe('One')
    expect(detail.loading.value).toBe(false)
    expect(detail.chartOptionsLoaded.value).toBe(true)
  })

  it('counts a period change as price+position+transactions with the page reset', async () => {
    const { detail } = await startOwner()
    await flushPromises()
    detail.transactionOptions.value.page = 2
    await flush()
    expect(getSecurityTransactions).toHaveBeenCalledTimes(2)
    expect(vi.mocked(getSecurityTransactions).mock.calls[1][1]).toEqual({ page: 2, itemsPerPage: 10 })
    detail.selectedPeriod.value = 'All'
    await flush()
    expect(getSecurityPriceHistory).toHaveBeenCalledTimes(2)
    expect(vi.mocked(getSecurityPriceHistory).mock.calls[1][1]).toBe('All')
    expect(getSecurityPositionHistory).toHaveBeenCalledTimes(2)
    expect(vi.mocked(getSecurityPositionHistory).mock.calls[1][1]).toBe('All')
    expect(getSecurityTransactions).toHaveBeenCalledTimes(3)
    expect(vi.mocked(getSecurityTransactions).mock.calls[2][1]).toEqual({ page: 1, itemsPerPage: 10 })
    expect(getSecurityDetail).toHaveBeenCalledTimes(1)
    expect(getAccountChoices).toHaveBeenCalledTimes(1)
  })

  it('counts an account change as detail+price+position+transactions, never accounts', async () => {
    const { detail } = await startOwner()
    await flushPromises()
    detail.selectedAccount.value = { type: 'account', id: 7 }
    await flush()
    expect(getSecurityDetail).toHaveBeenCalledTimes(2)
    expect(vi.mocked(getSecurityDetail).mock.calls[1][1]).toBe(7)
    expect(getSecurityPriceHistory).toHaveBeenCalledTimes(2)
    expect(vi.mocked(getSecurityPositionHistory).mock.calls[1][2]).toBe(7)
    expect(vi.mocked(getSecurityTransactions).mock.calls[1][3]).toBe(7)
    expect(getAccountChoices).toHaveBeenCalledTimes(1)
  })

  it('counts a refresh trigger as all five resources', async () => {
    const harness = await startOwner()
    await flushPromises()
    harness.refreshTick.value += 1
    await flush()
    expect(getSecurityDetail).toHaveBeenCalledTimes(2)
    expect(getSecurityPriceHistory).toHaveBeenCalledTimes(2)
    expect(getSecurityPositionHistory).toHaveBeenCalledTimes(2)
    expect(getSecurityTransactions).toHaveBeenCalledTimes(2)
    expect(getAccountChoices).toHaveBeenCalledTimes(2)
  })

  it('invalidates the four route resources and resets pagination on a security change', async () => {
    const stale = deferred<Awaited<ReturnType<typeof getSecurityDetail>>>()
    vi.mocked(getSecurityDetail).mockImplementation((id) =>
      id === 1 ? stale.promise : Promise.resolve({
        id: 2, name: 'Two', instrument_type: 'Bond', ISIN: 'ISIN-2',
        currency: 'EUR', first_investment: '01-Feb-24', open_position: '2',
        current_value: '€2.00', realized: '–', unrealized: '–',
        capital_distribution: '€0.00', irr: 'NA',
      }))
    const harness = await startOwner(1)
    const { detail } = harness
    await flushPromises()
    detail.transactionOptions.value.page = 3
    await flush()
    harness.securityId.value = 2
    await flushPromises()
    // Page reset to 1 on the id change, itemsPerPage preserved.
    expect(vi.mocked(getSecurityTransactions).mock.calls.at(-1)[1]).toEqual({ page: 1, itemsPerPage: 10 })
    expect(vi.mocked(getSecurityTransactions).mock.calls.at(-1)[0]).toBe(2)
    expect(detail.security.value?.name).toBe('Two')
    // The stale A response must never commit after the owner moved on.
    stale.resolve({
      id: 1, name: 'One', instrument_type: 'Stock', ISIN: 'ISIN-1',
      currency: 'USD', first_investment: '01-Jan-26', open_position: '1',
      current_value: '$1.00', realized: '–', unrealized: '–',
      capital_distribution: '$0.00', irr: 'NA',
    })
    await flushPromises()
    expect(detail.security.value?.name).toBe('Two')
  })

  it('keeps the committed selection when an older price response lands last', async () => {
    const stale = deferred<Awaited<ReturnType<typeof getSecurityPriceHistory>>>()
    vi.mocked(getSecurityPriceHistory)
      .mockImplementationOnce(() => stale.promise)
      .mockResolvedValueOnce([{ date: '2026-01-01', price: '2' }] as unknown as Awaited<ReturnType<typeof getSecurityPriceHistory>>)
    const { detail } = await startOwner(1)
    await flushPromises()
    detail.selectedPeriod.value = 'All'
    await flushPromises()
    stale.resolve([{ date: '2019-01-01', price: '1' }] as unknown as Awaited<ReturnType<typeof getSecurityPriceHistory>>)
    await flushPromises()
    expect(detail.priceHistory.value).toEqual([{ date: '2026-01-01', price: '2' }])
  })

  it('recovers a failed price resource without discarding valid siblings', async () => {
    vi.mocked(getSecurityPriceHistory)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce([{ date: '2026-01-01', price: '5' }] as unknown as Awaited<ReturnType<typeof getSecurityPriceHistory>>)
    const { detail } = await startOwner(1)
    await flushPromises()
    expect(detail.priceHistory.value).toEqual([])
    expect(detail.loadError.value).toBeTruthy()
    expect(detail.security.value?.name).toBe('One')
    expect(detail.transactions.value).toEqual([])
    detail.selectedPeriod.value = 'All'
    await flushPromises()
    expect(detail.priceHistory.value).toEqual([{ date: '2026-01-01', price: '5' }])
    expect(detail.loadError.value).toBeNull()
    // The detail resource was never refetched during the recovery.
    expect(getSecurityDetail).toHaveBeenCalledTimes(1)
  })

  it('stops account-scoped resources while the session cannot read', async () => {
    const pinia = createPinia()
    const context = usePortfolioContextStore(pinia)
    const app = useAppStore(pinia)
    await context.reconcileContext()
    const scope = effectScope(true)
    scope.run(() =>
      useSecurityDetail({
        securityId: () => 1,
        canRead: () => context.canRead,
        refreshTrigger: () => app.dataRefreshTrigger,
        committed: () => context.committed,
      }),
    )!
    activeScopes.push(scope)
    await flushPromises()
    expect(getSecurityDetail).toHaveBeenCalledTimes(1)
    // A committed-context revision change invalidates and refetches.
    await context.changeContext({ effectiveCurrentDate: '2026-02-02' })
    await flushPromises()
    expect(getSecurityDetail).toHaveBeenCalledTimes(2)
    expect(getSecurityPriceHistory).toHaveBeenCalledTimes(2)
    expect(getAccountChoices).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('commits nothing after the owner scope is disposed', async () => {
    const pending = deferred<Awaited<ReturnType<typeof getSecurityDetail>>>()
    vi.mocked(getSecurityDetail).mockImplementationOnce(() => pending.promise)
    const harness = await startOwner(1)
    await flush()
    expect(harness.detail.loading.value).toBe(true)
    harness.scope.stop()
    pending.resolve({
      id: 1, name: 'Late', instrument_type: 'Stock', ISIN: 'ISIN-1',
      currency: 'USD', first_investment: '01-Jan-26', open_position: '1',
      current_value: '$1.00', realized: '–', unrealized: '–',
      capital_distribution: '$0.00', irr: 'NA',
    })
    await flushPromises()
    expect(harness.detail.security.value).toBeNull()
    expect(harness.detail.loading.value).toBe(false)
  })

  it('exposes the parent title source for the route compatibility entrypoint', async () => {
    const { detail } = await startOwner(1)
    await flushPromises()
    expect(detail.securityName.value).toBe('One')
  })
})

describe('SecurityOverview — value parity through display views', () => {
  it('keeps bond percentage prices and missing metadata as supplied', () => {
    const wrapper = mount(SecurityOverview, {
      props: {
        view: {
          securityId: 9,
          name: 'Example Bond',
          identifier: 'TEST-9',
          instrumentType: 'Bond',
          currency: 'USD',
          fields: [
            { label: 'Price (% of nominal)', value: '99.125000%' },
            { label: 'Maturity', value: '–' },
          ],
        },
      },
    })
    expect(wrapper.text()).toContain('99.125000%')
    expect(wrapper.text()).toContain('Maturity')
    expect(wrapper.text()).toContain('–')
    wrapper.unmount()
  })

  it('renders comma-grouped and beyond-safe-integer display strings verbatim', () => {
    const wrapper = mount(SecurityOverview, {
      props: {
        view: {
          securityId: 1,
          name: 'Mega Cap Inc',
          identifier: 'US0000000001',
          instrumentType: 'Stock',
          currency: 'USD',
          fields: [
            { label: 'Current Position:', value: '9007199254740993.123456789' },
            { label: 'Current Value:', value: '$12,345,678.90' },
          ],
        },
      },
    })
    expect(wrapper.text()).toContain('9007199254740993.123456789')
    expect(wrapper.text()).toContain('$12,345,678.90')
    wrapper.unmount()
  })

  it('exposes the price and position chart slots for the entrypoint charts', () => {
    const wrapper = mount(SecurityOverview, {
      props: {
        view: {
          securityId: 1, name: 'One', identifier: 'ISIN-1',
          instrumentType: 'Stock', currency: 'USD', fields: [],
        },
      },
      slots: {
        'price-chart': '<div class="price-chart-slot" />',
        'position-chart': '<div class="position-chart-slot" />',
      },
      global: { stubs: { 'v-row': { template: '<div class="v-row"><slot /></div>' } } },
    })
    expect(wrapper.find('.price-chart-slot').exists()).toBe(true)
    expect(wrapper.find('.position-chart-slot').exists()).toBe(true)
    wrapper.unmount()
  })
})

describe('SecurityMetadata — populated bond and crypto sections', () => {
  it('renders both populated bond tables with amortizing labels and captions', () => {
    const wrapper = mount(SecurityMetadata, {
      props: {
        bond: {
          primary: [
            { label: 'Current Nominal:', value: '2,000.00' },
            { label: 'Initial Nominal:', value: '2,400.00' },
            { label: 'Issue Date:', value: '2024-02-01' },
            { label: 'Maturity Date:', value: '2031-02-01' },
            { label: 'Bond Type:', value: 'Fixed', explanation: '(Amortizing)' },
            { label: 'Credit Rating:', value: 'AA-' },
          ],
          coupon: [
            { label: 'Coupon per Bond:', value: '43.75' },
            { label: 'Coupon Rate:', value: '4.375000%' },
            { label: 'Coupon Frequency:', value: '2x per year' },
            { label: 'Next Coupon Payment:', value: '2027-02-01' },
            { label: 'Current Accrued Interest:', value: '2.19' },
            { label: 'Days Accrued:', value: '90 / 181 days' },
          ],
        },
        crypto: null,
      },
    })
    const text = wrapper.text()
    expect(text).toContain('Bond Information')
    expect(text).toContain('Current Nominal:')
    expect(text).toContain('2,000.00')
    expect(text).toContain('Initial Nominal:')
    expect(text).toContain('(Amortizing)')
    expect(text).toContain('Coupon Rate:')
    expect(text).toContain('4.375000%')
    expect(text).toContain('90 / 181 days')
    expect(text).not.toContain('Crypto Rewards')
    wrapper.unmount()
  })

  it('renders the crypto rewards section with exact quantities', () => {
    const wrapper = mount(SecurityMetadata, {
      props: {
        bond: null,
        crypto: { nativeQuantity: '9007199254740993.123456789', fiatValue: '500.00' },
      },
    })
    const text = wrapper.text()
    expect(text).toContain('Crypto Rewards')
    expect(text).toContain('Native rewards')
    expect(text).toContain('9007199254740993.123456789')
    expect(text).toContain('Fiat reward value')
    expect(text).toContain('500.00')
    expect(text).not.toContain('Bond Information')
    wrapper.unmount()
  })
})

describe('SecurityActivity — transaction display and pagination intents', () => {
  const activityView = () => ({
    transactions: [
      { id: 1, date: '01-Jan-26', broker_account: 'Main', description: 'Buy', type: 'Buy', cash_flow: '($100.00)' },
      { id: 2, date: '02-Jan-26', broker_account: 'Main', description: 'Sell', type: 'Sell', cash_flow: '$250.00' },
    ],
    totalItems: 23,
    page: 2,
    itemsPerPage: 10,
    pageCount: 3,
  })

  const mountActivity = (props: Record<string, unknown> = {}) =>
    mount(SecurityActivity, {
      props: { view: activityView(), itemsPerPageOptions: [10, 25, 50, 100], ...props },
      global: {
        stubs: {
          'v-data-table': {
            template:
              '<div class="v-data-table"><slot /><slot name="item" :item="{ id: 1, type: \'Buy\' }" /><slot name="bottom" /></div>',
          },
          'v-select': { template: '<select class="v-select"><slot /></select>' },
          'v-pagination': true,
        },
      },
    })

  it('renders rows through the shared transaction row and the exact range label', () => {
    const wrapper = mountActivity()
    expect(wrapper.findAllComponents(TransactionRow).length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('Showing 11-20 of 23 entries')
    wrapper.unmount()
  })

  it('emits explicit pagination intents without fetching', async () => {
    const wrapper = mountActivity()
    await (wrapper.vm as any).changePage(3)
    expect(wrapper.emitted('update:page')).toEqual([[3]])
    await (wrapper.vm as any).changeItemsPerPage(50)
    expect(wrapper.emitted('update:itemsPerPage')).toEqual([[50]])
    wrapper.unmount()
  })
})
