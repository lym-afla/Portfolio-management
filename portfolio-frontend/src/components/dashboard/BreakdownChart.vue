<template>
  <v-card>
    <v-card-title>{{ title }}</v-card-title>
    <v-card-text class="pa-0">
      <v-tabs v-model="tab">
        <v-tab value="chart">Pie Chart</v-tab>
        <v-tab value="table">Table</v-tab>
      </v-tabs>

      <v-window v-model="tab">
        <v-window-item value="chart">
          <Pie :data="chartData" :options="pieChartOptions" />
        </v-window-item>

        <v-window-item value="table">
          <v-table density="compact">
            <thead>
              <tr>
                <th class="text-left category-column"></th>
                <th class="text-right font-weight-bold">{{ currency }}</th>
                <th class="text-right font-weight-bold">%</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in sortedData" :key="index">
                <td class="text-left category-column">{{ item.label }}</td>
                <td class="text-right">{{ item.value }}</td>
                <td class="text-right">{{ item.percentage }}</td>
              </tr>
              <tr class="font-weight-bold">
                <td class="text-left category-column">Total</td>
                <td class="text-right">{{ props.data.totalNAV }}</td>
                <td class="text-right">100%</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>
      </v-window>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref, computed } from 'vue'
import { Pie } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, ArcElement, CategoryScale } from 'chart.js'
import { pieChartOptions, colorPalette } from '@/config/chartConfig'

ChartJS.register(Title, Tooltip, Legend, ArcElement, CategoryScale)

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
      required: true
    },
    currency: {
      type: String,
      required: true
    }
  },
  setup(props) {
    const tab = ref('chart')

    console.log("BreakdownChart.vue. props.data", props.data)

    const sortedData = computed(() => {
      return Object.entries(props.data.data)
        .map(([label, value]) => ({ 
          label, 
          value,
          percentage: props.data.percentage[label]
        }))
        .sort((a, b) => parseFloat(b.value.replace(/[^0-9.-]+/g,"")) - parseFloat(a.value.replace(/[^0-9.-]+/g,"")))
    })

    const chartData = computed(() => ({
      labels: sortedData.value.map(item => item.label),
      datasets: [{
        data: sortedData.value.map(item => parseFloat(item.value.replace(/[^0-9.-]+/g,""))),
        backgroundColor: colorPalette
      }]
    }))

    return {
      tab,
      chartData,
      pieChartOptions,
      sortedData,
      props // Expose props to the template
    }
  }
}
</script>

<style scoped>
.category-column {
  width: 50%;
}

.v-table :deep(th) {
  font-weight: bold !important;
}

.v-table :deep(td), .v-table :deep(th) {
  padding: 0 16px !important;
}
</style>