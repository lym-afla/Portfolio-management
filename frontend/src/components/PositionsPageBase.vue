<template>
  <v-container fluid class="pa-0">
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64" />
    </v-overlay>

    <slot name="above-table" />

    <v-row no-gutters>
      <v-col cols="12">
        <v-skeleton-loader v-if="initialLoading" type="table" />
        <v-data-table
          v-else
          :headers="headers"
          :items="positions"
          :loading="tableLoading"
          :search="search"
          :items-per-page="itemsPerPage"
          class="elevation-1 nowrap-table"
          density="compact"
          :sort-by="sortBy"
          @update:sort-by="handleSortChange"
          :server-items-length="totalItems"
          :items-length="totalItems"
          must-sort
          disable-sort
        >
          <template v-for="(_, name) in $slots" #[name]="slotData">
            <slot :name="name" v-bind="slotData" />
          </template>

          <template #top>
            <v-toolbar flat class="bg-grey-lighten-4 border-b">
              <v-col cols="12" sm="3" md="2" lg="2">
                <v-select
                  v-model="timespan"
                  :items="yearOptions"
                  item-title="text"
                  item-value="value"
                  label="Year"
                  density="compact"
                  hide-details
                  class="mr-2"
                >
                  <template #item="{ props, item }">
                    <v-list-item
                      v-if="!item.raw.divider"
                      v-bind="props"
                      :title="item.title"
                    />
                    <v-divider v-else class="my-2" />
                  </template>
                </v-select>
              </v-col>
              <v-col cols="12" sm="6" md="7" lg="8">
                <v-text-field
                  v-model="search"
                  append-icon="mdi-magnify"
                  label="Search"
                  single-line
                  hide-details
                  density="compact"
                  bg-color="white"
                  class="rounded-lg"
                />
              </v-col>
              <v-spacer />
              <v-col cols="12" sm="3" md="3" lg="2">
                <v-select
                  v-model="itemsPerPage"
                  :items="itemsPerPageOptions"
                  label="Rows per page"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="mr-2 rows-per-page-select"
                  @update:model-value="handleItemsPerPageChange"
                  bg-color="white"
                />
              </v-col>
            </v-toolbar>
          </template>

          <template #bottom>
            <div class="d-flex align-center justify-space-between pa-4">
              <span class="text-caption mr-4">
                Showing {{ (currentPage - 1) * itemsPerPage + 1 }}-{{
                  Math.min(currentPage * itemsPerPage, totalItems)
                }}
                of {{ totalItems }} entries
              </span>
              <v-pagination
                v-model="currentPage"
                :length="pageCount"
                :total-visible="7"
                rounded="circle"
                @update:model-value="handlePageChange"
              />
            </div>
          </template>

          <template #tfoot>
            <tfoot>
              <tr class="font-weight-bold">
                <td
                  v-for="header in flattenedHeaders"
                  :key="header.key"
                  :class="header.align"
                >
                  <slot :name="`tfoot-${header.key}`" :header="header">
                    {{ totals[header.key] }}
                  </slot>
                </td>
              </tr>
            </tfoot>
          </template>
        </v-data-table>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useStore } from 'vuex'
import { getYearOptions } from '@/services/api'
import { useTableSettings } from '@/composables/useTableSettings'
import logger from '@/utils/logger'

export default {
  name: 'PositionsPageBase',
  props: {
    fetchPositions: {
      type: Function,
      required: true,
    },
    headers: {
      type: Array,
      required: true,
    },
    pageTitle: {
      type: String,
      required: true,
    },
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()
    const positions = ref([])
    const totals = ref({})
    const tableLoading = ref(true)
    const yearOptions = ref([])
    const totalItems = ref(0)
    const initialLoading = ref(true)

    const {
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
    } = useTableSettings()

    const pageCount = computed(() =>
      Math.ceil(totalItems.value / itemsPerPage.value)
    )

    const flattenedHeaders = computed(() => {
      return props.headers.flatMap((header) =>
        header.children ? header.children : header
      )
    })

    const fetchData = async () => {
      tableLoading.value = true
      try {
        console.log('[PositionsPageBase] fetchData called with:', {
          // timespan: timespan.value,
          dateFrom: dateFrom.value,
          dateTo: dateTo.value,
          currentPage: currentPage.value,
          itemsPerPage: itemsPerPage.value,
          search: search.value,
          sortBy: sortBy.value,
        })
        const data = await props.fetchPositions({
          // timespan: timespan.value,
          dateFrom: dateFrom.value,
          dateTo: dateTo.value,
          page: currentPage.value,
          itemsPerPage: itemsPerPage.value,
          search: search.value,
          sortBy: sortBy.value[0] || {},
        })
        positions.value = data.positions
        totals.value = data.totals
        totalItems.value = data.total_items
      } catch (error) {
        store.dispatch('setError', error)
        logger.error('Unknown', 'Error fetching positions:', error)
      } finally {
        tableLoading.value = false
        initialLoading.value = false
        logger.log('Unknown', '[PositionsPageBase] Current state:', store.state)
      }
    }

    const fetchYearOptions = async () => {
      try {
        const years = await getYearOptions()
        yearOptions.value = years
      } catch (error) {
        store.dispatch('setError', error)
      } finally {
        initialLoading.value = false
      }
    }

    watch(
      [
        () => store.state.dataRefreshTrigger,
        search,
        itemsPerPage,
        currentPage,
        sortBy,
        timespan,
        dateFrom,
        dateTo,
      ],
      () => {
        fetchData()
      },
      { deep: true }
    )

    // This watch is used to update the year options when the selected account changes.
    // Data refresh is handled in AccountSelection.vue, dispatching the dataRefreshTrigger action.
    watch(
      () => store.state.selectedAccount,
      () => {
        fetchYearOptions()
      }
    )

    const initializeData = async () => {
      emit('update-page-title', props.pageTitle)

      if (!store.state.effectiveCurrentDate) {
        await store.dispatch('fetchEffectiveCurrentDate')
      }

      // Check if dateFrom and dateTo are already set in the store
      if (
        !store.state.tableSettings.dateFrom ||
        !store.state.tableSettings.dateTo
      ) {
        // If not set, use the default 'ytd' timespan
        await handleTimespanChange(store.state.tableSettings.timespan)
      } else {
        // If already set, update the local timespan value
        timespan.value = store.state.tableSettings.timespan
      }

      // Fetch year options
      await fetchYearOptions()
      await fetchData()
    }

    onMounted(() => {
      initializeData()
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    // const handlePageChangeWrapper = (newPage) => {
    //   handlePageChange(newPage)
    //   fetchData()
    // }

    // const handleItemsPerPageChangeWrapper = (newItemsPerPage) => {
    //   handleItemsPerPageChange(newItemsPerPage)
    //   fetchData()
    // }

    // const handleSortChangeWrapper = (newSortBy) => {
    //   handleSortChange(newSortBy)
    //   fetchData()
    // }

    return {
      positions,
      totals,
      tableLoading,
      timespan,
      dateFrom,
      dateTo,
      yearOptions,
      search,
      itemsPerPage,
      itemsPerPageOptions: computed(() => store.state.itemsPerPageOptions),
      currentPage,
      sortBy,
      flattenedHeaders,
      totalItems,
      pageCount,
      // handlePageChange: handlePageChangeWrapper,
      handlePageChange,
      // handleItemsPerPageChange: handleItemsPerPageChangeWrapper,
      handleItemsPerPageChange,
      // handleSortChange: handleSortChangeWrapper,
      handleSortChange,
      handleTimespanChange,
      loading: computed(() => store.state.loading),
      error: computed(() => store.state.error),
      initialLoading,
    }
  },
}
</script>
<style scoped>
.nowrap-table :deep(td) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rows-per-page-select {
  min-width: 180px;
  max-width: 200px;
}
</style>
