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
        <NavChartPanel
          :result="navChartResult"
          :loading="navChartQuery.loading.value"
          :updating="updating.navChart"
          :error="error.navChart"
          :initial-params="navChartInitialParams"
          :effective-current-date="effectiveCurrentDate"
          data-testid="nav-chart-panel"
          @update-params="fetchNAVChartData"
          @retry="fetchNAVChartData()"
        />
      </div>

      <WorkspaceSection
        heading-id="allocation-section"
        title="Allocation"
        description="Composition of total NAV; each card keeps its Table view for exact values."
        data-testid="allocation-section"
      >
        <v-alert
          v-if="allocationLegacyOnlyNotice"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          data-testid="allocation-capability-notice"
        >
          {{ allocationLegacyOnlyNotice }}
        </v-alert>
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
              :chart-document="breakdownDocuments?.[chart] ?? null"
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
import NavChartPanel from '@/features/charts/NavChartPanel.vue'
import {
  getDashboardSummary,
  getDashboardSummaryOverTime,
} from '@/services/api'
import { useNavChart, requireReadyChartContext } from '@/features/charts/useNavChart'
import { useBreakdownChart } from '@/features/charts/useBreakdownChart'
import { allocationEchartsRequested } from '@/features/charts/rendererPolicy'
import type { Frequency, NavMode, NavQuery } from '@/features/charts/contracts'

defineOptions({ name: 'DashboardPage' })
const emit = defineEmits<{
  (e: 'update-page-title', title: string): void
}>()

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
const breakdownQuery = useBreakdownChart()
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
// The negotiated breakdown feeds both surfaces from ONE request: the
// incumbent cards render the legacy fields; the gated modern path renders the
// three validated allocation documents.
const breakdownResult = computed(() => breakdownQuery.data.value)
const breakdownData = computed(() => breakdownResult.value?.legacy ?? {
  assetType: { data: {}, percentage: {} },
  assetClass: { data: {}, percentage: {} },
  currency: { data: {}, percentage: {} },
})
const totalNAV = computed(() => {
  const nav = (breakdownData.value as { totalNAV?: string }).totalNAV
  return nav ?? ''
})
const allocationPilotRequested = allocationEchartsRequested()
const allocationPilotActive = computed(
  () => allocationPilotRequested && breakdownResult.value?.capability === 'v2',
)
const breakdownDocuments = computed(() => {
  if (!allocationPilotActive.value || breakdownResult.value?.capability !== 'v2') return null
  return breakdownResult.value.documents
})
const allocationLegacyOnlyNotice = computed(() => {
  if (error.value.breakdownCharts || !breakdownResult.value) return null
  return allocationPilotRequested && breakdownResult.value.capability === 'legacy_only'
    ? 'Allocation data comes from a legacy response without the exact chart contract; values are unverified metadata.'
    : null
})
const summaryOverTimeData = historyQuery.data
const navChartResult = navChartQuery.data
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
// One negotiated breakdown request feeds all three cards (legacy fields and,
// when the gate is on, the three validated allocation documents).
function fetchBreakdownData() {
  const committed = context.committed
  if (!committed.effectiveCurrentDate || !committed.currency) {
    return Promise.resolve({ status: 'discarded' } as const)
  }
  return breakdownQuery.run({ context: requireReadyChartContext(committed) })
}
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
  // absent end date as the effective date. The request end is clamped to the
  // committed valuation date: a persisted custom To later than the effective
  // date must never sample periods after it.
  const requestEnd =
    params.dateTo && params.dateTo < committed.effectiveCurrentDate
      ? params.dateTo
      : committed.effectiveCurrentDate
  const query: NavQuery = {
    context: requireReadyChartContext(committed),
    mode: params.breakdown as NavMode,
    frequency: params.frequency as Frequency,
    fromDate: params.dateFrom,
    toDate: requestEnd,
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
