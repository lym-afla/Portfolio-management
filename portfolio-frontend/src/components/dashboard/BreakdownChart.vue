<template>
  <v-card class="d-flex flex-column">
    <v-card-title>{{ title }}</v-card-title>
    <v-card-text class="pa-0 flex-grow-1 d-flex flex-column">
      <v-tabs v-model="tab" v-if="hasData">
        <v-tab value="chart">Pie Chart</v-tab>
        <v-tab value="table">Table</v-tab>
      </v-tabs>

      <v-window v-model="tab" class="flex-grow-1" v-if="hasData">
        <v-window-item value="chart">
          <div class="chart-container">
            <Pie :data="chartData" :options="pieChartOptions" />
          </div>
        </v-window-item>

        <v-window-item value="table">
          <v-table density="compact">
            <thead>
              <tr>
                <th class="text-left category-column"></th>
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

      <div v-if="!hasData" class="text-center pa-4">
        No data available
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { Pie } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, ArcElement, CategoryScale } from 'chart.js'
import ChartDataLabels from 'chartjs-plugin-datalabels'
import { getChartOptions } from '@/config/chartConfig'

ChartJS.register(Title, Tooltip, Legend, ArcElement, CategoryScale, ChartDataLabels)

export default {
  name: 'BreakdownChart',
  components: { Pie },
  props: {
    title: {
      type: String,
      required: true
    },
    data: {
      type: Object,
      default: () => ({})
    },
    totalNAV: {
      type: String,
    },
    currency: {
      type: String,
      required: true
    }
  },
  setup(props) {
    const tab = ref('chart')
    const pieChartOptions = ref({})
    const colorPalette = ref([])

    const hasData = computed(() => {
      return props.data && props.data.data && Object.keys(props.data.data).length > 0
    })

    const sortedData = computed(() => {
      if (!hasData.value) return []
      console.log('sortedData', props.data)
      console.log('totalNAV', props.totalNAV)
      return Object.entries(props.data.data)
        .map(([label, value]) => ({ 
          label, 
          value,
          percentage: props.data.percentage[label]
        }))
        .filter(item => item.value !== '–' && parseFloat(item.value.replace(/[^0-9.-]+/g,"")) !== 0)
        .sort((a, b) => parseFloat(b.value.replace(/[^0-9.-]+/g,"")) - parseFloat(a.value.replace(/[^0-9.-]+/g,"")))
    })

    const chartData = computed(() => {
      if (!hasData.value) return { labels: [], datasets: [] }
      
      return {
        labels: sortedData.value.map(item => item.label),
        datasets: [{
          data: sortedData.value.map(item => parseFloat(item.value.replace(/[^0-9.-]+/g,""))),
          backgroundColor: colorPalette.value.slice(0, sortedData.value.length)
        }]
      }
    })
    onMounted(async () => {
      const { pieChartOptions: options, colorPalette: palette } = await getChartOptions()
      pieChartOptions.value = options
      colorPalette.value = palette
    })
    return {
      tab,
      chartData,
      pieChartOptions,
      sortedData,
      hasData,
      props // Expose props to the template
    }
  }
}
</script>
<style scoped>
.chart-container {
  position: relative;
  width: 100%;
  max-width: 300px; /* Adjust this value as needed */
  margin: 0 auto;
}

.v-window-item {
  height: 100%;
  width: 100%;
}

.v-table :deep(th) {
  font-weight: bold !important;
}

.v-table :deep(td), .v-table :deep(th) {
  padding: 0 16px !important;
}
</style>
