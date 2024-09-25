<template>
  <v-container fluid class="pa-0">
    <!-- Year selector -->
    <v-row no-gutters>
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
          @update:model-value="handleTimespanChange"
        >
          <template #item="{ props, item }">
            <v-list-item v-if="!item.raw.divider" v-bind="props" :title="item.title"></v-list-item>
            <v-divider v-else class="my-2"></v-divider>
          </template>
        </v-select>
      </v-col>
    </v-row>

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
import { useRouter } from 'vue-router'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { getSummaryAnalysis, getYearOptions } from '@/services/api'
import { useTableSettings } from '@/composables/useTableSettings'

export default {
  name: 'SummaryPage',
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()
    const router = useRouter()
    const { handleApiError } = useErrorHandler()
    const loading = ref({
      brokerPerformance: false,
      portfolioBreakdown: false,
    })
    const brokerPerformanceData = ref([])
    const portfolioBreakdownData = ref([])
    const years = ref([])
    const currentYear = new Date().getFullYear()

    const {
      timespan,
      dateFrom,
      dateTo,
      handleTimespanChange,
    } = useTableSettings()

    const yearOptions = ref([])

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

    const fetchYearOptions = async () => {
      try {
        const years = await getYearOptions()
        yearOptions.value = years
      } catch (error) {
        handleApiError(error)
      }
    }

    const fetchSummaryData = async () => {
      try {
        loading.value.brokerPerformance = true
        loading.value.portfolioBreakdown = true
        const data = await getSummaryAnalysis(dateFrom.value, dateTo.value)
        if (data && data.public_markets_context && data.restricted_investments_context) {
          brokerPerformanceData.value = data.public_markets_context.lines.concat(data.restricted_investments_context.lines)
          portfolioBreakdownData.value = data.total_context.line
          years.value = data.public_markets_context.years
        } else {
          console.error('Unexpected data structure:', data)
        }
      } catch (error) {
        if (error.message === 'Authentication required') {
          router.push('/login')  // Redirect to login page
        } else {
          handleApiError(error)
        }
      } finally {
        loading.value.brokerPerformance = false
        loading.value.portfolioBreakdown = false
      }
    }

    onMounted(async () => {
      emit('update-page-title', 'Summary Analysis')
      await fetchYearOptions()
      await handleTimespanChange('ytd')
    })

    // Watch for changes in the store that should trigger a data refresh
    watch(
      [timespan, dateFrom, dateTo, () => store.state.dataRefreshTrigger],
      () => {
        fetchSummaryData()
      },
      { deep: true }
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
      portfolioBreakdownHeaders,
      years,
      subHeaders,
      currentYear,
      timespan,
      yearOptions,
      handleTimespanChange,
    }
  }
}
</script>

<style scoped>
.highlight-column {
  background-color: rgba(0, 0, 0, 0.05);
}
</style>