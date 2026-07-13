import { computed, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { debounce } from 'lodash'
import { calculateDateRangeFromTimespan } from '@/utils/dateUtils'
import logger from '@/utils/logger'

export function useTableSettings() {
  const appStore = useAppStore()
  const effectiveCurrentDate = ref(appStore.effectiveCurrentDate)

  const tableSettings = computed(() => appStore.tableSettings)

  const timespan = computed({
    get: () => tableSettings.value.timespan,
    set: (value) => handleTimespanChange(value),
  })

  const dateFrom = computed({
    get: () => tableSettings.value.dateFrom,
    set: (value) => appStore.updateTableSettings({ dateFrom: value }),
  })

  const dateTo = computed({
    get: () => tableSettings.value.dateTo,
    set: (value) => appStore.updateTableSettings({ dateTo: value }),
  })

  const itemsPerPage = computed({
    get: () => tableSettings.value.itemsPerPage,
    set: (value) => appStore.updateTableSettings({ itemsPerPage: value }),
  })

  const currentPage = computed({
    get: () => tableSettings.value.page,
    set: (value) => appStore.updateTableSettings({ page: value }),
  })

  const sortBy = computed({
    get: () => tableSettings.value.sortBy,
    set: (value) => appStore.updateTableSettings({ sortBy: value }),
  })

  const search = computed({
    get: () => tableSettings.value.search,
    set: debounce(
      (value) => appStore.updateTableSettings({ search: value }),
      500
    ),
  })

  const handleTimespanChange = async (value: string) => {
    let currentDate = effectiveCurrentDate.value

    if (!currentDate) {
      await appStore.fetchEffectiveCurrentDate()
      currentDate = appStore.effectiveCurrentDate
      effectiveCurrentDate.value = currentDate
    }

    if (!currentDate) {
      logger.error('Unknown', 'Failed to fetch effective current date')
      return
    }

    const dateRange = calculateDateRangeFromTimespan(value, currentDate)
    if (!dateRange) return

    appStore.updateTableSettings({
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
    currentPage.value = 1
  }

  const handleSortChange = (newSortBy: unknown) => {
    if (Array.isArray(newSortBy) && newSortBy.length > 0) {
      sortBy.value = [newSortBy[0]]
    } else if (typeof newSortBy === 'object' && newSortBy !== null) {
      sortBy.value = [newSortBy]
    } else {
      sortBy.value = []
    }
    currentPage.value = 1
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
  }
}
