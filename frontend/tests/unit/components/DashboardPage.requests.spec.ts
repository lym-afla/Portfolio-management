import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import DashboardPage from '@/views/DashboardPage.vue'
import { useAppStore } from '@/stores/app'

const api = vi.hoisted(() => ({
  getDashboardSummary: vi.fn(), getDashboardBreakdown: vi.fn(),
  getDashboardSummaryOverTime: vi.fn(),
}))
vi.mock('@/services/api', () => api)

const chartApi = vi.hoisted(() => ({
  fetchNavChart: vi.fn(),
  ChartApiError: class ChartApiError extends Error {},
  ChartContextMismatchError: class ChartContextMismatchError extends Error {},
}))
vi.mock('@/features/charts/chartApi', () => chartApi)

const summaryFixture = { 'Current NAV': '1,000.00', Invested: '900.00', 'Cash-out': '0.00', total_return: '11.11%', irr: 'N/R' }
const legacyOnlyResult = (labels: string[] = ['2026-09-08']) => ({
  capability: 'legacy_only',
  legacy: { labels, currency: 'USDk', datasets: [{ label: 'NAV', type: 'bar', data: [1000] }] },
})
const fixtures = {
  getDashboardSummary: summaryFixture,
  getDashboardBreakdown: { assetType: { data: { Stocks: '1,000.00' }, percentage: { Stocks: '100%' } }, assetClass: {}, currency: {}, totalNAV: '1,000.00' },
  getDashboardSummaryOverTime: { lines: [{ name: 'EoP NAV', data: { YTD: '1,000.00', 'All-time': '1,000.00' } }], years: [], currentYear: 2026 },
  fetchNavChart: legacyOnlyResult(),
}
const vuetify = createVuetify({ components, directives })
async function mountDashboardWithRealStores() {
  const pinia = createPinia()
  await usePortfolioContextStore(pinia).reconcileContext()
  const wrapper = mount(DashboardPage, {
    global: {
      plugins: [vuetify, pinia], provide: { showError: vi.fn(), clearErrors: vi.fn() },
      stubs: {
        UpdateAccountPerformanceDialog: true,
        BreakdownChart: { props: ['data'], template: '<div class="allocation-content">{{ JSON.stringify(data) }}</div>' },
        NAVChart: { name: 'NAVChart', props: ['chartData'], template: '<div class="nav-content">{{ JSON.stringify(chartData) }}</div>' },
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
  Object.entries(api).forEach(([name, fetcher]) => fetcher.mockRejectedValue(new Error(`${name} temporarily failed`)))
  chartApi.fetchNavChart.mockRejectedValue(new Error('fetchNavChart temporarily failed'))
})

it.each([
  ['getDashboardSummary', 0, 'Total NAV'],
  ['getDashboardBreakdown', 2, 'Stocks'],
  ['getDashboardSummaryOverTime', 5, 'EoP NAV'],
  ['fetchNavChart', 1, '2026-09-08'],
] as const)('restores visible %s content after a successful retry while other widgets stay failed', async (name, buttonIndex, content) => {
  const wrapper = await mountDashboardWithRealStores()
  expect(wrapper.text()).toContain(`${name} temporarily failed`)
  const mock = name === 'fetchNavChart' ? chartApi.fetchNavChart : api[name as keyof typeof api]
  const fixture = fixtures[name as keyof typeof fixtures]
  mock.mockResolvedValueOnce(fixture)
  const buttons = wrapper.findAll('button').filter((button) => button.text().includes('Retry'))
  await buttons[buttonIndex].trigger('click')
  await flushPromises()
  expect(wrapper.text()).not.toContain(`${name} temporarily failed`)
  expect(wrapper.text()).toContain(content)
  if (name === 'getDashboardSummary') expect(wrapper.text()).toContain(summaryFixture['Current NAV'])
  const other = name === 'getDashboardSummary' ? 'getDashboardBreakdown' : 'getDashboardSummary'
  expect(wrapper.text()).toContain(`${other} temporarily failed`)
  expect(mock).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

function resolveAllWidgets() {
  Object.entries(fixtures).forEach(([name, value]) => {
    if (name === 'fetchNavChart') chartApi.fetchNavChart.mockResolvedValue(value)
    else api[name as keyof typeof api].mockResolvedValue(value)
  })
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
it('keeps accepted NAV mounted while replacing pending parameters and ignores the late old error', async () => {
  resolveAllWidgets()
  const wrapper = await mountDashboardWithRealStores()
  const chart = wrapper.getComponent({ name: 'NAVChart' })
  const original = wrapper.get('[data-testid="nav-chart"]').element
  const old = deferred<typeof fixtures.fetchNavChart>()
  const next = deferred<typeof fixtures.fetchNavChart>()
  chartApi.fetchNavChart.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise)
  chart.vm.$emit('update-params', { ...useAppStore().navChartParams, frequency: 'M' })
  await flushPromises()
  expect(wrapper.get('[data-testid="nav-chart"]').element).toBe(original)
  chart.vm.$emit('update-params', { ...useAppStore().navChartParams, frequency: 'Y' })
  await flushPromises()
  expect(chartApi.fetchNavChart.mock.calls[1][1].signal.aborted).toBe(true)
  next.resolve(legacyOnlyResult(['new NAV']))
  await flushPromises()
  old.reject(new Error('old NAV error'))
  await flushPromises()
  expect(wrapper.text()).toContain('new NAV')
  expect(wrapper.find('[data-testid="nav-error"]').exists()).toBe(false)
  expect(wrapper.get('[data-testid="nav-chart"]').element).toBe(original)
  wrapper.unmount()
})
it('accepts history 404 as empty data but keeps other request failures visible', async () => {
  resolveAllWidgets()
  api.getDashboardSummaryOverTime.mockRejectedValueOnce({ response: { status: 404 } })
  const wrapper = await mountDashboardWithRealStores()
  expect(wrapper.text()).toContain('No data for the selected account and period')
  expect(wrapper.find('[data-testid="history-error"]').exists()).toBe(false)
  api.getDashboardSummaryOverTime.mockRejectedValueOnce(new Error('history unavailable'))
  wrapper.getComponent({ name: 'SummaryOverTimeTable' }).vm.$emit('refresh-data')
  await flushPromises()
  expect(wrapper.get('[data-testid="history-error"]').text()).toContain('history unavailable')
  wrapper.unmount()
})
it.each(['ytd', 'custom', 'all_time'])('invalidates old context content and rederives %s NAV dates once', async (dateRange) => {
  resolveAllWidgets()
  const wrapper = await mountDashboardWithRealStores()
  const context = usePortfolioContextStore()
  const app = useAppStore()
  app.updateNavChartParams({ dateRange, dateFrom: '2024-02-01', dateTo: '2024-07-01' })
  const old = deferred<typeof fixtures.getDashboardSummary>()
  api.getDashboardSummary.mockReturnValueOnce(old.promise)
  context.triggerDataRefresh()
  await flushPromises()
  const oldSignal = api.getDashboardSummary.mock.calls[1][0].signal
  const change = context.changeContext({ effectiveCurrentDate: '2025-12-31' })
  expect(oldSignal.aborted).toBe(true)
  await wrapper.vm.$nextTick()
  expect(wrapper.find('[data-testid="nav-chart"]').exists()).toBe(false)
  await change
  await flushPromises()
  expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(3)
  const query = chartApi.fetchNavChart.mock.calls[2][0]
  expect([query.fromDate, query.toDate]).toEqual(dateRange === 'custom' ? ['2024-02-01', '2024-07-01'] : [dateRange === 'all_time' ? null : '2025-01-01', '2025-12-31'])
  expect(app.navChartParams.dateFrom).toBe(query.fromDate)
  expect(app.navChartParams.dateTo).toBe(query.toDate)
  old.resolve({ ...summaryFixture, 'Current NAV': 'old context NAV' })
  await flushPromises()
  expect(wrapper.text()).not.toContain('old context NAV')
  expect(api.getDashboardSummary).toHaveBeenCalledTimes(3)
  wrapper.unmount()
})
