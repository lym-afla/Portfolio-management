<template>
  <v-defaults-provider :defaults="workspaceDefaults">
    <v-container fluid class="pa-0 workspace-ui positions-workspace">
      <v-overlay :model-value="loading" class="align-center justify-center">
        <v-progress-circular color="primary" indeterminate size="64" />
      </v-overlay>

      <v-alert v-if="positionsQuery.error.value || yearsQuery.error.value" type="error" class="mb-4">
        Unable to load positions or year options. The displayed data may be from the previous request.
        <v-btn data-testid="positions-retry" variant="text" color="white" :disabled="!context.canRead" @click="retryFailedResources">Retry</v-btn>
      </v-alert>
      <slot name="above-table" :loading="tableLoading" />

    <v-row no-gutters>
      <v-col cols="12">
        <v-skeleton-loader v-if="initialLoading" type="table" />
        <v-data-table
          v-else
          ref="tableRef"
          fixed-header
          :headers="tableHeaders"
          :items="positions"
          :loading="tableLoading"
          :items-length="totalItems"
          :items-per-page="itemsPerPage"
          :sort-by="sortBy"
          :custom-key-sort="neutralSorters"
          class="elevation-1 nowrap-table positions-table"
          density="compact"
          :style="{ '--positions-pin-offset': `${pinOffsetPx}px` }"
          @update:sort-by="handleSortChange"
        >
          <!-- Caption + per-group colgroup. Vuetify 3.12 has no caption prop;
               the #colgroup slot content lands as the first <table> children,
               so the caption sits before the colgroup/thead. -->
          <template #colgroup>
            <caption class="positions-table-caption">
              {{ captionText }}
            </caption>
            <colgroup v-if="!positionView.flat">
              <col
                v-for="group in positionView.groups"
                :key="group.id"
                :span="group.keys.length"
                :data-group="group.id"
              >
            </colgroup>
          </template>

          <!-- Leaf header cells: qualified glossary trigger + sort icon driven
               by the server sort state (the table never re-sorts the received
               page, so Vuetify's own icon state is intentionally unused). -->
          <template
            v-for="leaf in positionView.leaves"
            :key="leaf.key"
            #[`header.${leaf.key}`]
          >
            <div class="v-data-table-header__content">
              <v-tooltip
                v-if="leaf.description"
                :text="leaf.description"
                location="top"
              >
                <template #activator="{ props: tooltipProps }">
                  <button
                    type="button"
                    class="positions-glossary"
                    :aria-label="`${leaf.fullTitle}: ${leaf.description}`"
                    v-bind="tooltipProps"
                    @click.stop
                    @keydown.stop
                  >
                    {{ leafTitle(leaf) }}<span v-if="leaf.unitLabel" class="positions-unit-label"> ({{ leaf.unitLabel }})</span>
                  </button>
                </template>
              </v-tooltip>
              <span v-else>{{ leafTitle(leaf) }}</span>
              <v-icon
                v-if="leaf.sortable"
                class="v-data-table-header__sort-icon"
                :class="{ 'positions-sort-icon--active': activeSortOrder(leaf) !== null }"
                :icon="sortIconFor(leaf)"
                aria-hidden="true"
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
            <workspace-table-toolbar
              :query="{ search, page: currentPage, itemsPerPage }"
              search-label="Search positions"
              :rows-per-page-options="itemsPerPageOptions"
              @update:query="handleQueryIntent"
            >
              <template #filters>
                <v-select
                  v-model="timespan"
                  :items="yearOptions"
                  item-title="text"
                  item-value="value"
                  label="Year"
                  density="compact"
                  variant="outlined"
                  hide-details
                  bg-color="surface"
                  class="positions-year-select"
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
              <template #columns>
                <v-select
                  :model-value="view.preset.value"
                  :items="presetItems"
                  item-title="label"
                  item-value="id"
                  label="View"
                  density="compact"
                  variant="outlined"
                  hide-details
                  bg-color="surface"
                  class="positions-view-select"
                  data-testid="positions-view-select"
                  @update:model-value="selectPreset"
                />
                <v-menu
                  v-model="columnsMenuOpen"
                  :close-on-content-click="false"
                >
                  <template #activator="{ props: menuProps }">
                    <v-btn
                      v-bind="menuProps"
                      icon="mdi-table-column"
                      density="compact"
                      variant="text"
                      aria-label="Show or hide columns"
                      class="workspace-touch-action"
                    />
                  </template>
                  <v-list density="compact" min-width="340" max-height="480" class="positions-columns-menu">
                    <template v-for="group in chooserGroups" :key="group.id">
                      <v-list-subheader>{{ group.title }}</v-list-subheader>
                      <v-list-item
                        v-for="leaf in group.leaves"
                        :key="leaf.key"
                        density="compact"
                      >
                        <v-checkbox-btn
                          :model-value="view.isColumnVisible(leaf.key)"
                          :label="chooserLabel(leaf)"
                          :disabled="leaf.key === POSITION_IDENTITY_KEY"
                          hide-details
                          :data-testid="`column-${leaf.key}`"
                          @update:model-value="view.toggleColumn(leaf.key)"
                        />
                      </v-list-item>
                    </template>
                    <v-divider class="my-1" />
                    <v-list-item density="compact">
                      <v-btn
                        color="primary"
                        size="small"
                        data-testid="columns-done"
                        @click="columnsMenuOpen = false"
                      >
                        Done
                      </v-btn>
                    </v-list-item>
                  </v-list>
                </v-menu>
              </template>
            </workspace-table-toolbar>
            <div
              v-if="hiddenSortSummary"
              class="positions-sort-summary d-flex align-center ga-2 px-4 py-1"
              role="status"
              data-testid="hidden-sort-summary"
            >
              <span class="text-body-2">
                Sorted by {{ hiddenSortSummary.fullTitle }} —
                {{ hiddenSortSummary.order === 'desc' ? 'descending' : 'ascending' }}
              </span>
              <v-btn size="x-small" variant="text" color="primary" data-testid="clear-sort" @click="clearSort">
                Clear sort
              </v-btn>
            </div>
          </template>

          <!-- Body rows render explicitly so every cell carries its header
               association, alignment, group boundary and key-based pin class;
               per-column item.<key> slots from the page stay authoritative. -->
          <template #item="{ item }">
            <tr>
              <template v-for="leaf in positionView.leaves" :key="leaf.key">
                <th
                  v-if="leaf.key === POSITION_IDENTITY_KEY"
                  scope="row"
                  :headers="leaf.headerId"
                  :data-leaf-key="leaf.key"
                  class="positions-cell"
                  :class="cellClasses(leaf)"
                >
                  <slot :name="`item.${leaf.key}`" :item="item">{{ item[leaf.key] }}</slot>
                </th>
                <td
                  v-else
                  :headers="leaf.headerId"
                  :data-leaf-key="leaf.key"
                  class="positions-cell"
                  :class="cellClasses(leaf)"
                >
                  <slot :name="`item.${leaf.key}`" :item="item">{{ item[leaf.key] }}</slot>
                </td>
              </template>
            </tr>
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
                  v-for="leaf in positionView.leaves"
                  :key="leaf.key"
                  :headers="leaf.headerId"
                  :data-leaf-key="leaf.key"
                  :class="cellClasses(leaf)"
                >
                  <slot
                    v-if="leaf.key === labelKey"
                    name="tfoot-label"
                    :header="leaf"
                  />
                  <slot v-else :name="`tfoot-${leaf.key}`" :header="leaf">
                    {{ totals[leaf.key] }}
                  </slot>
                </td>
              </tr>
              <!-- Extra footer rows (e.g. Cash / TOTAL on the Open page).
                   Receives the visible leaf headers, the key of the cell
                   that carries row labels, and a per-leaf binding helper so
                   page-rendered cells share the base row's header
                   associations and key-based pin classes — never a literal
                   colspan. -->
              <slot
                name="tfoot-extra"
                :flattened-headers="positionView.leaves"
                :label-key="labelKey"
                :footer-cell-props="toFooterCellProps"
              />
            </tfoot>
          </template>
        </v-data-table>
      </v-col>
    </v-row>
    </v-container>
  </v-defaults-provider>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { getYearOptions } from '@/services/api'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotTableQuery, snapshotContext, type TableQueryParams } from '@/types/query'
import type { RequestOptions } from '@/services/http/client'
import { useTableSettings } from '@/composables/useTableSettings'
import { usePositionsTableView } from '@/composables/usePositionsTableView'
import {
  buildPositionView,
  positionPresetLabel,
  positionPresets,
  positionTableLeaves,
  POSITION_GROUP_ORDER,
  POSITION_IDENTITY_KEY,
  type PositionPresetId,
  type PositionTableId,
  type PositionView,
  type PositionViewLeaf,
} from '@/config/positionsTableViews'
import WorkspaceTableToolbar from '@/components/workspace/WorkspaceTableToolbar.vue'
import { workspaceDefaults } from '@/theme/defaults'

// Vuetify header shape (custom props such as headerProps/cellProps/cellClass
// are spread onto the rendered th/td by Vuetify 3.12).
interface VuetifyHeader {
  title: string
  key: string
  align: 'start' | 'center' | 'end'
  sortable: boolean
  children?: VuetifyHeader[]
  class?: string
  headerProps?: Record<string, unknown>
  cellProps?: Record<string, unknown>
  cellClass?: string[]
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
  tableId: PositionTableId
  pageTitle: string
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

// Presentation preferences (preset/visible columns) are per-table and
// per-user; they deliberately share nothing with the query settings above.
const view = usePositionsTableView(props.tableId)
const columnsMenuOpen = ref(false)

const reportingCurrency = computed(() => context.committed.currency || 'USD')

const positionView = computed<PositionView>(() =>
  buildPositionView(props.tableId, view.preset.value, view.visibleKeys.value, reportingCurrency.value),
)

const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)

const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)

const loading = computed(() => appStore.loading)

// --- Header derivation: one ordered visible-leaf model feeds headers,
// boundaries, pinning and footers. ----------------------------------------

const leafTitle = (leaf: PositionViewLeaf) => (positionView.value.flat ? leaf.fullTitle : leaf.title)

const activeSortOrder = (leaf: PositionViewLeaf): 'asc' | 'desc' | null => {
  const active = sortBy.value[0]
  if (!active || active.key !== leaf.key) return null
  return active.order === 'desc' ? 'desc' : 'asc'
}

const sortIconFor = (leaf: PositionViewLeaf) => {
  const order = activeSortOrder(leaf)
  if (order === 'asc') return 'mdi-arrow-up'
  if (order === 'desc') return 'mdi-arrow-down'
  return 'mdi-unfold-more-vertical'
}

// Server-owned rendering repair: Vuetify 3.12 always sorts and filters the
// items it receives when sortBy/search are bound. customKeySort functions
// that return 0 for every pair make the internal sort a stable no-op, so the
// displayed order is exactly the server's page order while header clicks
// still cycle asc/desc/none and emit update:sort-by.
const neutralSorters = computed(() =>
  Object.fromEntries(positionTableLeaves(props.tableId).map((leaf) => [leaf.key, () => 0])),
)

const pinIndexFor = (leaf: PositionViewLeaf) => {
  if (!leaf.pinned) return 0
  const pinned = positionView.value.leaves.filter((candidate) => candidate.pinned)
  return pinned.findIndex((candidate) => candidate.key === leaf.key) + 1
}

const cellClasses = (leaf: PositionViewLeaf) => {
  const classes = [`text-${leaf.align}`]
  if (leaf.isFirstOfGroup) classes.push('group-start')
  const pinIndex = pinIndexFor(leaf)
  if (pinIndex > 0) classes.push(`col-pin-${pinIndex}`)
  return classes
}

const vuetifyLeaf = (leaf: PositionViewLeaf): VuetifyHeader => {
  const pinIndex = pinIndexFor(leaf)
  const ariaSort = activeSortOrder(leaf)
  const headerProps: Record<string, unknown> = {
    id: leaf.headerId,
    'data-leaf-key': leaf.key,
  }
  if (ariaSort) headerProps['aria-sort'] = ariaSort === 'asc' ? 'ascending' : 'descending'
  const classes: string[] = []
  if (leaf.isFirstOfGroup) classes.push('group-start')
  if (pinIndex > 0) classes.push(`col-pin-${pinIndex}`)
  if (classes.length) headerProps.class = classes
  return {
    title: leafTitle(leaf),
    key: leaf.key,
    align: leaf.align,
    sortable: leaf.sortable,
    ...(leaf.class ? { class: leaf.class } : {}),
    headerProps,
    cellProps: { headers: leaf.headerId },
  }
}

const tableHeaders = computed<VuetifyHeader[]>(() => {
  if (positionView.value.flat) {
    return positionView.value.leaves.map(vuetifyLeaf)
  }
  return positionView.value.groups.map((group) => ({
    title: group.title,
    key: group.id,
    align: 'start' as const,
    sortable: false,
    headerProps: { class: ['positions-group-band', 'group-start'], scope: 'colgroup' },
    children: group.keys
      .map((key) => positionView.value.leaves.find((leaf) => leaf.key === key)!)
      .map(vuetifyLeaf),
  }))
})

// The footer label (Total for assets / Cash / TOTAL) lives in the first
// visible identity leaf — Type when shown, otherwise the Security column.
const labelKey = computed(() => {
  const leaves = positionView.value.leaves
  const type = leaves.find((leaf) => leaf.key === 'type')
  return type ? 'type' : POSITION_IDENTITY_KEY
})

const captionText = computed(() =>
  `${props.pageTitle} — ${positionPresetLabel(props.tableId, view.preset.value)} view`,
)

// Shared cell binding for page-rendered footer rows: the same header
// association, leaf identity, alignment and key-based pin class the base
// totals row applies.
const toFooterCellProps = (leaf: PositionViewLeaf) => ({
  headers: leaf.headerId,
  'data-leaf-key': leaf.key,
  class: cellClasses(leaf),
})

// Chooser lists every original leaf grouped by lifecycle group, with fully
// qualified names, regardless of the current visibility.
const chooserGroups = computed(() => {
  const registry = buildPositionView(props.tableId, 'full-ledger', null, reportingCurrency.value)
  return POSITION_GROUP_ORDER
    .map((groupId) => ({
      id: groupId,
      title: registry.groups.find((group) => group.id === groupId)?.title ?? groupId,
      leaves: registry.leaves.filter((leaf) => leaf.groupId === groupId),
    }))
    .filter((group) => group.leaves.length > 0)
})

const chooserLabel = (leaf: PositionViewLeaf) =>
  leaf.unitKind === 'reporting-money' && leaf.unitLabel
    ? `${leaf.fullTitle} (${leaf.unitLabel})`
    : leaf.fullTitle

const presetItems = computed(() => [
  ...positionPresets(props.tableId).map((preset) => ({ id: preset.id, label: preset.label })),
  { id: 'custom', label: 'Custom columns', disabled: true },
])

const selectPreset = (value: unknown) => {
  if (typeof value === 'string' && value !== 'custom') view.setPreset(value as PositionPresetId)
}

const handleQueryIntent = (patch: { search?: string; itemsPerPage?: number; page?: number }) => {
  if (typeof patch.search === 'string') search.value = patch.search
  if (typeof patch.itemsPerPage === 'number') itemsPerPage.value = patch.itemsPerPage
  if (typeof patch.page === 'number') currentPage.value = patch.page
}

// --- Hidden active sort: the sorted leaf may be hidden by the current view;
// its full name and a Clear action stay visible, and the server sort is
// untouched until the user explicitly clears it. ---------------------------

const hiddenSortSummary = computed(() => {
  const active = sortBy.value[0]
  if (!active) return null
  if (positionView.value.leafKeys.includes(String(active.key))) return null
  const leaf = positionTableLeaves(props.tableId).find((entry) => entry.key === active.key)
  if (!leaf) return null
  return { fullTitle: leaf.fullTitle, order: active.order === 'desc' ? 'desc' : 'asc' }
})

const clearSort = () => handleSortChange([])

// --- Key-based pinning with measured offsets. The sticky left offset of the
// second pinned column equals the rendered width of the first; a
// ResizeObserver keeps it current when columns/widths change. -------------

const tableRef = ref<{ $el: HTMLElement } | null>(null)
const pinOffsetPx = ref(90)
let pinObserver: ResizeObserver | null = null

const pinnedLeaves = computed(() => positionView.value.leaves.filter((leaf) => leaf.pinned))

const measurePins = async () => {
  await nextTick()
  const root = tableRef.value?.$el as HTMLElement | undefined
  if (!root) return
  // Name the scroll region so keyboard users can reach it.
  const scrollRegion = root.querySelector('.v-table__wrapper')
  if (scrollRegion && scrollRegion.getAttribute('tabindex') !== '0') {
    scrollRegion.setAttribute('tabindex', '0')
    scrollRegion.setAttribute('role', 'region')
    scrollRegion.setAttribute('aria-label', `${props.pageTitle} table, scrollable`)
  }
  const [first] = pinnedLeaves.value
  if (!first) return
  const firstCell = root.querySelector(`th[data-leaf-key="${first.key}"], td[data-leaf-key="${first.key}"]`)
  if (!firstCell) return
  pinOffsetPx.value = Math.max(48, Math.round(firstCell.getBoundingClientRect().width))

  if (typeof ResizeObserver === 'undefined') return
  pinObserver?.disconnect()
  pinObserver = new ResizeObserver(() => {
    const width = Math.max(48, Math.round(firstCell.getBoundingClientRect().width))
    if (width > 0) pinOffsetPx.value = width
  })
  pinObserver.observe(firstCell)
}

watch(
  () => [positionView.value.leafKeys.join('|'), props.pageTitle],
  () => { measurePins() },
  { immediate: true },
)

// The table itself renders late (skeleton while loading): initialize the
// caption-era accessibility attributes and pin offsets on FIRST render too,
// not only after a view change.
watch(tableRef, (table) => {
  if (table) measurePins()
})

onMounted(() => {
  measurePins()
  initializeData()
})

onUnmounted(() => {
  pinObserver?.disconnect()
  pinObserver = null
  emit('update-page-title', '')
})

// --- Existing query lifecycle (unchanged ownership). -----------------------

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
watch(yearsQuery.data, (options) => {
  // The server list is authoritative (numeric years plus its own All-time/
  // YTD entries and dividers). The special values map to the local timespan
  // values; calendar years keep their numeric value for the query builder.
  yearOptions.value = (options ?? []).map((option) =>
    option.divider
      ? { divider: true, text: '', value: '' }
      : {
          text: option.value === 'ytd' ? 'YTD' : option.value === 'all_time' ? 'All time' : option.text,
          value: option.value === 'ytd' || option.value === 'all_time' ? option.value : Number(option.value),
        })
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
</script>

<style scoped>
.positions-workspace :deep(.positions-table .v-table__wrapper):focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.positions-table-caption {
  /* Real caption semantics kept available to assistive tech without
     duplicating the page heading visually. */
  position: static;
  width: 100%;
  padding: 4px 16px 8px;
  text-align: left;
  caption-side: top;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.nowrap-table :deep(td),
.nowrap-table :deep(th) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-variant-numeric: tabular-nums;
}

/* Key-based sticky identity: classes come from the ordered visible-leaf
   model (col-pin-1 / col-pin-2), never from cell positions, so hiding
   Type can never make Currency sticky. The second offset is the measured
   width of the first pinned column via --positions-pin-offset. */
.nowrap-table :deep(.col-pin-1) {
  position: sticky;
  left: 0;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
}
.nowrap-table :deep(.col-pin-2) {
  position: sticky;
  left: var(--positions-pin-offset, 90px);
  z-index: 2;
  background: rgb(var(--v-theme-surface));
}
.nowrap-table :deep(thead .col-pin-1),
.nowrap-table :deep(thead .col-pin-2) {
  z-index: 3; /* header cells above sticky body cells */
}
/* Narrow screens: cap the pinned pair so it never covers the viewport. */
@media (max-width: 599px) {
  .nowrap-table :deep(.col-pin-1) {
    min-width: 72px;
  }
  .nowrap-table :deep(.col-pin-2) {
    max-width: calc(100vw - 176px);
  }
}

/* Group boundaries from the same metadata: a restrained rule at the start
   of each group across header, body and footer. */
.nowrap-table :deep(.group-start) {
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

/* Quiet left-aligned group bands: the leaf row keeps reading priority. */
.nowrap-table :deep(th.positions-group-band) {
  text-align: start !important;
  font-size: 0.7rem;
  font-weight: 500;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.6);
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-bottom: none;
}

.positions-glossary {
  padding: 0;
  font: inherit;
  letter-spacing: inherit;
  text-align: inherit;
  text-decoration: underline dotted rgba(var(--v-theme-on-surface), 0.5);
  text-underline-offset: 2px;
  cursor: help;
  background: transparent;
  border: none;
}

.positions-unit-label {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 0.72em;
}

.nowrap-table :deep(.positions-sort-icon--active) {
  color: rgb(var(--v-theme-primary));
  opacity: 1;
}
.nowrap-table :deep(.v-data-table-header__sort-icon:not(.positions-sort-icon--active)) {
  opacity: 0.35;
}

.positions-sort-summary {
  background: rgba(var(--v-theme-surface-variant), 0.35);
  border-top: thin solid rgba(var(--v-theme-on-surface), 0.08);
}

.positions-year-select {
  min-width: 128px;
  max-width: 160px;
}

.positions-view-select {
  min-width: 190px;
  max-width: 220px;
}
</style>
