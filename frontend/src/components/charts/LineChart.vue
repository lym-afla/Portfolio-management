<template>
  <Line :data="chartData" :options="options" />
</template>

<script setup>
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  TimeScale,
  Title,
  Tooltip,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  CategoryScale,
} from 'chart.js'
import ChartDataLabels from 'chartjs-plugin-datalabels'
import 'chartjs-adapter-date-fns'

// C5a: the time scale, its date-fns adapter and the default locale moved here
// from SecurityDetailPage so this lazy legacy leaf carries its own
// registration; loading this module is the only way the Chart.js runtime
// reaches the security detail route.
ChartJS.register(
  TimeScale,
  Title,
  Tooltip,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  CategoryScale,
  ChartDataLabels
)

// Set the default locale for Chart.js
ChartJS.defaults.locale = 'en-US'

defineProps({
  chartData: {
    type: Object,
    required: true,
  },
  options: {
    type: Object,
    default: () => ({}),
  },
})
</script>
