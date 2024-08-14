<template>
  <v-container fluid>
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
      <v-col cols="12" md="3" lg="2">
        <v-text-field
          v-model="search"
          append-icon="mdi-magnify"
          label="Search"
          single-line
          hide-details
          density="compact"
        ></v-text-field>
      </v-col>
    </v-row>

    <v-row>
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
          must-sort
        >
          <template #top>
            <v-toolbar flat>
              <v-toolbar-title>Closed Positions</v-toolbar-title>
            </v-toolbar>
          </template>

          <template #[`item.currency`]="{ item }">
            {{ item.currency }}
          </template>
          
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
              <v-select
                v-model="itemsPerPage"
                :items="itemsPerPageOptions"
                label="Rows per page"
                density="compact"
                variant="outlined"
                hide-details
                class="mr-2"
                style="max-width: 150px;"
                @update:model-value="handleItemsPerPageChange"
              ></v-select>
              <v-text class="text-caption mr-4">
                {{ (currentPage - 1) * itemsPerPage + 1 }}-{{ Math.min(currentPage * itemsPerPage, totalItems) }} of {{ totalItems }}
              </v-text>
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
                  <template v-else-if="header.key === 'currency'">
                    {{ totals[header.key] }}
                  </template>
                  <template v-else-if="['investment_date', 'exit_date'].includes(header.key)">
                    {{ formatDate(totals[header.key]) }}
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
    const sortBy = ref([])

    const percentageColumns = [
      'price_change_percentage',
      'capital_distribution_percentage',
      'commission_percentage',
      'total_return_percentage',
      'irr'
    ]

    const headers = computed(() => [
      {
        title: 'Type',
        key: 'type',
        align: 'start',
      },
      { title: 'Name', key: 'name', align: 'start' },
      { title: 'Currency', key: 'currency', align: 'center' },
      { title: 'Max position', key: 'max_position', align: 'center' },
      {
        title: 'Entry',
        key: 'entry',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Date', key: 'investment_date', align: 'center' },
          { title: 'Value', key: 'entry_value', align: 'center' },
        ],
      },
      {
        title: 'Exit',
        key: 'exit',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Date', key: 'exit_date', align: 'center' },
          { title: 'Value', key: 'exit_value', align: 'center' },
        ],
      },
      {
        title: 'Realized gain/(loss)',
        key: 'realized',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Amount', key: 'realized_gl', align: 'center' },
          { title: '%', key: 'price_change_percentage', align: 'center', class: 'font-italic' },
        ],
      },
      {
        title: 'Capital distribution',
        key: 'capital',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Amount', key: 'capital_distribution', align: 'center' },
          { title: '%', key: 'capital_distribution_percentage', align: 'center', class: 'font-italic' },
        ],
      },
      {
        title: 'Commission',
        key: 'commission',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Amount', key: 'commission', align: 'center' },
          { title: '%', key: 'commission_percentage', align: 'center', class: 'font-italic' },
        ],
      },
      {
        title: 'Total return',
        key: 'total',
        align: 'center',
        sortable: false,
        children: [
          { title: 'Amount', key: 'total_return_amount', align: 'center' },
          { title: '%', key: 'total_return_percentage', align: 'center', class: 'font-italic' },
          { title: 'IRR', key: 'irr', align: 'center', class: 'font-italic' },
        ],
      },
    ])

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

    const fetchClosedPositions = async () => {
      tableLoading.value = true
      try {
        const data = await getClosedPositions(
          selectedYear.value,
          currentPage.value,
          itemsPerPage.value,
          search.value,
          sortBy.value
        )
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

    const fetchYearOptions = async () => {
      try {
        const years = await getYearOptions()
        yearOptions.value = years
      } catch (error) {
        store.dispatch('setError', error)
      }
    }

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
</style>