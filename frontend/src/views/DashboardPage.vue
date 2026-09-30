<template>
  <v-container fluid class="pa-0">
    <v-skeleton-loader
      v-if="isEffectiveDateLoading"
      type="article"
      class="my-4"
    />
    <template v-else>
      <v-row class="equal-height-row">
        <v-col cols="12" md="3">
          <v-skeleton-loader v-if="loading.summary" type="card" class="h-100" />
          <SummaryCard
            v-else-if="!error.summary"
            data-testid="summary-card"
            :summary="summary"
            :currency="userCurrency"
            class="h-100"
          />
          <v-alert v-else type="error" class="h-100" data-testid="summary-error">
            {{ error.summary }}
            <v-btn
              color="error"
              variant="outlined"
              class="ml-2"
              data-testid="summary-retry"
              @click="fetchSummaryData"
            >
              Retry
            </v-btn>
          </v-alert>
        </v-col>
        <v-col cols="12" md="9">
          <v-row class="equal-height-row h-100">
            <v-col
              v-for="(chart, index) in chartTypes"
              :key="index"
              cols="12"
              md="4"
            >
              <v-skeleton-loader
                v-if="loading.breakdownCharts"
                type="card"
                class="h-100"
              />
              <BreakdownChart
                v-else-if="!error.breakdownCharts"
                :data-testid="`allocation-${chart}-card`"
                :title="chartTitles[chart]"
                :data="breakdownData[chart]"
                :currency="userCurrency"
                :totalNAV="totalNAV"
                class="h-100"
              />
              <v-alert v-else type="error" class="h-100" :data-testid="`allocation-${chart}-error`">
                {{ error.breakdownCharts }}
                <v-btn
                  color="error"
                  variant="outlined"
                  class="ml-2"
                  :data-testid="`allocation-${chart}-retry`"
                  @click="fetchBreakdownData"
                >
                  Retry
                </v-btn>
              </v-alert>
            </v-col>
          </v-row>
        </v-col>
      </v-row>

      <v-row>
        <v-col cols="12">
          <v-skeleton-loader v-if="loading.summaryOverTime" type="table" />
          <div v-else-if="!error.summaryOverTime" data-testid="history-table">
          <SummaryOverTimeTable
            :lines="summaryOverTimeData?.lines ?? []"
            :years="summaryOverTimeData?.years ?? []"
            :currentYear="
              String(summaryOverTimeData?.currentYear ?? '')
            "
            @refresh-data="fetchSummaryOverTimeData"
          />
          </div>
          <v-alert v-else type="error" data-testid="history-error">
            {{ error.summaryOverTime }}
            <v-btn
              color="error"
              variant="outlined"
              class="ml-2"
              data-testid="history-retry"
              @click="fetchSummaryOverTimeData"
            >
              Retry
            </v-btn>
          </v-alert>
        </v-col>
      </v-row>

      <v-row>
        <v-col cols="12">
          <v-alert v-if="error.navChart" type="error" class="mb-2" data-testid="nav-error">
            {{ error.navChart }}
            <v-btn
              color="error"
              variant="outlined"
              class="ml-2"
              data-testid="nav-retry"
              @click="fetchNAVChartData()"
            >
              Retry
            </v-btn>
          </v-alert>
          <v-skeleton-loader v-if="loading.navChart" type="card" height="400" />
          <NAVChart
            v-else-if="navChartData"
            data-testid="nav-chart"
            :chartData="navChartData"
            :loading="updating.navChart"
            :initialParams="navChartInitialParams"
            :effectiveCurrentDate="effectiveCurrentDate"
            @update-params="fetchNAVChartData"
          />
        </v-col>
      </v-row>
    </template>
  </v-container>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, watch, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotContext } from '@/types/query'
import type { PortfolioContext } from '@/types/portfolioContext'
import { calculateDateRange } from '@/utils/dateRangeUtils'
import SummaryCard from '@/components/dashboard/SummaryCard.vue'
import BreakdownChart from '@/components/dashboard/BreakdownChart.vue'
import SummaryOverTimeTable from '@/components/dashboard/SummaryOverTimeTable.vue'
import NAVChart from '@/components/dashboard/NAVChart.vue'
import {
  getDashboardSummary,
  getDashboardBreakdown,
  getDashboardSummaryOverTime,
  getNAVChartData,
} from '@/services/api'

defineOptions({ name: 'DashboardPage' })
const emit = defineEmits<{
  (e: 'update-page-title', title: string): void
}>()

interface BreakdownData {
  assetType: Record<string, unknown>
  assetClass: Record<string, unknown>
  currency: Record<string, unknown>
  totalNAV?: string
}
interface ChartData {
  labels: unknown[]
  datasets: unknown[]
  [key: string]: unknown
}
interface SummaryOverTimeData {
  lines?: unknown[]
  years?: unknown[]
  currentYear?: string | number
}
interface NavChartParams {
  frequency: string
  breakdown: string
  dateRange: string
  dateFrom: string | null
  dateTo: string | null
}
interface NavQueryParams {
  readonly context: PortfolioContext
  readonly chart: NavChartParams
}

const appStore = useAppStore()
const context = usePortfolioContextStore()
const summaryQuery = usePortfolioRequest(
  (_params: PortfolioContext, options) => getDashboardSummary(options),
  snapshotContext
)
const breakdownQuery = usePortfolioRequest(
  async (_params: PortfolioContext, options) =>
    await getDashboardBreakdown(options) as unknown as BreakdownData,
  snapshotContext
)
const historyQuery = usePortfolioRequest(
  async (_params: PortfolioContext, options): Promise<SummaryOverTimeData | null> => {
    try {
      return await getDashboardSummaryOverTime(options)
    } catch (error) {
      // Only this endpoint documents 404 as an empty history.
      if ((error as { response?: { status?: number } }).response?.status === 404) return null
      throw error
    }
  },
  snapshotContext
)
const navQuery = usePortfolioRequest(
  async (params: NavQueryParams, options) => await getNAVChartData(
    params.chart.breakdown, params.chart.frequency,
    params.chart.dateFrom, params.chart.dateTo, options
  ) as unknown as ChartData,
  (params: NavQueryParams) => Object.freeze({
    context: snapshotContext(params.context),
    chart: Object.freeze({ ...params.chart }),
  })
)
const summary = computed(() => summaryQuery.data.value ?? {})
const breakdownData = computed(() => breakdownQuery.data.value ?? {
  assetType: {}, assetClass: {}, currency: {},
})
const totalNAV = computed(() => breakdownQuery.data.value?.totalNAV ?? '')
const summaryOverTimeData = historyQuery.data
const navChartData = navQuery.data
const navChartInitialParams = computed(() => appStore.navChartParams)
const effectiveCurrentDate = computed(() => context.committed.effectiveCurrentDate)
const isEffectiveDateLoading = computed(() => !context.canRead)
const userCurrency = computed(() => context.committed.currency)
const loading = computed(() => ({
  summary: summaryQuery.loading.value,
  breakdownCharts: breakdownQuery.loading.value,
  summaryOverTime: historyQuery.loading.value,
  navChart: navQuery.loading.value && !navQuery.data.value,
}))
const updating = computed(() => ({ navChart: navQuery.loading.value && !!navQuery.data.value }))
const error = computed(() => ({
  summary: summaryQuery.error.value?.message,
  breakdownCharts: breakdownQuery.error.value?.message,
  summaryOverTime: historyQuery.error.value?.message,
  navChart: navQuery.error.value?.message,
}))
const chartTypes = ['assetType', 'assetClass', 'currency'] as const
const chartTitles = { assetType: 'Asset Type', assetClass: 'Asset Class', currency: 'Currency' }
const fetchSummaryData = () => summaryQuery.run(context.committed)
const fetchBreakdownData = () => breakdownQuery.run(context.committed)
const fetchSummaryOverTimeData = () => historyQuery.run(context.committed)
const fetchNAVChartData = (params: NavChartParams = navChartInitialParams.value) =>
  navQuery.run({ context: context.committed, chart: params })

// One watcher owns initial/context/explicit refresh reads. Child parameter changes
// already persist their tuple and emit once; observing that tuple too would double-fetch.
watch(
  [() => context.canRead, () => context.dataRefreshTrigger],
  ([ready]) => {
    if (!ready) return
    const params = appStore.navChartParams
    const date = context.committed.effectiveCurrentDate
    if (date) {
      const range = calculateDateRange(params.dateRange, date, params.dateFrom, params.dateTo)
      appStore.updateNavChartParams({ dateFrom: range.from, dateTo: range.to })
    }
    fetchSummaryData()
    fetchBreakdownData()
    fetchSummaryOverTimeData()
    fetchNAVChartData()
  },
  { immediate: true }
)
onMounted(() => emit('update-page-title', 'Dashboard'))
onUnmounted(() => emit('update-page-title', ''))
</script>
<style scoped>
.equal-height-row {
  display: flex;
  flex-wrap: wrap;
}

.equal-height-row > [class*='col-'] {
  display: flex;
  flex-direction: column;
}

.equal-height-row .v-card {
  flex: 1 1 auto;
}

.h-100 {
  height: 100%;
}
</style>
