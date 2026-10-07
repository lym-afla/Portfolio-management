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
      <SecurityOverview :view="overviewView">
        <template #price-chart>
          <v-row v-if="chartOptionsLoaded">
            <v-col cols="12">
              <WorkspaceSection heading-id="security-price-history" title="Price History">
                <div>
                  <TimelineSelector
                    v-model="selectedPeriod"
                    :effective-current-date="effectiveCurrentDate"
                  />
                  <!-- The incumbent loading treatment applies to BOTH
                       renderers: while a period change is pending the
                       skeleton replaces the chart and table, so the previous
                       period's data can never look current. -->
                  <div v-if="loadingPriceChart" style="height: 400px">
                    <v-skeleton-loader type="image" />
                  </div>
                  <!-- C4: the gated modern composition (view-only zoom plus
                       the exact observed-point table); zoom state lives in
                       the page and is reconciled across compatible
                       refreshes. The fallback slot keeps the incumbent
                       Chart.js chart one click away. -->
                  <SecurityHistoryChart
                    v-else-if="priceDocument"
                    :document="priceDocument"
                    :interaction="priceInteraction"
                    :requested="true"
                    @update:interaction="priceInteraction = $event"
                  >
                    <template #fallback>
                      <div style="height: 400px">
                        <LineChart
                          :chart-data="priceChartData"
                          :options="priceChartOptions"
                        />
                      </div>
                    </template>
                  </SecurityHistoryChart>
                  <div v-else style="height: 400px">
                    <LineChart
                      :chart-data="priceChartData"
                      :options="priceChartOptions"
                    />
                  </div>
                </div>
              </WorkspaceSection>
            </v-col>
          </v-row>
        </template>
        <template #position-chart>
          <v-row v-if="chartOptionsLoaded">
            <v-col cols="12">
              <WorkspaceSection heading-id="security-position-history" title="Position History">
                <div>
                  <TimelineSelector
                    v-model="selectedPeriod"
                    :effective-current-date="effectiveCurrentDate"
                  />
                  <div v-if="loadingPositionChart" style="height: 400px">
                    <v-skeleton-loader type="image" />
                  </div>
                  <SecurityHistoryChart
                    v-else-if="positionDocument"
                    :document="positionDocument"
                    :interaction="positionInteraction"
                    :requested="true"
                    @update:interaction="positionInteraction = $event"
                  >
                    <template #fallback>
                      <div style="height: 400px">
                        <LineChart
                          :chart-data="positionChartData"
                          :options="positionChartOptions"
                        />
                      </div>
                    </template>
                  </SecurityHistoryChart>
                  <div v-else style="height: 400px">
                    <LineChart
                      :chart-data="positionChartData"
                      :options="positionChartOptions"
                    />
                  </div>
                </div>
              </WorkspaceSection>
            </v-col>
          </v-row>
        </template>
      </SecurityOverview>

      <SecurityMetadata :bond="bondView" :crypto="cryptoView" />

      <SecurityActivity
        :view="activityView"
        :items-per-page-options="itemsPerPageOptions"
        :loading="loadingTransactions"
        @update:page="transactionOptions.page = $event"
        @update:items-per-page="transactionOptions.itemsPerPage = $event"
      >
        <template #timeline>
          <TimelineSelector
            v-model="selectedPeriod"
            :effective-current-date="effectiveCurrentDate"
          />
        </template>
      </SecurityActivity>
    </template>

    <template v-else>
      <v-alert type="error">Security not found or error loading data.</v-alert>
    </template>
  </WorkspacePage>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import { useSecurityDetail } from '@/features/securities/useSecurityDetail'
import SecurityHistoryChart from '@/features/charts/SecurityHistoryChart.vue'
import { securityEchartsRequested } from '@/features/charts/rendererPolicy'
import { defaultSecurityInteraction, reconcileSecurityInteraction } from '@/features/charts/securityInteraction'
import SecurityOverview from '@/features/securities/SecurityOverview.vue'
import SecurityMetadata from '@/features/securities/SecurityMetadata.vue'
import SecurityActivity from '@/features/securities/SecurityActivity.vue'
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
  priceChartResult,
  positionChartResult,
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

// C4: the gated modern history renderers — active only while the security
// gate is on and the negotiated result is a validated v2 document; legacy_only
// payloads keep the incumbent Chart.js charts unchanged.
const securityPilotRequested = securityEchartsRequested()
const priceDocument = computed(() => {
  if (!securityPilotRequested || priceChartResult.value?.capability !== 'v2') return null
  return priceChartResult.value.document
})
const positionDocument = computed(() => {
  if (!securityPilotRequested || positionChartResult.value?.capability !== 'v2') return null
  return positionChartResult.value.document
})

// C4: zoom state is owned here (one interaction per section) so it survives
// renderer re-renders and is RECONCILED across compatible refreshes — keys
// that survive in the new plotted axis keep the window, anything else resets.
const priceInteraction = ref(defaultSecurityInteraction())
const positionInteraction = ref(defaultSecurityInteraction())
watch(priceDocument, (next, previous) => {
  priceInteraction.value = reconcileSecurityInteraction(previous ?? next, next, priceInteraction.value)
}, { immediate: true })
watch(positionDocument, (next, previous) => {
  positionInteraction.value = reconcileSecurityInteraction(previous ?? next, next, positionInteraction.value)
}, { immediate: true })

// ---- Display views: pure mappings from the accepted server response to the
// section models. Every value stays the server display string; conditions
// replicate the incumbent rows exactly.

const asText = (value) => (value === undefined || value === null ? '' : String(value))

const overviewView = computed(() => {
  const record = security.value
  if (!record) return null
  const isBond = record.instrument_type === 'Bond'
  const bond = record.bond_data ?? null
  const fields = [{ label: 'Current Position:', value: asText(record.open_position) }]
  if (record.buy_in_price) {
    fields.push({ label: 'Buy-in Price:', value: asText(record.buy_in_price) })
  }
  if (record.current_price) {
    fields.push({ label: 'Current Price:', value: asText(record.current_price) })
  }
  fields.push({ label: 'Current Value:', value: asText(record.current_value) })
  if (
    isBond &&
    bond &&
    bond.total_aci !== undefined &&
    bond.total_aci !== '–'
  ) {
    fields.push({
      label: 'Total Accrued Interest:',
      value: asText(bond.total_aci),
      explanation: '(net of ACI paid at acquisition)',
    })
  }
  if (isBond && bond && bond.ytm) {
    fields.push({ label: 'YTM at Acquisition:', value: asText(bond.ytm) })
  }
  fields.push(
    { label: 'Realized Gain/Loss:', value: asText(record.realized) },
    { label: 'Unrealized Gain/Loss:', value: asText(record.unrealized) },
    { label: 'Capital Distribution:', value: asText(record.capital_distribution) },
    { label: 'IRR:', value: asText(record.irr) },
  )
  return {
    securityId: record.id,
    name: asText(record.name),
    identifier: asText(record.ISIN),
    instrumentType: asText(record.instrument_type),
    currency: asText(record.currency),
    firstInvestment: asText(record.first_investment),
    fields,
  }
})

const bondView = computed(() => {
  const bond = security.value?.bond_data
  if (security.value?.instrument_type !== 'Bond' || !bond) return null
  const primary = []
  if (bond.current_notional !== null && bond.current_notional !== undefined) {
    primary.push({
      label: bond.is_amortizing ? 'Current Nominal:' : 'Notional:',
      value: asText(bond.current_notional),
    })
  }
  if (bond.is_amortizing && bond.initial_notional !== null && bond.initial_notional !== undefined) {
    primary.push({ label: 'Initial Nominal:', value: asText(bond.initial_notional) })
  }
  if (bond.issue_date) primary.push({ label: 'Issue Date:', value: asText(bond.issue_date) })
  if (bond.maturity_date) primary.push({ label: 'Maturity Date:', value: asText(bond.maturity_date) })
  primary.push({
    label: 'Bond Type:',
    value: bond.coupon_type || 'Standard',
    explanation: bond.is_amortizing ? 'Amortizing' : undefined,
  })
  if (bond.credit_rating) {
    primary.push({ label: 'Credit Rating:', value: asText(bond.credit_rating) })
  }
  const coupon = []
  if (bond.coupon_amount !== null && bond.coupon_amount !== undefined) {
    coupon.push({ label: 'Coupon per Bond:', value: asText(bond.coupon_amount) })
  }
  if (bond.coupon_rate) coupon.push({ label: 'Coupon Rate:', value: asText(bond.coupon_rate) })
  if (bond.coupon_frequency) {
    coupon.push({ label: 'Coupon Frequency:', value: `${bond.coupon_frequency}x per year` })
  }
  if (bond.next_coupon_date) {
    coupon.push({ label: 'Next Coupon Payment:', value: asText(bond.next_coupon_date) })
  }
  if (bond.current_aci) {
    if (bond.current_aci.aci_amount) {
      coupon.push({ label: 'Current Accrued Interest:', value: asText(bond.current_aci.aci_amount) })
    }
    if (bond.current_aci.aci_days) {
      coupon.push({
        label: 'Days Accrued:',
        value: `${bond.current_aci.aci_days} / ${bond.current_aci.total_days} days`,
      })
    }
  }
  return { primary, coupon }
})

const cryptoView = computed(() => {
  const record = security.value
  if (record?.instrument_type !== 'Crypto') return null
  return {
    nativeQuantity: asText(record.crypto_reward_native_quantity),
    fiatValue: asText(record.crypto_reward_fiat_value),
  }
})

const activityView = computed(() => ({
  transactions: transactions.value,
  totalItems: totalTransactions.value,
  page: transactionOptions.value.page,
  itemsPerPage: transactionOptions.value.itemsPerPage,
  pageCount: pageCount.value,
}))

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
