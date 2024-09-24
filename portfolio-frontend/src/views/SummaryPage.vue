<template>
  <v-container fluid>
    <!-- Date range selector component -->
    <DateRangeSelector @date-range-changed="handleDateRangeChange" />

    <!-- Broker performance breakdown table -->
    <v-card class="mt-4">
      <v-card-title>Broker performance breakdown</v-card-title>
      <v-card-text>
        <v-data-table
          :headers="brokerPerformanceHeaders"
          :items="brokerPerformanceData"
          :loading="loading.brokerPerformance"
          class="elevation-1"
        >
          <!-- Custom header to handle multi-level headers -->
          <template v-slot:header>
            <thead>
              <tr>
                <th rowspan="2"></th>
                <th v-for="year in years" :key="year" :colspan="8" class="text-center" :class="{ 'highlight-column': year === 'YTD' || year === 'All-time' }">
                  {{ year === 'YTD' ? currentYear : year }}
                </th>
              </tr>
              <tr>
                <template v-for="year in years" :key="`subheader-${year}`">
                  <th v-for="subheader in subHeaders" :key="`${year}-${subheader.value}`" class="text-center" :class="{ 'highlight-column': year === 'YTD' || year === 'All-time' }">
                    {{ subheader.text }}
                  </th>
                </template>
              </tr>
            </thead>
          </template>

          <!-- Custom item slot to handle nested data -->
          <template v-slot:item="{ item }">
            <tr>
              <td>{{ item.name }}</td>
              <template v-for="year in years" :key="`data-${year}`">
                <td v-for="subheader in subHeaders" :key="`${year}-${subheader.value}`" class="text-center" :class="{ 'highlight-column': year === 'YTD' || year === 'All-time' }">
                  {{ item[year][subheader.value] }}
                </td>
              </template>
            </tr>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Portfolio breakdown table -->
    <v-card class="mt-4">
      <v-card-title>Portfolio breakdown</v-card-title>
      <v-card-text>
        <v-data-table
          :headers="portfolioBreakdownHeaders"
          :items="portfolioBreakdownData"
          :loading="loading.portfolioBreakdown"
          class="elevation-1"
        >
          <!-- Add custom slots if needed -->
        </v-data-table>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { useStore } from 'vuex'
import { useErrorHandler } from '@/composables/useErrorHandler'
import DateRangeSelector from '@/components/DateRangeSelector.vue'
import { getSummaryAnalysis } from '@/services/api'

export default {
  name: 'SummaryPage',
  components: {
    DateRangeSelector,
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()
    const { handleApiError } = useErrorHandler()
    const loading = ref({
      brokerPerformance: false,
      portfolioBreakdown: false,
    })
    const brokerPerformanceData = ref([])
    const portfolioBreakdownData = ref([])
    const years = ref([])
    const currentYear = new Date().getFullYear()

    const brokerPerformanceHeaders = computed(() => [
      { text: '', value: 'name', sortable: false },
      ...years.value.flatMap(year => 
        subHeaders.value.map(subheader => ({
          text: subheader.text,
          value: `${year}.${subheader.value}`,
          sortable: false,
          align: 'center',
          class: year === 'YTD' || year === 'All-time' ? 'highlight-column' : ''
        }))
      )
    ])

    const portfolioBreakdownHeaders = ref([
      { text: 'Category', value: 'category' },
      { text: 'Value', value: 'value' },
      { text: 'Percentage', value: 'percentage' },
    ])

    const subHeaders = ref([
      { text: 'BoP NAV', value: 'bop_nav' },
      { text: 'Cash-in/(out)', value: 'cash_flow' },
      { text: 'Return', value: 'return' },
      { text: 'FX', value: 'fx' },
      { text: 'TSR', value: 'tsr' },
      { text: 'EoP NAV', value: 'eop_nav' },
      { text: 'Commissions', value: 'commissions' },
      { text: 'Fee per AuM', value: 'fee_per_aum' },
    ])

    const handleDateRangeChange = async (dateRange) => {
      await fetchSummaryData(dateRange.startDate, dateRange.endDate)
    }

    const fetchSummaryData = async (startDate, endDate) => {
      try {
        loading.value.brokerPerformance = true
        loading.value.portfolioBreakdown = true
        const data = await getSummaryAnalysis(startDate, endDate)
        brokerPerformanceData.value = data.brokerPerformance
        portfolioBreakdownData.value = data.portfolioBreakdown
        years.value = data.years
      } catch (error) {
        handleApiError(error)
      } finally {
        loading.value.brokerPerformance = false
        loading.value.portfolioBreakdown = false
      }
    }

    onMounted(async () => {
      emit('update-page-title', 'Summary Analysis')
      // Load initial data with default date range (e.g., current year)
      const currentDate = new Date()
      const startDate = new Date(currentDate.getFullYear(), 0, 1) // January 1st of current year
      const endDate = currentDate
      await fetchSummaryData(startDate, endDate)
    })

    // Watch for changes in the store that should trigger a data refresh
    watch(
      () => store.state.dataRefreshTrigger,
      async () => {
        console.log('Summary page detected a change that requires data refresh')
        const currentDate = new Date(store.state.effectiveCurrentDate)
        const startDate = new Date(currentDate.getFullYear(), 0, 1)
        await fetchSummaryData(startDate, currentDate)
      }
    )

    return {
      loading,
      brokerPerformanceData,
      portfolioBreakdownData,
      brokerPerformanceHeaders,
      portfolioBreakdownHeaders,
      years,
      subHeaders,
      currentYear,
      handleDateRangeChange,
    }
  }
}
</script>

<style scoped>
.highlight-column {
  background-color: rgba(0, 0, 0, 0.05);
}
</style>