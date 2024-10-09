<template>
  <v-container fluid class="pa-0">
    <v-alert v-if="error" type="error" dismissible>
      {{ error }}
    </v-alert>

    <!-- Broker performance breakdown table -->
    <v-card class="mt-4">
      <v-card-title>Broker performance breakdown</v-card-title>
      <v-card-text>
        <v-skeleton-loader
          v-if="loading.brokerPerformance"
          type="table"
        ></v-skeleton-loader>
        <div v-else class="table-wrapper">
          <table class="v-data-table">
            <thead>
              <tr>
                <th rowspan="2" class="text-left no-wrap">Broker</th>
                <th 
                  v-for="year in years" 
                  :key="year" 
                  :colspan="subHeaders.length" 
                  class="text-center"
                  :class="{ 'highlight-column': year === 'YTD' || year === 'All-time' }"
                >
                  {{ year }}
                </th>
              </tr>
              <tr>
                <template v-for="year in years" :key="`subheader-${year}`">
                  <th 
                    v-for="subheader in subHeaders" 
                    :key="`${year}-${subheader.value}`" 
                    class="text-center"
                    :class="{ 
                      'highlight-column': year === 'YTD' || year === 'All-time',
                      'italic': subheader.value === 'TSR percentage' || subheader.value === 'Fee per AuM (percentage)'
                    }"
                  >
                    {{ subheader.text }}
                  </th>
                </template>
              </tr>
            </thead>
            <tbody>
              <template v-for="(group, groupIndex) in brokerPerformanceData" :key="groupIndex">
                <tr class="group-header">
                  <td :colspan="years.length * subHeaders.length + 1">
                    {{ group.name === 'public_markets_context' ? 'Public Markets' : 'Restricted Investments' }}
                  </td>
                </tr>
                <tr v-for="(item, itemIndex) in group.lines" :key="`${groupIndex}-${itemIndex}`">
                  <td class="no-wrap">{{ item.name }}</td>
                  <template v-for="year in years" :key="`data-${year}`">
                    <td 
                      v-for="subheader in subHeaders" 
                      :key="`${year}-${subheader.value}`" 
                      class="text-center"
                      :class="{ 
                        'highlight-column': year === 'YTD' || year === 'All-time',
                        'italic': subheader.value === 'TSR percentage' || subheader.value === 'Fee per AuM (percentage)'
                      }"
                    >
                      {{ item.data && item.data[year] ? item.data[year][subheader.value] : 'N/A' }}
                    </td>
                  </template>
                </tr>
                <tr v-if="group.subtotal" class="subtotal-row">
                  <td class="no-wrap">Sub-total</td>
                  <template v-for="year in years" :key="`subtotal-${year}`">
                    <td 
                      v-for="subheader in subHeaders" 
                      :key="`${year}-${subheader.value}`" 
                      class="text-center"
                      :class="{ 
                        'highlight-column': year === 'YTD' || year === 'All-time',
                        'italic': subheader.value === 'TSR percentage' || subheader.value === 'Fee per AuM (percentage)'
                      }"
                    >
                      {{ group.subtotal[year] ? group.subtotal[year][subheader.value] : 'N/A' }}
                    </td>
                  </template>
                </tr>
              </template>
              <tr class="total-row">
                <td class="no-wrap"><strong>{{ totalData.name }}</strong></td>
                <template v-for="year in years" :key="`total-${year}`">
                  <td 
                    v-for="subheader in subHeaders" 
                    :key="`${year}-${subheader.value}`" 
                    class="text-center"
                    :class="{ 
                      'highlight-column': year === 'YTD' || year === 'All-time',
                      'italic': subheader.value === 'TSR percentage' || subheader.value === 'Fee per AuM (percentage)'
                    }"
                  >
                    <strong>{{ totalData.data && totalData.data[year] ? totalData.data[year][subheader.value] : 'N/A' }}</strong>
                  </td>
                </template>
              </tr>
            </tbody>
          </table>
        </div>
      </v-card-text>
    </v-card>

    <!-- Portfolio breakdown table -->
    <v-card class="mt-4">
      <v-card-title>Portfolio breakdown</v-card-title>
      <v-card-text>
        <!-- Year selector -->
        <v-row no-gutters class="mb-4">
          <v-col cols="12" sm="3" md="2" lg="2">
            <v-select
              v-model="selectedYear"
              :items="yearOptions"
              item-title="text"
              item-value="value"
              label="Year"
              density="compact"
              hide-details
              class="mr-2"
              @update:model-value="handleYearChange"
            >
              <template #item="{ props, item }">
                <v-list-item v-if="!item.raw.divider" v-bind="props" :title="item.title"></v-list-item>
                <v-divider v-else class="my-2"></v-divider>
              </template>
            </v-select>
          </v-col>
        </v-row>
        
        <v-skeleton-loader
          v-if="loading.portfolioBreakdown"
          type="table"
        ></v-skeleton-loader>
        <div v-else class="table-wrapper">
          <table class="v-data-table portfolio-breakdown-table">
            <thead>
              <tr>
                <th v-for="header in portfolioBreakdownHeaders" :key="header.value"
                    :rowspan="header.rowspan" :colspan="header.colspan"
                    :class="[header.class, 'text-center']">
                  {{ header.text }}
                </th>
              </tr>
              <tr>
                <template v-for="header in portfolioBreakdownHeaders" :key="`sub-${header.value}`">
                  <template v-if="header.colspan === 2">
                    <th v-for="subHeader in portfolioBreakdownSubHeaders.filter(sh => sh.value.startsWith(header.value))"
                        :key="subHeader.value" :class="[subHeader.class, 'text-center']">
                      {{ subHeader.text }}
                    </th>
                  </template>
                </template>
              </tr>
            </thead>
            <tbody>
              <template v-for="(category, categoryIndex) in portfolioBreakdownCategories" :key="categoryIndex">
                <tr class="group-header">
                  <td :colspan="portfolioBreakdownHeaders.length + portfolioBreakdownSubHeaders.length - 5">
                    {{ category.toUpperCase() }}
                  </td>
                </tr>
                <tr v-for="(item, itemIndex) in portfolioBreakdownData[`${category}_context`]"
                    :key="`${categoryIndex}-${itemIndex}`"
                    :class="{ 'total-row': item.name === 'TOTAL' }">
                  <td>{{ item.name }}</td>
                  <td class="text-right">{{ item.cost }}</td>
                  <td class="text-right">{{ item.unrealized }}</td>
                  <td class="text-right">{{ item.unrealized_percent }}</td>
                  <td class="text-right">{{ item.market_value }}</td>
                  <td class="text-right">{{ item.portfolio_percent }}</td>
                  <td class="text-right">{{ item.realized }}</td>
                  <td class="text-right">{{ item.realized_percent }}</td>
                  <td class="text-right">{{ item.capital_distribution }}</td>
                  <td class="text-right">{{ item.capital_distribution_percent }}</td>
                  <td class="text-right">{{ item.commission }}</td>
                  <td class="text-right">{{ item.commission_percent }}</td>
                  <td class="text-right">{{ item.total }}</td>
                  <td class="text-right">{{ item.total_percent }}</td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { useStore } from 'vuex'
import { useRouter } from 'vue-router'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { getBrokerPerformanceSummary, getYearOptions, getPortfolioBreakdownSummary } from '@/services/api'

export default {
  name: 'SummaryPage',
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()
    const router = useRouter()
    const { handleApiError } = useErrorHandler()
    const loading = ref({
      brokerPerformance: true,
      portfolioBreakdown: true,
    })
    const brokerPerformanceData = ref([])
    const portfolioBreakdownData = ref([])
    const years = ref([])
    const currentYear = new Date().getFullYear()
    const selectedYear = ref(currentYear.toString())
    const yearOptions = ref([])

    const brokerPerformanceHeaders = computed(() => [
      { text: 'Broker', value: 'name', sortable: false, rowspan: 2 },
      ...years.value.map(year => ({
        text: year === 'YTD' ? currentYear : year,
        value: year,
        sortable: false,
        align: 'center',
        colspan: subHeaders.value.length,
        class: year === 'YTD' || year === 'All-time' ? 'highlight-column' : ''
      }))
    ])

    const brokerPerformanceSubHeaders = computed(() => 
      years.value.flatMap(year => 
        subHeaders.value.map(subheader => ({
          text: subheader.text,
          value: `${year}.${subheader.value}`,
          sortable: false,
          align: 'center',
          class: year === 'YTD' || year === 'All-time' ? 'highlight-column' : ''
        }))
      )
    )

    const portfolioBreakdownHeaders = ref([
      { text: 'Asset Class', value: 'name', rowspan: 2, class: 'fixed-column' },
      { text: 'Cost', value: 'cost', rowspan: 2 },
      { text: 'Unrealized', value: 'unrealized', colspan: 2 },
      { text: 'Market value', value: 'market_value', rowspan: 2 },
      { text: '% of portfolio', value: 'portfolio_percent', rowspan: 2, class: 'fst-italic' },
      { text: 'Realized', value: 'realized', colspan: 2 },
      { text: 'Capital distribution', value: 'capital_distribution', colspan: 2 },
      { text: 'Commission', value: 'commission', colspan: 2 },
      { text: 'Total', value: 'total', colspan: 2 },
    ])

    const portfolioBreakdownSubHeaders = ref([
      { text: `(${store.state.selectedCurrency})`, value: 'unrealized' },
      { text: '(%)', value: 'unrealized_percent', class: 'fst-italic' },
      { text: `(${store.state.selectedCurrency})`, value: 'realized' },
      { text: '(%)', value: 'realized_percent', class: 'fst-italic' },
      { text: `(${store.state.selectedCurrency})`, value: 'capital_distribution' },
      { text: '(%)', value: 'capital_distribution_percent', class: 'fst-italic' },
      { text: `(${store.state.selectedCurrency})`, value: 'commission' },
      { text: '(%)', value: 'commission_percent', class: 'fst-italic' },
      { text: `(${store.state.selectedCurrency})`, value: 'total' },
      { text: '(%)', value: 'total_percent', class: 'fst-italic' },
    ])

    const portfolioBreakdownCategories = ['consolidated', 'unrestricted', 'restricted']

    const subHeaders = ref([
      { text: 'BoP NAV', value: 'BoP NAV' },
      { text: 'Cash-in/(out)', value: 'Cash-in/out' },
      { text: 'Return', value: 'Return' },
      { text: 'FX', value: 'FX' },
      { text: 'TSR', value: 'TSR percentage' },
      { text: 'EoP NAV', value: 'EoP NAV' },
      { text: 'Commissions', value: 'Commission' },
      { text: 'Fee per AuM', value: 'Fee per AuM (percentage)' },
    ])

    const totalData = ref({})

    const fetchYearOptions = async () => {
      try {
        const years = await getYearOptions()
        yearOptions.value = years
      } catch (error) {
        handleApiError(error)
      }
    }

    const fetchBrokerPerformanceData = async () => {
      try {
        loading.value.brokerPerformance = true
        const data = await getBrokerPerformanceSummary()
        if (data && data.public_markets_context && data.restricted_investments_context && data.total_context) {
          brokerPerformanceData.value = [
            {
              name: 'public_markets_context',
              lines: data.public_markets_context.lines,
              subtotal: data.public_markets_context.subtotal
            },
            {
              name: 'restricted_investments_context',
              lines: data.restricted_investments_context.lines,
              subtotal: data.restricted_investments_context.subtotal
            }
          ]
          totalData.value = data.total_context.line
          years.value = data.total_context.years || []
        } else {
          console.error('Unexpected data structure:', data)
        }
      } catch (error) {
        if (error.message === 'Authentication required') {
          router.push('/login')
        } else {
          handleApiError(error)
        }
      } finally {
        loading.value.brokerPerformance = false
      }
    }

    const fetchPortfolioBreakdown = async (year) => {
      try {
        loading.value.portfolioBreakdown = true
        const data = await getPortfolioBreakdownSummary(year)
        portfolioBreakdownData.value = data
        if (!data || !data.consolidated_context) {
          console.error('Unexpected data structure for portfolio breakdown:', data)
        }
      } catch (error) {
        handleApiError(error)
      } finally {
        loading.value.portfolioBreakdown = false
      }
    }

    const handleYearChange = (year) => {
      selectedYear.value = year
      fetchPortfolioBreakdown(year)
    }

    const error = ref(null)

    const portfolioBreakdownItems = computed(() => {
      if (!portfolioBreakdownData.value) return []
      
      const result = []
      for (const category of ['consolidated_context', 'unrestricted_context', 'restricted_context']) {
        if (portfolioBreakdownData.value[category]) {
          result.push({ name: category.replace('_context', '').toUpperCase(), isHeader: true })
          
          portfolioBreakdownData.value[category].forEach(item => {
            result.push(item)
          })
        }
      }
      return result
    })

    onMounted(async () => {
      emit('update-page-title', 'Summary Analysis')
      await fetchYearOptions()
      await fetchBrokerPerformanceData()
      await fetchPortfolioBreakdown(selectedYear.value)
    })

    // Watch for changes in the store that should trigger a data refresh
    watch(
      () => store.state.dataRefreshTrigger,
      () => {
        fetchBrokerPerformanceData()
        fetchPortfolioBreakdown(selectedYear.value)
      }
    )

    // This watch is used to update the year options when the selected broker changes.
    watch(
      () => store.state.selectedBroker,
      () => {
        fetchYearOptions()
      }
    )

    return {
      loading,
      brokerPerformanceData,
      portfolioBreakdownData,
      brokerPerformanceHeaders,
      brokerPerformanceSubHeaders,
      portfolioBreakdownHeaders,
      portfolioBreakdownSubHeaders,
      portfolioBreakdownCategories,
      years,
      subHeaders,
      currentYear,
      selectedYear,
      yearOptions,
      handleYearChange,
      error,
      totalData,
      portfolioBreakdownItems,
    }
  }
}
</script>

<style scoped>
.table-wrapper {
  overflow-x: auto;
  margin-bottom: 20px;
}
.v-data-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}
.v-data-table th, .v-data-table td {
  padding: 8px;
}
.v-data-table th {
  border-bottom: 2px solid #bdbdbd;
}
.highlight-column {
  background-color: rgba(0, 0, 0, 0.03);
}
.italic {
  font-style: italic;
}
.no-wrap {
  white-space: nowrap;
}
.group-header {
  background-color: #e0e0e0;
  font-weight: bold;
  border-top: 1px solid #bdbdbd;
  border-bottom: 1px solid #bdbdbd;
}
.subtotal-row {
  background-color: #f0f0f0;
}
.total-row {
  font-weight: bold;
  background-color: #c0c0c0;
}
/* Add vertical lines between year groups in the main part of the table */
.v-data-table tbody td:nth-child(8n+1):not(:first-child):not(:last-child) {
  border-right: 2px solid #bdbdbd;
}
/* Add vertical lines for the first header row (years) */
.v-data-table thead tr:first-child th:nth-child(n+3) {
  border-left: 2px solid #bdbdbd;
}
/* Add vertical lines for the second header row (subheaders) */
.v-data-table thead tr:nth-child(2) th:nth-child(8n+1):not(:first-child) {
  border-left: 2px solid #bdbdbd;
}
/* Zebra striping for rows */
.v-data-table tbody tr:nth-child(even):not(.group-header):not(.total-row) {
  background-color: #f9f9f9;
}
/* Highlight YTD and All-time columns in the header */
.v-data-table thead th.highlight-column {
  background-color: rgba(0, 0, 0, 0.03);
}
/* Add these new styles */
.v-data-table >>> thead th {
  font-weight: bold;
  background-color: #f5f5f5;
}

.v-data-table >>> tbody td {
  height: 48px;
}

.group-header td {
  font-weight: bold;
  background-color: #e0e0e0;
  text-transform: capitalize;
}

.portfolio-breakdown-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.portfolio-breakdown-table thead th {
  font-weight: bold;
  background-color: #f5f5f5;
  text-align: right;
  padding: 12px 8px;
}

.portfolio-breakdown-table thead th:first-child {
  text-align: left;
}

.portfolio-breakdown-table tbody td {
  height: 48px;
  text-align: right;
  padding: 8px;
}

.portfolio-breakdown-table tbody td:first-child {
  text-align: left;
}

.group-header td {
  font-weight: bold;
  background-color: #e0e0e0;
  text-transform: uppercase;
  padding: 12px 8px;
}

.total-row {
  font-weight: bold;
}

/* Zebra striping for rows */
.portfolio-breakdown-table tbody tr:nth-child(even):not(.group-header):not(.total-row) {
  background-color: #f9f9f9;
}
</style>