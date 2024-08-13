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
          @update:model-value="handleYearChange"
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
          :items-per-page="itemsPerPage"
          class="elevation-1"
          density="compact"
          :sort-by="sortBy"
          @update:sort-by="updateSort"
        >
          <template #top>
            <v-toolbar flat>
              <v-toolbar-title>Closed Positions</v-toolbar-title>
            </v-toolbar>
          </template>

          <template #[`item.currency`]="{ item }">
            {{ currencySymbol(item.currency) }}
          </template>
          
          <template #[`item.investment_date`]="{ item }">
            {{ formatDate(item.investment_date) }}
          </template>
          
          <template #[`item.exit_date`]="{ item }">
            {{ formatDate(item.exit_date) }}
          </template>
          
          <template v-for="key in percentageColumns" :key="key" #[`item.${key}`]="{ item }">
            <span class="font-italic">{{ item[key] }}</span>
          </template>

          <template #bottom>
            <v-divider></v-divider>
            <v-row class="mt-2">
              <v-col cols="12">
                <v-data-table-footer
                  :pagination="pagination"
                  :items-per-page-options="itemsPerPageOptions"
                  @update:options="updateOptions"
                ></v-data-table-footer>
              </v-col>
            </v-row>
          </template>

          <template #tfoot>
            <tfoot>
              <tr class="font-weight-bold">
                <td v-for="header in flattenedHeaders" :key="header.key" :class="header.align">
                  <template v-if="header.key === 'type'">
                    TOTAL
                  </template>
                  <template v-else-if="header.key === 'currency'">
                    {{ currencySymbol(totals[header.key]) }}
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
import axios from 'axios'
import { format, parseISO } from 'date-fns'

export default {
  name: 'ClosedPositions',
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const closedPositions = ref([])
    const totals = ref({})
    const loading = ref(true)
    const tableLoading = ref(true)
    const selectedYear = ref('YTD')
    const yearOptions = ref([])
    const search = ref('')
    const itemsPerPage = ref(25)
    const itemsPerPageOptions = [10, 25, 50, 100]
    const pagination = ref({})
    const sortBy = ref([])

    const currencyMap = {
      'USD': '$',
      'EUR': '€',
      'GBP': '£',
      'RUB': '₽',
      'CHF': '₣'
    }

    const currencySymbol = (code) => currencyMap[code] || code

    const formatDate = (dateString) => {
      if (!dateString) return ''
      try {
        return format(parseISO(dateString), 'd-MMM-yy')
      } catch (error) {
        console.error('Error formatting date:', error)
        return dateString
      }
    }

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

    const updateOptions = (newOptions) => {
      pagination.value = newOptions
    }

    const fetchClosedPositions = async () => {
      tableLoading.value = true
      try {
        const response = await axios.post(
          '/closed_positions/api/get_closed_positions_table/',
          {
            timespan: selectedYear.value,
          }
        )
        closedPositions.value = response.data.portfolio_closed
        totals.value = response.data.portfolio_closed_totals
      } catch (error) {
        console.error('Error fetching closed positions:', error)
      } finally {
        tableLoading.value = false
      }
    }

    const handleYearChange = (newValue) => {
      selectedYear.value = newValue
      fetchClosedPositions()
    }

    const fetchYearOptions = async () => {
      try {
        const response = await axios.get(
          '/closed_positions/api/get_year_options/'
        )
        yearOptions.value = response.data.closed_table_years.map((year) => {
          if (typeof year === 'string') {
            return { text: year, value: year }
          }
          return year // For divider and special options
        })
      } catch (error) {
        console.error('Error fetching year options:', error)
      }
    }

    const fetchData = async () => {
      loading.value = true
      await Promise.all([fetchYearOptions(), fetchClosedPositions()])
      loading.value = false
    }

    const updateSort = (newSortBy) => {
      sortBy.value = newSortBy
    }

    watch([sortBy, closedPositions], () => {
      if (sortBy.value.length > 0) {
        const { key, order } = sortBy.value[0]
        closedPositions.value.sort((a, b) => {
          if (a[key] < b[key]) return order === 'asc' ? -1 : 1
          if (a[key] > b[key]) return order === 'asc' ? 1 : -1
          return 0
        })
      }
    })

    onMounted(() => {
      fetchData()
      emit('update-page-title', 'Closed Positions')
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    return {
      closedPositions,
      totals,
      loading,
      tableLoading,
      headers,
      selectedYear,
      yearOptions,
      handleYearChange,
      search,
      itemsPerPage,
      itemsPerPageOptions,
      pagination,
      updateOptions,
      sortBy,
      updateSort,
      flattenedHeaders,
      currencySymbol,
      formatDate,
      percentageColumns,
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