<template>
  <v-container>
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
        <v-col cols="12" md="6">
          <v-card>
            <v-card-title>Price History</v-card-title>
            <v-card-text>
              <LineChart v-if="priceChartData" :chart-data="priceChartData" :options="priceChartOptions" />
              <v-skeleton-loader v-else type="image" height="300"></v-skeleton-loader>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="12" md="6">
          <v-card>
            <v-card-title>Position History</v-card-title>
            <v-card-text>
              <LineChart v-if="positionChartData" :chart-data="positionChartData" :options="positionChartOptions" />
              <v-skeleton-loader v-else type="image" height="300"></v-skeleton-loader>
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
import { getSecurityDetail, getSecurityPriceHistory, getSecurityPositionHistory, getSecurityTransactions } from '@/services/api'
import LineChart from '@/components/charts/LineChart.vue'
import TransactionsTable from '@/components/tables/TransactionsTable.vue'
import { getChartOptions } from '@/config/chartConfig'

export default {
  name: 'SecurityDetailPage',
  components: {
    LineChart,
    TransactionsTable
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const route = useRoute()
    const security = ref(null)
    const priceHistory = ref([])
    const positionHistory = ref([])
    const recentTransactions = ref([])
    const chartOptions = ref(null)
    const chartOptionsLoaded = ref(false)
    const loading = ref(true)

    const fetchSecurityData = async () => {
      try {
        const securityId = route.params.id
        const [securityResponse, priceHistoryResponse, positionHistoryResponse, transactionsResponse] = await Promise.all([
          getSecurityDetail(securityId),
          getSecurityPriceHistory(securityId),
          getSecurityPositionHistory(securityId),
          getSecurityTransactions(securityId)
        ])
        
        security.value = securityResponse
        priceHistory.value = priceHistoryResponse || []
        positionHistory.value = positionHistoryResponse || []
        recentTransactions.value = transactionsResponse || []

        // Update page title
        emit('update-page-title', security.value.name)

        // Get chart options after security data is loaded
        chartOptions.value = await getChartOptions(security.value.currency)
        chartOptionsLoaded.value = true
      } catch (error) {
        console.error('Error fetching security data:', error)
        // Handle error (e.g., show error message to user)
      } finally {
        loading.value = false
      }
    }

    const priceChartData = computed(() => {
      if (!priceHistory.value.length || !chartOptions.value) return null
      return {
        labels: priceHistory.value.map(item => item.date),
        datasets: [{
          label: 'Price',
          data: priceHistory.value.map(item => item.price),
          borderColor: chartOptions.value.colorPalette[0] || '#1976D2',
          tension: 0.1
        }]
      }
    })

    const positionChartData = computed(() => {
      if (!positionHistory.value.length || !chartOptions.value) return null
      return {
        labels: positionHistory.value.map(item => item.date),
        datasets: [{
          label: 'Position',
          data: positionHistory.value.map(item => item.position),
          borderColor: chartOptions.value.colorPalette[1] || '#4CAF50',
          tension: 0.1
        }]
      }
    })

    const priceChartOptions = computed(() => {
      if (!chartOptions.value) return {}
      return {
        ...chartOptions.value.navChartOptions,
        scales: {
          ...chartOptions.value.navChartOptions.scales,
          y: {
            ...chartOptions.value.navChartOptions.scales.y,
            title: {
              ...chartOptions.value.navChartOptions.scales.y.title,
              text: security.value?.currency
            }
          }
        }
      }
    })

    const positionChartOptions = computed(() => {
      if (!chartOptions.value) return {}
      return {
        ...chartOptions.value.navChartOptions,
        scales: {
          ...chartOptions.value.navChartOptions.scales,
          y: {
            ...chartOptions.value.navChartOptions.scales.y,
            title: {
              ...chartOptions.value.navChartOptions.scales.y.title,
              text: 'Quantity'
            }
          }
        }
      }
    })

    onMounted(fetchSecurityData)

    return {
      security,
      priceChartData,
      positionChartData,
      priceChartOptions,
      positionChartOptions,
      recentTransactions,
      chartOptionsLoaded,
      loading
    }
  }
}
</script>