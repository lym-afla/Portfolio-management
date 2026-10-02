<template>
  <v-container fluid class="pa-0 workspace-ui">
    <v-alert v-if="transactionsQuery.error.value" type="error" class="mb-4">Unable to load transactions. Change the filters or try again.</v-alert>
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64" />
    </v-overlay>

    <v-card class="mb-4">
      <v-card-text>
        <workspace-actions
          :primary="{ id: 'add-transaction', label: 'Add transaction', icon: 'mdi-plus' }"
          :secondary="[{ id: 'import-transactions', label: 'Import transactions', icon: 'mdi-upload' }]"
          :overflow="[
            { id: 'add-fx-transaction', label: 'Add FX transaction', icon: 'mdi-swap-horizontal' },
            { id: 'transfer-asset', label: 'Transfer asset', icon: 'mdi-swap-horizontal' },
            { id: 'record-merger', label: 'Record merger', icon: 'mdi-call-merge' },
          ]"
          @action="handleWorkspaceAction"
        />
            <MergerDialog v-if="showMergerDialogMounted" v-model="showMergerDialog" @created="onMergerCreated" />
      </v-card-text>
    </v-card>

    <v-row no-gutters>
      <v-col cols="12">
        <v-data-table
          :headers="headers"
          :items="transactions"
          :loading="tableLoading"
          :items-per-page="itemsPerPage"
          :items-length="totalItems"
          class="elevation-1 nowrap-table"
          density="compact"
          :sort-by="sortBy"
          @update:sort-by="handleSortChange"
          disable-sort
          item-key="id"
        >
          <template #top>
            <workspace-table-toolbar
              :query="{ search, page: currentPage, itemsPerPage }"
              search-label="Search transactions"
              :rows-per-page-options="itemsPerPageOptions"
              @update:query="handleQueryIntent"
            >
              <template #filters>
                <DateRangeSelector
                  :model-value="dateRangeModel"
                  @update:model-value="handleDateRangeChange"
                />
              </template>
            </workspace-table-toolbar>
          </template>

          <template #header>
            <tr>
              <th
                v-for="header in headers"
                :key="header.key"
                :colspan="header.children ? header.children.length : 1"
                :rowspan="header.children ? 1 : 2"
                :class="['text-' + header.align]"
              >
                {{ header.title }}
              </th>
            </tr>
            <tr>
              <template v-for="header in headers" :key="header.key">
                <th
                  v-for="subHeader in header.children"
                  :key="subHeader.key"
                  :class="['text-' + subHeader.align]"
                >
                  {{ subHeader.title }}
                </th>
              </template>
            </tr>
          </template>

          <template #item="{ item }">
            <transaction-row
              :transaction="item"
              :currencies="currencies"
              :show-balances="true"
              :show-cash-flow="true"
              :show-actions="true"
              @edit="editTransaction"
              @delete="processDeleteTransaction"
            />
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
      </v-col>
    </v-row>

    <TransactionFormDialog v-if="showTransactionDialogMounted"
      v-model="showTransactionDialog"
      :edit-item="editedTransaction"
      @transaction-added="fetchTransactions"
      @transaction-updated="fetchTransactions"
    />

    <FXTransactionFormDialog v-if="showFXTransactionDialogMounted"
      v-model="showFXTransactionDialog"
      :edit-item="editedTransaction"
      @transaction-added="fetchTransactions"
      @transaction-updated="fetchTransactions"
    />

    <ConfirmActionDialog
      :model-value="deleteDialog"
      :subject="deleteSubject"
      :busy="deleteBusy"
      :error="deleteError"
      :details-pending="detailsPending"
      :confirm-disabled="detailsFailed"
      @update:model-value="onConfirmDialogChange"
      @confirm="deleteTransactionConfirm"
    />

    <TransactionImportDialog v-if="showImportDialogMounted"
      v-model="showImportDialog"
      @import-completed="handleImportCompleted"
    />

    <AssetTransferDialog v-if="showTransferDialogMounted"
      v-model="showTransferDialog"
      @transfer-completed="handleTransferCompleted"
    />
  </v-container>
</template>

<script setup>
import { defineAppDialog } from '@/composables/asyncDialog'
import { useFirstOpen } from '@/composables/useFirstOpen'
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { calculateDateRange } from '@/utils/dateRangeUtils'
import {
  getTransactions,
  deleteTransaction,
  deleteFXTransaction,
  getTransactionDetails,
  getFXTransactionDetails,
} from '@/services/api'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotTableQuery } from '@/types/query'
import { useTableSettings } from '@/composables/useTableSettings'
import { useErrorHandler } from '@/composables/useErrorHandler'
import DateRangeSelector from '@/components/DateRangeSelector.vue'
const TransactionFormDialog = defineAppDialog(() => import('@/components/dialogs/TransactionFormDialog.vue'))
const FXTransactionFormDialog = defineAppDialog(() => import('@/components/dialogs/FXTransactionFormDialog.vue'))
const TransactionImportDialog = defineAppDialog(() => import('@/components/dialogs/TransactionImportDialog.vue'))
const AssetTransferDialog = defineAppDialog(() => import('@/components/dialogs/AssetTransferDialog.vue'))
const MergerDialog = defineAppDialog(() => import('@/components/dialogs/MergerDialog.vue'))
import TransactionRow from '@/components/transactions/TransactionRow.vue'
import WorkspaceActions from '@/components/workspace/WorkspaceActions.vue'
import WorkspaceTableToolbar from '@/components/workspace/WorkspaceTableToolbar.vue'
import ConfirmActionDialog from '@/components/workspace/ConfirmActionDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { displayTransactionType } from '@/utils/formatUtils'
import logger from '@/utils/logger'

defineOptions({ name: 'TransactionsPage' })

const emit = defineEmits(['update-page-title'])

const appStore = useAppStore()
const context = usePortfolioContextStore()
const showMergerDialog = ref(false)
const showMergerDialogMounted = useFirstOpen(showMergerDialog)
const { handleApiError } = useErrorHandler()

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

const dateRangeModel = ref({
  dateRange: 'all_time',
  dateFrom: null,
  dateTo: null,
})
const initialized = ref(false)

const transactionsQuery = usePortfolioRequest((params, options) => getTransactions(
  params.dateFrom, params.dateTo, params.page, params.itemsPerPage,
  params.search, params.sortBy, options
), snapshotTableQuery)

const fetchTransactions = async () => {
  if (!context.canRead || !dateTo.value) return
  await transactionsQuery.run({
    context: context.committed, dateFrom: dateFrom.value, dateTo: dateTo.value,
    page: currentPage.value, itemsPerPage: itemsPerPage.value,
    search: search.value, sortBy: sortBy.value[0] || {},
  })
}
const handleDateRangeChange = (newDateRange) => {
  dateRangeModel.value = newDateRange
  updateDateRange({
    timespan: ['ytd', 'all_time'].includes(newDateRange.dateRange) ? newDateRange.dateRange : 'custom',
    dateFrom: newDateRange.dateFrom,
    dateTo: newDateRange.dateTo,
  })
}

const syncRelativeDate = (date) => {
  if (!date || dateRangeModel.value.dateRange === 'custom') return
  const { from, to } = calculateDateRange(dateRangeModel.value.dateRange, date)
  dateRangeModel.value = { ...dateRangeModel.value, dateFrom: from, dateTo: to }
  if (from !== dateFrom.value || to !== dateTo.value) {
    updateDateRange({
      timespan: ['ytd', 'all_time'].includes(dateRangeModel.value.dateRange) ? dateRangeModel.value.dateRange : 'custom',
      dateFrom: from,
      dateTo: to,
    })
  }
}

const loading = ref(false)
const tableLoading = transactionsQuery.loading
const transactions = computed(() => transactionsQuery.data.value?.transactions ?? [])
const totalItems = computed(() => transactionsQuery.data.value?.total_items ?? 0)
const currencies = computed(() => transactionsQuery.data.value?.currencies ?? [])
const showTransactionDialog = ref(false)
const showTransactionDialogMounted = useFirstOpen(showTransactionDialog)
const showFXTransactionDialog = ref(false)
const showFXTransactionDialogMounted = useFirstOpen(showFXTransactionDialog)
const editedTransaction = ref(null)
const showImportDialog = ref(false)
const showImportDialogMounted = useFirstOpen(showImportDialog)
const showTransferDialog = ref(false)
const showTransferDialogMounted = useFirstOpen(showTransferDialog)

const authStore = useAuthStore()

// --- Exact-identity delete confirmation. The snapshot (kind + numeric id +
// display details) is fixed when the dialog opens; list filters, delayed
// detail replies and later selections can never retarget it. -------------
const deleteDialog = ref(false)
const deleteSubject = ref(null)
const deleteError = ref(null)
const deleteBusy = ref(false)
const detailsPending = ref(false)
const detailsFailed = ref(false)
const deleteSnapshot = ref(null)
let deleteGeneration = 0

const hasValue = (value) => value !== undefined && value !== null && value !== ''
const accountLabelOf = (item) =>
  item.account ? [item.account.broker_name, item.account.name].filter(Boolean).join(' — ') : ''

// Wire-contract note: LIST rows carry cur/from_cur/to_cur, while the DETAIL
// endpoints return the serializer fields (currency / from_currency /
// to_currency / commission_currency) — each mapping reads its own shape and
// displays values verbatim.
const detailsFromListItem = (item, kind) => {
  const details = [{ label: 'Date', value: String(item.date ?? '') }]
  if (item.type) details.push({ label: 'Type', value: displayTransactionType(item.type) })
  const account = accountLabelOf(item)
  if (account) details.push({ label: 'Account', value: account })
  const securityName = item.security?.name
  if (securityName) details.push({ label: 'Security', value: securityName })
  if (kind === 'fx') {
    if (hasValue(item.from_amount)) {
      details.push({ label: 'From', value: `${item.from_amount}${item.from_cur ? ` ${item.from_cur}` : ''}` })
    }
    if (hasValue(item.to_amount)) {
      details.push({ label: 'To', value: `${item.to_amount}${item.to_cur ? ` ${item.to_cur}` : ''}` })
    }
    if (hasValue(item.commission)) details.push({ label: 'Commission', value: String(item.commission) })
  } else {
    if (hasValue(item.quantity)) details.push({ label: 'Quantity', value: String(item.quantity) })
    if (hasValue(item.price)) details.push({ label: 'Price', value: String(item.price) })
    if (hasValue(item.cash_flow)) {
      details.push({ label: 'Cash flow', value: `${item.cash_flow}${item.cur ? ` ${item.cur}` : ''}` })
    }
  }
  return details
}

const detailsFromDetail = (kind, detail) => {
  const details = []
  if (kind === 'fx') {
    if (hasValue(detail.from_amount)) {
      details.push({ label: 'From', value: `${detail.from_amount}${detail.from_currency ? ` ${detail.from_currency}` : ''}` })
    }
    if (hasValue(detail.to_amount)) {
      details.push({ label: 'To', value: `${detail.to_amount}${detail.to_currency ? ` ${detail.to_currency}` : ''}` })
    }
    if (hasValue(detail.commission)) {
      details.push({ label: 'Commission', value: `${detail.commission}${detail.commission_currency ? ` ${detail.commission_currency}` : ''}` })
    }
  } else {
    if (hasValue(detail.quantity)) details.push({ label: 'Quantity', value: String(detail.quantity) })
    if (hasValue(detail.price)) details.push({ label: 'Price', value: String(detail.price) })
    if (hasValue(detail.cash_flow)) {
      details.push({ label: 'Cash flow', value: `${detail.cash_flow}${detail.currency ? ` ${detail.currency}` : ''}` })
    }
  }
  return details
}

const processDeleteTransaction = (item) => {
  const kind = item.transaction_type === 'fx' ? 'fx' : 'regular'
  const numericId = extractTransactionId(item.id)
  deleteGeneration += 1
  const generation = deleteGeneration
  deleteSnapshot.value = { kind, numericId }
  deleteSubject.value = {
    title: 'Delete transaction',
    confirmLabel: 'Delete transaction',
    details: detailsFromListItem(item, kind),
  }
  deleteError.value = null
  deleteBusy.value = false
  detailsFailed.value = false

  // List rows already carry amount fields for most transactions; only load
  // the existing detail endpoint when they genuinely lack them.
  const needsDetail = kind === 'fx'
    ? ![item.from_amount, item.to_amount, item.commission].some(hasValue)
    : !hasValue(item.cash_flow)
  detailsPending.value = needsDetail
  deleteDialog.value = true

  if (!needsDetail) return
  const loader = kind === 'fx' ? getFXTransactionDetails : getTransactionDetails
  loader(numericId)
    .then((detail) => {
      if (generation !== deleteGeneration || !deleteDialog.value) return
      const extra = detailsFromDetail(kind, detail)
      if (extra.length) {
        deleteSubject.value = { ...deleteSubject.value, details: [...deleteSubject.value.details, ...extra] }
      }
      detailsPending.value = false
    })
    .catch((error) => {
      if (generation !== deleteGeneration || !deleteDialog.value) return
      logger.error('Unknown', 'Error loading transaction details for deletion:', error)
      detailsPending.value = false
      detailsFailed.value = true
      deleteError.value = 'Could not load the transaction details, so deletion is disabled. Cancel and try again.'
    })
}

const closeDeleteDialog = () => {
  // Bumping the generation invalidates any in-flight detail reply. The
  // subject object is kept (not nulled): the closing overlay keeps
  // rendering briefly and a null subject would crash its template; the
  // snapshot below is what gates deletion.
  deleteGeneration += 1
  deleteDialog.value = false
  deleteSnapshot.value = null
  deleteError.value = null
  detailsPending.value = false
  detailsFailed.value = false
}

const onConfirmDialogChange = (value) => {
  if (!value) closeDeleteDialog()
}

const deleteTransactionConfirm = async () => {
  const snapshot = deleteSnapshot.value
  if (!snapshot || deleteBusy.value || detailsPending.value || detailsFailed.value) return
  // Delayed outcomes must land only on the dialog/session that issued them.
  const generation = deleteGeneration
  const epoch = authStore.sessionEpoch
  const isStale = () => generation !== deleteGeneration || epoch !== authStore.sessionEpoch
  deleteBusy.value = true
  deleteError.value = null
  try {
    if (snapshot.kind === 'fx') {
      await deleteFXTransaction(snapshot.numericId)
    } else {
      await deleteTransaction(snapshot.numericId)
    }
    if (isStale()) return
    closeDeleteDialog()
    await fetchTransactions()
  } catch (error) {
    if (isStale()) return
    logger.error('Unknown', 'Error deleting transaction:', error)
    handleApiError(error)
    deleteError.value = 'The transaction could not be deleted. Please try again.'
  } finally {
    deleteBusy.value = false
  }
}

// The dialog returns focus to the invoking row button; if that row was just
// deleted, fall back to the page's primary action.
watch(deleteDialog, async (open) => {
  if (open) return
  await nextTick()
  if (!document.activeElement || document.activeElement === document.body) {
    document.querySelector('[data-action="add-transaction"]')?.focus()
  }
})

// A session change invalidates any open confirmation and its pending replies.
watch(() => authStore.sessionEpoch, () => {
  if (deleteDialog.value) closeDeleteDialog()
})

const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)
const effectiveCurrentDate = computed(() => appStore.effectiveCurrentDate)

const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)

const headers = computed(() => [
  { title: '', key: 'actions', align: 'center', sortable: false },
  { title: 'Date', key: 'date', align: 'start', sortable: true },
  {
    title: 'Transaction',
    key: 'transaction',
    align: 'start',
    sortable: false,
  },
  { title: 'Type', key: 'type', align: 'center', sortable: false },
  {
    title: 'Cash flow',
    key: 'cash_flow',
    align: 'center',
    sortable: false,
    children: currencies.value.map((currency) => ({
      title: currency,
      key: `cash_flow_${currency}`,
      align: 'center',
      sortable: false,
    })),
  },
  { title: '', key: 'spacer', align: 'center', sortable: false },
  {
    title: 'Balance',
    key: 'balance',
    align: 'center',
    sortable: false,
    children: currencies.value.map((currency) => ({
      title: currency,
      key: `balance_${currency}`,
      align: 'center',
      sortable: false,
    })),
  },
  { title: 'Actions', align: 'end', key: 'actions', sortable: false },
])

watch(
  [
    initialized,
    () => context.canRead,
    () => appStore.dataRefreshTrigger,
    dateFrom,
    dateTo,
    itemsPerPage,
    currentPage,
    sortBy,
    search,
  ],
  () => {
    if (initialized.value && context.canRead && dateTo.value) fetchTransactions()
  },
  { deep: true }
)

watch(effectiveCurrentDate, (date) => {
  if (initialized.value) syncRelativeDate(date)
})

const openAddTransactionDialog = () => {
  editedTransaction.value = null
  showTransactionDialog.value = true
}

const openAddFXTransactionDialog = () => {
  editedTransaction.value = null
  showFXTransactionDialog.value = true
}

// WorkspaceActions emits exact ids; each maps to the existing handler and
// its lazy dialog/completion payload, keeping all five flows reachable.
const handleWorkspaceAction = (id) => {
  switch (id) {
    case 'add-transaction': return openAddTransactionDialog()
    case 'import-transactions': return openImportDialog()
    case 'add-fx-transaction': return openAddFXTransactionDialog()
    case 'transfer-asset': return openTransferDialog()
    case 'record-merger': return (showMergerDialog.value = true)
    default: logger.error('Unknown', `Unknown workspace action: ${id}`)
  }
}

const handleQueryIntent = (patch) => {
  if (typeof patch.search === 'string') search.value = patch.search
  if (typeof patch.itemsPerPage === 'number') itemsPerPage.value = patch.itemsPerPage
  if (typeof patch.page === 'number') currentPage.value = patch.page
}

const extractTransactionId = (prefixedId) => {
  // Extract the actual database ID from prefixed format (e.g., "regular_5" -> "5")
  if (prefixedId.startsWith('regular_')) {
    return prefixedId.replace('regular_', '')
  } else if (prefixedId.startsWith('fx_')) {
    return prefixedId.replace('fx_', '')
  }
  return prefixedId // fallback for backwards compatibility
}

const editTransaction = async (item) => {
  logger.log('Unknown', 'Editing item:', item)
  try {
    const actualId = extractTransactionId(item.id)
    let transactionDetails
    if (item.transaction_type === 'regular') {
      transactionDetails = await getTransactionDetails(actualId)
    } else if (item.transaction_type === 'fx') {
      transactionDetails = await getFXTransactionDetails(actualId)
    }
    editedTransaction.value = {
      ...transactionDetails,
      transaction_type: item.transaction_type,
    }
    logger.log(
      'Unknown',
      'Transaction fetched for editing:',
      editedTransaction.value
    )
    if (item.transaction_type === 'regular') {
      showTransactionDialog.value = true
    } else if (item.transaction_type === 'fx') {
      showFXTransactionDialog.value = true
    }
  } catch (error) {
    handleApiError(error)
  }
}

const openImportDialog = () => {
  showImportDialog.value = true
}

const handleImportCompleted = async (importResults) => {
  logger.log(
    'Unknown',
    '[TransactionsPage] Import completed:',
    importResults
  )
  await fetchTransactions()
}

const openTransferDialog = () => {
  showTransferDialog.value = true
}

const handleTransferCompleted = async () => {
  logger.log('Unknown', '[TransactionsPage] Transfer completed')
  await fetchTransactions()
}

const onMergerCreated = (mergerResult) => {
  logger.log('Unknown', '[TransactionsPage] Merger created:', mergerResult)
  fetchTransactions()
}

onMounted(async () => {
  emit('update-page-title', 'Transactions')
  if (!effectiveCurrentDate.value) {
    await appStore.fetchEffectiveCurrentDate()
  }
  syncRelativeDate(effectiveCurrentDate.value)
  initialized.value = true
})

onUnmounted(() => {
  emit('update-page-title', '')
})
</script>
