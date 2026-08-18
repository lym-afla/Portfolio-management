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
          />
        </v-col>
        <v-col cols="12" sm="4">
          <v-btn-toggle
            v-model="selectedFrequency"
            mandatory
            aria-label="Chart frequency"
            @update:model-value="updateParams"
          >
            <v-btn value="D" title="Day">Day</v-btn>
            <v-btn value="W" title="Week">Week</v-btn>
            <v-btn value="M" title="Month">Month</v-btn>
            <v-btn value="Q" title="Quarter">Quarter</v-btn>
            <v-btn value="Y" title="Year">Year</v-btn>
          </v-btn-toggle>
        </v-col>
        <v-col cols="12" sm="4">
          <DateRangeSelector
            v-model="dateRangeForSelector"
            @update:model-value="handleDateRangeChange"
          />
        </v-col>
      </v-row>
      <div class="chart-wrapper" v-if="!hasNoData">
        <StackedBarLineChart
          v-if="!loading && chartDataComputed && chartOptionsComputed"
          :chart-data="chartDataComputed"
          :options="chartOptionsComputed"
        />
        <div v-if="loading" class="chart-overlay">
          <v-progress-circular indeterminate color="primary" size="64" />
        </div>
      </div>
      <v-alert v-else type="info" text="No data available" />
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import StackedBarLineChart from '@/components/charts/StackedBarLineChart.vue'
import { getChartOptions, colorPalette } from '@/config/chartConfig'
import DateRangeSelector from '@/components/DateRangeSelector.vue'
// import { calculateDateRange } from '@/utils/dateRangeUtils'

const props = defineProps({
  chartData: {
    type: Object,
    default: () => ({
      labels: [],
      datasets: [],
    }),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  initialParams: {
    type: Object,
    required: true,
  },
  effectiveCurrentDate: {
    type: String,
    required: true,
  },
})
const emit = defineEmits(['update-params'])

const appStore = useAppStore()
const chartOptions = ref(null)

const navChartParams = computed(() => appStore.navChartParams)

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
  { title: 'Cumulative Value', value: 'value_contributions_cumulative' },
]

function updateParams() {
  const params = {
    frequency: selectedFrequency.value,
    dateFrom: dateFrom.value,
    dateTo: dateTo.value,
    breakdown: selectedBreakdown.value,
    dateRange: dateRange.value,
  }
  appStore.updateNavChartParams(params)
  emit('update-params', params)
}

function handleDateRangeChange(newDateRange) {
  dateRange.value = newDateRange.dateRange
  dateFrom.value = newDateRange.dateFrom
  dateTo.value = newDateRange.dateTo
  updateParams()
}

// "No data" means the series carry no points at all. An all-zero portfolio
// is data, not an absence of data.
const hasNoData = computed(
  () =>
    !props.chartData ||
    !props.chartData.datasets ||
    props.chartData.datasets.every(
      (dataset) => !dataset.data || dataset.data.length === 0
    )
)

// Initialize chart options
const initChartOptions = async () => {
  chartOptions.value = await getChartOptions(props.chartData.currency)
}

// Watch for both currency changes and entire chartData changes
watch(
  [() => props.chartData?.currency, () => props.chartData],
  async ([newCurrency]) => {
    if (newCurrency) {
      await initChartOptions()
    }
  },
  { deep: true, immediate: true }
) // Added immediate: true to run on mount

const chartDataComputed = computed(() => {
  if (!props.chartData?.datasets || !chartOptions.value) {
    return {
      labels: [],
      datasets: [],
    }
  }

  const chartPalette = colorPalette

  return {
    labels: props.chartData.labels,
    datasets: props.chartData.datasets.map((dataset, index) => ({
      ...dataset,
      backgroundColor:
        dataset.type === 'bar'
          ? chartPalette[index % chartPalette.length]
          : dataset.backgroundColor,
      borderColor:
        dataset.type === 'line'
          ? chartPalette[index % chartPalette.length]
          : undefined,
      order: dataset.type === 'line' ? 0 : index + 1,
      yAxisID: dataset.type === 'line' ? 'y1' : 'y',
    })),
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
          text: props.chartData?.currency,
        },
      },
    },
  }
})

const dateRangeForSelector = computed(() => ({
  dateRange: dateRange.value,
  dateFrom: dateFrom.value,
  dateTo: dateTo.value,
}))
</script>

<style scoped>
.chart-wrapper {
  position: relative;
  width: 100%;
  height: 600px;
  padding: 16px; /* Add some padding */
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
