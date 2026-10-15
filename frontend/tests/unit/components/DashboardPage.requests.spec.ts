import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import DashboardPage from '@/views/DashboardPage.vue'
import { useAppStore } from '@/stores/app'

const api = vi.hoisted(() => ({
  getDashboardSummaryV2: vi.fn(),
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

const summaryFixture = { 'Current NAV': '1,000.00', Invested: '900.00', 'Cash-out': '0.00', total_return: '11.11%', irr: 'N/R' }
const legacyOnlyResult = (labels: string[] = ['2026-09-08']) => ({
  capability: 'legacy_only',
  legacy: { labels, currency: 'USDk', datasets: [{ label: 'NAV', type: 'bar', data: [1000] }] },
})
const fixtures = {
  getDashboardSummaryV2: { capability: 'legacy_only', legacy: summaryFixture },
  fetchBreakdownChart: {
    capability: 'legacy_only',
    legacy: { assetType: { data: { Stocks: '1,000.00' }, percentage: { Stocks: '100%' } }, assetClass: {}, currency: {}, totalNAV: '1,000.00' },
  },
  getDashboardSummaryOverTime: { lines: [{ name: 'EoP NAV', data: { YTD: '1,000.00', 'All-time': '1,000.00' } }], years: [], currentYear: 2026 },
  fetchNavChart: legacyOnlyResult(),
}
const vuetify = createVuetify({ components, directives })
async function mountDashboardWithRealStores(pinia = createPinia()) {
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
  chartApi.fetchBreakdownChart.mockRejectedValue(new Error('fetchBreakdownChart temporarily failed'))
})

it.each([
  ['getDashboardSummaryV2', 0, 'Total NAV'],
  ['fetchBreakdownChart', 2, 'Stocks'],
  ['getDashboardSummaryOverTime', 5, 'EoP NAV'],
  ['fetchNavChart', 1, '2026-09-08'],
] as const)('restores visible %s content after a successful retry while other widgets stay failed', async (name, buttonIndex, content) => {
  const wrapper = await mountDashboardWithRealStores()
  expect(wrapper.text()).toContain(`${name} temporarily failed`)
  const mock = name in chartApi ? chartApi[name as keyof typeof chartApi] : api[name as keyof typeof api]
  const fixture = fixtures[name as keyof typeof fixtures]
  mock.mockResolvedValueOnce(fixture)
  const buttons = wrapper.findAll('button').filter((button) => button.text().includes('Retry'))
  await buttons[buttonIndex].trigger('click')
  await flushPromises()
  expect(wrapper.text()).not.toContain(`${name} temporarily failed`)
  expect(wrapper.text()).toContain(content)
  if (name === 'getDashboardSummaryV2') expect(wrapper.text()).toContain(summaryFixture['Current NAV'])
  const other = name === 'getDashboardSummaryV2' ? 'fetchBreakdownChart' : 'getDashboardSummaryV2'
  expect(wrapper.text()).toContain(`${other} temporarily failed`)
  expect(mock).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

function resolveAllWidgets() {
  Object.entries(fixtures).forEach(([name, value]) => {
    if (name === 'fetchNavChart') chartApi.fetchNavChart.mockResolvedValue(value)
    else if (name === 'fetchBreakdownChart') chartApi.fetchBreakdownChart.mockResolvedValue(value)
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
  const old = deferred<{ capability: string; legacy: typeof summaryFixture }>()
  api.getDashboardSummaryV2.mockReturnValueOnce(old.promise)
  context.triggerDataRefresh()
  await flushPromises()
  const oldSignal = api.getDashboardSummaryV2.mock.calls[1][0].signal
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
  old.resolve({ capability: 'legacy_only', legacy: { ...summaryFixture, 'Current NAV': 'old context NAV' } })
  await flushPromises()
  expect(wrapper.text()).not.toContain('old context NAV')
  expect(api.getDashboardSummaryV2).toHaveBeenCalledTimes(3)
  wrapper.unmount()
})

// Task 1 (real-data corrections): the NAV request end is clamped to the
// committed valuation date — a persisted custom To later than the effective
// date must never sample periods after it.
it('reconciles a persisted custom range when a historical valuation date commits (one accepted refresh; From and To clamp; selector agrees)', async () => {
  // Custom bounds persist across sessions: To=2026-10-09, From=2026-01-01.
  // The owner then commits valuation date 2024-06-30. The displayed range,
  // the persisted/applied params and the outgoing request must all agree on
  // the clamped window (From later than the new effective date clamps to it
  // too), with exactly one accepted refresh for the date change.
  const pinia = createPinia()
  setActivePinia(pinia)
  const { useAppStore: useAppStoreInner } = await import('@/stores/app')
  const appStore = useAppStoreInner()
  appStore.updateNavChartParams({ dateRange: 'custom', dateFrom: '2026-01-01', dateTo: '2026-10-09' })
  chartApi.fetchNavChart.mockResolvedValue(legacyOnlyResult(['2026-09-08']))
  await mountDashboardWithRealStores(pinia)
  await flushPromises()
  expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(1)

  // Commit the historical valuation date through the context store (the same
  // owner the header uses).
  const context = usePortfolioContextStore(pinia)
  await context.changeContext({ effectiveCurrentDate: '2024-06-30' })
  await flushPromises()
  expect(chartApi.fetchNavChart).toHaveBeenCalledTimes(2)
  const query = chartApi.fetchNavChart.mock.calls[1][0]
  expect(query.fromDate).toBe('2024-06-30')
  expect(query.toDate).toBe('2024-06-30')
  // The persisted/applied range agrees with the outgoing request.
  expect(appStore.navChartParams.dateFrom).toBe('2024-06-30')
  expect(appStore.navChartParams.dateTo).toBe('2024-06-30')
  // The rendered DateRangeSelector reconciliation is covered by the dates
  // browser case (the selector renders inside the stubbed NAVChart here).
})

it('clamps the NAV request end to the committed valuation date', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const { useAppStore: useAppStoreInner } = await import('@/stores/app')
  const appStore = useAppStoreInner()
  appStore.updateNavChartParams({ dateRange: 'custom', dateFrom: '2024-01-01', dateTo: '2026-12-31' })
  chartApi.fetchNavChart.mockResolvedValue(legacyOnlyResult(['2026-09-08']))
  await mountDashboardWithRealStores(pinia)
  await flushPromises()
  expect(chartApi.fetchNavChart).toHaveBeenCalled()
  const query = chartApi.fetchNavChart.mock.calls[0][0]
  expect(query.toDate).toBe('2026-09-08')
  expect(query.fromDate).toBe('2024-01-01')
})
