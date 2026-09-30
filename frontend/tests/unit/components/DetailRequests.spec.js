import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia } from 'pinia'
import { configureContextFixture } from '../context-fixture'
import { deferred } from '../helpers/deferred'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import SecurityDetailPage from '@/views/database/SecurityDetailPage.vue'
import SummaryPage from '@/views/SummaryPage.vue'
import PricesPage from '@/views/database/PricesPage.vue'
import { useAppStore } from '@/stores/app'

const mocks = vi.hoisted(() => ({
  getSecurityDetail: vi.fn(), getSecurityPriceHistory: vi.fn(), getSecurityPositionHistory: vi.fn(),
  getSecurityTransactions: vi.fn(), getAccountChoices: vi.fn(), getYearOptions: vi.fn(),
  getAccountPerformanceSummary: vi.fn(), getPortfolioBreakdownSummary: vi.fn(),
  getPrices: vi.fn(), getAssetTypes: vi.fn(), getAccounts: vi.fn(), getSecurities: vi.fn(),
}))
let route
vi.mock('vue-router', () => ({
  useRoute: () => route, useRouter: () => ({ push: vi.fn() }),
  createRouter: () => ({ beforeEach() {}, afterEach() {} }), createWebHistory: () => ({}),
}))
vi.mock('@/services/api', () => ({
  ...mocks, getPriceDetails: vi.fn(), deletePrice: vi.fn(),
}))
vi.mock('@/config/chartConfig', () => ({ getChartOptions: vi.fn().mockResolvedValue({}), colorPalette: [] }))
vi.mock('chartjs-adapter-date-fns', () => ({}))

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  route = reactive({ params: { id: 1 } })
  configureContextFixture('2026-09-08')
  mocks.getAccountChoices.mockResolvedValue({ options: [] })
  mocks.getYearOptions.mockResolvedValue([2026])
  mocks.getSecurityDetail.mockResolvedValue({ id: 1, name: 'One', currency: 'USD' })
  mocks.getSecurityPriceHistory.mockResolvedValue([])
  mocks.getSecurityPositionHistory.mockResolvedValue([])
  mocks.getSecurityTransactions.mockResolvedValue({ transactions: [], total_items: 0 })
  mocks.getAssetTypes.mockResolvedValue([])
  mocks.getAccounts.mockResolvedValue([])
  mocks.getSecurities.mockResolvedValue([])
})

async function setup(component) {
  const pinia = createPinia()
  await usePortfolioContextStore(pinia).reconcileContext()
  const wrapper = mount(component, { shallow: true, global: { plugins: [pinia], provide: { showError: vi.fn() } } })
  await flushPromises()
  return { wrapper, app: useAppStore(pinia) }
}

it('accepts details only for the current security route ID', async () => {
  const old = deferred()
  mocks.getSecurityDetail.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ id: 2, name: 'Two', currency: 'EUR' })
  const { wrapper } = await setup(SecurityDetailPage)
  route.params.id = 2
  await flushPromises()
  expect(mocks.getSecurityDetail).toHaveBeenCalledTimes(2)
  old.resolve({ id: 1, name: 'One', currency: 'USD' })
  await flushPromises()
  expect(wrapper.vm.security.id).toBe(2)
  expect(wrapper.emitted('update-page-title').at(-1)).toEqual(['Two'])
  wrapper.unmount()
})

it('loads detail panels independently when price history fails', async () => {
  mocks.getSecurityPriceHistory.mockRejectedValueOnce(new Error('offline'))
  mocks.getSecurityPositionHistory.mockResolvedValueOnce([{ date: '2026-09-08', position: '2' }])
  const { wrapper } = await setup(SecurityDetailPage)
  expect(wrapper.vm.positionHistory).toEqual([{ date: '2026-09-08', position: '2' }])
  expect(wrapper.vm.loadingPriceChart).toBe(false)
  expect(wrapper.vm.loadingPositionChart).toBe(false)
  wrapper.unmount()
})

it('ignores old detail history after a new period finishes', async () => {
  const old = deferred()
  mocks.getSecurityPriceHistory.mockReturnValueOnce(old.promise).mockResolvedValueOnce([{ date: '2026-09-08', price: '2' }])
  const { wrapper } = await setup(SecurityDetailPage)
  wrapper.vm.selectedPeriod = 'All'
  await flushPromises()
  old.resolve([{ date: '2020-01-01', price: '1' }])
  await flushPromises()
  expect(wrapper.vm.priceHistory).toEqual([{ date: '2026-09-08', price: '2' }])
  wrapper.unmount()
})

it('keeps a newer summary year and the account panel through an obsolete response', async () => {
  const old = deferred()
  mocks.getAccountPerformanceSummary.mockResolvedValue({
    public_markets_context: { lines: [] }, restricted_investments_context: { lines: [] },
    total_context: { line: { nav: '200' }, years: [2026] },
  })
  mocks.getPortfolioBreakdownSummary.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ consolidated_context: [{ name: 'New' }] })
  const { wrapper } = await setup(SummaryPage)
  wrapper.vm.handleYearChange('2025')
  await flushPromises()
  old.resolve({ consolidated_context: [{ name: 'Old' }] })
  await flushPromises()
  expect(wrapper.vm.portfolioBreakdownData.consolidated_context[0].name).toBe('New')
  expect(wrapper.vm.totalData.nav).toBe('200')
  mocks.getPortfolioBreakdownSummary.mockRejectedValueOnce(new Error('offline'))
  wrapper.vm.handleYearChange('2024')
  await flushPromises()
  expect(wrapper.vm.totalData.nav).toBe('200')
  expect(wrapper.vm.loading.portfolioBreakdown).toBe(false)
  wrapper.unmount()
})

it('keeps the current price page when old transport ignores cancellation', async () => {
  const old = deferred()
  mocks.getPrices.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ prices: [{ id: 2 }], total_items: 1 })
  const { wrapper, app } = await setup(PricesPage)
  app.updateTableSettings({ page: 2 })
  await flushPromises()
  old.resolve({ prices: [{ id: 1 }], total_items: 99 })
  await flushPromises()
  expect(wrapper.vm.priceData).toEqual([{ id: 2 }])
  expect(wrapper.vm.totalItems).toBe(1)
  wrapper.unmount()
})
