import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { configureContextFixture } from '../context-fixture'
import { deferred } from '../helpers/deferred'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import { configurePortfolioContextBackend } from '@/services/api/context'
import FXPage from '@/views/database/FXPage.vue'
import TransactionsPage from '@/views/TransactionsPage.vue'
import OpenPositionsPage from '@/views/OpenPositionsPage.vue'
import ClosedPositionsPage from '@/views/ClosedPositionsPage.vue'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import AccountsPage from '@/views/database/AccountsPage.vue'
import BrokersPage from '@/views/database/BrokersPage.vue'
import SecuritiesPage from '@/views/database/SecuritiesPage.vue'

const mocks = vi.hoisted(() => ({
  getFXData: vi.fn(), getTransactions: vi.fn(), getOpenPositions: vi.fn(), getClosedPositions: vi.fn(),
  getAccountsTable: vi.fn(), getBrokersTable: vi.fn(), getSecuritiesForDatabase: vi.fn(),
}))
vi.mock('@/services/api', () => ({
  ...mocks, getYearOptions: vi.fn().mockResolvedValue([2026]),
  deleteFXRate: vi.fn(), getFXDetails: vi.fn(),
  deleteTransaction: vi.fn(), deleteFXTransaction: vi.fn(),
  getTransactionDetails: vi.fn(), getFXTransactionDetails: vi.fn(),
  deleteAccount: vi.fn(), getAccountDetails: vi.fn(),
  deleteBroker: vi.fn(), getBrokerDetails: vi.fn(),
  deleteSecurity: vi.fn(), getSecurityDetails: vi.fn(),
}))

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  configureContextFixture('2026-09-08')
})

it.each([
  [AccountsPage, 'getAccountsTable', 'accounts'],
  [BrokersPage, 'getBrokersTable', 'items'],
  [SecuritiesPage, 'getSecuritiesForDatabase', 'securities'],
])('keeps the current database page after an old result (%s)', async (component, key, rows) => {
  const old = deferred()
  const current = deferred()
  mocks[key].mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
  const { wrapper, app } = await setup(component)
  app.updateTableSettings({ page: 2 })
  await flushPromises()
  current.resolve({ [rows]: [{ id: 2, name: 'New', cash: { EUR: '20' } }], total_items: 1, totals: { nav: '200' } })
  await flushPromises()
  old.resolve({ [rows]: [{ id: 1, name: 'Old', cash: { GBP: '10' } }], total_items: 99, totals: { nav: '100' } })
  await flushPromises()
  expect(wrapper.vm.totalItems).toBe(1)
  expect(wrapper.vm[rows === 'items' ? 'brokers' : rows][0].name).toBe('New')
  if (rows !== 'securities') expect(wrapper.vm.totals.nav).toBe('200')
  wrapper.unmount()
})

async function setup(component) {
  const pinia = createPinia()
  const context = usePortfolioContextStore(pinia)
  const app = useAppStore(pinia)
  await context.reconcileContext()
  const wrapper = mount(component, {
    shallow: true,
    global: { plugins: [pinia], stubs: { PositionsPageBase: false } },
  })
  await flushPromises()
  return { wrapper, context, app }
}

it('runs a changed FX search while the previous request is still pending', async () => {
  const old = deferred()
  const current = deferred()
  mocks.getFXData.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
  const { wrapper, app } = await setup(FXPage)
  app.updateTableSettings({ search: 'EUR' })
  await flushPromises()
  expect(mocks.getFXData).toHaveBeenCalledTimes(2)
  expect(mocks.getFXData.mock.calls[0][1].signal.aborted).toBe(true)
  current.resolve({ results: [{ id: 2, date: '2026-09-08', from_currency: 'EUR', to_currency: 'USD', rate: '1.2' }], count: 1 })
  await flushPromises()
  const accepted = JSON.stringify(wrapper.vm.fxData)
  old.resolve({ results: [{ id: 1, date: '2020-01-01', from_currency: 'GBP', to_currency: 'USD', rate: '0.5' }], count: 99 })
  await flushPromises()
  expect(JSON.stringify(wrapper.vm.fxData)).toBe(accepted)
  expect(wrapper.vm.totalItems).toBe(1)
  expect(wrapper.vm.tableLoading).toBe(false)
  wrapper.unmount()
})

it('keeps the latest transaction rows, currencies and count after an old completion', async () => {
  const old = deferred()
  const current = deferred()
  mocks.getTransactions.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
  const { wrapper, app } = await setup(TransactionsPage)
  app.updateTableSettings({ page: 2 })
  await flushPromises()
  expect(mocks.getTransactions).toHaveBeenCalledTimes(2)
  current.resolve({ transactions: [{ id: 'new' }], total_items: 1, currencies: ['EUR'] })
  await flushPromises()
  old.resolve({ transactions: [{ id: 'old' }], total_items: 99, currencies: ['GBP'] })
  await flushPromises()
  expect(wrapper.vm.transactions).toEqual([{ id: 'new' }])
  expect(wrapper.vm.currencies).toEqual(['EUR'])
  expect(wrapper.vm.totalItems).toBe(1)
  wrapper.unmount()
})

it.each([
  [OpenPositionsPage, 'getOpenPositions', 'portfolio_open', 'portfolio_open_totals'],
  [ClosedPositionsPage, 'getClosedPositions', 'portfolio_closed', 'portfolio_closed_totals'],
])('accepts parent totals and cash only with the current positions response (%s)', async (component, key, rows, totals) => {
  const old = deferred()
  const current = deferred()
  mocks[key].mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
  const { wrapper, app } = await setup(component)
  app.updateTableSettings({ page: 2 })
  await flushPromises()
  expect(mocks[key]).toHaveBeenCalledTimes(2)
  current.resolve({ [rows]: [{ name: 'New', type: 'Stock' }], [totals]: { total_nav: '200' }, cash_balances: { EUR: '20' }, total_items: 1 })
  await flushPromises()
  old.resolve({ [rows]: [{ name: 'Old', type: 'Stock' }], [totals]: { total_nav: '100' }, cash_balances: { GBP: '10' }, total_items: 99 })
  await flushPromises()
  expect(wrapper.vm.totals).toEqual({ total_nav: '200' })
  if (key === 'getOpenPositions') expect(wrapper.vm.cashBalances).toEqual({ EUR: '20' })
  expect(wrapper.findComponent(PositionsPageBase).vm.positions[0].name).toBe('New')
  wrapper.unmount()
})

it('invalidates a table synchronously before a context reconciliation await', async () => {
  const old = deferred()
  mocks.getTransactions.mockReturnValueOnce(old.promise).mockResolvedValue({ transactions: [], total_items: 0, currencies: [] })
  const { wrapper, context } = await setup(TransactionsPage)
  const committed = { ...context.committed }
  const canonical = deferred()
  configurePortfolioContextBackend({ read: () => canonical.promise, updateAccount: async () => {}, updateSettings: async () => {} })
  const transition = context.reconcileContext()
  expect(mocks.getTransactions.mock.calls[0][6].signal.aborted).toBe(true)
  old.resolve({ transactions: [{ id: 'old-context' }], total_items: 99, currencies: ['GBP'] })
  await flushPromises()
  expect(context.canRead).toBe(false)
  expect(mocks.getTransactions).toHaveBeenCalledTimes(1)
  expect(wrapper.vm.transactions).toEqual([])
  canonical.resolve(committed)
  await transition
  await flushPromises()
  expect(mocks.getTransactions).toHaveBeenCalledTimes(2)
  expect(wrapper.vm.transactions).toEqual([])
  wrapper.unmount()
})
