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
        <template v-else>
          <!-- Year selector -->
          <v-row no-gutters class="mb-4">
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
          
          <v-data-table
            :headers="brokerPerformanceHeaders"
            :items="brokerPerformanceData"
            class="elevation-1"
          >
            <template v-slot:header="{ props: { headers } }">
              <thead>
                <tr>
                  <th v-for="header in headers" :key="header.value" :colspan="header.colspan" :rowspan="header.rowspan" :class="header.class">
                    {{ header.text }}
                  </th>
                </tr>
                <tr>
                  <th v-for="subheader in brokerPerformanceSubHeaders" :key="subheader.value" :class="subheader.class">
                    {{ subheader.text }}
                  </th>
                </tr>
              </thead>
            </template>

            <!-- Custom item slot to handle nested data -->
            <template v-slot:item="{ item }">
              <tr>
                <td>{{ item.name }}</td>
                <template v-for="year in years" :key="`data-${year}`">
                  <td v-for="subheader in subHeaders" :key="`${year}-${subheader.value}`" class="text-center" :class="{ 'highlight-column': year === 'YTD' || year === 'All-time' }">
                    {{ item.data && item.data[year] ? item.data[year][subheader.value] : 'N/A' }}
                  </td>
                </template>
              </tr>
            </template>
          </v-data-table>
        </template>
      </v-card-text>
    </v-card>

    <!-- Portfolio breakdown table -->
    <v-card class="mt-4">
      <v-card-title>Portfolio breakdown</v-card-title>
      <v-card-text>
        <v-skeleton-loader
          v-if="loading.portfolioBreakdown"
          type="table"
        ></v-skeleton-loader>
        <v-data-table
          v-else
          :headers="portfolioBreakdownHeaders"
          :items="portfolioBreakdownData"
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
      { text: 'Category', value: 'category' },
      { text: 'Value', value: 'value' },
      { text: 'Percentage', value: 'percentage' },
    ])

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
        if (data && data.public_markets_context && data.restricted_investments_context && data.total_context) {
          brokerPerformanceData.value = [
            ...data.public_markets_context.lines,
            ...data.restricted_investments_context.lines,
            data.total_context.line
          ]
          portfolioBreakdownData.value = [] // You might need to adjust this based on your actual data structure
          years.value = data.public_markets_context.years || []
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

    const error = ref(null)

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
      brokerPerformanceSubHeaders,
      portfolioBreakdownHeaders,
      years,
      subHeaders,
      currentYear,
      timespan,
      yearOptions,
      handleTimespanChange,
      error,
    }
  }
}
</script>

<style scoped>
.highlight-column {
  background-color: rgba(0, 0, 0, 0.05);
}
</style>