<template>
  <!-- Legacy allocation leaf (C5a): the incumbent Chart.js horizontal bars
       extracted verbatim from BreakdownChart. This is the allocation cards'
       only Chart.js import site — the shell loads it asynchronously, so the
       legacy runtime (and its datalabels plugin) is downloaded only when a
       rollback build, a legacy-only payload or an explicit user fallback
       actually renders it. -->
  <div class="chart-container">
    <Bar :data="data" :options="options" />
  </div>
</template>

<script setup>
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale,
} from 'chart.js'
import ChartDataLabels from 'chartjs-plugin-datalabels'

ChartJS.register(
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale,
  ChartDataLabels
)

defineProps({
  data: {
    type: Object,
    required: true,
  },
  options: {
    type: Object,
    required: true,
  },
})
</script>

<style scoped>
.chart-container {
  position: relative;
  width: 100%;
}
</style>
