import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { effectScope, nextTick } from 'vue'
import { configureContextFixture } from '../context-fixture'
import { configurePortfolioContextBackend } from '@/services/api/context'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import { useTableSettings } from '@/composables/useTableSettings'

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  configureContextFixture('2026-09-08')
})

describe('useTableSettings effective-date presets', () => {
  it('uses the newly committed date for the next YTD selection', async () => {
    const context = usePortfolioContextStore()
    await context.reconcileContext()
    const settings = useTableSettings()
    configureContextFixture('2025-12-31')
    await context.reconcileContext()
    await settings.handleTimespanChange('ytd')
    expect(settings.dateFrom.value).toBe('2025-01-01')
    expect(settings.dateTo.value).toBe('2025-12-31')
  })

  it('recomputes relative presets on a mounted context change, but preserves explicit ranges', async () => {
    const context = usePortfolioContextStore()
    const app = useAppStore()
    await context.reconcileContext()
    const settings = useTableSettings()
    await settings.handleTimespanChange('ytd')
    configureContextFixture('2024-02-29')
    await context.reconcileContext()
    await nextTick()
    expect(app.tableSettings).toMatchObject({ timespan: 'ytd', dateFrom: '2024-01-01', dateTo: '2024-02-29', page: 1 })

    await settings.handleTimespanChange('all_time')
    expect(app.tableSettings).toMatchObject({ dateFrom: null, dateTo: '2024-02-29' })
    await settings.handleTimespanChange('2023')
    expect(app.tableSettings).toMatchObject({ dateFrom: '2023-01-01', dateTo: '2023-12-31' })

    app.updateTableSettings({ timespan: 'custom', dateFrom: '2020-01-10', dateTo: '2020-03-20' })
    configureContextFixture('2025-12-31')
    await context.reconcileContext()
    await nextTick()
    expect(app.tableSettings).toMatchObject({ timespan: 'custom', dateFrom: '2020-01-10', dateTo: '2020-03-20' })
  })

  it('resets page on an account switch with unchanged date and dedupes multiple table consumers', async () => {
    const context = usePortfolioContextStore()
    const app = useAppStore()
    await context.reconcileContext()
    useTableSettings()
    useTableSettings()
    app.updateTableSettings({ timespan: 'ytd', dateFrom: '2026-01-01', dateTo: '2026-09-08', page: 7 })
    const update = vi.spyOn(app, 'updateTableSettings')
    configurePortfolioContextBackend({
      read: async () => ({ accountSelection: { type: 'account', id: 2 }, effectiveCurrentDate: '2026-09-08', currency: 'USD', digits: 2 }),
      updateAccount: vi.fn(), updateSettings: vi.fn(),
    })
    await context.reconcileContext()
    await nextTick()
    expect(app.tableSettings.page).toBe(1)
    update.mockClear()
    configureContextFixture('2025-12-31')
    await context.reconcileContext()
    await nextTick()
    expect(update).toHaveBeenCalledTimes(1)
  })

  it('marks a manually edited date as custom so later context changes cannot rebase it', async () => {
    const context = usePortfolioContextStore()
    const app = useAppStore()
    await context.reconcileContext()
    const settings = useTableSettings()
    await settings.handleTimespanChange('ytd')
    settings.dateFrom.value = '2020-01-10'
    settings.dateTo.value = '2020-03-20'
    configureContextFixture('2025-12-31')
    await context.reconcileContext()
    await nextTick()
    expect(app.tableSettings).toMatchObject({ timespan: 'custom', dateFrom: '2020-01-10', dateTo: '2020-03-20' })
  })

  it('waits for a pending context transition instead of using the prior date', async () => {
    const context = usePortfolioContextStore()
    await context.reconcileContext()
    const settings = useTableSettings()
    const priorDate = settings.dateTo.value
    type ReadValue = Awaited<ReturnType<NonNullable<Parameters<typeof configurePortfolioContextBackend>[0]>['read']>>
    let release!: (value: ReadValue) => void
    configurePortfolioContextBackend({
      read: () => new Promise<ReadValue>((resolve) => { release = resolve }),
      updateAccount: vi.fn(), updateSettings: vi.fn(),
    })
    const pending = context.reconcileContext()
    const choosing = settings.handleTimespanChange('ytd')
    expect(settings.dateTo.value).toBe(priorDate)
    release({ accountSelection: { type: 'all', id: null }, effectiveCurrentDate: '2025-12-31', currency: 'USD', digits: 2 })
    await pending
    await nextTick()
    // A queued reconciliation is permitted to re-read the same canonical tuple.
    release({ accountSelection: { type: 'all', id: null }, effectiveCurrentDate: '2025-12-31', currency: 'USD', digits: 2 })
    await choosing
    expect(settings.dateFrom.value).toBe('2025-01-01')
    expect(settings.dateTo.value).toBe('2025-12-31')
  })

  it('updates page and range atomically, and cancels delayed search on scope disposal', async () => {
    vi.useFakeTimers()
    try {
      const context = usePortfolioContextStore()
      const app = useAppStore()
      await context.reconcileContext()
      app.updateTableSettings({ page: 4 })
      const scope = effectScope()
      const settings = scope.run(() => useTableSettings())!
      await settings.handleTimespanChange('ytd')
      expect(app.tableSettings.page).toBe(1)
      app.updateTableSettings({ page: 3 })
      settings.handleItemsPerPageChange(50)
      expect(app.tableSettings).toMatchObject({ page: 1, itemsPerPage: 50 })
      settings.search.value = 'old-page-search'
      scope.stop()
      vi.advanceTimersByTime(500)
      expect(app.tableSettings.search).toBe('')
    } finally {
      vi.useRealTimers()
    }
  })
})
