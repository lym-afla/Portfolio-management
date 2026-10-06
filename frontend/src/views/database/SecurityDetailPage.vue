<template>
  <WorkspacePage
    :title="security?.name || 'Security'"
    :description="security ? `${security.ISIN || 'No ISIN'} · ${security.instrument_type} · ${security.currency}` : 'Security detail'"
  >
    <v-alert v-if="loadError" type="error" class="mb-4">Unable to load part of this security. Change the selection or try again.</v-alert>
    <!-- Account filter -->
    <v-row class="mb-4">
      <v-col cols="12" sm="6" md="4">
        <v-select
          v-model="selectedAccount"
          :items="accountOptions"
          item-title="title"
          item-value="value"
          label="Broker Account"
          density="comfortable"
          hide-details
          clearable
          outlined
        >
          <template v-slot:item="{ props, item }">
            <v-list-item
              v-if="item.raw.type === 'option'"
              v-bind="props"
              :title="null"
            >
              {{ item.raw.title }}
            </v-list-item>
            <v-divider v-else-if="item.raw.type === 'divider'" class="my-2" />
            <v-list-subheader
              v-else-if="item.raw.type === 'header'"
              class="custom-subheader"
            >
              {{ item.raw.title }}
            </v-list-subheader>
          </template>
        </v-select>
      </v-col>
    </v-row>

    <template v-if="loading">
      <v-skeleton-loader v-for="i in 3" :key="i" type="card" class="mb-6" />
    </template>

    <template v-else-if="security">
      <v-row>
        <v-col cols="12" md="6">
          <WorkspaceSection heading-id="security-basic" title="Basic Information">
            <div>
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
            </div>
          </WorkspaceSection>
        </v-col>
        <v-col cols="12" md="6">
          <WorkspaceSection heading-id="security-performance" title="Performance Metrics">
            <div>
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
            </div>
          </WorkspaceSection>
        </v-col>
      </v-row>

      <v-row v-if="security.instrument_type === 'Crypto'">
        <v-col cols="12">
          <WorkspaceSection heading-id="security-crypto" title="Crypto Rewards">
            <div>
              <v-table density="compact">
                <tbody>
                  <tr>
                    <td>Native rewards</td>
                    <td>{{ security.crypto_reward_native_quantity }}</td>
                  </tr>
                  <tr>
                    <td>Fiat reward value</td>
                    <td>{{ security.crypto_reward_fiat_value }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </WorkspaceSection>
        </v-col>
      </v-row>

      <!-- Bond-specific Information -->
      <v-row v-if="security.instrument_type === 'Bond' && security.bond_data">
        <v-col cols="12">
          <WorkspaceSection heading-id="security-bond" title="Bond Information">
            <div>
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
            </div>
          </WorkspaceSection>
        </v-col>
      </v-row>

      <v-row v-if="chartOptionsLoaded">
        <v-col cols="12">
          <WorkspaceSection heading-id="security-price-history" title="Price History">
            <div>
              <TimelineSelector
                v-model="selectedPeriod"
                :effective-current-date="effectiveCurrentDate"
              />
              <div style="height: 400px">
                <v-skeleton-loader v-if="loadingPriceChart" type="image" />
                <LineChart
                  v-else
                  :chart-data="priceChartData"
                  :options="priceChartOptions"
                />
              </div>
            </div>
          </WorkspaceSection>
        </v-col>
      </v-row>

      <v-row v-if="chartOptionsLoaded">
        <v-col cols="12">
          <WorkspaceSection heading-id="security-position-history" title="Position History">
            <div>
              <TimelineSelector
                v-model="selectedPeriod"
                :effective-current-date="effectiveCurrentDate"
              />
              <div style="height: 400px">
                <v-skeleton-loader v-if="loadingPositionChart" type="image" />
                <LineChart
                  v-else
                  :chart-data="positionChartData"
                  :options="positionChartOptions"
                />
              </div>
            </div>
          </WorkspaceSection>
        </v-col>
      </v-row>

      <v-row>
        <v-col cols="12">
          <WorkspaceSection heading-id="security-transactions" title="Transaction History">
            <TimelineSelector
              v-model="selectedPeriod"
              :effective-current-date="effectiveCurrentDate"
            />
            <div>
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
                    :show-broker-account="true"
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
            </div>
          </WorkspaceSection>
        </v-col>
      </v-row>
    </template>

    <template v-else>
      <v-alert type="error">Security not found or error loading data.</v-alert>
    </template>
  </WorkspacePage>
</template>

<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import { useSecurityDetail } from '@/features/securities/useSecurityDetail'
import LineChart from '@/components/charts/LineChart.vue'
import TimelineSelector from '@/components/TimelineSelector.vue'
import { colorPalette } from '@/config/chartConfig'
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

import TransactionRow from '@/components/transactions/TransactionRow.vue'
import WorkspacePage from '@/components/workspace/WorkspacePage.vue'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'

defineOptions({ name: 'SecurityDetailPage' })

const emit = defineEmits(['update-page-title'])

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

const route = useRoute()
const appStore = useAppStore()
const context = usePortfolioContextStore()

// D7: the five resources, their triggers and their invalidation live in the
// security feature owner; this entrypoint keeps the route/title surface and
// the chart presentation unchanged.
const {
  selectedAccount,
  selectedPeriod,
  transactionOptions,
  itemsPerPageOptions,
  security,
  priceHistory,
  positionHistory,
  transactions,
  chartOptions,
  chartOptionsLoaded,
  accountOptions,
  loading,
  loadingPriceChart,
  loadingPositionChart,
  loadingTransactions,
  totalTransactions,
  pageCount,
  loadError,
} = useSecurityDetail({
  securityId: () => Number(route.params.id),
  canRead: () => context.canRead,
  refreshTrigger: () => appStore.dataRefreshTrigger,
  committed: () => context.committed,
})

watch(security, (value) => { emit('update-page-title', value?.name ?? '') }, { flush: 'sync' })

const effectiveCurrentDate = computed(() => appStore.effectiveCurrentDate)

const transactionHeaders = [
  { title: 'Date', key: 'date', align: 'start' },
  { title: 'Account', key: 'broker_account', align: 'start' },
  { title: 'Description', key: 'description', align: 'start' },
  { title: 'Type', key: 'type', align: 'center' },
  { title: 'Cash Flow', key: 'cash_flow', align: 'center' },
]

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
  const chartData = filteredPriceHistory.value.map((item) => ({
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
        borderColor: colorPalette[0],
        tension: 0.1,
      },
    ],
  }
})

const positionChartData = computed(() => {
  const chartData = filteredPositionHistory.value.map((item) => ({
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
        borderColor: colorPalette[1],
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
            return new Date(context[0].parsed.x).toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
            })
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

</script>

<style scoped>
.custom-subheader {
  font-weight: bold;
  font-size: 1.1em;
  color: #000000;
  padding-top: 12px;
  padding-bottom: 12px;
  background-color: #f5f5f5;
}
</style>
