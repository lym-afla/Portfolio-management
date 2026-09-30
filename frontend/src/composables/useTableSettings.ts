import { computed, onScopeDispose, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { calculateDateRangeFromTimespan } from '@/utils/dateUtils'
import logger from '@/utils/logger'

export function useTableSettings({ syncRelativeDate = true } = {}) {
  const appStore = useAppStore()
  const context = usePortfolioContextStore()
  const effectiveCurrentDate = computed(
    () => context.committed.effectiveCurrentDate
  )

  const tableSettings = computed(() => appStore.tableSettings)

  const timespan = computed({
    get: () => tableSettings.value.timespan,
    set: (value) => handleTimespanChange(value),
  })

  const dateFrom = computed({
    get: () => tableSettings.value.dateFrom,
    set: (value) => appStore.updateTableSettings({ dateFrom: value, timespan: 'custom', page: 1 }),
  })

  const dateTo = computed({
    get: () => tableSettings.value.dateTo,
    set: (value) => appStore.updateTableSettings({ dateTo: value, timespan: 'custom', page: 1 }),
  })

  const itemsPerPage = computed({
    get: () => tableSettings.value.itemsPerPage,
    set: (value) => appStore.updateTableSettings({ itemsPerPage: value, page: 1 }),
  })

  const currentPage = computed({
    get: () => tableSettings.value.page,
    set: (value) => appStore.updateTableSettings({ page: value }),
  })

  const sortBy = computed({
    get: () => tableSettings.value.sortBy,
    set: (value) => appStore.updateTableSettings({ sortBy: value, page: 1 }),
  })

  let searchTimer: ReturnType<typeof setTimeout> | undefined
  const delayedSearch = (value: string) => {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      appStore.updateTableSettings({ search: value, page: 1 })
      searchTimer = undefined
    }, 500)
  }
  onScopeDispose(() => clearTimeout(searchTimer), true)
  const search = computed({
    get: () => tableSettings.value.search,
    set: delayedSearch,
  })

  const updateDateRange = (range: { dateFrom: string | null; dateTo: string | null; timespan?: string }) => {
    appStore.updateTableSettings({ ...range, page: 1 })
  }

  if (syncRelativeDate) {
    watch(
      [effectiveCurrentDate, () => context.canRead],
      ([currentDate, canRead]) => {
        if (!canRead || !currentDate) return
        const span = String(tableSettings.value.timespan)
        if (span === 'custom') return
        const range = calculateDateRangeFromTimespan(span, currentDate)
        if (!range) return
        if (range.dateFrom !== tableSettings.value.dateFrom || range.dateTo !== tableSettings.value.dateTo) {
          updateDateRange(range)
        }
      },
      { immediate: true }
    )
  }

  const handleTimespanChange = async (value: string) => {
    if (value === 'custom') {
      appStore.updateTableSettings({ timespan: value, page: 1 })
      return
    }
    let currentDate = effectiveCurrentDate.value

    if (!context.canRead) {
      await context.reconcileContext()
      currentDate = effectiveCurrentDate.value
    }

    if (!currentDate) {
      logger.error('Unknown', 'Failed to fetch effective current date')
      return
    }

    const dateRange = calculateDateRangeFromTimespan(value, currentDate)
    if (!dateRange) return

    updateDateRange({
      timespan: value,
      dateFrom: dateRange.dateFrom,
      dateTo: dateRange.dateTo,
    })
  }

  const handlePageChange = (newPage: number) => {
    currentPage.value = newPage
  }

  const handleItemsPerPageChange = (newItemsPerPage: number) => {
    itemsPerPage.value = newItemsPerPage
  }

  const handleSortChange = (newSortBy: unknown) => {
    if (Array.isArray(newSortBy) && newSortBy.length > 0) {
      sortBy.value = [newSortBy[0]]
    } else if (typeof newSortBy === 'object' && newSortBy !== null) {
      sortBy.value = [newSortBy as { key: string; order?: boolean | 'asc' | 'desc' }]
    } else {
      sortBy.value = []
    }
  }

  return {
    timespan,
    dateFrom,
    dateTo,
    itemsPerPage,
    currentPage,
    sortBy,
    search,
    handlePageChange,
    handleItemsPerPageChange,
    handleSortChange,
    handleTimespanChange,
    updateDateRange,
  }
}
