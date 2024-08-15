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

    <v-row no-gutters>
      <v-col cols="12">
        <v-data-table
          :headers="headers"
          :items="closedPositions"
          :loading="tableLoading"
          :search="search"
          :items-per-page="-1"
          class="elevation-1"
          density="compact"
          :sort-by="sortBy"
          @update:sort-by="handleSortChange"
          :server-items-length="totalItems"
          :items-length="totalItems"
          must-sort
          disable-sort
        >
          <template #header="{ header }">
            <span>{{ header.value }}</span>
            <v-icon v-if="header.sortable" size="small" class="ml-1">{{ getSortIcon(header.key) }}</v-icon>
          </template>
          
          <template #top>
            <v-toolbar flat class="bg-grey-lighten-4">
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

          <!-- <template #[`item.currency`]="{ item }">
            {{ item.currency }}
          </template> -->
          
          <template #[`item.investment_date`]="{ item }">
            {{ formatDate(item.investment_date) }}
          </template>
          
          <template #[`item.exit_date`]="{ item }">
            {{ formatDate(item.exit_date) }}
          </template>
          
          <template v-for="key in percentageColumns" :key="key" #[`item.${key}`]="{ item }">
            <span v-if="item && item[key] !== undefined" class="font-italic">{{ item[key] }}</span>
            <span v-else>-</span>
          </template>

          <template #bottom>
            <div class="d-flex align-center justify-space-between pa-4">
              <span class="text-caption mr-4">
                Showing {{ (currentPage - 1) * itemsPerPage + 1 }}-{{ Math.min(currentPage * itemsPerPage, totalItems) }} of {{ totalItems }} entries
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

          <template #tfoot>
            <tfoot>
              <tr class="font-weight-bold">
                <td v-for="header in flattenedHeaders" :key="header.key" :class="header.align">
                  <template v-if="header.key === 'type'">
                    TOTAL
                  </template>
                  <template v-else-if="percentageColumns.includes(header.key)">
                    <span class="font-italic">{{ totals[header.key] }}</span>
                  </template>
                  <template v-else>
                    {{ totals[header.key] }}
                  </template>
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
import { getClosedPositions, getYearOptions } from '@/services/api'
import { formatDate } from '@/utils/formatters'

export default {
  name: 'ClosedPositions',
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()
    const closedPositions = ref([])
    const totals = ref({})
    const tableLoading = ref(true)
    const selectedYear = ref('All-time')
    const yearOptions = ref([])
    const search = ref('')
    const itemsPerPage = ref(25)
    const itemsPerPageOptions = [10, 25, 50, 100]
    const currentPage = ref(1)
    const totalItems = ref(0)
    const pageCount = computed(() => Math.ceil(totalItems.value / itemsPerPage.value))
    const sortBy = ref([])  // Keep this as an array for Vuetify compatibility
    
    console.log('Initial sortBy:', sortBy.value)

    const percentageColumns = [
      'price_change_percentage',
      'capital_distribution_percentage',
      'commission_percentage',
      'total_return_percentage',
      'irr'
    ]

    const headers = computed(() => {
      const generatedHeaders = [
        { title: 'Type', key: 'type', align: 'start', sortable: true },
        { title: 'Name', key: 'name', align: 'start', sortable: true },
        { title: 'Currency', key: 'currency', align: 'center', sortable: true },
        // { title: 'Max position', key: 'max_position', align: 'center', sortable: true },
        {
          title: 'Entry',
          key: 'entry',
          align: 'center',
          sortable: false,
          children: [
            { title: 'Date', key: 'investment_date', align: 'center', sortable: true },
            { title: 'Value', key: 'entry_value', align: 'center', sortable: true },
          ],
        },
        {
          title: 'Exit',
          key: 'exit',
          align: 'center',
          sortable: false,
          children: [
            { title: 'Date', key: 'exit_date', align: 'center', sortable: true },
            { title: 'Value', key: 'exit_value', align: 'center', sortable: true },
          ],
        },
        {
          title: 'Realized gain/(loss)',
          key: 'realized',
          align: 'center',
          sortable: false,
          children: [
            { title: 'Amount', key: 'realized_gl', align: 'center', sortable: true },
            { title: '%', key: 'price_change_percentage', align: 'center', class: 'font-italic', sortable: true },
          ],
        },
        {
          title: 'Capital distribution',
          key: 'capital',
          align: 'center',
          sortable: false,
          children: [
            { title: 'Amount', key: 'capital_distribution', align: 'center', sortable: true },
            { title: '%', key: 'capital_distribution_percentage', align: 'center', class: 'font-italic', sortable: true },
          ],
        },
        {
          title: 'Commission',
          key: 'commission',
          align: 'center',
          sortable: false,
          children: [
            { title: 'Amount', key: 'commission', align: 'center', sortable: true },
            { title: '%', key: 'commission_percentage', align: 'center', class: 'font-italic', sortable: true },
          ],
        },
        {
          title: 'Total return',
          key: 'total',
          align: 'center',
          sortable: false,
          children: [
            { title: 'Amount', key: 'total_return_amount', align: 'center', sortable: true },
            { title: '%', key: 'total_return_percentage', align: 'center', class: 'font-italic', sortable: true },
            { title: 'IRR', key: 'irr', align: 'center', class: 'font-italic', sortable: true },
          ],
        },
      ]
      return generatedHeaders.map(header => ({
        ...header,
        title: header.sortable ? header.title : header.title,
      }))
    })
    
    const flattenedHeaders = computed(() => {
      return headers.value.flatMap(header => 
        header.children 
          ? header.children
          : header
      );
    });
    
    const handlePageChange = (newPage) => {
      console.log('Page changed to:', newPage)
      currentPage.value = newPage
      fetchClosedPositions()
    }

    const handleItemsPerPageChange = (newItemsPerPage) => {
      console.log('Items per page changed to:', newItemsPerPage)
      itemsPerPage.value = newItemsPerPage
      currentPage.value = 1 // Reset to first page when changing items per page
      fetchClosedPositions()
    }

    const handleHeaderClick = (column) => {
      console.log('Header clicked:', column)
      if (!column.sortable) return
      
      const currentSort = sortBy.value
      let newOrder = 'asc'
      
      if (currentSort && currentSort.key === column.key) {
        newOrder = currentSort.order === 'asc' ? 'desc' : 'asc'
      }
      
      console.log('New sort order:', newOrder)
      handleSortChange({ key: column.key, order: newOrder })
    }

    const handleSortChange = async (newSortBy) => {
      console.log('Sort changed:', newSortBy)
      if (Array.isArray(newSortBy) && newSortBy.length > 0) {
        sortBy.value = [newSortBy[0]]  // Keep only the first sort criterion
      } else if (typeof newSortBy === 'object' && newSortBy !== null) {
        sortBy.value = [newSortBy]  // Wrap the object in an array
      } else {
        sortBy.value = []  // Reset to empty array if invalid input
      }
      console.log('Updated sortBy:', sortBy.value)
      currentPage.value = 1 // Reset to first page when changing sort
      await fetchClosedPositions()
    }

    const getSortIcon = (key) => {
      const sort = sortBy.value[0]
      return !sort || sort.key !== key ? 'mdi-sort' : 
             (sort.order === 'asc' ? 'mdi-sort-ascending' : 'mdi-sort-descending')
    }

    const fetchClosedPositions = async () => {
      tableLoading.value = true
      try {
        console.log('Fetching closed positions with sort:', sortBy.value)
        const data = await getClosedPositions(
          selectedYear.value,
          currentPage.value,
          itemsPerPage.value,
          search.value,
          sortBy.value[0] || {}  // Send the first (and only) sort criterion, or an empty object if none
        )
        console.log('Received data:', data.portfolio_closed.slice(0, 5)) // Log first 5 items
        closedPositions.value = data.portfolio_closed
        totals.value = data.portfolio_closed_totals
        totalItems.value = data.total_items
      } catch (error) {
        store.dispatch('setError', error)
        console.error('Error in fetchClosedPositions:', error)
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

    watch(
      [
        () => store.state.dataRefreshTrigger,
        selectedYear,
        search,
      ],
      () => {
        currentPage.value = 1
        fetchClosedPositions()
      },
      { deep: true }
    )

    watch(closedPositions, (newValue) => {
      console.log('closedPositions updated:', newValue.slice(0, 5))
    }, { deep: true })

    watch(() => store.state.selectedBroker, () => {
      fetchYearOptions()
    })

    onMounted(() => {
      fetchYearOptions()
      fetchClosedPositions()
      emit('update-page-title', 'Closed Positions')
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    return {
      closedPositions,
      totals,
      tableLoading,
      headers,
      flattenedHeaders,
      selectedYear,
      yearOptions,
      search,
      itemsPerPage,
      itemsPerPageOptions,
      currentPage,
      sortBy,
      handlePageChange,
      pageCount,
      totalItems,
      formatDate,
      percentageColumns,
      loading: computed(() => store.state.loading),
      error: computed(() => store.state.error),
      handleItemsPerPageChange,
      handleSortChange,
      getSortIcon,
      handleHeaderClick,
    }
  },
}
</script>

<style scoped>
.v-data-table :deep(.v-data-table__wrapper) {
  overflow-x: auto;
}

.v-data-table :deep(table) {
  white-space: nowrap;
}

.v-data-table :deep(th) {
  font-weight: bold !important;
}

.v-data-table :deep(td),
.v-data-table :deep(th) {
  font-size: 0.875rem;
}

.v-data-table :deep(th.v-data-table__th) {
  vertical-align: bottom !important;
  padding-bottom: 8px !important; /* Add space from bottom border */
  white-space: normal;
  hyphens: auto;
}

.v-data-table :deep(tfoot td) {
  white-space: nowrap;
  font-size: 0.875rem;
}

.v-data-table :deep(tfoot td.start) {
  text-align: left;
}

.v-data-table :deep(tfoot td.center) {
  text-align: center;
}

.v-data-table :deep(.font-italic) {
  font-style: italic;
}

.v-toolbar {
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
}

.rows-per-page-select {
  min-width: 180px;
  max-width: 200px;
}
</style>