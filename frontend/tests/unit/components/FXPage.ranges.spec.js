import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import FXPage from '@/views/database/FXPage.vue'

const mocks = vi.hoisted(() => ({ getFXData: vi.fn() }))
vi.mock('@/services/api', () => ({
  getFXData: mocks.getFXData,
  deleteFXRate: vi.fn(),
  getFXDetails: vi.fn(),
}))

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  configureContextFixture('2026-09-08')
  mocks.getFXData.mockResolvedValue({ results: [], count: 0 })
})

it('commits one FX range tuple and makes one request for an applied range', async () => {
  const pinia = createPinia()
  const context = usePortfolioContextStore(pinia)
  const app = useAppStore(pinia)
  await context.reconcileContext()
  const wrapper = mount(FXPage, { shallow: true, global: { plugins: [pinia] } })
  await flushPromises()
  expect(mocks.getFXData).toHaveBeenCalledTimes(1)
  mocks.getFXData.mockClear()
  app.updateTableSettings({ page: 5 })
  await flushPromises()
  mocks.getFXData.mockClear()
  wrapper.vm.handleDateRangeChange({ dateRange: 'custom', dateFrom: '2020-01-01', dateTo: '2020-03-31' })
  await flushPromises()
  expect(app.tableSettings).toMatchObject({ dateFrom: '2020-01-01', dateTo: '2020-03-31', page: 1 })
  expect(mocks.getFXData).toHaveBeenCalledTimes(1)
  expect(mocks.getFXData).toHaveBeenCalledWith(expect.objectContaining({ startDate: '2020-01-01', endDate: '2020-03-31', page: 1 }))
  wrapper.unmount()
})

it('keeps an explicit FX range fixed when the effective date changes', async () => {
  const pinia = createPinia()
  const context = usePortfolioContextStore(pinia)
  await context.reconcileContext()
  const wrapper = mount(FXPage, { shallow: true, global: { plugins: [pinia] } })
  await flushPromises()
  wrapper.vm.handleDateRangeChange({ dateRange: 'custom', dateFrom: '2020-01-01', dateTo: '2020-03-31' })
  await flushPromises()
  mocks.getFXData.mockClear()
  configureContextFixture('2025-12-31')
  await context.reconcileContext()
  await flushPromises()
  expect(wrapper.vm.dateFrom).toBe('2020-01-01')
  expect(wrapper.vm.dateTo).toBe('2020-03-31')
  wrapper.unmount()
})

it('recomputes mounted FX YTD once after a committed date change', async () => {
  const pinia = createPinia()
  const context = usePortfolioContextStore(pinia)
  await context.reconcileContext()
  const wrapper = mount(FXPage, { shallow: true, global: { plugins: [pinia] } })
  await flushPromises()
  mocks.getFXData.mockClear()
  configureContextFixture('2025-12-31')
  await context.reconcileContext()
  await flushPromises()
  expect(mocks.getFXData).toHaveBeenCalledTimes(1)
  expect(mocks.getFXData).toHaveBeenCalledWith(expect.objectContaining({ startDate: '2025-01-01', endDate: '2025-12-31' }))
  wrapper.unmount()
})
