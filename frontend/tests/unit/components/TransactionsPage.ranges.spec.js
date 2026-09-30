import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import TransactionsPage from '@/views/TransactionsPage.vue'

const mocks = vi.hoisted(() => ({ getTransactions: vi.fn() }))
vi.mock('@/services/api', () => ({
  getTransactions: mocks.getTransactions,
  deleteTransaction: vi.fn(), deleteFXTransaction: vi.fn(),
  getTransactionDetails: vi.fn(), getFXTransactionDetails: vi.fn(),
}))
beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  configureContextFixture('2026-09-08')
  mocks.getTransactions.mockResolvedValue({ transactions: [], total_items: 0, currencies: [] })
})

it('applies a transaction range through one watcher request and resets pagination', async () => {
  const pinia = createPinia()
  const context = usePortfolioContextStore(pinia)
  const app = useAppStore(pinia)
  await context.reconcileContext()
  const wrapper = mount(TransactionsPage, { shallow: true, global: { plugins: [pinia] } })
  await flushPromises()
  mocks.getTransactions.mockClear()
  app.updateTableSettings({ page: 5 })
  await flushPromises()
  mocks.getTransactions.mockClear()
  wrapper.vm.handleDateRangeChange({ dateRange: 'custom', dateFrom: '2020-01-01', dateTo: '2020-03-31' })
  await flushPromises()
  expect(app.tableSettings).toMatchObject({ timespan: 'custom', dateFrom: '2020-01-01', dateTo: '2020-03-31', page: 1 })
  expect(mocks.getTransactions).toHaveBeenCalledTimes(1)
  expect(mocks.getTransactions).toHaveBeenCalledWith('2020-01-01', '2020-03-31', 1, expect.any(Number), expect.any(String), expect.any(Object))
  wrapper.unmount()
})

it('recomputes all-time end date but leaves an explicit transaction range intact', async () => {
  const pinia = createPinia()
  const context = usePortfolioContextStore(pinia)
  await context.reconcileContext()
  const wrapper = mount(TransactionsPage, { shallow: true, global: { plugins: [pinia] } })
  await flushPromises()
  configureContextFixture('2025-12-31')
  await context.reconcileContext()
  await flushPromises()
  expect(wrapper.vm.dateTo).toBe('2025-12-31')
  wrapper.vm.handleDateRangeChange({ dateRange: 'custom', dateFrom: '2020-01-01', dateTo: '2020-03-31' })
  await flushPromises()
  configureContextFixture('2024-02-29')
  await context.reconcileContext()
  await flushPromises()
  expect(wrapper.vm.dateFrom).toBe('2020-01-01')
  expect(wrapper.vm.dateTo).toBe('2020-03-31')
  wrapper.unmount()
})
