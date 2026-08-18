<template>
  <v-card class="d-flex flex-column">
    <v-card-title>{{ title }}</v-card-title>
    <v-card-text class="pa-0 flex-grow-1 d-flex flex-column">
      <v-tabs v-model="tab" v-if="hasData">
        <v-tab value="chart">Chart</v-tab>
        <v-tab value="table">Table</v-tab>
      </v-tabs>

      <v-window v-model="tab" class="flex-grow-1" v-if="hasData">
        <v-window-item value="chart">
          <div class="chart-container">
            <Bar :data="chartData" :options="barChartOptions" />
          </div>
        </v-window-item>

        <v-window-item value="table">
          <v-table density="compact">
            <thead>
              <tr>
                <th class="text-left category-column" />
                <th class="text-right font-weight-bold">{{ currency }}</th>
                <th class="text-right font-weight-bold font-italic">%</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in sortedData" :key="index">
                <td class="text-left category-column">{{ item.label }}</td>
                <td class="text-right">{{ item.value }}</td>
                <td class="text-right font-italic">{{ item.percentage }}</td>
              </tr>
              <tr class="font-weight-bold">
                <td class="text-left category-column">Total</td>
                <td class="text-right">{{ props.totalNAV }}</td>
                <td class="text-right font-italic">100%</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>
      </v-window>

      <v-alert v-if="!hasData" type="info" variant="tonal" density="compact"
        text="No data for the selected account and period. Adjust the date range or select another account." />
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
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
import { getChartOptions, colorPalette } from '@/config/chartConfig'

ChartJS.register(
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale,
  ChartDataLabels
)

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  data: {
    type: Object,
    default: () => ({}),
  },
  totalNAV: {
    type: String,
  },
  currency: {
    type: String,
    required: true,
  },
})

const tab = ref('chart')
const barChartOptions = ref({})

const hasData = computed(() => {
  return (
    props.data && props.data.data && Object.keys(props.data.data).length > 0
  )
})

// Sort descending, then reverse so the biggest bar renders at the top
// (Chart.js y-axis places the first label at the top).
const sortedData = computed(() => {
  if (!hasData.value) return []
  return Object.entries(props.data.data)
    .map(([label, value]) => ({
      label,
      value,
      percentage: props.data.percentage[label],
    }))
    .filter(
      (item) =>
        item.value !== '–' &&
        parseFloat(item.value.replace(/[^0-9.-]+/g, '')) !== 0
    )
    .sort(
      (a, b) =>
        parseFloat(b.value.replace(/[^0-9.-]+/g, '')) -
        parseFloat(a.value.replace(/[^0-9.-]+/g, ''))
    )
    .reverse()
})

const chartData = computed(() => {
  if (!hasData.value) return { labels: [], datasets: [] }

  return {
    labels: sortedData.value.map((item) => item.label),
    datasets: [
      {
        data: sortedData.value.map((item) =>
          parseFloat(item.value.replace(/[^0-9.-]+/g, ''))
        ),
        backgroundColor: colorPalette.slice(0, sortedData.value.length),
      },
    ],
  }
})

onMounted(async () => {
  const { barChartOptions: options } = await getChartOptions()
  barChartOptions.value = options
})
</script>
<style scoped>
.chart-container {
  position: relative;
  width: 100%;
}

.v-window-item {
  height: 100%;
  width: 100%;
}

.v-table :deep(th) {
  font-weight: bold;
}

.v-table :deep(td),
.v-table :deep(th) {
  padding: 0 16px !important;
}
</style>
