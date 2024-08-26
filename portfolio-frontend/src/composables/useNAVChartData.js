import { ref, computed } from 'vue'

export function useNAVChartData() {
  const chartData = ref({ labels: [], datasets: [] })

  const updateChartData = (newData) => {
    chartData.value = newData
  }

  const sortedData = computed(() => {
    if (!chartData.value.datasets || chartData.value.datasets.length === 0) {
      return []
    }
    const data = chartData.value.datasets[0].data
    const labels = chartData.value.labels
    return labels.map((label, index) => ({
      label,
      value: data[index]
    })).sort((a, b) => b.value - a.value)
  })

  const totalAmount = computed(() => 
    sortedData.value.reduce((sum, item) => sum + item.value, 0)
  )

  return {
    chartData,
    updateChartData,
    sortedData,
    totalAmount
  }
}