<template>
  <div>
    <Line
      v-if="chartData.datasets.length > 0"
      :data="chartData"
      :options="chartOptions"
    />
    <p v-else>No data available for the chart.</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import logger from '@/utils/logger'
import {
  Chart as ChartJS,
  Title,
  Tooltip,
  Legend,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
} from 'chart.js'

ChartJS.register(
  Title,
  Tooltip,
  Legend,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale
)

const props = defineProps({
  prices: {
    type: Array,
    required: true,
  },
})

const chartData = computed(() => {
  logger.log('Unknown', 'Prices prop:', props.prices)

  if (!props.prices || props.prices.length === 0) {
    logger.log('Unknown', 'No prices available')
    return {
      labels: [],
      datasets: [],
    }
  }

  // Group prices by security
  const pricesBySecurity = props.prices.reduce((acc, price) => {
    if (!acc[price.security__name]) {
      acc[price.security__name] = []
    }
    acc[price.security__name].push(price)
    return acc
  }, {})

  // Get unique dates across all securities and sort them
  const allDates = [
    ...new Set(props.prices.map((price) => price.date)),
  ].sort((a, b) => new Date(a) - new Date(b))

  // Generate datasets for each security
  const datasets = Object.entries(pricesBySecurity).map(
    ([securityName, prices], index) => {
      const data = allDates.map((date) => {
        const price = prices.find((p) => p.date === date)
        return price ? parseFloat(price.price) : null
      })

      return {
        label: securityName,
        data: data,
        borderColor: getColor(index),
        backgroundColor: getColor(index, 0.2),
        fill: false,
        tension: 0.1,
        spanGaps: true, // This will connect points even if there are null values in between
      }
    }
  )

  logger.log('Unknown', 'Datasets:', datasets)

  return {
    labels: allDates,
    datasets: datasets,
  }
})

const chartOptions = computed(() => {
  return {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: {
        beginAtZero: true,
      },
    },
    plugins: {
      legend: {
        display: true,
      },
    },
  }
})

function getColor(index, alpha = 1) {
  const colors = [
    `rgba(66, 165, 245, ${alpha})`, // blue
    `rgba(239, 83, 80, ${alpha})`, // red
    `rgba(102, 187, 106, ${alpha})`, // green
    `rgba(255, 167, 38, ${alpha})`, // orange
    `rgba(171, 71, 188, ${alpha})`, // purple
    `rgba(255, 214, 0, ${alpha})`, // yellow
  ]
  return colors[index % colors.length]
}
</script>

<style scoped>
.chart-container {
  position: relative;
  height: 120vh;
  width: 100%;
}
</style>
