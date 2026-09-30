<template>
  <v-container fluid class="pa-0">
    <v-alert v-if="transactionsQuery.error.value" type="error" class="mb-4">Unable to load transactions. Change the filters or try again.</v-alert>
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64" />
    </v-overlay>

    <v-card class="mb-4">
      <v-card-text>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          class="mr-2"
          @click="openAddTransactionDialog"
        >
          Add Transaction
        </v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          class="mr-2"
          @click="openAddFXTransactionDialog"
        >
          Add FX Transaction
        </v-btn>
        <MergerDialog @created="onMergerCreated" />
        <v-btn
          color="secondary"
          prepend-icon="mdi-upload"
          @click="openImportDialog"
        >
          Import Transactions
        </v-btn>
        <v-btn
          color="info"
          prepend-icon="mdi-swap-horizontal"
          class="ml-2"
          @click="openTransferDialog"
        >
          Transfer Asset
        </v-btn>
      </v-card-text>
    </v-card>

    <v-row no-gutters>
      <v-col cols="12">
        <v-data-table
          :headers="headers"
          :items="transactions"
          :loading="tableLoading"
          :items-per-page="itemsPerPage"
          class="elevation-1 nowrap-table"
          density="compact"
          :sort-by="sortBy"
          @update:sort-by="handleSortChange"
          :server-items-length="totalItems"
          :items-length="totalItems"
          disable-sort
          item-key="id"
        >
          <template #top>
            <v-toolbar flat class="bg-grey-lighten-4 border-b px-2">
              <DateRangeSelector
                :model-value="dateRangeModel"
                @update:model-value="handleDateRangeChange"
              />
              <v-col cols="12" sm="5" md="6" lg="7" class="px-2">
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
              <v-col
                cols="12"
                sm="4"
                md="3"
                lg="2"
                class="d-flex align-center justify-end px-2"
              >
                <v-select
                  v-model="itemsPerPage"
                  :items="itemsPerPageOptions"
                  label="Rows per page"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="rows-per-page-select"
                  bg-color="white"
                />
              </v-col>
            </v-toolbar>
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

    <TransactionFormDialog
      v-model="showTransactionDialog"
      :edit-item="editedTransaction"
      @transaction-added="fetchTransactions"
      @transaction-updated="fetchTransactions"
    />

    <FXTransactionFormDialog
      v-model="showFXTransactionDialog"
      :edit-item="editedTransaction"
      @transaction-added="fetchTransactions"
      @transaction-updated="fetchTransactions"
    />

    <v-dialog v-model="deleteDialog" max-width="500px">
      <v-card>
        <v-card-title class="text-h5">Delete Transaction</v-card-title>
        <v-card-text
          >Are you sure you want to delete this transaction?</v-card-text
        >
        <v-card-actions>
          <v-spacer />
          <v-btn color="blue darken-1" text @click="closeDeleteDialog"
            >Cancel</v-btn
          >
          <v-btn color="red darken-1" text @click="deleteTransactionConfirm"
            >OK</v-btn
          >
          <v-spacer />
        </v-card-actions>
      </v-card>
    </v-dialog>

    <TransactionImportDialog
      v-model="showImportDialog"
      @import-completed="handleImportCompleted"
    />

    <AssetTransferDialog
      v-model="showTransferDialog"
      @transfer-completed="handleTransferCompleted"
    />
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
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
import TransactionFormDialog from '@/components/dialogs/TransactionFormDialog.vue'
import FXTransactionFormDialog from '@/components/dialogs/FXTransactionFormDialog.vue'
import TransactionImportDialog from '@/components/dialogs/TransactionImportDialog.vue'
import AssetTransferDialog from '@/components/dialogs/AssetTransferDialog.vue'
import MergerDialog from '@/components/dialogs/MergerDialog.vue'
import TransactionRow from '@/components/transactions/TransactionRow.vue'
import logger from '@/utils/logger'

defineOptions({ name: 'TransactionsPage' })

const emit = defineEmits(['update-page-title'])

const appStore = useAppStore()
const context = usePortfolioContextStore()
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
const showFXTransactionDialog = ref(false)
const editedTransaction = ref(null)
const deleteDialog = ref(false)
const transactionToDelete = ref(null)
const showImportDialog = ref(false)
const showTransferDialog = ref(false)

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

const processDeleteTransaction = (item) => {
  transactionToDelete.value = item
  deleteDialog.value = true
}

const closeDeleteDialog = () => {
  deleteDialog.value = false
  transactionToDelete.value = null
}

const deleteTransactionConfirm = async () => {
  if (transactionToDelete.value) {
    try {
      const actualId = extractTransactionId(transactionToDelete.value.id)
      if (transactionToDelete.value.transaction_type === 'fx') {
        await deleteFXTransaction(actualId)
      } else {
        await deleteTransaction(actualId)
      }
      await fetchTransactions()
    } catch (error) {
      handleApiError(error)
    } finally {
      closeDeleteDialog()
    }
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
