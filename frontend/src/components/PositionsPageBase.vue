<template>
  <v-container fluid class="pa-0">
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64" />
    </v-overlay>

    <v-alert v-if="positionsQuery.error.value || yearsQuery.error.value" type="error" class="mb-4">
      Unable to load positions or year options. The displayed data may be from the previous request.
      <v-btn data-testid="positions-retry" :disabled="!context.canRead" @click="retryFailedResources">Retry</v-btn>
    </v-alert>
    <slot name="above-table" :loading="tableLoading" />

    <v-row no-gutters>
      <v-col cols="12">
        <v-skeleton-loader v-if="initialLoading" type="table" />
        <v-data-table
          v-else
          :headers="visibleHeaders"
          :items="positions"
          :loading="tableLoading"
          :search="search"
          :items-per-page="itemsPerPage"
          class="elevation-1 nowrap-table"
          density="compact"
          :sort-by="sortBy"
          @update:sort-by="handleSortChange"
          :server-items-length="totalItems"
          :items-length="totalItems"
        >
          <template v-for="(_, name) in $slots" #[name]="slotData">
            <slot :name="name" v-bind="slotData" />
          </template>

          <!-- Glossary tooltips: Vuetify 3.12 only offers per-column
               `header.<key>` slots (no generic #header). Slot payload:
               { column, selectAll, isSorted, toggleSort, sortBy, getSortIcon, ... }
               Custom header props (e.g. `description`) are spread directly onto
               `column` by useHeaders, so column.description is available.
               We re-render Vuetify's own content div + sort icon so clicking
               the <th> (whose onClick Vuetify keeps) still sorts. -->
          <template
            v-for="h in describedHeaderSlots"
            :key="h.key"
            #[h.slotName]="{ column, getSortIcon }"
          >
            <div class="v-data-table-header__content">
              <v-tooltip :text="column.description" location="top">
                <template #activator="{ props: tooltipProps }">
                  <span v-bind="tooltipProps">{{ column.title }}</span>
                </template>
              </v-tooltip>
              <v-icon
                v-if="column.sortable"
                class="v-data-table-header__sort-icon"
                :icon="getSortIcon(column)"
              />
            </div>
          </template>

          <!-- Distinct empty states: truly empty vs filtered out. -->
          <template #no-data>
            <div v-if="totalItems === 0 && !search" class="text-center pa-4">
              No positions yet —
              <router-link :to="{ name: 'Transactions' }">
                import transactions
              </router-link>
              to get started.
            </div>
            <div v-else class="text-center pa-4">
              No positions match your search.
            </div>
          </template>

          <template #top>
            <v-toolbar flat class="bg-grey-lighten-4 border-b">
              <v-col cols="12" sm="3" md="2" lg="2">
                <v-select
                  v-model="timespan"
                  :items="yearOptions"
                  item-title="text"
                  item-value="value"
                  label="Year"
                  density="compact"
                  hide-details
                  class="mr-2"
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
              </v-col>
              <v-col cols="12" sm="6" md="7" lg="8">
                <v-text-field
                  v-model="search"
                  append-icon="mdi-magnify"
                  label="Search"
                  single-line
                  hide-details
                  density="compact"
                  bg-color="white"
                  class="rounded-lg"
                />
              </v-col>
              <v-spacer />
              <v-menu close-on-content-click>
                <template #activator="{ props: menuProps }">
                  <v-btn
                    v-bind="menuProps"
                    icon="mdi-table-column"
                    density="compact"
                    variant="text"
                    aria-label="Show or hide columns"
                  />
                </template>
                <v-list density="compact" max-height="360px">
                  <v-list-item
                    v-for="leaf in allLeaves"
                    :key="leaf.key"
                    density="compact"
                  >
                    <v-checkbox-btn
                      :model-value="visibleKeys.has(String(leaf.key))"
                      :label="leaf.title"
                      hide-details
                      @update:model-value="toggleColumn(String(leaf.key))"
                    />
                  </v-list-item>
                </v-list>
              </v-menu>
              <v-col cols="12" sm="3" md="3" lg="2">
                <v-select
                  v-model="itemsPerPage"
                  :items="itemsPerPageOptions"
                  label="Rows per page"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="mr-2 rows-per-page-select"
                  bg-color="white"
                />
              </v-col>
            </v-toolbar>
          </template>

          <template #bottom>
            <div class="d-flex align-center justify-space-between pa-4">
              <span class="text-caption mr-4">
                Showing {{ (currentPage - 1) * itemsPerPage + 1 }}-{{
                  Math.min(currentPage * itemsPerPage, totalItems)
                }}
                of {{ totalItems }} entries
              </span>
              <v-pagination
                v-model="currentPage"
                :length="pageCount"
                :total-visible="7"
                rounded="circle"
              />
            </div>
          </template>

          <template #tfoot>
            <tfoot>
              <tr class="font-weight-bold">
                <td
                  v-for="header in flattenedHeaders"
                  :key="header.key"
                  :class="header.align ? 'text-' + header.align : ''"
                >
                  <slot :name="`tfoot-${header.key}`" :header="header">
                    {{ totals[header.key] }}
                  </slot>
                </td>
              </tr>
              <!-- Extra footer rows (e.g. Cash / TOTAL on the Open page).
                   Receives the flattened *visible* leaf headers so callers can
                   compute cell spans at render time — never a literal colspan. -->
              <slot name="tfoot-extra" :flattened-headers="flattenedHeaders" />
            </tfoot>
          </template>
        </v-data-table>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { getYearOptions } from '@/services/api'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotTableQuery, snapshotContext, type TableQueryParams } from '@/types/query'
import type { RequestOptions } from '@/services/http/client'
import { useTableSettings } from '@/composables/useTableSettings'
import { flattenHeaders } from '@/config/positionsHeaders'

// A column header may group children (parent header) or be a leaf column.
// `align` mirrors Vuetify's accepted values so the prop type is compatible
// with <v-data-table :headers>.
interface TableHeader {
  key?: string
  title?: string
  align?: 'start' | 'center' | 'end'
  children?: TableHeader[]
  [key: string]: unknown
}

type FetchPositionsParams = TableQueryParams

// Response returned by fetchPositions (shape of the paginated table payload).
interface FetchPositionsResponse {
  positions: Record<string, unknown>[]
  totals: Record<string, unknown>
  total_items: number
  cash_balances?: Record<string, unknown> | null
  [key: string]: unknown
}

// The backend returns numeric years; the select renders text/value items.
interface YearOption {
  text: string
  value: number | string
  divider?: boolean
}

interface Props {
  fetchPositions: (params: FetchPositionsParams, options: RequestOptions) => Promise<FetchPositionsResponse>
  headers: TableHeader[]
  pageTitle: string
  defaultVisibleKeys?: string[] | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update-page-title', title: string): void
  (e: 'accepted-result', result: FetchPositionsResponse | null): void
}>()

const appStore = useAppStore()
const context = usePortfolioContextStore()
const positionsQuery = usePortfolioRequest(props.fetchPositions, snapshotTableQuery)
const positions = computed(() => positionsQuery.data.value?.positions ?? [])
const totals = computed(() => positionsQuery.data.value?.totals ?? {})
const tableLoading = positionsQuery.loading
const yearOptions = ref<YearOption[]>([])
const totalItems = computed(() => positionsQuery.data.value?.total_items ?? 0)
const initialLoading = computed(() => !context.canRead || (positionsQuery.loading.value && positionsQuery.data.value === null))

const {
  timespan,
  dateFrom,
  dateTo,
  itemsPerPage,
  currentPage,
  sortBy,
  search,
  handleSortChange,
  handleTimespanChange,
} = useTableSettings()

const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)

const flattenedHeaders = computed<TableHeader[]>(() => {
  return visibleHeaders.value.flatMap((header) =>
    header.children ? header.children : [header]
  )
})

// Column visibility: all leaf columns of the unfiltered headers, plus the
// currently visible subset (component-local for now — not persisted).
const allLeaves = computed<TableHeader[]>(() =>
  flattenHeaders(props.headers as TableHeader[])
)

const visibleKeys = ref<Set<string>>(
  new Set(
    props.defaultVisibleKeys ??
      allLeaves.value.map((l) => String(l.key))
  )
)

watch(
  allLeaves,
  (leaves) => {
    if (!props.defaultVisibleKeys) {
      visibleKeys.value = new Set(leaves.map((l) => String(l.key)))
    }
  },
  { immediate: true }
)

const toggleColumn = (key: string) => {
  const next = new Set(visibleKeys.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  visibleKeys.value = next
}

// Vuetify 3.12 emits no divider class of its own for grouped headers, so we
// inject a `group-start` class (via headerProps, which merge onto the <th>)
// on every top-level group header and on its first leaf, giving a vertical
// rule between top-level groups in both header rows.
const withGroupStartClasses = (headers: TableHeader[]): TableHeader[] =>
  headers.map((h) => {
    if (!h.children) return h
    const children = h.children.map((c, i) => {
      if (i !== 0) return c
      const props = (c.headerProps ?? {}) as Record<string, unknown>
      return { ...c, headerProps: { ...props, class: 'group-start' } }
    })
    const props = (h.headerProps ?? {}) as Record<string, unknown>
    return {
      ...h,
      children,
      headerProps: { ...props, class: 'group-start' },
    }
  })

// Vuetify 3.12 has no generic #header slot — only per-column
// `header.<key>` slots. Build the dynamic slot names for leaves that carry a
// glossary `description`.
const describedHeaderSlots = computed(() =>
  flattenedHeaders.value
    .filter((h) => h.description)
    .map((h) => ({ key: String(h.key), slotName: `header.${h.key}` }))
)

const visibleHeaders = computed<TableHeader[]>(() => {
  const allowed = visibleKeys.value
  const filtered = props.headers
    .map((h) =>
      h.children
        ? {
            ...h,
            children: h.children.filter((c) => allowed.has(String(c.key))),
          }
        : h
    )
    .filter((h) =>
      h.children ? h.children.length > 0 : allowed.has(String(h.key))
    )
  return withGroupStartClasses(filtered)
})

const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)

const loading = computed(() => appStore.loading)

watch(positionsQuery.data, (result) => emit('accepted-result', result), { flush: 'sync' })
const yearsQuery = usePortfolioRequest(getYearOptionsForContext, snapshotContext)
async function getYearOptionsForContext(_params: TableQueryParams['context'], options: RequestOptions) {
  return getYearOptions(options)
}

const fetchData = async () => {
  if (!context.canRead || !dateTo.value) return
  await positionsQuery.run({
    context: context.committed,
    dateFrom: dateFrom.value, dateTo: dateTo.value,
    page: currentPage.value, itemsPerPage: itemsPerPage.value,
    search: search.value, sortBy: sortBy.value[0] || {},
  })
}

const fetchYearOptions = async () => {
  await yearsQuery.run(context.committed)
}
const retryFailedResources = () => {
  if (!context.canRead) return
  if (positionsQuery.error.value) fetchData()
  if (yearsQuery.error.value) fetchYearOptions()
}
watch(yearsQuery.data, (years) => {
  yearOptions.value = [
    { text: 'YTD', value: 'ytd' }, { text: 'All time', value: 'all_time' },
    ...(years ?? []).map((year) => ({ text: String(year), value: year })),
  ]
}, { flush: 'sync' })

watch(
  [() => context.canRead, () => appStore.dataRefreshTrigger,
    search, itemsPerPage, currentPage, sortBy, timespan, dateFrom, dateTo],
  () => { if (context.canRead && dateTo.value) fetchData() },
  { deep: true, immediate: true }
)
watch(
  [() => context.canRead, () => appStore.dataRefreshTrigger],
  () => { if (context.canRead) fetchYearOptions() },
  { immediate: true }
)
const initializeData = async () => {
  emit('update-page-title', props.pageTitle)

  if (!appStore.effectiveCurrentDate) {
    await appStore.fetchEffectiveCurrentDate()
  }

  // Check if dateFrom and dateTo are already set in the store
  if (!appStore.tableSettings.dateTo && appStore.tableSettings.timespan !== 'custom') {
    // If not set, use the default 'ytd' timespan
    await handleTimespanChange(appStore.tableSettings.timespan)
  }

  // Fetch year options
  // Year options follow committed context through their own request watcher.
}

onMounted(() => {
  initializeData()
})

onUnmounted(() => {
  emit('update-page-title', '')
})
</script>
<style scoped>
.nowrap-table :deep(td),
.nowrap-table :deep(th) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-variant-numeric: tabular-nums;
}

/* Sticky identity columns: Type sticks at 0, Name after it. Scoped to
   body/footer cells and the FIRST header row only — in a grouped two-row
   header, row 2 leaves are children of other groups and must not stick.
   Widths are fixed so the left offset is stable. */
.nowrap-table :deep(tbody td:nth-child(1)),
.nowrap-table :deep(tfoot td:nth-child(1)),
.nowrap-table :deep(thead tr:first-child th:nth-child(1)) {
  position: sticky;
  left: 0;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
  min-width: 90px;
}
.nowrap-table :deep(tbody td:nth-child(2)),
.nowrap-table :deep(tfoot td:nth-child(2)),
.nowrap-table :deep(thead tr:first-child th:nth-child(2)) {
  position: sticky;
  left: 90px;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
  min-width: 160px;
}
.nowrap-table :deep(thead tr:first-child th:nth-child(-n+2)) {
  z-index: 3; /* leaf header row above sticky body cells */
}

/* Group separation: vertical rules between top-level groups survive
   without reading the group row. The class is injected via headerProps
   (see withGroupStartClasses) — Vuetify 3.12 emits no divider class. */
.nowrap-table :deep(th.group-start) {
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

.rows-per-page-select {
  min-width: 180px;
  max-width: 200px;
}
</style>
