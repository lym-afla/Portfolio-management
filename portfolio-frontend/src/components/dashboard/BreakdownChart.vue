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
          <Pie :data="chartData" :options="chartOptions" />
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
                <td class="text-right">{{ formatCurrency(item.value) }}</td>
                <td class="text-right">{{ formatPercentage(item.value) }}</td>
              </tr>
              <tr class="font-weight-bold">
                <td class="text-left category-column">Total</td>
                <td class="text-right">{{ formatCurrency(totalAmount) }}</td>
                <td class="text-right">100.00%</td>
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
      default: 'USD'
    }
  },
  setup(props) {
    const tab = ref('chart')

    const sortedData = computed(() => {
      return Object.entries(props.data)
        .map(([label, value]) => ({ label, value: parseFloat(value.amount) }))
        .sort((a, b) => b.value - a.value)
    })

    const chartData = computed(() => ({
      labels: sortedData.value.map(item => item.label),
      datasets: [{
        data: sortedData.value.map(item => item.value),
        backgroundColor: [
          '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40',
          '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40'
        ]
      }]
    }))

    const chartOptions = {
      responsive: true,
      maintainAspectRatio: false
    }

    const totalAmount = computed(() => 
      sortedData.value.reduce((sum, item) => sum + item.value, 0)
    )

    const formatCurrency = (value) => {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: props.currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      }).format(value)
    }

    const formatPercentage = (value) => {
      return ((value / totalAmount.value) * 100).toFixed(2) + '%'
    }

    return {
      tab,
      chartData,
      chartOptions,
      totalAmount,
      sortedData,
      formatCurrency,
      formatPercentage
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