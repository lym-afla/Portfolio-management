<template>
  <canvas ref="chartRef"></canvas>
</template>

<script>
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import {
  Chart,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  BarController,
  LineController
} from 'chart.js'
import ChartDataLabels from 'chartjs-plugin-datalabels'

// Register the components we need
Chart.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  BarController,
  LineController,
  ChartDataLabels
)

export default {
  name: 'StackedBarLineChart',
  props: {
    chartData: {
      type: Object,
      required: true
    },
    options: {
      type: Object,
      required: true
    }
  },
  setup(props) {
    const chartRef = ref(null)
    let chartInstance = null

    const initChart = () => {
      if (!chartRef.value || !props.chartData || !props.options) return
      
      if (chartInstance) {
        chartInstance.destroy()
      }

      const ctx = chartRef.value.getContext('2d')
      chartInstance = new Chart(ctx, {
        type: 'bar',
        data: props.chartData,
        options: props.options
      })
    }

    const updateChart = () => {
      if (!chartInstance || !props.chartData || !props.options) return
      
      // If data structure has changed significantly, reinitialize the chart
      if (chartInstance.data.datasets.length !== props.chartData.datasets.length) {
        initChart()
        return
      }
      
      chartInstance.data = props.chartData
      chartInstance.options = props.options
      chartInstance.update()
    }

    onMounted(() => {
      if (props.chartData && props.options) {
        initChart()
      }
    })

    // Watch both props with immediate effect
    watch([() => props.chartData, () => props.options], () => {
      if (props.chartData && props.options) {
        if (chartInstance) {
          updateChart()
        } else {
          initChart()
        }
      }
    }, { deep: true, immediate: true })

    onBeforeUnmount(() => {
      if (chartInstance) {
        chartInstance.destroy()
      }
    })

    return {
      chartRef
    }
  }
}
</script> 