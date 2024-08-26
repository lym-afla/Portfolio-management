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
            @update:model-value="updateChart"
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
            transition="scale-transition"
            offset-y
            min-width="auto"
          >
            <template v-slot:activator="{ props }">
              <v-text-field
                v-model="dateRangeText"
                label="Date range"
                prepend-icon="mdi-calendar"
                readonly
                v-bind="props"
              ></v-text-field>
            </template>
            <v-date-picker
              v-model="dateRange"
              range
              @update:model-value="updateChart"
            ></v-date-picker>
          </v-menu>
        </v-col>
      </v-row>
      <v-progress-circular
        v-if="loading"
        indeterminate
        color="primary"
      ></v-progress-circular>
      <Line
        v-else-if="chartData.datasets && chartData.datasets.length > 0"
        :data="chartData"
        :options="chartOptions"
      />
      <v-alert v-else type="info">No data available for the chart.</v-alert>
    </v-card-text>
  </v-card>
</template>

<script>
import { ref, onMounted, watch } from 'vue'
import { Line } from 'vue-chartjs'
import { useNAVChartData } from '@/composables/useNAVChartData'
import { chartOptions } from '@/config/chartConfig'
import { getNAVChartData } from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'

export default {
  name: 'NAVChart',
  components: { Line },
  emits: ['update-chart'],
  setup(props, { emit }) {
    const { chartData, updateChartData } = useNAVChartData()
    const { handleApiError } = useErrorHandler()

    const selectedBreakdown = ref('currency')
    const selectedFrequency = ref('M')
    const dateRange = ref([])
    const loading = ref(false)
    const breakdownOptions = ['currency', 'broker', 'account', 'asset_class', 'region']

    const fetchChartData = async () => {
      loading.value = true
      try {
        const params = {
          frequency: selectedFrequency.value,
          from: dateRange.value[0],
          to: dateRange.value[1],
          breakdown: selectedBreakdown.value
        }
        const data = await getNAVChartData(params)
        updateChartData(data)
        emit('update-chart', data)
      } catch (error) {
        handleApiError(error)
      } finally {
        loading.value = false
      }
    }

    onMounted(fetchChartData)

    watch([selectedBreakdown, selectedFrequency, dateRange], fetchChartData)

    return {
      chartData,
      selectedBreakdown,
      selectedFrequency,
      dateRange,
      loading,
      breakdownOptions,
      chartOptions
    }
  }
}
</script>