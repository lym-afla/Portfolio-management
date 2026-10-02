<template>
  <WorkspacePage title="Dashboard">
    <v-skeleton-loader
      v-if="isEffectiveDateLoading"
      type="article"
      class="my-4"
    />
    <template v-else>
      <PortfolioMetrics
        v-if="!loading.summary && !error.summary"
        data-testid="summary-card"
        :metrics="metrics"
        :context-label="contextLabel"
      />
      <v-skeleton-loader v-else-if="loading.summary" type="card" />
      <v-alert v-else type="error" data-testid="summary-error">
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

      <div class="dashboard-trajectory">
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
        <v-alert
          v-else-if="navChartLegacyOnly"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-2"
          data-testid="nav-capability-notice"
        >
          Chart data comes from a legacy response without the exact chart contract; values are
          unverified metadata.
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
      </div>

      <WorkspaceSection
        heading-id="allocation-section"
        title="Allocation"
        description="Composition of total NAV; each card keeps its Table view for exact values."
        data-testid="allocation-section"
      >
        <v-row class="equal-height-row">
          <v-col
            v-for="chart in chartTypes"
            :key="chart"
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
      </WorkspaceSection>

      <WorkspaceSection
        heading-id="history-section"
        title="Historical reconciliation"
        description="Year-end performance history with year-to-date and all-time columns."
        data-testid="history-section"
      >
        <template #actions>
          <v-btn
            v-if="historyReady"
            data-testid="update-performance"
            variant="tonal"
            color="primary"
            size="small"
            @click="historyTable?.openUpdateDialog()"
          >
            Update Account Performance
          </v-btn>
        </template>
        <v-skeleton-loader v-if="loading.summaryOverTime" type="table" />
        <div v-else-if="!error.summaryOverTime" data-testid="history-table">
          <SummaryOverTimeTable
            ref="historyTable"
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
      </WorkspaceSection>
    </template>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, watch, computed, ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotContext } from '@/types/query'
import type { PortfolioContext } from '@/types/portfolioContext'
import { calculateDateRange } from '@/utils/dateRangeUtils'
import { committedAccountLabel } from '@/utils/accountUtils'
import WorkspacePage from '@/components/workspace/WorkspacePage.vue'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import PortfolioMetrics from '@/components/dashboard/PortfolioMetrics.vue'
import { summaryMetrics } from '@/components/dashboard/summaryMetrics'
import BreakdownChart from '@/components/dashboard/BreakdownChart.vue'
import SummaryOverTimeTable from '@/components/dashboard/SummaryOverTimeTable.vue'
import NAVChart from '@/components/dashboard/NAVChart.vue'
import {
  getDashboardSummary,
  getDashboardBreakdown,
  getDashboardSummaryOverTime,
} from '@/services/api'
import { useNavChart, requireReadyChartContext } from '@/features/charts/useNavChart'
import type { Frequency, NavMode, NavQuery } from '@/features/charts/contracts'

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

const CHART_MODES: readonly NavMode[] = [
  'none', 'account', 'asset_type', 'asset_class', 'currency',
  'value_contributions', 'value_contributions_cumulative',
]
const CHART_FREQUENCIES: readonly Frequency[] = ['D', 'W', 'M', 'Q', 'Y']

const appStore = useAppStore()
const context = usePortfolioContextStore()
const historyTable = ref<{ openUpdateDialog: () => void } | null>(null)
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
const navChartQuery = useNavChart()
const metrics = computed(() =>
  summaryQuery.data.value ? summaryMetrics(summaryQuery.data.value) : []
)
const breakdownData = computed(() => breakdownQuery.data.value ?? {
  assetType: {}, assetClass: {}, currency: {},
})
const totalNAV = computed(() => breakdownQuery.data.value?.totalNAV ?? '')
const summaryOverTimeData = historyQuery.data
const navChartResult = navChartQuery.data
// The renderer owns a fresh copy; the retained validated NavResult must
// survive renderer-side dataset mutation untouched.
const navChartData = computed(() =>
  navChartResult.value ? structuredClone(navChartResult.value.legacy) : null
)
const navChartLegacyOnly = computed(() => navChartResult.value?.capability === 'legacy_only')
const navChartInitialParams = computed(() => appStore.navChartParams)
const effectiveCurrentDate = computed(() => context.committed.effectiveCurrentDate)
const isEffectiveDateLoading = computed(() => !context.canRead)
const userCurrency = computed(() => context.committed.currency)
// Account label follows the accepted committed presentation shared with the shell.
const accountLabel = computed(() =>
  committedAccountLabel(context.accountOptions, context.committed.accountSelection)
)
const contextLabel = computed(() =>
  [
    accountLabel.value,
    context.committed.effectiveCurrentDate ?? 'Unavailable',
    context.committed.currency ?? 'Unavailable',
  ].join(' · ')
)
const loading = computed(() => ({
  summary: summaryQuery.loading.value,
  breakdownCharts: breakdownQuery.loading.value,
  summaryOverTime: historyQuery.loading.value,
  navChart: navChartQuery.loading.value && !navChartQuery.data.value,
}))
const updating = computed(() => ({ navChart: navChartQuery.loading.value && !!navChartQuery.data.value }))
const error = computed(() => ({
  summary: summaryQuery.error.value?.message,
  breakdownCharts: breakdownQuery.error.value?.message,
  summaryOverTime: historyQuery.error.value?.message,
  navChart: navChartQuery.error.value?.message,
}))
const historyReady = computed(() =>
  !loading.value.summaryOverTime && !error.value.summaryOverTime
)
const chartTypes = ['assetType', 'assetClass', 'currency'] as const
const chartTitles = { assetType: 'Asset Type', assetClass: 'Asset Class', currency: 'Currency' }
const fetchSummaryData = () => summaryQuery.run(context.committed)
const fetchBreakdownData = () => breakdownQuery.run(context.committed)
const fetchSummaryOverTimeData = () => historyQuery.run(context.committed)
type NavRunResult = Awaited<ReturnType<typeof navChartQuery.run>>
function fetchNAVChartData(params: NavChartParams = navChartInitialParams.value): Promise<NavRunResult> {
  const committed = context.committed
  if (!committed.effectiveCurrentDate || !committed.currency) {
    return Promise.resolve({ status: 'discarded' } as NavRunResult)
  }
  if (!CHART_MODES.includes(params.breakdown as NavMode) ||
      !CHART_FREQUENCIES.includes(params.frequency as Frequency)) {
    return Promise.resolve({ status: 'discarded' } as NavRunResult)
  }
  // The guards above make this refinement total; the backend treats an
  // absent end date as the effective date.
  const query: NavQuery = {
    context: requireReadyChartContext(committed),
    mode: params.breakdown as NavMode,
    frequency: params.frequency as Frequency,
    fromDate: params.dateFrom,
    toDate: params.dateTo ?? committed.effectiveCurrentDate,
  }
  return navChartQuery.run(query)
}

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
.dashboard-trajectory {
  min-width: 0;
}

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
