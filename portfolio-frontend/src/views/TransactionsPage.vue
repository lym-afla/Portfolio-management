<template>
  <v-container fluid class="pa-0">
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
                v-model="dateRangeModel"
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
                  @update:model-value="handleItemsPerPageChange"
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
                @update:model-value="handlePageChange"
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

<script>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useStore } from 'vuex'
import { format } from 'date-fns'
import {
  getTransactions,
  deleteTransaction,
  deleteFXTransaction,
  getTransactionDetails,
  getFXTransactionDetails,
} from '@/services/api'
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

export default {
  name: 'TransactionsPage',
  components: {
    DateRangeSelector,
    TransactionFormDialog,
    FXTransactionFormDialog,
    TransactionImportDialog,
    AssetTransferDialog,
    MergerDialog,
    TransactionRow,
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()
    const { handleApiError } = useErrorHandler()

    const {
      dateFrom,
      dateTo,
      itemsPerPage,
      currentPage,
      sortBy,
      search,
      handlePageChange,
      handleItemsPerPageChange,
      handleSortChange,
    } = useTableSettings()

    const dateRangeModel = ref({
      dateRange: 'all_time',
      dateFrom: null,
      dateTo: null,
    })

    const handleDateRangeChange = (newDateRange) => {
      dateRangeModel.value = newDateRange
      dateFrom.value = newDateRange.dateFrom
      dateTo.value = newDateRange.dateTo
      currentPage.value = 1
      fetchTransactions()
    }

    const loading = ref(false)
    const tableLoading = ref(false)
    const transactions = ref([])
    const totalItems = ref(0)
    const currencies = ref([])
    const showTransactionDialog = ref(false)
    const showFXTransactionDialog = ref(false)
    const editedTransaction = ref(null)
    const deleteDialog = ref(false)
    const transactionToDelete = ref(null)
    const showImportDialog = ref(false)
    const showTransferDialog = ref(false)

    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
    const effectiveCurrentDate = computed(
      () => store.state.effectiveCurrentDate
    )

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

    const fetchTransactions = async () => {
      tableLoading.value = true
      try {
        const response = await getTransactions(
          dateFrom.value,
          dateTo.value,
          currentPage.value,
          itemsPerPage.value,
          search.value,
          sortBy.value[0] || {}
        )
        transactions.value = response.transactions
        totalItems.value = response.total_items
        currencies.value = response.currencies || []
      } catch (error) {
        handleApiError(error)
      } finally {
        tableLoading.value = false
      }
    }

    const formatDate = (date) => {
      return format(new Date(date), 'yyyy-MM-dd')
    }

    const formatExchangeRate = (rate) => {
      // If rate is a string, parse it to a number
      const rateNum = parseFloat(rate)

      // If rate is less than 1, display as 1/x for better readability
      if (rateNum < 1 && rateNum > 0) {
        const inverted = 1 / rateNum
        return `${inverted.toFixed(4)}`
      }

      // Otherwise, display the rate as-is, rounded to 4 decimals
      return rateNum.toFixed(4)
    }

    watch(
      [
        () => store.state.dataRefreshTrigger,
        itemsPerPage,
        currentPage,
        sortBy,
        search,
      ],
      () => {
        fetchTransactions()
      },
      { deep: true }
    )

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
        await store.dispatch('fetchEffectiveCurrentDate')
      }
      fetchTransactions()
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    return {
      dateRangeModel,
      handleDateRangeChange,
      loading,
      tableLoading,
      transactions,
      totalItems,
      currentPage,
      itemsPerPage,
      itemsPerPageOptions,
      pageCount,
      sortBy,
      search,
      headers,
      currencies,
      handleItemsPerPageChange,
      handlePageChange,
      handleSortChange,
      fetchTransactions,
      formatDate,
      formatExchangeRate,
      showTransactionDialog,
      showFXTransactionDialog,
      editedTransaction,
      deleteDialog,
      transactionToDelete,
      showImportDialog,
      showTransferDialog,
      openAddTransactionDialog,
      openAddFXTransactionDialog,
      extractTransactionId,
      editTransaction,
      processDeleteTransaction,
      closeDeleteDialog,
      deleteTransactionConfirm,
      openImportDialog,
      handleImportCompleted,
      openTransferDialog,
      handleTransferCompleted,
      onMergerCreated,
    }
  },
}
</script>
