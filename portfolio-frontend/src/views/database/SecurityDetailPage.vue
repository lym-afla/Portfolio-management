<template>
  <v-container fluid class="pa-0">
    <template v-if="loading">
      <v-skeleton-loader
        v-for="i in 3"
        :key="i"
        type="card"
        class="mb-6"
      ></v-skeleton-loader>
    </template>
    
    <template v-else-if="security">
      <v-row>
        <v-col cols="12" md="6">
          <v-card>
            <v-card-title>Basic Information</v-card-title>
            <v-card-text>
              <v-list>
                <v-list-item>
                  <v-list-item-title>ISIN:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.ISIN }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Type:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.type }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Currency:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.currency }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>First Investment:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.first_investment }}</v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="12" md="6">
          <v-card>
            <v-card-title>Performance Metrics</v-card-title>
            <v-card-text>
              <v-list>
                <v-list-item>
                  <v-list-item-title>Current Position:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.open_position }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Current Value:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.current_value }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Realized Gain/Loss:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.realized }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Unrealized Gain/Loss:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.unrealized }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Capital Distribution:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.capital_distribution }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>IRR:</v-list-item-title>
                  <v-list-item-subtitle>{{ security.irr }}</v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
      
      <v-row v-if="chartOptionsLoaded">
        <v-col cols="12">
          <v-card>
            <v-card-title>Price History</v-card-title>
            <v-card-text>
              <TimelineSelector
                v-model="selectedPeriod"
                :effective-current-date="effectiveCurrentDate"
              />
              <div style="height: 400px;">
                <LineChart
                  :chart-data="priceChartData"
                  :options="priceChartOptions"
                />
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
      
      <v-row v-if="chartOptionsLoaded">
        <v-col cols="12">
          <v-card>
            <v-card-title>Position History</v-card-title>
            <v-card-text>
              <div style="height: 400px;">
                <LineChart
                  :chart-data="positionChartData"
                  :options="positionChartOptions"
                />
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
      
      <v-row>
        <v-col cols="12">
          <v-card>
            <v-card-title>Recent Transactions</v-card-title>
            <v-card-text>
              <TransactionsTable :transactions="recentTransactions" />
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>
    
    <template v-else>
      <v-alert type="error">Security not found or error loading data.</v-alert>
    </template>
  </v-container>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useStore } from 'vuex'
import { getSecurityDetail, getSecurityPriceHistory, getSecurityPositionHistory } from '@/services/api'
import LineChart from '@/components/charts/LineChart.vue'
import TransactionsTable from '@/components/tables/TransactionsTable.vue'
import TimelineSelector from '@/components/TimelineSelector.vue'
import { getChartOptions } from '@/config/chartConfig'
import 'chartjs-adapter-date-fns'
import { Chart } from 'chart.js'
import { subDays, subMonths, subYears, startOfYear, differenceInDays } from 'date-fns'

// Set the default locale for Chart.js
Chart.defaults.locale = 'en-US'

export default {
  name: 'SecurityDetailPage',
  components: {
    LineChart,
    TransactionsTable,
    TimelineSelector
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const route = useRoute()
    const store = useStore()
    const security = ref(null)
    const priceHistory = ref([])
    const positionHistory = ref([])
    const recentTransactions = ref([])
    const chartOptions = ref(null)
    const chartOptionsLoaded = ref(false)
    const loading = ref(true)

    const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)

    const selectedPeriod = ref('1Y')

    const updateChartPeriod = (period) => {
      selectedPeriod.value = period
    }

    const getStartDate = (period) => {
      const currentDate = new Date(effectiveCurrentDate.value)
      switch (period) {
        case '7d': return subDays(currentDate, 7)
        case '1m': return subMonths(currentDate, 1)
        case '3m': return subMonths(currentDate, 3)
        case '6m': return subMonths(currentDate, 6)
        case '1Y': return subYears(currentDate, 1)
        case '3Y': return subYears(currentDate, 3)
        case '5Y': return subYears(currentDate, 5)
        case 'All': return null
        default:
          if (period.startsWith('YTD-')) {
            return startOfYear(currentDate)
          }
          return subYears(currentDate, 1) // Default to 1Y
      }
    }

    const filteredPriceHistory = computed(() => {
      const startDate = getStartDate(selectedPeriod.value)
      if (!startDate) return priceHistory.value
      return priceHistory.value.filter(item => new Date(item.date) >= startDate)
    })

    const filteredPositionHistory = computed(() => {
      const startDate = getStartDate(selectedPeriod.value)
      if (!startDate) return positionHistory.value
      return positionHistory.value.filter(item => new Date(item.date) >= startDate)
    })

    const fetchSecurityData = async () => {
      try {
        const securityId = route.params.id
        const [securityResponse, priceHistoryResponse, positionHistoryResponse] = await Promise.all([
          getSecurityDetail(securityId),
          getSecurityPriceHistory(securityId),
          getSecurityPositionHistory(securityId)
        ])
        
        security.value = securityResponse
        priceHistory.value = priceHistoryResponse || []
        positionHistory.value = positionHistoryResponse || []

        // Update page title
        emit('update-page-title', security.value.name)

        // Get chart options after security data is loaded
        chartOptions.value = await getChartOptions(security.value.currency)
        chartOptionsLoaded.value = true

        // Fetch effective current date if not available
        if (!effectiveCurrentDate.value) {
          await store.dispatch('fetchEffectiveCurrentDate')
        }
      } catch (error) {
        console.error('Error fetching security data:', error)
        // Handle error (e.g., show error message to user)
      } finally {
        loading.value = false
      }
    }

    const getLastAvailableDataPoint = (data, targetDate) => {
      const sortedData = [...data].sort((a, b) => new Date(b.date) - new Date(a.date))
      return sortedData.find(item => new Date(item.date) <= new Date(targetDate)) || sortedData[0]
    }

    const priceChartData = computed(() => {
      let chartData = filteredPriceHistory.value.map(item => ({ x: new Date(item.date), y: item.price }))
      
      if (effectiveCurrentDate.value) {
        const lastDataPoint = getLastAvailableDataPoint(filteredPriceHistory.value, effectiveCurrentDate.value)
        if (lastDataPoint) {
          chartData.push({ x: new Date(effectiveCurrentDate.value), y: lastDataPoint.price })
        }
      }

      return {
        labels: chartData.map(item => item.x),
        datasets: [{
          label: 'Price',
          data: chartData,
          borderColor: chartOptions.value?.colorPalette[0] || 'rgba(75, 192, 192, 1)',
          tension: 0.1
        }]
      }
    })

    const positionChartData = computed(() => {
      let chartData = filteredPositionHistory.value.map(item => ({ x: new Date(item.date), y: item.position }))
      
      if (effectiveCurrentDate.value) {
        const lastDataPoint = getLastAvailableDataPoint(filteredPositionHistory.value, effectiveCurrentDate.value)
        if (lastDataPoint) {
          chartData.push({ x: new Date(effectiveCurrentDate.value), y: lastDataPoint.position })
        }
      }

      return {
        labels: chartData.map(item => item.x),
        datasets: [{
          label: 'Position',
          data: chartData,
          borderColor: chartOptions.value?.colorPalette[1] || 'rgba(153, 102, 255, 1)',
          tension: 0.1
        }]
      }
    })

    const getTimeConfig = (period) => {
      const currentDate = new Date(effectiveCurrentDate.value)
      const startDate = getStartDate(period)
      const daysDiff = differenceInDays(currentDate, startDate)

      if (daysDiff <= 14) {
        return { unit: 'day', stepSize: 1 }
      } else if (daysDiff <= 31) {
        return { unit: 'day', stepSize: 2 }
      } else if (daysDiff <= 90) {
        return { unit: 'week', stepSize: 1 }
      } else if (daysDiff <= 180) {
        return { unit: 'month', stepSize: 1 }
      } else if (daysDiff <= 365) {
        return { unit: 'month', stepSize: 2 }
      } else if (daysDiff <= 365 * 2) {
        return { unit: 'quarter', stepSize: 1 }
      } else {
        return { unit: 'year', stepSize: 1 }
      }
    }

    const commonChartOptions = computed(() => {
      const timeConfig = getTimeConfig(selectedPeriod.value)
      return {
        ...chartOptions.value?.navChartOptions,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            type: 'time',
            time: {
              unit: timeConfig.unit,
              stepSize: timeConfig.stepSize,
              displayFormats: {
                day: 'd MMM',
                week: 'd MMM',
                month: 'MMM yyyy',
                quarter: 'QQQ yyyy',
                year: 'yyyy'
              }
            },
            grid: {
              display: false // Remove vertical grid lines
            },
            title: {
              display: false
            },
            max: effectiveCurrentDate.value
          },
          y: {
            beginAtZero: false,
            grid: {
              display: true // Keep horizontal grid lines
            },
            title: {
              display: true
            }
          }
        },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              title: function(context) {
                return new Date(context[0].parsed.x).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
              }
            }
          },
          datalabels: {
            display: false
          }
        }
      }
    })

    const priceChartOptions = computed(() => ({
      ...commonChartOptions.value,
      scales: {
        ...commonChartOptions.value.scales,
        y: {
          ...commonChartOptions.value.scales.y,
          title: {
            ...commonChartOptions.value.scales.y.title,
            text: `Price (${security.value?.currency})`
          }
        }
      }
    }))

    const positionChartOptions = computed(() => ({
      ...commonChartOptions.value,
      scales: {
        ...commonChartOptions.value.scales,
        y: {
          ...commonChartOptions.value.scales.y,
          beginAtZero: true,
          title: {
            ...commonChartOptions.value.scales.y.title,
            text: 'Position'
          }
        }
      }
    }))

    onMounted(fetchSecurityData)

    return {
      security,
      priceChartData,
      positionChartData,
      priceChartOptions,
      positionChartOptions,
      recentTransactions,
      chartOptionsLoaded,
      loading,
      selectedPeriod,
      updateChartPeriod,
      effectiveCurrentDate
    }
  }
}
</script>