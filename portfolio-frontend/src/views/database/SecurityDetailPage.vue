<template>
  <v-container fluid class="pa-0">
    <template v-if="loading">
      <v-skeleton-loader v-for="i in 3" :key="i" type="card" class="mb-6" />
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
                  <v-list-item-subtitle>{{
                    security.ISIN
                  }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Type:</v-list-item-title>
                  <v-list-item-subtitle>{{
                    security.instrument_type
                  }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Currency:</v-list-item-title>
                  <v-list-item-subtitle>{{
                    security.currency
                  }}</v-list-item-subtitle>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>First Investment:</v-list-item-title>
                  <v-list-item-subtitle>{{
                    security.first_investment
                  }}</v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="12" md="6">
          <v-card>
            <v-card-title>Performance Metrics</v-card-title>
            <v-card-text>
              <!-- Table format for better readability -->
              <v-table density="compact">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Current Position:</td>
                    <td>{{ security.open_position }}</td>
                  </tr>

                  <!-- Buy-in Price -->
                  <tr v-if="security.buy_in_price">
                    <td>Buy-in Price:</td>
                    <td>
                      {{ security.buy_in_price }}
                    </td>
                  </tr>

                  <!-- Current Price -->
                  <tr v-if="security.current_price">
                    <td>Current Price:</td>
                    <td>{{ security.current_price }}</td>
                  </tr>

                  <tr>
                    <td>Current Value:</td>
                    <td>{{ security.current_value }}</td>
                  </tr>

                  <!-- Bond-specific: Total ACI for Position -->
                  <tr
                    v-if="
                      security.instrument_type === 'Bond' &&
                      security.bond_data &&
                      security.bond_data.total_aci !== undefined &&
                      security.bond_data.total_aci !== '–'
                    "
                  >
                    <td>Total Accrued Interest:</td>
                    <td>
                      {{ security.bond_data.total_aci }}
                      <span class="text-caption text-grey">
                        (net of ACI paid at acquisition)</span
                      >
                    </td>
                  </tr>

                  <!-- Bond-specific: YTM -->
                  <tr
                    v-if="
                      security.instrument_type === 'Bond' &&
                      security.bond_data &&
                      security.bond_data.ytm
                    "
                  >
                    <td>YTM at Acquisition:</td>
                    <td>{{ security.bond_data.ytm }}</td>
                  </tr>

                  <tr>
                    <td>Realized Gain/Loss:</td>
                    <td>{{ security.realized }}</td>
                  </tr>
                  <tr>
                    <td>Unrealized Gain/Loss:</td>
                    <td>{{ security.unrealized }}</td>
                  </tr>
                  <tr>
                    <td>Capital Distribution:</td>
                    <td>{{ security.capital_distribution }}</td>
                  </tr>
                  <tr>
                    <td>IRR:</td>
                    <td>{{ security.irr }}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <!-- Bond-specific Information -->
      <v-row v-if="security.instrument_type === 'Bond' && security.bond_data">
        <v-col cols="12">
          <v-card>
            <v-card-title>Bond Information</v-card-title>
            <v-card-text>
              <v-row>
                <!-- Basic Bond Details -->
                <v-col cols="12" md="6">
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th>Detail</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      <!-- Show notional based on amortizing status -->
                      <tr
                        v-if="
                          security.bond_data.current_notional !== null &&
                          security.bond_data.current_notional !== undefined
                        "
                      >
                        <td>
                          {{
                            security.bond_data.is_amortizing
                              ? 'Current Nominal'
                              : 'Notional'
                          }}:
                        </td>
                        <td>
                          {{ security.bond_data.current_notional }}
                        </td>
                      </tr>

                      <!-- Show initial notional only for amortizing bonds -->
                      <tr
                        v-if="
                          security.bond_data.is_amortizing &&
                          security.bond_data.initial_notional !== null &&
                          security.bond_data.initial_notional !== undefined
                        "
                      >
                        <td>Initial Nominal:</td>
                        <td>
                          {{ security.bond_data.initial_notional }}
                        </td>
                      </tr>

                      <tr v-if="security.bond_data.issue_date">
                        <td>Issue Date:</td>
                        <td>{{ security.bond_data.issue_date }}</td>
                      </tr>

                      <tr v-if="security.bond_data.maturity_date">
                        <td>Maturity Date:</td>
                        <td>{{ security.bond_data.maturity_date }}</td>
                      </tr>

                      <!-- Show bond type with amortizing status -->
                      <tr>
                        <td>Bond Type:</td>
                        <td>
                          {{ security.bond_data.coupon_type || 'Standard' }}
                          <span
                            v-if="security.bond_data.is_amortizing"
                            class="text-caption text-grey"
                            >(Amortizing)</span
                          >
                        </td>
                      </tr>

                      <tr v-if="security.bond_data.credit_rating">
                        <td>Credit Rating:</td>
                        <td>{{ security.bond_data.credit_rating }}</td>
                      </tr>
                    </tbody>
                  </v-table>
                </v-col>

                <!-- Coupon Details -->
                <v-col cols="12" md="6">
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th>Detail</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-if="
                          security.bond_data.coupon_amount !== null &&
                          security.bond_data.coupon_amount !== undefined
                        "
                      >
                        <td>Coupon per Bond:</td>
                        <td>
                          {{ security.bond_data.coupon_amount }}
                        </td>
                      </tr>

                      <tr v-if="security.bond_data.coupon_rate">
                        <td>Coupon Rate:</td>
                        <td>{{ security.bond_data.coupon_rate }}</td>
                      </tr>

                      <tr v-if="security.bond_data.coupon_frequency">
                        <td>Coupon Frequency:</td>
                        <td>
                          {{ security.bond_data.coupon_frequency }}x per year
                        </td>
                      </tr>

                      <!-- Show next coupon date from bond_data -->
                      <tr v-if="security.bond_data.next_coupon_date">
                        <td>Next Coupon Payment:</td>
                        <td>{{ security.bond_data.next_coupon_date }}</td>
                      </tr>

                      <!-- Show ACI data from bond_data -->
                      <template v-if="security.bond_data.current_aci">
                        <tr v-if="security.bond_data.current_aci.aci_amount">
                          <td>Current Accrued Interest:</td>
                          <td>
                            {{ security.bond_data.current_aci.aci_amount }}
                          </td>
                        </tr>

                        <tr v-if="security.bond_data.current_aci.aci_days">
                          <td>Days Accrued:</td>
                          <td>
                            {{ security.bond_data.current_aci.aci_days }} /
                            {{ security.bond_data.current_aci.total_days }} days
                          </td>
                        </tr>
                      </template>
                    </tbody>
                  </v-table>
                </v-col>
              </v-row>
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
              <div style="height: 400px">
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
              <div style="height: 400px">
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
                  <transaction-row
                    :transaction="item"
                    :currencies="[]"
                    :show-balances="false"
                    :show-cash-flow="false"
                    :show-single-cash-flow="true"
                    :show-actions="false"
                  />
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
                      style="max-width: 150px"
                      bg-color="white"
                    />
                    <span class="text-caption">
                      Showing
                      {{
                        (transactionOptions.page - 1) *
                          transactionOptions.itemsPerPage +
                        1
                      }}-{{
                        Math.min(
                          transactionOptions.page *
                            transactionOptions.itemsPerPage,
                          totalTransactions
                        )
                      }}
                      of {{ totalTransactions }} entries
                    </span>
                    <v-pagination
                      v-model="transactionOptions.page"
                      :length="pageCount"
                      :total-visible="7"
                      rounded="circle"
                    />
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
import {
  getSecurityDetail,
  getSecurityPriceHistory,
  getSecurityPositionHistory,
  getSecurityTransactions,
} from '@/services/api'
import LineChart from '@/components/charts/LineChart.vue'
import TimelineSelector from '@/components/TimelineSelector.vue'
import { getChartOptions } from '@/config/chartConfig'
import 'chartjs-adapter-date-fns'
import {
  Chart,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'
import {
  subDays,
  subMonths,
  subYears,
  startOfYear,
  differenceInDays,
} from 'date-fns'
import logger from '@/utils/logger'

// Register Chart.js components
Chart.register(
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

// Set the default locale for Chart.js
Chart.defaults.locale = 'en-US'

import TransactionRow from '@/components/transactions/TransactionRow.vue'

export default {
  name: 'SecurityDetailPage',
  components: {
    LineChart,
    TimelineSelector,
    TransactionRow,
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

    const effectiveCurrentDate = computed(
      () => store.state.effectiveCurrentDate
    )

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

    const pageCount = computed(() =>
      Math.ceil(totalTransactions.value / transactionOptions.value.itemsPerPage)
    )

    const getTransactionDescription = (item) => {
      if (
        item.type.includes('Cash') ||
        item.type === 'Dividend' ||
        item.type.includes('Coupon')
      ) {
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
        case '7d':
          return subDays(currentDate, 7)
        case '1m':
          return subMonths(currentDate, 1)
        case '3m':
          return subMonths(currentDate, 3)
        case '6m':
          return subMonths(currentDate, 6)
        case '1Y':
          return subYears(currentDate, 1)
        case '3Y':
          return subYears(currentDate, 3)
        case '5Y':
          return subYears(currentDate, 5)
        case 'ytd':
          return startOfYear(currentDate)
        case 'All':
          return null
        default:
          return subYears(currentDate, 1) // Default to 1Y
      }
    }

    const filteredPriceHistory = computed(() => {
      const startDate = getStartDate(selectedPeriod.value)
      if (!startDate) return priceHistory.value
      return priceHistory.value.filter(
        (item) => new Date(item.date) >= startDate
      )
    })

    const filteredPositionHistory = computed(() => {
      const startDate = getStartDate(selectedPeriod.value)
      if (!startDate) return positionHistory.value
      return positionHistory.value.filter(
        (item) => new Date(item.date) >= startDate
      )
    })

    const fetchSecurityData = async () => {
      try {
        const securityId = route.params.id

        // Debug logging - Log current effective date before API calls
        logger.log(
          'SecurityDetailPage',
          '[DEBUG] fetchSecurityData - Current effectiveCurrentDate from store:',
          store.state.effectiveCurrentDate
        )

        // loading.value = true
        loadingPriceChart.value = true
        loadingPositionChart.value = true

        if (!security.value) {
          const securityResponse = await getSecurityDetail(securityId)
          security.value = securityResponse
          emit('update-page-title', security.value.name)
        }

        // Always fetch the effective current date to ensure it's up-to-date
        logger.log(
          'SecurityDetailPage',
          '[DEBUG] fetchSecurityData - Fetching effective current date from backend...'
        )
        await store.dispatch('fetchEffectiveCurrentDate')
        logger.log(
          'SecurityDetailPage',
          '[DEBUG] fetchSecurityData - Updated effectiveCurrentDate from store:',
          store.state.effectiveCurrentDate
        )

        const [priceHistoryResponse, positionHistoryResponse] =
          await Promise.all([
            getSecurityPriceHistory(securityId, selectedPeriod.value),
            getSecurityPositionHistory(securityId, selectedPeriod.value),
          ])

        priceHistory.value = priceHistoryResponse || []
        positionHistory.value = positionHistoryResponse || []

        if (!chartOptionsLoaded.value) {
          chartOptions.value = await getChartOptions(security.value.currency)
          chartOptionsLoaded.value = true
        }

        loadingPriceChart.value = false
        loadingPositionChart.value = false
      } catch (error) {
        logger.error('Unknown', 'Error fetching security data:', error)
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
        logger.error('Unknown', 'Error fetching transactions:', error)
      } finally {
        loadingTransactions.value = false
      }
    }

    watch(selectedPeriod, () => {
      fetchSecurityData()
      transactionOptions.value.page = 1
      fetchTransactions()
    })

    watch(
      transactionOptions,
      () => {
        fetchTransactions()
      },
      { deep: true }
    )

    onMounted(async () => {
      logger.log('SecurityDetailPage', '[DEBUG] onMounted - Starting...')
      logger.log(
        'SecurityDetailPage',
        '[DEBUG] onMounted - Initial effectiveCurrentDate from store:',
        store.state.effectiveCurrentDate
      )
      loading.value = true
      await fetchSecurityData()
      logger.log(
        'SecurityDetailPage',
        '[DEBUG] onMounted - After fetchSecurityData, effectiveCurrentDate from store:',
        store.state.effectiveCurrentDate
      )
      await fetchTransactions()
      loading.value = false
      logger.log(
        'SecurityDetailPage',
        '[DEBUG] onMounted - Completed, final effectiveCurrentDate from store:',
        store.state.effectiveCurrentDate
      )
    })

    const getLastAvailableDataPoint = (data, targetDate) => {
      const sortedData = [...data].sort(
        (a, b) => new Date(b.date) - new Date(a.date)
      )
      return (
        sortedData.find(
          (item) => new Date(item.date) <= new Date(targetDate)
        ) || sortedData[0]
      )
    }

    const priceChartData = computed(() => {
      let chartData = filteredPriceHistory.value.map((item) => ({
        x: new Date(item.date),
        y: item.price,
      }))

      if (effectiveCurrentDate.value) {
        const lastDataPoint = getLastAvailableDataPoint(
          filteredPriceHistory.value,
          effectiveCurrentDate.value
        )
        if (lastDataPoint) {
          chartData.push({
            x: new Date(effectiveCurrentDate.value),
            y: lastDataPoint.price,
          })
        }
      }

      return {
        labels: chartData.map((item) => item.x),
        datasets: [
          {
            label: 'Price',
            data: chartData,
            borderColor:
              chartOptions.value?.colorPalette[0] || 'rgba(75, 192, 192, 1)',
            tension: 0.1,
          },
        ],
      }
    })

    const positionChartData = computed(() => {
      let chartData = filteredPositionHistory.value.map((item) => ({
        x: new Date(item.date),
        y: item.position,
      }))

      if (effectiveCurrentDate.value) {
        const lastDataPoint = getLastAvailableDataPoint(
          filteredPositionHistory.value,
          effectiveCurrentDate.value
        )
        if (lastDataPoint) {
          chartData.push({
            x: new Date(effectiveCurrentDate.value),
            y: lastDataPoint.position,
          })
        }
      }

      return {
        labels: chartData.map((item) => item.x),
        datasets: [
          {
            label: 'Position',
            data: chartData,
            borderColor:
              chartOptions.value?.colorPalette[1] || 'rgba(153, 102, 255, 1)',
            tension: 0.1,
          },
        ],
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
                year: 'yyyy',
              },
            },
            grid: {
              display: false, // Remove vertical grid lines
            },
            title: {
              display: false,
            },
            max: effectiveCurrentDate.value,
          },
          y: {
            beginAtZero: false,
            grid: {
              display: true, // Keep horizontal grid lines
            },
            title: {
              display: true,
            },
          },
        },
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            callbacks: {
              title: function (context) {
                return new Date(context[0].parsed.x).toLocaleDateString(
                  'en-US',
                  { year: 'numeric', month: 'short', day: 'numeric' }
                )
              },
            },
          },
          datalabels: {
            display: false,
          },
        },
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
            text: `Price (${security.value?.currency})`,
          },
        },
      },
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
            text: 'Position',
          },
        },
      },
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
      getTransactionDescription,
    }
  },
}
</script>
