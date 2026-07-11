import { computed, ref } from 'vue'
import { useStore } from 'vuex'
import { debounce } from 'lodash'
import { calculateDateRangeFromTimespan } from '@/utils/dateUtils'
import logger from '@/utils/logger'

export function useTableSettings() {
  const store = useStore()
  const effectiveCurrentDate = ref(store.state.effectiveCurrentDate)

  const tableSettings = computed(() => store.state.tableSettings)

  const timespan = computed({
    get: () => tableSettings.value.timespan,
    set: (value) => handleTimespanChange(value),
  })

  const dateFrom = computed({
    get: () => tableSettings.value.dateFrom,
    set: (value) => store.dispatch('updateTableSettings', { dateFrom: value }),
  })

  const dateTo = computed({
    get: () => tableSettings.value.dateTo,
    set: (value) => store.dispatch('updateTableSettings', { dateTo: value }),
  })

  const itemsPerPage = computed({
    get: () => tableSettings.value.itemsPerPage,
    set: (value) =>
      store.dispatch('updateTableSettings', { itemsPerPage: value }),
  })

  const currentPage = computed({
    get: () => tableSettings.value.page,
    set: (value) => store.dispatch('updateTableSettings', { page: value }),
  })

  const sortBy = computed({
    get: () => tableSettings.value.sortBy,
    set: (value) => store.dispatch('updateTableSettings', { sortBy: value }),
  })

  const search = computed({
    get: () => tableSettings.value.search,
    set: debounce(
      (value) => store.dispatch('updateTableSettings', { search: value }),
      500
    ),
  })

  const handleTimespanChange = async (value) => {
    let currentDate = effectiveCurrentDate.value

    if (!currentDate) {
      await store.dispatch('fetchEffectiveCurrentDate')
      currentDate = store.state.effectiveCurrentDate
      effectiveCurrentDate.value = currentDate
    }

    if (!currentDate) {
      logger.error('Unknown', 'Failed to fetch effective current date')
      return
    }

    const dateRange = calculateDateRangeFromTimespan(value, currentDate)
    if (!dateRange) return

    store.dispatch('updateTableSettings', {
      timespan: value,
      dateFrom: dateRange.dateFrom,
      dateTo: dateRange.dateTo,
    })
  }

  const handlePageChange = (newPage) => {
    currentPage.value = newPage
  }

  const handleItemsPerPageChange = (newItemsPerPage) => {
    itemsPerPage.value = newItemsPerPage
    currentPage.value = 1
  }

  const handleSortChange = (newSortBy) => {
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
