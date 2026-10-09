<template>
  <WorkspacePage
    title="Performance"
    description="Account performance by period and portfolio composition by reporting year."
  >
    <v-alert v-if="error" type="error" dismissible>
      {{ error }}
    </v-alert>

    <!-- Account performance breakdown table -->
    <WorkspaceSection
      heading-id="account-performance-section"
      title="Account performance"
      description="Per account and group; YTD, returned calendar years and all-time periods."
    >
      <template #actions>
        <div class="summary-controls">
          <v-select
            v-model="viewMode"
            :items="viewModeItems"
            item-title="text"
            item-value="value"
            label="View"
            density="compact"
            hide-details
            :disabled="!periods.length"
            data-testid="performance-view-select"
            class="summary-controls__view"
          />
          <v-select
            v-if="viewMode === 'single'"
            v-model="singlePeriod"
            :items="years"
            label="Period"
            density="compact"
            hide-details
            :disabled="!periods.length"
            data-testid="performance-period-select"
            class="summary-controls__period"
          />
          <v-select
            v-else-if="viewMode === 'comparison'"
            v-model="comparisonSelection"
            :items="years"
            label="Periods"
            multiple
            density="compact"
            hide-details
            :disabled="!periods.length"
            data-testid="performance-periods-select"
            class="summary-controls__period"
          />
        </div>
      </template>

      <v-skeleton-loader v-if="loading.accountPerformance" type="table" />
      <WorkspaceEmptyState
        v-else-if="!periods.length"
        title="No account performance data"
        description="No periods were returned for the current selection."
      />
      <div v-else class="workspace-table-region" data-testid="account-performance-region">
        <table class="workspace-table account-performance-table">
          <thead>
            <template v-if="viewMode === 'single'">
              <tr>
                <th scope="col" class="text-left no-wrap">Account</th>
                <th
                  v-for="leaf in metricLeaves"
                  :key="leaf.key"
                  scope="col"
                  class="text-right workspace-number"
                  :class="{ 'highlight-column': periodIsHighlight(periods[0]) }"
                >
                  {{ leafQualifiedLabel(leaf, periods[0]) }}
                </th>
              </tr>
            </template>
            <template v-else>
              <tr>
                <th scope="col" rowspan="2" class="text-left no-wrap">Account</th>
                <th
                  v-for="period in periods"
                  :key="period"
                  scope="colgroup"
                  :colspan="metricLeaves.length"
                  class="text-center period-band"
                  :class="{ 'highlight-column': periodIsHighlight(period) }"
                >
                  {{ period }}
                </th>
              </tr>
              <tr>
                <template v-for="period in periods" :key="`leaf-${period}`">
                  <th
                    v-for="leaf in metricLeaves"
                    :key="`${period}-${leaf.key}`"
                    scope="col"
                    class="text-right workspace-number"
                    :class="{ 'highlight-column': periodIsHighlight(period) }"
                  >
                    {{ leaf.label }}
                  </th>
                </template>
              </tr>
            </template>
          </thead>
          <tbody>
            <template
              v-for="(group, groupIndex) in accountPerformanceData"
              :key="group.name"
            >
              <tr class="group-header">
                <td :colspan="1 + periods.length * metricLeaves.length">
                  {{ accountGroupLabel(group.name) }}
                </td>
              </tr>
              <tr
                v-for="(item, itemIndex) in group.lines"
                :key="`${groupIndex}-${itemIndex}`"
                :class="{ 'subtotal-row': item.name === 'Sub-total' }"
              >
                <td class="no-wrap">{{ item.name }}</td>
                <template v-for="period in periods" :key="`data-${period}`">
                  <td
                    v-for="leaf in metricLeaves"
                    :key="`${period}-${leaf.key}`"
                    class="text-right workspace-number"
                    :class="{ 'highlight-column': periodIsHighlight(period) }"
                  >
                    {{ performanceCell(item, period, leaf.key) }}
                  </td>
                </template>
              </tr>
              <tr v-if="group.subtotal" class="subtotal-row">
                <td class="no-wrap">Sub-total</td>
                <template v-for="period in periods" :key="`subtotal-${period}`">
                  <td
                    v-for="leaf in metricLeaves"
                    :key="`${period}-${leaf.key}`"
                    class="text-right workspace-number"
                    :class="{ 'highlight-column': periodIsHighlight(period) }"
                  >
                    {{ performanceCell(group.subtotal, period, leaf.key) }}
                  </td>
                </template>
              </tr>
            </template>
            <tr class="total-row">
              <td class="no-wrap">{{ totalData.name }}</td>
              <template v-for="period in periods" :key="`total-${period}`">
                <td
                  v-for="leaf in metricLeaves"
                  :key="`${period}-${leaf.key}`"
                  class="text-right workspace-number"
                  :class="{ 'highlight-column': periodIsHighlight(period) }"
                >
                  {{ performanceCell(totalData, period, leaf.key) }}
                </td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>
    </WorkspaceSection>

    <!-- Portfolio breakdown table -->
    <WorkspaceSection
      heading-id="portfolio-breakdown-section"
      title="Portfolio breakdown"
      description="Cost, returns and capital per asset for the selected reporting year."
    >
      <template #actions>
        <v-select
          v-model="selectedYear"
          :items="yearOptions"
          item-title="text"
          item-value="value"
          label="Year"
          density="compact"
          hide-details
          class="summary-controls__year"
          data-testid="breakdown-year-select"
          @update:model-value="handleYearChange"
        >
          <template #item="{ props, item }">
            <v-list-item
              v-if="!item.raw.divider"
              v-bind="props"
              :title="item.title"
            />
            <v-divider v-else class="my-2" />
          </template>
        </v-select>
      </template>

      <v-skeleton-loader v-if="loading.portfolioBreakdown" type="table" />
      <div v-else-if="hasBreakdownData" class="workspace-table-region">
        <table class="workspace-table portfolio-breakdown-table">
          <thead>
            <tr>
              <th
                v-for="header in portfolioBreakdownHeaders"
                :key="header.value"
                :rowspan="header.rowspan"
                :colspan="header.colspan"
                :class="[header.class, { 'text-right': header.value !== 'name' }]"
              >
                {{ header.text }}
              </th>
            </tr>
            <tr>
              <template
                v-for="header in portfolioBreakdownHeaders"
                :key="`sub-${header.value}`"
              >
                <template v-if="header.colspan === 2">
                  <th
                    v-for="subHeader in portfolioBreakdownSubHeaders.filter(
                      (sh) => sh.value.startsWith(header.value)
                    )"
                    :key="subHeader.value"
                    :class="[subHeader.class, 'text-right']"
                  >
                    {{ subHeader.text }}
                  </th>
                </template>
              </template>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="(category, categoryIndex) in portfolioBreakdownCategories"
              :key="categoryIndex"
            >
              <tr class="group-header">
                <td
                  :colspan="
                    portfolioBreakdownHeaders.length +
                    portfolioBreakdownSubHeaders.length -
                    5
                  "
                >
                  {{ categoryLabel(category) }}
                </td>
              </tr>
              <tr
                v-for="(item, itemIndex) in portfolioBreakdownData[
                  `${category}_context`
                ]"
                :key="`${categoryIndex}-${itemIndex}`"
                :class="{ 'total-row': item.name === 'TOTAL' }"
              >
                <td>{{ item.name }}</td>
                <td class="text-right workspace-number">{{ item.cost }}</td>
                <td class="text-right workspace-number">{{ item.unrealized }}</td>
                <td class="text-right workspace-number">
                  {{ item.unrealized_percent }}
                </td>
                <td class="text-right workspace-number">{{ item.market_value }}</td>
                <td class="text-right workspace-number">
                  {{ item.portfolio_percent }}
                </td>
                <td class="text-right workspace-number">{{ item.realized }}</td>
                <td class="text-right workspace-number">
                  {{ item.realized_percent }}
                </td>
                <td class="text-right workspace-number">
                  {{ item.capital_distribution }}
                </td>
                <td class="text-right workspace-number">
                  {{ item.capital_distribution_percent }}
                </td>
                <td class="text-right workspace-number">{{ item.commission }}</td>
                <td class="text-right workspace-number">
                  {{ item.commission_percent }}
                </td>
                <td class="text-right workspace-number">{{ item.total }}</td>
                <td class="text-right workspace-number">
                  {{ item.total_percent }}
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <WorkspaceEmptyState
        v-else
        title="No breakdown data"
        description="No portfolio breakdown was returned for the selected year."
      />
    </WorkspaceSection>
  </WorkspacePage>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotContext } from '@/types/query'
import WorkspacePage from '@/components/workspace/WorkspacePage.vue'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import WorkspaceEmptyState from '@/components/workspace/WorkspaceEmptyState.vue'
import {
  accountGroupLabel,
  defaultPeriod,
  leafQualifiedLabel,
  metricLeaves,
  performanceCell,
  periodIsHighlight,
  visiblePeriods,
} from '@/config/summaryPerformanceViews'

import {
  getAccountPerformanceSummary,
  getYearOptions,
  calendarYearOptions,
  getPortfolioBreakdownSummary,
} from '@/services/api'


defineOptions({ name: 'SummaryPage' })

const emit = defineEmits(['update-page-title'])

const appStore = useAppStore()
const context = usePortfolioContextStore()

const performanceQuery = usePortfolioRequest(async (_params, options) => {
  const data = await getAccountPerformanceSummary(options)
  if (!data?.public_markets_context || !data?.restricted_investments_context || !data?.total_context) {
    throw new Error('Invalid account performance response')
  }
  return data
}, snapshotContext)
const breakdownQuery = usePortfolioRequest((params, options) => getPortfolioBreakdownSummary(params.year, options),
  (params) => Object.freeze({ ...params, context: snapshotContext(params.context) }))
const yearsQuery = usePortfolioRequest((_params, options) => getYearOptions(options), snapshotContext)
const loading = computed(() => ({
  accountPerformance: performanceQuery.loading.value, portfolioBreakdown: breakdownQuery.loading.value,
}))
const accountPerformanceData = computed(() => {
  const data = performanceQuery.data.value
  return data ? ['public_markets_context', 'restricted_investments_context'].map((name) => ({
    name, lines: data[name].lines || [], subtotal: data[name].subtotal || null,
  })) : []
})
const emptyBreakdownData = () => ({ consolidated_context: [], unrestricted_context: [], restricted_context: [] })
const portfolioBreakdownData = computed(() => breakdownQuery.data.value ?? emptyBreakdownData())
const years = computed(() => performanceQuery.data.value?.total_context.years ?? [])
const currentYear = new Date().getFullYear()
const selectedYear = ref(currentYear.toString())
// Keep the selection inside the offered ranges: when the default year is not
// offered (e.g. no data for the current year yet), select the newest offered
// year instead of leaving an empty, misleading selection.
watch(yearOptions, (options) => {
  const offered = options.some((option) => String(option.value) === selectedYear.value)
  if (!offered && options.length > 0) selectedYear.value = String(options[options.length - 1].value)
})
const yearOptions = computed(() => calendarYearOptions(yearsQuery.data.value ?? []))

// View state is presentation-only: switching modes or periods never issues
// a request; the queries above stay bound to context/refresh/year changes.
const viewModeItems = [
  { text: 'Single period', value: 'single' },
  { text: 'Comparison', value: 'comparison' },
  { text: 'Full history', value: 'history' },
]
const viewMode = ref('single')
const singlePeriod = ref(null)
const comparisonSelection = ref([])
const periods = computed(() =>
  visiblePeriods(viewMode.value, years.value, singlePeriod.value, comparisonSelection.value)
)
watch(years, (next) => {
  const fallback = defaultPeriod(next)
  if (!fallback) return
  if (!next.includes(singlePeriod.value)) singlePeriod.value = fallback
  comparisonSelection.value = next.filter((year) => comparisonSelection.value.includes(year))
})

const portfolioBreakdownHeaders = ref([
  { text: 'Asset Class', value: 'name', rowspan: 2, class: 'text-left' },
  { text: 'Cost', value: 'cost', rowspan: 2 },
  { text: 'Unrealized', value: 'unrealized', colspan: 2 },
  { text: 'Market value', value: 'market_value', rowspan: 2 },
  { text: '% of portfolio', value: 'portfolio_percent', rowspan: 2 },
  { text: 'Realized', value: 'realized', colspan: 2 },
  { text: 'Capital distribution', value: 'capital_distribution', colspan: 2 },
  { text: 'Commission', value: 'commission', colspan: 2 },
  { text: 'Total', value: 'total', colspan: 2 },
])

const portfolioBreakdownSubHeaders = computed(() => [
  { text: `(${appStore.selectedCurrency})`, value: 'unrealized' },
  { text: '(%)', value: 'unrealized_percent' },
  { text: `(${appStore.selectedCurrency})`, value: 'realized' },
  { text: '(%)', value: 'realized_percent' },
  { text: `(${appStore.selectedCurrency})`, value: 'capital_distribution' },
  { text: '(%)', value: 'capital_distribution_percent' },
  { text: `(${appStore.selectedCurrency})`, value: 'commission' },
  { text: '(%)', value: 'commission_percent' },
  { text: `(${appStore.selectedCurrency})`, value: 'total' },
  { text: '(%)', value: 'total_percent' },
])

const portfolioBreakdownCategories = [
  'consolidated',
  'unrestricted',
  'restricted',
]
const categoryLabel = (category) =>
  category.charAt(0).toUpperCase() + category.slice(1)

const totalData = computed(() => performanceQuery.data.value?.total_context.line ?? {})
const fetchYearOptions = () => yearsQuery.run(context.committed)
const fetchAccountPerformanceData = () => performanceQuery.run(context.committed)
const fetchPortfolioBreakdown = (year) => breakdownQuery.run({ context: context.committed, year })
const handleYearChange = (year) => { selectedYear.value = year }
const error = computed(() => (performanceQuery.error.value || breakdownQuery.error.value || yearsQuery.error.value)
  ? 'Unable to load part of the summary. Change the selection or try again.' : null)
const hasBreakdownData = computed(() => {
  const d = portfolioBreakdownData.value
  return (
    d &&
    d.consolidated_context &&
    d.consolidated_context.length > 0
  )
})

onMounted(() => { emit('update-page-title', 'Summary Analysis') })
watch([() => context.canRead, () => appStore.dataRefreshTrigger], () => {
  if (!context.canRead) return
  fetchYearOptions()
  fetchAccountPerformanceData()
}, { immediate: true })
watch([() => context.canRead, () => appStore.dataRefreshTrigger, selectedYear], () => {
  if (context.canRead) fetchPortfolioBreakdown(selectedYear.value)
}, { immediate: true })
</script>

<style scoped>
.workspace-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.workspace-table :deep(th),
.workspace-table :deep(td) {
  padding: 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

/* Remove highlight from table headings */
.workspace-table :deep(th) {
  font-weight: bold;
  background-color: transparent;
}

.highlight-column {
  background-color: rgba(var(--v-theme-on-surface), 0.03);
}

.no-wrap {
  white-space: nowrap;
}

.summary-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.summary-controls__view {
  min-width: 150px;
  max-width: 180px;
}

.summary-controls__period {
  min-width: 170px;
  max-width: 260px;
}

.summary-controls__year {
  min-width: 120px;
  max-width: 150px;
}

.group-header {
  font-weight: bold;
  background-color: rgba(var(--v-theme-on-surface), 0.06);
}

.subtotal-row {
  background-color: rgba(var(--v-theme-on-surface), 0.03);
}

/* Add top border to TOTAL lines */
.total-row {
  font-weight: bold;
  background-color: rgba(var(--v-theme-on-surface), 0.06);
  border-top: 2px solid rgba(var(--v-theme-on-surface), 0.12);
}

/* Add vertical lines between year groups in the main part of the first table */
.account-performance-table
  :deep(tbody td:nth-child(8n + 1):not(:first-child):not(:last-child)) {
  border-right: 2px solid rgba(var(--v-theme-on-surface), 0.25);
}

/* Add vertical lines for the first header row (years) in the first table */
.account-performance-table :deep(thead tr:first-child th:nth-child(n + 3)) {
  border-left: 2px solid rgba(var(--v-theme-on-surface), 0.25);
}

/* Add vertical lines for the second header row (subheaders) in the first table */
.account-performance-table
  :deep(thead tr:nth-child(2) th:nth-child(8n + 1):not(:first-child)) {
  border-left: 2px solid rgba(var(--v-theme-on-surface), 0.25);
}

/* Zebra striping for rows */
.workspace-table
  :deep(tbody tr:nth-child(even):not(.group-header):not(.total-row):not(.subtotal-row)) {
  background-color: rgba(var(--v-theme-on-surface), 0.02);
}

/* Portfolio breakdown table specific styles */
.portfolio-breakdown-table :deep(tbody td) {
  text-align: right;
}

.portfolio-breakdown-table :deep(thead th:first-child),
.portfolio-breakdown-table :deep(tbody td:first-child) {
  text-align: left;
}

/* Remove vertical lines for the Portfolio breakdown table */
.portfolio-breakdown-table :deep(th),
.portfolio-breakdown-table :deep(td) {
  border-left: none !important;
  border-right: none !important;
}
</style>
