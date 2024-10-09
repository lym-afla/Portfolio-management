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
          <DateRangeSelector v-model="dateRangeForSelector" @update:model-value="handleDateRangeChange" />
        </v-col>
      </v-row>
      <div class="chart-wrapper">
        <canvas ref="chartRef"></canvas>
        <div v-if="loading" class="chart-overlay">
          <v-progress-circular indeterminate color="primary" size="64" />
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref, watch, onMounted, computed } from 'vue'
import { useStore } from 'vuex'
import { Chart, registerables } from 'chart.js'
import { getChartOptions } from '@/config/chartConfig'
import DateRangeSelector from '@/components/DateRangeSelector.vue'
// import { calculateDateRange } from '@/utils/dateRangeUtils'

Chart.register(...registerables)

export default {
  name: 'NAVChart',
  components: { DateRangeSelector },
  props: {
    chartData: {
      type: Object,
      required: true
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
    const chartRef = ref(null)
    const chartInstance = ref(null)

    const navChartParams = computed(() => store.state.navChartParams)

    const selectedBreakdown = ref(navChartParams.value.breakdown)
    const selectedFrequency = ref(navChartParams.value.frequency)
    const dateRange = ref(navChartParams.value.dateRange)
    const dateFrom = ref(navChartParams.value.dateFrom)
    const dateTo = ref(navChartParams.value.dateTo)

    const breakdownOptions = [
      { title: 'Broker', value: 'broker' },
      { title: 'Asset Type', value: 'asset_type' },
      { title: 'Asset Class', value: 'asset_class' },
      { title: 'Currency', value: 'currency' },
      { title: 'No breakdown', value: 'none' },
      { title: 'Value Contributions', value: 'value_contributions' }
    ]

    const updateParams = () => {
      const params = {
        frequency: selectedFrequency.value,
        dateFrom: dateFrom.value,
        dateTo: dateTo.value,
        breakdown: selectedBreakdown.value
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

    onMounted(() => {
      initChart()
    })

    const initChart = async () => {
      if (!chartRef.value || !props.chartData) return
      const ctx = chartRef.value.getContext('2d')
      const { navChartOptions, colorPalette } = await getChartOptions(props.chartData.currency)
      if (chartInstance.value) {
        chartInstance.value.destroy()
      }

      const datasets = props.chartData.datasets.map((dataset, index) => ({
        ...dataset,
        backgroundColor: dataset.type === 'bar' ? colorPalette[index % colorPalette.length] : dataset.backgroundColor,
        // Set order for line charts to be higher (will be drawn last)
        order: dataset.type === 'line' ? 0 : index + 1
      }))

      chartInstance.value = new Chart(ctx, {
        type: 'bar',
        data: {
          ...props.chartData,
          datasets: datasets,
        },
        options: navChartOptions,
      })
    }

    watch(() => props.chartData, initChart, { deep: true })

    return {
      chartRef,
      selectedBreakdown,
      selectedFrequency,
      dateRange,
      dateFrom,
      dateTo,
      breakdownOptions,
      updateParams,
      handleDateRangeChange,
      dateRangeForSelector: {
        dateRange: dateRange.value,
        dateFrom: dateFrom.value,
        dateTo: dateTo.value
      }
    }
  }
}
</script>

<style scoped>
.chart-wrapper {
  position: relative;
  width: 100%;
  height: 600px;
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