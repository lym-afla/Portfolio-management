<template>
  <v-container fluid class="pa-0">
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64" />
    </v-overlay>

    <slot name="above-table" />

    <v-row no-gutters>
      <v-col cols="12">
        <v-skeleton-loader v-if="initialLoading" type="table" />
        <v-data-table
          v-else
          :headers="headers"
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
          must-sort
          disable-sort
        >
          <template v-for="(_, name) in $slots" #[name]="slotData">
            <slot :name="name" v-bind="slotData" />
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
              <v-col cols="12" sm="3" md="3" lg="2">
                <v-select
                  v-model="itemsPerPage"
                  :items="itemsPerPageOptions"
                  label="Rows per page"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="mr-2 rows-per-page-select"
                  @update:model-value="handleItemsPerPageChange"
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
                @update:model-value="handlePageChange"
              />
            </div>
          </template>

          <template #tfoot>
            <tfoot>
              <tr class="font-weight-bold">
                <td
                  v-for="header in flattenedHeaders"
                  :key="header.key"
                  :class="header.align"
                >
                  <slot :name="`tfoot-${header.key}`" :header="header">
                    {{ totals[header.key] }}
                  </slot>
                </td>
              </tr>
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
import { getYearOptions } from '@/services/api'
import { useTableSettings } from '@/composables/useTableSettings'
import logger from '@/utils/logger'

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

// Query params passed to the parent-provided fetchPositions function.
interface FetchPositionsParams {
  dateFrom: string | null
  dateTo: string | null
  page: number
  itemsPerPage: number
  search: string
  sortBy: Record<string, unknown>
  [key: string]: unknown
}

// Response returned by fetchPositions (shape of the paginated table payload).
interface FetchPositionsResponse {
  positions: Record<string, unknown>[]
  totals: Record<string, unknown>
  total_items: number
  [key: string]: unknown
}

// The year <v-select> items. The backend returns plain years, but the
// template renders them as items with text/value and an optional divider, so
// we widen the local ref to match what the template expects.
interface YearOption {
  text: string
  value: number | string
  divider?: boolean
  [key: string]: unknown
}

interface Props {
  fetchPositions: (params: FetchPositionsParams) => Promise<FetchPositionsResponse>
  headers: TableHeader[]
  pageTitle: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update-page-title', title: string): void
}>()

const appStore = useAppStore()
const positions = ref<Record<string, unknown>[]>([])
const totals = ref<Record<string, unknown>>({})
const tableLoading = ref(true)
const yearOptions = ref<YearOption[]>([])
const totalItems = ref(0)
const initialLoading = ref(true)

const {
  timespan,
  dateFrom,
  dateTo,
  itemsPerPage,
  currentPage,
  sortBy,
  search,
  handlePageChange,
  handleItemsPerPageChange,
  handleSortChange,
  handleTimespanChange,
} = useTableSettings()

const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)

const flattenedHeaders = computed<TableHeader[]>(() => {
  return props.headers.flatMap((header) =>
    header.children ? header.children : [header]
  )
})

const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)

const loading = computed(() => appStore.loading)
const error = computed(() => appStore.error)

const fetchData = async () => {
  tableLoading.value = true
  try {
    console.log('[PositionsPageBase] fetchData called with:', {
      // timespan: timespan.value,
      dateFrom: dateFrom.value,
      dateTo: dateTo.value,
      currentPage: currentPage.value,
      itemsPerPage: itemsPerPage.value,
      search: search.value,
      sortBy: sortBy.value,
    })
    const data = await props.fetchPositions({
      // timespan: timespan.value,
      dateFrom: dateFrom.value,
      dateTo: dateTo.value,
      page: currentPage.value,
      itemsPerPage: itemsPerPage.value,
      search: search.value,
      sortBy: sortBy.value[0] || {},
    })
    positions.value = data.positions
    totals.value = data.totals
    totalItems.value = data.total_items
  } catch (error) {
    appStore.setError(error)
    logger.error('Unknown', 'Error fetching positions:', error)
  } finally {
    tableLoading.value = false
    initialLoading.value = false
    logger.log(
      'Unknown',
      '[PositionsPageBase] Current appStore state:',
      {
        loading: appStore.loading,
        error: appStore.error,
        effectiveCurrentDate: appStore.effectiveCurrentDate,
        dataRefreshTrigger: appStore.dataRefreshTrigger,
      }
    )
  }
}

const fetchYearOptions = async () => {
  try {
    const years = await getYearOptions()
    // The backend returns plain years; the template consumes {text, value,
    // divider} items, so cast through unknown to the expected shape.
    yearOptions.value = years as unknown as YearOption[]
  } catch (error) {
    appStore.setError(error)
  } finally {
    initialLoading.value = false
  }
}

watch(
  [
    () => appStore.dataRefreshTrigger,
    search,
    itemsPerPage,
    currentPage,
    sortBy,
    timespan,
    dateFrom,
    dateTo,
  ],
  () => {
    fetchData()
  },
  { deep: true }
)

// This watch is used to update the year options when the selected account changes.
// Data refresh is handled in AccountSelection.vue, triggering dataRefreshTrigger.
watch(
  () => appStore.accountSelection,
  () => {
    fetchYearOptions()
  }
)

const initializeData = async () => {
  emit('update-page-title', props.pageTitle)

  if (!appStore.effectiveCurrentDate) {
    await appStore.fetchEffectiveCurrentDate()
  }

  // Check if dateFrom and dateTo are already set in the store
  if (
    !appStore.tableSettings.dateFrom ||
    !appStore.tableSettings.dateTo
  ) {
    // If not set, use the default 'ytd' timespan
    await handleTimespanChange(appStore.tableSettings.timespan)
  } else {
    // If already set, update the local timespan value
    timespan.value = appStore.tableSettings.timespan
  }

  // Fetch year options
  await fetchYearOptions()
  await fetchData()
}

onMounted(() => {
  initializeData()
})

onUnmounted(() => {
  emit('update-page-title', '')
})
</script>
<style scoped>
.nowrap-table :deep(td) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rows-per-page-select {
  min-width: 180px;
  max-width: 200px;
}
</style>
