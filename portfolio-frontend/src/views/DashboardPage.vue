<template>
  <v-container fluid class="pa-0">
    <v-row class="equal-height-row">
      <v-col cols="12" md="3">
        <v-skeleton-loader v-if="loading.summary" type="card" class="h-100" />
        <SummaryCard v-else-if="!error.summary" :summary="summary" :currency="currency" class="h-100" />
        <v-alert v-else type="error" class="h-100">{{ error.summary }}</v-alert>
      </v-col>
      <v-col cols="12" md="9">
        <v-row class="equal-height-row h-100">
          <v-col v-for="(chart, index) in chartTypes" :key="index" cols="12" md="4">
            <v-skeleton-loader v-if="loading.breakdownCharts" type="card" class="h-100" />
            <BreakdownChart 
              v-else-if="!error.breakdownCharts" 
              :title="chartTitles[chart]" 
              :data="breakdownData[chart]" 
              :currency="currency"
              class="h-100" 
            />
            <v-alert v-else type="error" class="h-100">{{ error.breakdownCharts }}</v-alert>
          </v-col>
        </v-row>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <v-skeleton-loader v-if="loading.summaryOverTime" type="table" />
        <SummaryOverTimeTable
          v-else-if="!error.summaryOverTime"
          :lines="summaryOverTimeData ? summaryOverTimeData.lines : []"
          :years="summaryOverTimeData ? summaryOverTimeData.years : []"
          :currentYear="summaryOverTimeData ? summaryOverTimeData.currentYear : ''"
        />
        <v-alert v-else type="error">{{ error.summaryOverTime }}</v-alert>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <v-skeleton-loader v-if="loading.navChart" type="card" height="400" />
        <NAVChart 
          v-else
          :chartData="navChartData"
          :loading="updating.navChart"
          :initialParams="navChartInitialParams"
          :effectiveCurrentDate="effectiveCurrentDate"
          @update-params="fetchNAVChartData"
        />
        <v-alert v-if="error.navChart" type="error" class="mt-2">{{ error.navChart }}</v-alert>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import { ref, onMounted, onUnmounted, inject, watch, computed } from 'vue'
import { useStore } from 'vuex'
import { calculateDateRange } from '@/utils/dateRangeUtils'
import SummaryCard from '@/components/dashboard/SummaryCard.vue'
import BreakdownChart from '@/components/dashboard/BreakdownChart.vue'
import SummaryOverTimeTable from '@/components/dashboard/SummaryOverTimeTable.vue'
import NAVChart from '@/components/dashboard/NAVChart.vue'
import { getDashboardSummary, getDashboardBreakdown, getDashboardSummaryOverTime, getNAVChartData } from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'

export default {
  name: 'DashboardPage',
  components: {
    SummaryCard,
    BreakdownChart,
    SummaryOverTimeTable,
    NAVChart,
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()
    const { handleApiError } = useErrorHandler()
    const clearErrors = inject('clearErrors')
    const summary = ref({})
    const currency = ref('USD')
    const breakdownData = ref({
      assetType: {},
      assetClass: {},
      currency: {},
    })
    const totalNAV = ref('')
    const summaryOverTimeData = ref({})
    const navChartData = ref(null)
    // const navChartInitialParams = computed(() => store.state.navChartParams)
    
    const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)

    const navChartInitialParams = computed(() => {
      const params = store.state.navChartParams
      const defaultDateRange = 'ytd'

      if (!params.dateFrom || !params.dateTo) {
        const calculatedRange = calculateDateRange(params.dateRange || defaultDateRange, effectiveCurrentDate.value)
        return {
          ...params,
          dateRange: params.dateRange || defaultDateRange,
          dateFrom: calculatedRange.from,
          dateTo: calculatedRange.to
        }
      }
      return params
    })
    const loading = ref({
      summary: true,
      breakdownCharts: true,
      summaryOverTime: true,
      navChart: true,
    })
    const updating = ref({ navChart: false })
    const error = ref({
      summary: null,
      breakdownCharts: null,
      summaryOverTime: null,
      navChart: null,
    })

    const chartTypes = ['assetType', 'assetClass', 'currency']
    const chartTitles = {
      assetType: 'Asset Type',
      assetClass: 'Asset Class',
      currency: 'Currency',
    }

    const fetchSummaryData = async () => {
      try {
        clearErrors()
        loading.value.summary = true
        console.log('Fetching dashboard summary...')
        const data = await getDashboardSummary()
        console.log('Received summary data:', data)
        summary.value = data
        loading.value.summary = false
      } catch (err) {
        console.error('Error fetching summary:', err)
        error.value.summary = handleApiError(err)
        loading.value.summary = false
      }
    }

    const fetchBreakdownData = async () => {
      try {
        clearErrors()
        loading.value.breakdownCharts = true
        console.log('Fetching dashboard breakdown...')
        const data = await getDashboardBreakdown()
        console.log('Received breakdown data:', data)
        breakdownData.value = {
          assetType: { ...data.assetType, totalNAV: data.totalNAV },
          assetClass: { ...data.assetClass, totalNAV: data.totalNAV },
          currency: { ...data.currency, totalNAV: data.totalNAV },
        }
        totalNAV.value = data.totalNAV
        loading.value.breakdownCharts = false
      } catch (err) {
        console.error('Error fetching breakdown:', err)
        error.value.breakdownCharts = handleApiError(err)
        loading.value.breakdownCharts = false
      }
    }

    const fetchSummaryOverTimeData = async () => {
      try {
        clearErrors()
        loading.value.summaryOverTime = true
        console.log('Fetching summary over time data...')
        const data = await getDashboardSummaryOverTime()
        console.log('Received summary over time data:', data)
        summaryOverTimeData.value = data
        loading.value.summaryOverTime = false
      } catch (err) {
        console.error('Error fetching summary over time:', err)
        if (err.response && err.response.status === 404) {
          // Handle 404 as "no data" instead of an error
          summaryOverTimeData.value = null
        } else {
          error.value.summaryOverTime = handleApiError(err)
        }
        loading.value.summaryOverTime = false
      }
    }

    const fetchNAVChartData = async (params = navChartInitialParams.value) => {
      try {
        clearErrors()
        updating.value.navChart = true
        console.log('Fetching NAV chart data...')
        const data = await getNAVChartData(
          params.breakdown,
          params.frequency,
          params.dateFrom,
          params.dateTo,
        )
        console.log('Received NAV chart data:', data)
        navChartData.value = data
      } catch (err) {
        console.error('Error fetching NAV chart data:', err)
        error.value.navChart = handleApiError(err)
      } finally {
        updating.value.navChart = false
        loading.value.navChart = false
      }
    }

    const refreshAllData = async () => {
      await fetchSummaryData()
      await fetchBreakdownData()
      await fetchSummaryOverTimeData()
      await fetchNAVChartData()
    }

    // Watch for changes in the store that should trigger a data refresh
    watch(
      [
        () => store.state.dataRefreshTrigger,
      ],
      async () => {
        console.log('Dashboard detected a change that requires data refresh')
        await refreshAllData()
      }
    )

    onMounted(async () => {
      if (!effectiveCurrentDate.value) {
        await store.dispatch('fetchEffectiveCurrentDate')
      }

      if (!store.state.navChartParams.dateFrom || !store.state.navChartParams.dateTo) {
        const defaultDateRange = 'ytd'
        const calculatedDateRange = calculateDateRange(defaultDateRange, effectiveCurrentDate.value)
        await store.dispatch('updateNavChartParams', { dateRange: defaultDateRange, dateFrom: calculatedDateRange.from, dateTo: calculatedDateRange.to })
      }
      console.log('Date range:', navChartInitialParams.value)
      await fetchSummaryData()
      await fetchBreakdownData()
      await fetchSummaryOverTimeData()
      await fetchNAVChartData(navChartInitialParams.value)
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    return {
      summary,
      currency,
      breakdownData,
      totalNAV,
      summaryOverTimeData,
      navChartData,
      loading,
      error,
      updating,
      chartTypes,
      chartTitles,
      navChartInitialParams,
      fetchNAVChartData,
      effectiveCurrentDate,
    }
  },
}
</script>
<style scoped>
.equal-height-row {
  display: flex;
  flex-wrap: wrap;
}

.equal-height-row > [class*='col-'] {
  display: flex;
  flex-direction: column;
}

.equal-height-row .v-card {
  flex: 1 1 auto;
}

.h-100 {
  height: 100%;
}
</style>
