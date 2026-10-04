<template>
  <div>
    <WorkspaceSection
      heading-id="fx-section"
      title="FX rates"
      description="Exchange-rate grid by date and currency pair; each pair is quoted from the first currency to the second."
    >
    <template #actions>
      <WorkspaceActions
        :primary="{ id: 'add-fx', label: 'Add FX Rate', icon: 'mdi-plus' }"
        :secondary="[{ id: 'import-fx', label: 'Import FX Rates', icon: 'mdi-upload' }]"
        :overflow="[]"
        @action="handleWorkspaceAction"
      />
    </template>
    <v-alert v-if="fxQuery.error.value" type="error" class="mb-4">Unable to load exchange rates. Change the filters or try again.</v-alert>

    <WorkspaceTableToolbar
      class="mb-2"
      :query="{ search: search, page: currentPage, itemsPerPage: itemsPerPage }"
      :search-label="'Search'"
      search-placeholder="Search FX rates"
      :rows-per-page-options="itemsPerPageOptions"
      @update:query="onToolbarQuery"
    >
      <template #filters>
        <DateRangeSelector
          :model-value="dateRangeForSelector"
          @update:model-value="handleDateRangeChange"
        />
      </template>
    </WorkspaceTableToolbar>

      <v-data-table
          :headers="headers"
          :items="fxData"
          :loading="tableLoading"
          :items-per-page="itemsPerPage"
          class="elevation-1 nowrap-table"
          density="compact"
          :sort-by="sortBy"
          @update:sort-by="handleSortChange"
          :server-items-length="totalItems"
          :items-length="totalItems"
          disable-sort
      >

          <template #item="{ item }">
            <tr>
              <td>{{ item.date }}</td>
              <td
                v-for="pairLabel in currencies"
                :key="pairLabel"
                class="text-center pa-0"
              >
                <!--
                  Per-cell editing: a filled cell opens the record for editing;
                  an empty (—) cell opens Add mode with date + pair prefilled.
                  Each cell maps to exactly one FX record, so there's no row vs.
                  record ambiguity.
                -->
                <v-btn
                  variant="text"
                  size="small"
                  class="cell-btn"
                  :class="item[pairLabel] ? 'cell-btn--filled' : 'cell-btn--empty'"
                  @click="onCellClick(item, pairLabel)"
                >
                  {{ item[pairLabel]?.rate ?? '—' }}
                </v-btn>
              </td>
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
        </v-data-table>
    </WorkspaceSection>

    <!-- Add/edit dialog. editItem drives Edit mode; prefill seeds Add-from-cell. -->
    <FXDialog v-if="showFXDialogMounted"
      v-model="showFXDialog"
      :edit-item="editedItem"
      :prefill="dialogPrefill"
      @fx-added="fetchFXData"
      @fx-updated="fetchFXData"
      @fx-delete="onDeleteFromDialog"
    />
    <FXImportDialog v-if="showImportDialogMounted"
      v-model="showImportDialog"
      @import-completed="fetchFXData"
      @refresh-table="fetchFXData"
    />

    <!-- Delete confirmation: exact subject identity, parent handlers authoritative -->
    <ConfirmActionDialog
      :model-value="showDeleteDialog"
      :subject="deleteSubject"
      :busy="deleteLoading"
      :error="deleteError"
      @update:model-value="onDeleteDialogChange"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup>
import { defineAppDialog } from '@/composables/asyncDialog'
import { useFirstOpen } from '@/composables/useFirstOpen'
import { ref, computed, watch, watchEffect, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import {
  getFXData,
  deleteFXRate,
  getFXDetails,
} from '@/services/api'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotTableQuery } from '@/types/query'
import { useTableSettings } from '@/composables/useTableSettings'
import DateRangeSelector from '@/components/DateRangeSelector.vue'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import WorkspaceActions from '@/components/workspace/WorkspaceActions.vue'
import WorkspaceTableToolbar from '@/components/workspace/WorkspaceTableToolbar.vue'
import ConfirmActionDialog from '@/components/workspace/ConfirmActionDialog.vue'
import { calculateDateRange } from '@/utils/dateRangeUtils'
const FXDialog = defineAppDialog(() => import('@/components/dialogs/FXDialog.vue'))
const FXImportDialog = defineAppDialog(() => import('@/components/dialogs/FXImportDialog.vue'))
import { useErrorHandler } from '@/composables/useErrorHandler'
import { pivotFxRows, splitPairLabel } from '@/utils/fxPivot'
import logger from '@/utils/logger'

const appStore = useAppStore()
const context = usePortfolioContextStore()

const dateRange = ref('ytd')
const {
  dateFrom,
  dateTo,
  itemsPerPage,
  currentPage,
  sortBy,
  search,
  handleSortChange,
  updateDateRange,
} = useTableSettings({ syncRelativeDate: false })

const { handleApiError } = useErrorHandler()

const loading = ref(true)
const tableLoading = computed(() => fxQuery.loading.value)
const deleteLoading = ref(false)
const fxData = computed(() => fxQuery.data.value?.pivoted ?? [])
const totalItems = computed(() => fxQuery.data.value?.count ?? 0)
const currencies = computed(() => fxQuery.data.value?.pairLabels ?? [])

let didInit = false

const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)
const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)
const effectiveCurrentDate = computed(() => appStore.effectiveCurrentDate)

const headers = computed(() => [
  { title: 'Date', key: 'date', align: 'start', sortable: true },
  ...currencies.value.map((pairLabel) => ({
    title: pairLabel,
    key: pairLabel,
    align: 'center',
    sortable: true,
  })),
])

const fxQuery = usePortfolioRequest(async (params, options) => {
  const response = await getFXData({
    startDate: params.dateFrom, endDate: params.dateTo,
    page: params.page, itemsPerPage: params.itemsPerPage,
    sortBy: params.sortBy, search: params.search,
  }, options)
  return { ...pivotFxRows(response.results), count: response.count }
}, snapshotTableQuery)

const fetchFXData = async () => {
  if (!context.canRead || !dateTo.value) return
  await fxQuery.run({
    context: context.committed, dateFrom: dateFrom.value, dateTo: dateTo.value,
    page: currentPage.value, itemsPerPage: itemsPerPage.value,
    sortBy: sortBy.value[0] || {}, search: search.value,
  })
}
const initializeDateRange = async () => {
  logger.log('Unknown', 'Initializing date range')
  logger.log('Unknown', 'effectiveCurrentDate:', effectiveCurrentDate.value)
  logger.log('Unknown', 'dateRange:', dateRange.value)

  if (!effectiveCurrentDate.value) {
    try {
      await appStore.fetchEffectiveCurrentDate()
    } catch (error) {
      logger.error(
        'Unknown',
        'Failed to fetch effective current date:',
        error
      )
      return // Exit the function if we can't get the effective current date
    }
  }

  if (effectiveCurrentDate.value) {
    const { from, to } = calculateDateRange(
      dateRange.value,
      effectiveCurrentDate.value,
      dateFrom.value,
      dateTo.value
    )
    logger.log('Unknown', 'Calculated date range:', { from, to })

    updateDateRange({
      timespan: ['ytd', 'all_time'].includes(dateRange.value) ? dateRange.value : 'custom',
      dateFrom: from,
      dateTo: to,
    })
  } else {
    logger.error(
      'Unknown',
      'effectiveCurrentDate is still not set after attempting to fetch it'
    )
  }
}

const handleDateRangeChange = (newDateRange) => {
  logger.log('Unknown', 'Date range changed:', newDateRange)
  dateRange.value = newDateRange.dateRange
  updateDateRange({
    timespan: ['ytd', 'all_time'].includes(dateRange.value) ? dateRange.value : 'custom',
    dateFrom: newDateRange.dateFrom,
    dateTo: newDateRange.dateTo,
  })
}

// Initialize the date range exactly once. `watchEffect` covers the case where
// the store is already hydrated (runs immediately on setup); if it isn't,
// `onMounted` fetches the effective date and drives the init. The `didInit`
// guard ensures the two never both fire (which previously caused a duplicate
// `list_fx/` request).
watchEffect(async () => {
  if (didInit) return
  if (effectiveCurrentDate.value) {
    didInit = true
    await initializeDateRange()
    loading.value = false
  }
})

// Re-fetch on genuine user-driven changes only. NOTE: `loading` is
// intentionally excluded — it flips during init, and having it here caused the
// watch to re-fire and issue a second, duplicate `list_fx/` POST.
watch(effectiveCurrentDate, (date) => {
  if (!didInit || !date || dateRange.value === 'custom') return
  const { from, to } = calculateDateRange(dateRange.value, date)
  if (from !== dateFrom.value || to !== dateTo.value) {
    updateDateRange({
      timespan: ['ytd', 'all_time'].includes(dateRange.value) ? dateRange.value : 'custom',
      dateFrom: from,
      dateTo: to,
    })
  }
})

watch(
  [() => context.canRead, () => appStore.dataRefreshTrigger, dateFrom, dateTo, currentPage, itemsPerPage, sortBy, search],
  () => {
    if (didInit && context.canRead && dateTo.value) fetchFXData()
  },
  { immediate: true }
)

onMounted(async () => {
  logger.log('Unknown', 'Mounting FXPage')
  if (didInit) return
  if (!effectiveCurrentDate.value) {
    didInit = true
    await initializeDateRange()
    loading.value = false
  }
})

const showFXDialog = ref(false)
const showFXDialogMounted = useFirstOpen(showFXDialog)
const showImportDialog = ref(false)
const showImportDialogMounted = useFirstOpen(showImportDialog)
const showDeleteDialog = ref(false)
const editedItem = ref(null)
// Prefill for Add-from-cell: { date, from_currency, to_currency }. Null when
// the dialog is in plain Add (toolbar) or Edit mode.
const dialogPrefill = ref(null)
const itemToDelete = ref(null)
const deleteSubject = ref(null)
const deleteError = ref(null)

const openAddFXDialog = () => {
  editedItem.value = null
  dialogPrefill.value = null
  showFXDialog.value = true
}

/**
 * Per-cell click handler. Each cell maps to exactly one FX record (filled) or
 * one missing pair to add (empty). We open the shared FXDialog in the right
 * mode instead of acting on the whole pivoted row.
 * @param {object} item pivoted row
 * @param {string} pairLabel e.g. "USD/EUR"
 */
const onCellClick = async (item, pairLabel) => {
  const entry = item?.[pairLabel]
  const [from_currency, to_currency] = splitPairLabel(pairLabel)
  if (entry && entry.id != null) {
    // Filled cell → edit that specific record.
    logger.log('Unknown', 'Editing FX record:', { date: item.date, pairLabel, id: entry.id })
    try {
      const fxDetails = await getFXDetails(entry.id)
      editedItem.value = fxDetails
      dialogPrefill.value = null
      showFXDialog.value = true
    } catch (error) {
      handleApiError(error)
    }
  } else {
    // Empty cell (—) → Add that pair for this date, pre-filled.
    logger.log('Unknown', 'Adding FX pair:', { date: item.date, pairLabel })
    editedItem.value = null
    dialogPrefill.value = { date: item.date, from_currency, to_currency }
    showFXDialog.value = true
  }
}

// Delete is now triggered from inside FXDialog (the dialog knows the record).
const onDeleteFromDialog = (record) => {
  if (!record?.id) return
  itemToDelete.value = record
  deleteSubject.value = {
    title: `Delete FX rate ${record.from_currency}/${record.to_currency}`,
    confirmLabel: 'Delete FX rate',
    details: [
      { label: 'Date', value: record.date ?? '—' },
      { label: 'Pair', value: `${record.from_currency}/${record.to_currency}` },
      { label: 'Rate', value: record.rate ?? '—' },
    ],
  }
  deleteError.value = null
  showDeleteDialog.value = true
}

const onDeleteDialogChange = (value) => {
  if (deleteLoading.value && value === false) return
  showDeleteDialog.value = false
  deleteError.value = null
}

const confirmDelete = async () => {
  if (!itemToDelete.value?.id) return
  deleteLoading.value = true
  deleteError.value = null
  try {
    await deleteFXRate(itemToDelete.value.id)
    showFXDialog.value = false
    showDeleteDialog.value = false
    await fetchFXData()
  } catch (error) {
    deleteError.value = handleApiError(error)
  } finally {
    deleteLoading.value = false
  }
}

const onToolbarQuery = (patch) => {
  if ('search' in patch && patch.search !== search.value) search.value = patch.search
}

// Presentation-only action hierarchy: the existing openers stay authoritative.
const handleWorkspaceAction = (id) => {
  if (id === 'add-fx') openAddFXDialog()
  else if (id === 'import-fx') showImportDialog.value = true
}

const dateRangeForSelector = computed(() => ({
  dateRange: dateRange.value,
  dateFrom: dateFrom.value,
  dateTo: dateTo.value,
}))
</script>

<style scoped>
/* Per-cell buttons: the whole grid is editable, so each rate is a button.
   Filled cells read as plain text but reveal an edit affordance on hover;
   empty (—) cells signal they are addable. */
.cell-btn {
  width: 100%;
  min-width: 0;
  height: auto;
  text-transform: none;
  letter-spacing: normal;
  font-weight: normal;
}

.cell-btn--filled {
  color: rgba(0, 0, 0, 0.87);
}

.cell-btn--empty {
  color: rgba(0, 0, 0, 0.38);
  font-style: italic;
}

.cell-btn--empty:hover {
  color: rgb(var(--v-theme-primary));
}
</style>
