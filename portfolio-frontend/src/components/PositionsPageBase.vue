<template>
  <v-container fluid class="pa-0">
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular
        color="primary"
        indeterminate
        size="64"
      ></v-progress-circular>
    </v-overlay>

    <v-row>
      <v-col cols="12" md="3" lg="2">
        <v-select
          v-model="selectedYear"
          :items="yearOptions"
          item-title="text"
          item-value="value"
          label="Year"
          density="compact"
        >
          <template #item="{ props, item }">
            <v-list-item
              v-if="!item.raw.divider"
              v-bind="props"
              :title="item.title"
            ></v-list-item>
            <v-divider v-else class="my-2"></v-divider>
          </template>
        </v-select>
      </v-col>
    </v-row>

    <slot name="above-table"></slot>

    <v-row no-gutters>
      <v-col cols="12">
        <v-data-table
          :headers="headers"
          :items="positions"
          :loading="tableLoading"
          :search="search"
          :items-per-page="-1"
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
            <slot :name="name" v-bind="slotData"/>
          </template>

          <template #top>
            <v-toolbar flat class="bg-grey-lighten-4 border-b">
              <v-col cols="12" md="4" lg="4">
                <v-text-field
                  v-model="search"
                  append-icon="mdi-magnify"
                  label="Search"
                  single-line
                  hide-details
                  density="compact"
                  bg-color="white"
                  class="rounded-lg"
                ></v-text-field>
              </v-col>
              <v-spacer></v-spacer>
              <v-col cols="auto">
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
                ></v-select>
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
              ></v-pagination>
            </div>
          </template>
        </v-data-table>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useStore } from 'vuex'
import { formatDate } from '@/utils/formatters'
import { getYearOptions } from '@/services/api'

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
    const selectedYear = ref('All-time')
    const yearOptions = ref([])
    const search = ref('')
    const itemsPerPage = ref(25)
    const itemsPerPageOptions = [10, 25, 50, 100]
    const currentPage = ref(1)
    const totalItems = ref(0)
    const pageCount = computed(() =>
      Math.ceil(totalItems.value / itemsPerPage.value)
    )
    const sortBy = ref([])

    const flattenedHeaders = computed(() => {
      return props.headers.flatMap((header) =>
        header.children ? header.children : header
      )
    })

    const fetchData = async () => {
      tableLoading.value = true
      try {
        const data = await props.fetchPositions(
          selectedYear.value,
          currentPage.value,
          itemsPerPage.value,
          search.value,
          sortBy.value[0] || {}
        )
        positions.value = data.positions
        // Handle total rows in respective pages, as have different totals for each page
        // totals.value = data.totals
        totalItems.value = data.total_items
      } catch (error) {
        store.dispatch('setError', error)
        console.error('Error fetching positions:', error)
      } finally {
        tableLoading.value = false
      }
    }

    const fetchYearOptions = async () => {
      try {
        const years = await getYearOptions()
        yearOptions.value = years
      } catch (error) {
        store.dispatch('setError', error)
      }
    }

    const handlePageChange = (newPage) => {
      currentPage.value = newPage
      fetchData()
    }

    const handleItemsPerPageChange = (newItemsPerPage) => {
      itemsPerPage.value = newItemsPerPage
      currentPage.value = 1
      fetchData()
    }

    const handleSortChange = async (newSortBy) => {
      if (Array.isArray(newSortBy) && newSortBy.length > 0) {
        sortBy.value = [newSortBy[0]]
      } else if (typeof newSortBy === 'object' && newSortBy !== null) {
        sortBy.value = [newSortBy]
      } else {
        sortBy.value = []
      }
      currentPage.value = 1
      await fetchData()
    }

    watch(
      [() => store.state.dataRefreshTrigger, selectedYear, search],
      () => {
        currentPage.value = 1
        fetchData()
      },
      { deep: true }
    )

    watch(
      () => store.state.selectedBroker,
      () => {
        fetchYearOptions()
      }
    )

    onMounted(() => {
      fetchYearOptions()
      fetchData()
      emit('update-page-title', props.pageTitle)
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    return {
      positions,
      totals,
      tableLoading,
      selectedYear,
      yearOptions,
      search,
      itemsPerPage,
      itemsPerPageOptions,
      currentPage,
      sortBy,
      flattenedHeaders,
      totalItems,
      pageCount,
      handlePageChange,
      handleItemsPerPageChange,
      handleSortChange,
      formatDate,
      loading: computed(() => store.state.loading),
      error: computed(() => store.state.error),
    }
  },
}
</script>

<style scoped>
.nowrap-table :deep(td) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  /* font-size: small; */
}

.rows-per-page-select {
  min-width: 180px;
  max-width: 200px;
}
</style>