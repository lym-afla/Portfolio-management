<template>
  <v-card>
    <v-card-title>Value and return over time</v-card-title>
    <v-card-text>
      <v-row>
        <v-col cols="12" sm="4">
          <v-select
            v-model="selectedBreakdown"
            :items="breakdownOptions"
            label="Breakdown by"
            @update:model-value="updateParams"
          ></v-select>
        </v-col>
        <v-col cols="12" sm="4">
          <v-btn-toggle v-model="selectedFrequency" mandatory @update:model-value="updateParams">
            <v-btn value="D">D</v-btn>
            <v-btn value="W">W</v-btn>
            <v-btn value="M">M</v-btn>
            <v-btn value="Q">Q</v-btn>
            <v-btn value="Y">Y</v-btn>
          </v-btn-toggle>
        </v-col>
        <v-col cols="12" sm="4">
          <DateRangeSelector
            v-model="dateRangeForSelector"
            @update:model-value="handleDateRangeChange"
          />
        </v-col>
      </v-row>
      <div class="chart-wrapper" v-if="!isEmptyData">
        <StackedBarLineChart
          v-if="!loading && chartDataComputed && chartOptionsComputed"
          :chart-data="chartDataComputed"
          :options="chartOptionsComputed"
        />
        <div v-if="loading" class="chart-overlay">
          <v-progress-circular indeterminate color="primary" size="64" />
        </div>
      </div>
      <v-alert v-else type="info" text="No data available"></v-alert>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref, watch, computed } from 'vue'
import { useStore } from 'vuex'
import StackedBarLineChart from '@/components/charts/StackedBarLineChart.vue'
import { getChartOptions } from '@/config/chartConfig'
import DateRangeSelector from '@/components/DateRangeSelector.vue'
// import { calculateDateRange } from '@/utils/dateRangeUtils'

export default {
  name: 'NAVChart',
  components: { StackedBarLineChart, DateRangeSelector },
  props: {
    chartData: {
      type: Object,
      default: () => ({
        labels: [],
        datasets: []
      })
    },
    loading: {
      type: Boolean,
      default: false
    },
    initialParams: {
      type: Object,
      required: true
    },
    effectiveCurrentDate: {
      type: String,
      required: true
    }
  },
  emits: ['update-params'],
  setup(props, { emit }) {
    const store = useStore()
    const chartOptions = ref(null)

    const navChartParams = computed(() => store.state.navChartParams)

    const selectedBreakdown = ref(navChartParams.value.breakdown)
    const selectedFrequency = ref(navChartParams.value.frequency)
    const dateRange = ref(navChartParams.value.dateRange)
    const dateFrom = ref(navChartParams.value.dateFrom)
    const dateTo = ref(navChartParams.value.dateTo)

    const breakdownOptions = [
      { title: 'Account', value: 'account' },
      { title: 'Asset Type', value: 'asset_type' },
      { title: 'Asset Class', value: 'asset_class' },
      { title: 'Currency', value: 'currency' },
      { title: 'No breakdown', value: 'none' },
      { title: 'Value Contributions', value: 'value_contributions' },
      { title: 'Cumulative Value', value: 'value_contributions_cumulative' }
    ]

    const updateParams = () => {
      const params = {
        frequency: selectedFrequency.value,
        dateFrom: dateFrom.value,
        dateTo: dateTo.value,
        breakdown: selectedBreakdown.value,
        dateRange: dateRange.value
      }
      store.dispatch('updateNavChartParams', params)
      emit('update-params', params)
    }

    const handleDateRangeChange = (newDateRange) => {
      dateRange.value = newDateRange.dateRange
      dateFrom.value = newDateRange.dateFrom
      dateTo.value = newDateRange.dateTo
      updateParams()
    }

    // Add isEmptyData computed property
    const isEmptyData = computed(() => {
      // Case 1: Explicit empty flag
      if (props.chartData?.empty === true) {
        return true
      }

      // Case 2: No datasets or labels
      if (!props.chartData?.datasets?.length || !props.chartData?.labels?.length) {
        return true
      }

      // Case 3: Check if all data points are empty/zero/N/A
      const hasValidData = props.chartData.datasets.some(dataset => {
        return dataset.data.some(value => {
          if (typeof value === 'number') {
            return value !== 0
          }
          return value !== 'N/A'
        })
      })

      return !hasValidData
    })

    // Initialize chart options
    const initChartOptions = async () => {
      chartOptions.value = await getChartOptions(props.chartData.currency)
    }

    // Watch for both currency changes and entire chartData changes
    watch([
      () => props.chartData?.currency,
      () => props.chartData
    ], async ([newCurrency]) => {
      if (newCurrency) {
        await initChartOptions()
      }
    }, { deep: true, immediate: true }) // Added immediate: true to run on mount

    const chartDataComputed = computed(() => {
      if (!props.chartData?.datasets || !chartOptions.value) {
        return {
          labels: [],
          datasets: []
        }
      }
      
      const { colorPalette } = chartOptions.value
      
      return {
        labels: props.chartData.labels,
        datasets: props.chartData.datasets.map((dataset, index) => ({
          ...dataset,
          backgroundColor: dataset.type === 'bar' ? colorPalette[index % colorPalette.length] : dataset.backgroundColor,
          borderColor: dataset.type === 'line' ? colorPalette[index % colorPalette.length] : undefined,
          order: dataset.type === 'line' ? 0 : index + 1,
          yAxisID: dataset.type === 'line' ? 'y1' : 'y'
        }))
      }
    })

    const chartOptionsComputed = computed(() => {
      if (!chartOptions.value) {
        return {}
      }
      
      return {
        ...chartOptions.value.navChartOptions,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          ...chartOptions.value.navChartOptions.scales,
          y: {
            ...chartOptions.value.navChartOptions.scales.y,
            title: {
              ...chartOptions.value.navChartOptions.scales.y.title,
              text: props.chartData?.currency
            }
          }
        }
      }
    })

    return {
      chartDataComputed,
      chartOptionsComputed,
      selectedBreakdown,
      selectedFrequency,
      dateRange,
      dateFrom,
      dateTo,
      breakdownOptions,
      updateParams,
      handleDateRangeChange,
      dateRangeForSelector: computed(() => ({
        dateRange: dateRange.value,
        dateFrom: dateFrom.value,
        dateTo: dateTo.value
      })),
      isEmptyData,
    }
  }
}
</script>

<style scoped>
.chart-wrapper {
  position: relative;
  width: 100%;
  height: 600px;
  padding: 16px;  /* Add some padding */
}

.chart-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1;
}
</style>
