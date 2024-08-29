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
            @update:model-value="fetchChartData"
          ></v-select>
        </v-col>
        <v-col cols="12" sm="4">
          <v-btn-toggle v-model="selectedFrequency" mandatory @change="fetchChartData">
            <v-btn value="D">D</v-btn>
            <v-btn value="W">W</v-btn>
            <v-btn value="M">M</v-btn>
            <v-btn value="Q">Q</v-btn>
            <v-btn value="Y">Y</v-btn>
          </v-btn-toggle>
        </v-col>
        <v-col cols="12" sm="4">
          <DateRangeSelector v-model="dateRange" @update:model-value="fetchChartData" />
        </v-col>
      </v-row>
      <div ref="chartContainer">
        <v-skeleton-loader v-if="loading" type="card" height="400" />
        <canvas v-else ref="chartRef" height="400"></canvas>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref, watch, onMounted, nextTick } from 'vue'
import { Chart, registerables } from 'chart.js'
import { getChartOptions } from '@/config/chartConfig'
import { getNAVChartData } from '@/services/api'
import DateRangeSelector from '@/components/DateRangeSelector.vue'

Chart.register(...registerables)

export default {
  name: 'NAVChart',
  components: { DateRangeSelector },
  emits: ['fetch-start', 'fetch-end', 'fetch-error'],
  setup(props, { emit }) {
    const chartRef = ref(null)
    const chartContainer = ref(null)
    const chartInstance = ref(null)
    const chartData = ref({ labels: [], datasets: [] })
    const currency = ref('')
    const loading = ref(true)

    const selectedBreakdown = ref('none')
    const selectedFrequency = ref('M')
    const dateRange = ref({ from: null, to: null })
    const breakdownOptions = [
      { title: 'Broker', value: 'broker' },
      { title: 'Asset Type', value: 'asset_type' },
      { title: 'Asset Class', value: 'asset_class' },
      { title: 'Currency', value: 'currency' },
      { title: 'No breakdown', value: 'none' },
      { title: 'Value Contributions', value: 'value_contributions' }
    ]

    const initChart = async () => {
      await nextTick()
      console.log('Initializing chart', chartRef.value, chartContainer.value)
      if (!chartRef.value) {
        console.error('Chart canvas element not found', chartRef, chartRef.value, !chartRef.value)
        if (chartContainer.value) {
          console.log('Recreating canvas element')
          const canvas = document.createElement('canvas')
          canvas.height = 400
          chartContainer.value.innerHTML = ''
          chartContainer.value.appendChild(canvas)
          chartRef.value = canvas
        } else {
          console.error('Chart container not found')
          return
        }
      }
      const ctx = chartRef.value.getContext('2d')
      const options = await getChartOptions(currency.value)
      if (chartInstance.value) {
        chartInstance.value.destroy()
      }
      chartInstance.value = new Chart(ctx, {
        type: 'bar',
        data: chartData.value,
        options: options.navChartOptions
      })
    }

    const fetchChartData = async () => {
      console.log('fetchChartData called')
      loading.value = true
      emit('fetch-start')
      try {
        const params = {
          frequency: selectedFrequency.value,
          from_date: dateRange.value.from,
          to_date: dateRange.value.to,
          breakdown: selectedBreakdown.value
        }
        console.log('Fetching chart data with params:', params)
        const data = await getNAVChartData(params)
        console.log('Received chart data:', data)
        chartData.value = data
        currency.value = data.currency
        await nextTick()
        await initChart()
        loading.value = false
        emit('fetch-end')
      } catch (error) {
        console.error('Error fetching NAV chart data:', error)
        loading.value = false
        emit('fetch-error', error.message || 'An error occurred while fetching chart data')
      }
    }

    onMounted(() => {
      console.log('NAVChart mounted')
      console.log('chartRef:', chartRef.value)
      console.log('chartContainer:', chartContainer.value)
      nextTick(() => {
        fetchChartData()
      })
    })

    watch([selectedBreakdown, selectedFrequency, dateRange], fetchChartData)

    return {
      chartRef,
      chartContainer,
      selectedBreakdown,
      selectedFrequency,
      dateRange,
      loading,
      breakdownOptions,
      fetchChartData
    }
  }
}
</script>