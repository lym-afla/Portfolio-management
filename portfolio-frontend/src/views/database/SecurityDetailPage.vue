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
              <TimelineSelector
                v-model="selectedPeriod"
                :effective-current-date="effectiveCurrentDate"
              />
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
            <v-card-title>Transaction History</v-card-title>
            <TimelineSelector
              v-model="selectedPeriod"
              :effective-current-date="effectiveCurrentDate"
            />
            <v-card-text>
              <v-data-table
                :headers="transactionHeaders"
                :items="transactions"
                :loading="loadingTransactions"
                :items-per-page="transactionOptions.itemsPerPage"
                disable-sort
              >

                <template #item="{ item }">
                  <tr>
                    <td>{{ item.date }}</td>
                    <td class="text-start text-nowrap">
                      {{ item.type }}
                      <template v-if="item.type === 'Dividend'">
                        payout of {{ item.cash_flow }}
                      </template>
                      <template v-else-if="item.type === 'Close'">
                        Close of {{ item.quantity }} securities
                      </template>
                      <template v-else-if="!['Broker commission', 'Tax', 'Interest income'].includes(item.type)">
                        {{ item.quantity }}
                        @ {{ item.price }}
                        <span v-if="item.commission" class="text-caption text-grey"> || Fee: {{ item.commission }}</span>
                      </template>
                    </td>
                    <td class="text-center">{{ item.type }}</td>
                    <td class="text-center">
                      <template v-if="['Dividend', 'Tax'].includes(item.type) || item.type.includes('Interest') || item.type.includes('Cash')">
                        {{ item.cash_flow }}
                      </template>
                      <template v-else>
                        {{ item.value }}
                      </template>
                    </td>
                  </tr>
                </template>

                <template #bottom>
                  <div class="d-flex align-center justify-space-between pa-2">
                    <v-select
                      v-model="transactionOptions.itemsPerPage"
                      :items="itemsPerPageOptions"
                      label="Rows per page"
                      density="compact"
                      variant="outlined"
                      hide-details
                      class="rows-per-page-select mr-4"
                      style="max-width: 150px;"
                      bg-color="white"
                    ></v-select>
                    <span class="text-caption">
                      Showing {{ (transactionOptions.page - 1) * transactionOptions.itemsPerPage + 1 }}-{{
                        Math.min(transactionOptions.page * transactionOptions.itemsPerPage, totalTransactions)
                      }}
                      of {{ totalTransactions }} entries
                    </span>
                    <v-pagination
                      v-model="transactionOptions.page"
                      :length="pageCount"
                      :total-visible="7"
                      rounded="circle"
                    ></v-pagination>
                  </div>
                </template>
              </v-data-table>
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useStore } from 'vuex'
import { getSecurityDetail, getSecurityPriceHistory, getSecurityPositionHistory, getSecurityTransactions } from '@/services/api'
import LineChart from '@/components/charts/LineChart.vue'
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
    TimelineSelector
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const route = useRoute()
    const store = useStore()
    const security = ref(null)
    const priceHistory = ref([])
    const positionHistory = ref([])
    const transactions = ref([])
    const chartOptions = ref(null)
    const chartOptionsLoaded = ref(false)
    const loading = ref(true)
    const loadingPriceChart = ref(true)
    const loadingPositionChart = ref(true)
    const loadingTransactions = ref(true)
    const totalTransactions = ref(0)

    const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)

    const selectedPeriod = ref('1Y')

    const transactionOptions = ref({
      page: 1,
      itemsPerPage: 10,
    })

    const itemsPerPageOptions = [10, 25, 50, 100]

    const transactionHeaders = [
      { title: 'Date', key: 'date', align: 'start' },
      { title: 'Description', key: 'description', align: 'start' },
      { title: 'Type', key: 'type', align: 'center' },
      { title: 'Cash Flow', key: 'cash_flow', align: 'center' },
    ]

    const pageCount = computed(() => Math.ceil(totalTransactions.value / transactionOptions.value.itemsPerPage))

    const getTransactionDescription = (item) => {
      if (item.type.includes('Cash') || item.type === 'Dividend') {
        return item.type
      } else if (item.type === 'Close') {
        return `${item.quantity} of ${item.price}`
      } else {
        return `${item.quantity} @ ${item.price}`
      }
    }

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
        case 'ytd': return startOfYear(currentDate)
        case 'All': return null
        default:
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
        // loading.value = true
        loadingPriceChart.value = true
        loadingPositionChart.value = true

        if (!security.value) {
          const securityResponse = await getSecurityDetail(securityId)
          security.value = securityResponse
          emit('update-page-title', security.value.name)
        }

        const [priceHistoryResponse, positionHistoryResponse] = await Promise.all([
          getSecurityPriceHistory(securityId, selectedPeriod.value),
          getSecurityPositionHistory(securityId, selectedPeriod.value)
        ])
        
        priceHistory.value = priceHistoryResponse || []
        positionHistory.value = positionHistoryResponse || []

        if (!chartOptionsLoaded.value) {
          chartOptions.value = await getChartOptions(security.value.currency)
          chartOptionsLoaded.value = true
        }

        if (!effectiveCurrentDate.value) {
          await store.dispatch('fetchEffectiveCurrentDate')
        }

        loadingPriceChart.value = false
        loadingPositionChart.value = false
      } catch (error) {
        console.error('Error fetching security data:', error)
      // } finally {
      //   loading.value = false
      }
    }

    const fetchTransactions = async () => {
      try {
        loadingTransactions.value = true
        const securityId = route.params.id
        const response = await getSecurityTransactions(
          securityId, 
          {
            page: transactionOptions.value.page,
            itemsPerPage: transactionOptions.value.itemsPerPage,
          },
          selectedPeriod.value
        )
        transactions.value = response.transactions
        totalTransactions.value = response.total_items
      } catch (error) {
        console.error('Error fetching transactions:', error)
      } finally {
        loadingTransactions.value = false
      }
    }

    watch(selectedPeriod, () => {
      fetchSecurityData()
      transactionOptions.value.page = 1
      fetchTransactions()
    })

    watch(transactionOptions, () => {
      fetchTransactions()
    }, { deep: true })

    onMounted(async () => {
      loading.value = true
      await fetchSecurityData()
      await fetchTransactions()
      loading.value = false
    })

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

    return {
      security,
      priceChartData,
      positionChartData,
      priceChartOptions,
      positionChartOptions,
      transactions,
      transactionHeaders,
      transactionOptions,
      totalTransactions,
      itemsPerPageOptions,
      pageCount,
      chartOptionsLoaded,
      loading,
      loadingPriceChart,
      loadingPositionChart,
      loadingTransactions,
      selectedPeriod,
      updateChartPeriod,
      effectiveCurrentDate,
      getTransactionDescription
    }
  }
}
</script>



