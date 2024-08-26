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
            @change="updateChart"
          ></v-select>
        </v-col>
        <v-col cols="12" sm="4">
          <v-btn-toggle v-model="selectedFrequency" mandatory @change="updateChart">
            <v-btn value="D">D</v-btn>
            <v-btn value="W">W</v-btn>
            <v-btn value="M">M</v-btn>
          </v-btn-toggle>
        </v-col>
        <v-col cols="12" sm="4">
          <v-menu
            v-model="menu"
            :close-on-content-click="false"
            :nudge-right="40"
            transition="scale-transition"
            offset-y
            min-width="auto"
          >
            <template v-slot:activator="{ on, attrs }">
              <v-text-field
                v-model="dateRangeText"
                label="Date range"
                prepend-icon="mdi-calendar"
                readonly
                v-bind="attrs"
                v-on="on"
              ></v-text-field>
            </template>
            <v-date-picker
              v-model="dateRange"
              range
              @change="updateChart"
            ></v-date-picker>
          </v-menu>
        </v-col>
      </v-row>
      <Line
        v-if="chartData.datasets && chartData.datasets.length > 0"
        :data="chartData"
        :options="chartOptions"
      />
      <v-alert v-else type="info">No data available for the chart.</v-alert>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, LinearScale, PointElement, CategoryScale } from 'chart.js'

ChartJS.register(Title, Tooltip, Legend, LineElement, LinearScale, PointElement, CategoryScale)

export default {
  name: 'NAVChart',
  components: { Line },
  props: {
    initialData: {
      type: Object,
      default: () => ({ labels: [], datasets: [] })
    }
  },
  emits: ['update-chart'],
  setup(props, { emit }) {
    const selectedBreakdown = ref('currency')
    const selectedFrequency = ref('M')
    const dateRange = ref([])
    const menu = ref(false)
    const breakdownOptions = ['currency', 'broker', 'account', 'asset_class', 'region']

    const chartData = ref(props.initialData)
    const chartOptions = {
      responsive: false,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: false
        }
      }
    }

    const dateRangeText = computed(() => {
      return dateRange.value.join(' - ')
    })

    const updateChart = () => {
      emit('update-chart', {
        frequency: selectedFrequency.value,
        from: dateRange.value[0],
        to: dateRange.value[1],
        breakdown: selectedBreakdown.value
      })
    }

    watch([selectedBreakdown, selectedFrequency, dateRange], updateChart)

    onMounted(() => {
      if (props.initialData && props.initialData.labels && props.initialData.datasets) {
        chartData.value = props.initialData
      }
    })

    return {
      selectedBreakdown,
      selectedFrequency,
      dateRange,
      menu,
      breakdownOptions,
      dateRangeText,
      chartData,
      chartOptions,
      updateChart
    }
  }
}
</script>