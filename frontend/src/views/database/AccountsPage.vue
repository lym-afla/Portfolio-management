<template>
  <div>
    <v-alert v-if="tableQuery.error.value" type="error" class="mb-4">
      Unable to load this table. The displayed rows may be from the previous request.
      <v-btn data-testid="table-retry" :disabled="!context.canRead" @click="fetchAccounts">Retry</v-btn>
    </v-alert>

    <WorkspaceSection
      heading-id="accounts-section"
      title="Accounts"
      description="Investment accounts per broker with cash balances by currency."
    >
      <template #actions>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          data-testid="add-account"
          @click="openAddDialog"
        >
          Add Account
        </v-btn>
      </template>

      <WorkspaceTableToolbar
        class="mb-2"
        :query="{ search: search, page: currentPage, itemsPerPage: itemsPerPage }"
        :search-label="'Search'"
        search-placeholder="Search accounts"
        :rows-per-page-options="itemsPerPageOptions"
        @update:query="onToolbarQuery"
      />

      <v-data-table
        :headers="headers"
        :items="accounts"
        :loading="tableLoading"
        :items-per-page="itemsPerPage"
        :page="currentPage"
        :server-items-length="totalItems"
        :sort-by="sortBy"
        density="compact"
        disable-sort
        class="elevation-1 nowrap-table"
        @update:sort-by="handleSortChange"
      >
        <template #item="{ item }">
          <tr>
            <td :class="`text-${headerAlignments.name}`">{{ item.name }}</td>
            <td :class="`text-${headerAlignments.broker_name}`">
              {{ item.broker_name }}
            </td>
            <td class="text-center workspace-number">
              {{ item.no_of_securities }}
            </td>
            <td :class="`text-${headerAlignments.first_investment}`">
              {{ item.first_investment }}
            </td>
            <td class="text-center workspace-number">{{ item.nav }}</td>
            <td
              v-for="currency in currencies"
              :key="`cash-${currency}`"
              class="text-center workspace-number"
            >
              {{ item.cash[currency] }}
            </td>
            <td class="text-center workspace-number">{{ item.irr }}</td>
            <td class="text-end">
              <div class="d-flex justify-end">
                <v-btn
                  icon="mdi-pencil"
                  variant="text"
                  size="small"
                  class="workspace-row-action"
                  :aria-label="`Edit account ${item.name}`"
                  @click="editAccount(item)"
                />
                <v-btn
                  icon="mdi-delete"
                  variant="text"
                  size="small"
                  class="workspace-row-action"
                  :aria-label="`Delete account ${item.name}`"
                  @click="openDeleteDialog(item)"
                />
              </div>
            </td>
          </tr>
        </template>
        <template #tfoot>
          <tfoot>
            <tr class="font-weight-bold">
              <td
                v-for="header in flattenedHeaders"
                :key="header.key"
                :class="['text-' + header.align]"
              >
                <template v-if="header.key === 'name'">TOTAL</template>
                <template
                  v-else-if="
                    ['no_of_securities', 'nav', 'irr'].includes(header.key)
                  "
                >
                  {{ totals[header.key] }}
                </template>
              </td>
            </tr>
          </tfoot>
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
    </WorkspaceSection>

    <AccountFormDialog v-if="showAccountDialogMounted"
      v-model="showAccountDialog"
      :edit-item="editingAccount"
      @account-added="handleAccountAdded"
      @account-updated="handleAccountUpdated"
    />

    <ConfirmActionDialog
      :model-value="showDeleteDialog"
      :subject="deleteSubject"
      :busy="deleteBusy"
      :error="deleteError"
      @update:model-value="closeDeleteDialog"
      @confirm="deleteAccountConfirm"
    />
  </div>
</template>

<script setup>
import { defineAppDialog } from '@/composables/asyncDialog'
import { useFirstOpen } from '@/composables/useFirstOpen'
import { ref, computed, watch } from 'vue'
import { useAppStore } from '@/stores/app'
const AccountFormDialog = defineAppDialog(() => import('@/components/dialogs/AccountFormDialog.vue'))
import {
  getAccountsTable,
  deleteAccount,
  getAccountDetails,
} from '@/services/api'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotTableQuery } from '@/types/query'
import { useTableSettings } from '@/composables/useTableSettings'
import { useErrorHandler } from '@/composables/useErrorHandler'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import WorkspaceTableToolbar from '@/components/workspace/WorkspaceTableToolbar.vue'
import ConfirmActionDialog from '@/components/workspace/ConfirmActionDialog.vue'

const appStore = useAppStore()
const context = usePortfolioContextStore()
const tableQuery = usePortfolioRequest((params, options) => getAccountsTable({ page: params.page, itemsPerPage: params.itemsPerPage, sortBy: params.sortBy, search: params.search }, options), snapshotTableQuery)
const {
  itemsPerPage,
  currentPage,
  sortBy,
  search,
  handlePageChange,
  handleItemsPerPageChange,
  handleSortChange,
} = useTableSettings()

const { handleApiError } = useErrorHandler()

const accounts = computed(() => tableQuery.data.value?.accounts ?? [])
const tableLoading = tableQuery.loading

const currencies = computed(() => [...new Set(accounts.value.flatMap((account) => Object.keys(account.cash)))])
const totalItems = computed(() => tableQuery.data.value?.total_items ?? 0)
const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)
const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)

const headers = computed(() => [
  { title: 'Name', key: 'name', align: 'start', sortable: true },
  { title: 'Broker', key: 'broker_name', align: 'center', sortable: true },
  {
    title: 'Number of securities',
    key: 'no_of_securities',
    align: 'center',
    sortable: true,
  },
  {
    title: 'First investment',
    key: 'first_investment',
    align: 'center',
    sortable: true,
  },
  { title: 'Current NAV', key: 'nav', align: 'center', sortable: true },
  {
    title: 'Cash balance',
    key: 'cash',
    align: 'center',
    sortable: false,
    children: currencies.value.map((currency) => ({
      title: currency,
      key: `cash_${currency}`,
      align: 'center',
      sortable: true,
    })),
  },
  { title: 'IRR', key: 'irr', align: 'center', sortable: true },
  { title: 'Actions', key: 'actions', align: 'end', sortable: false },
])

const headerAlignments = computed(() => {
  const alignments = {}
  headers.value.forEach((header) => {
    alignments[header.key] = header.align || 'start'
    if (header.children) {
      header.children.forEach((child) => {
        alignments[child.key] = child.align || 'start'
      })
    }
  })
  return alignments
})

const totals = computed(() => tableQuery.data.value?.totals ?? {})

const flattenedHeaders = computed(() => {
  const flattened = []
  headers.value.forEach((header) => {
    if (header.children) {
      header.children.forEach((child) => {
        flattened.push(child)
      })
    } else {
      flattened.push(header)
    }
  })
  return flattened
})

const fetchAccounts = async () => {
  await tableQuery.run({
    context: context.committed, dateFrom: null, dateTo: context.committed.effectiveCurrentDate,
    page: currentPage.value, itemsPerPage: itemsPerPage.value,
    sortBy: sortBy.value[0] || {}, search: search.value,
  })
}
const showAccountDialog = ref(false)
const showAccountDialogMounted = useFirstOpen(showAccountDialog)
const editingAccount = ref(null)

const showDeleteDialog = ref(false)
const deleteSubject = ref(null)
const deleteTargetId = ref(null)
const deleteBusy = ref(false)
const deleteError = ref(null)

const openAddDialog = () => {
  editingAccount.value = null
  showAccountDialog.value = true
}

const editAccount = async (item) => {
  try {
    const accountDetails = await getAccountDetails(item.id)
    editingAccount.value = accountDetails
    showAccountDialog.value = true
  } catch (error) {
    handleApiError(error)
  }
}

const onToolbarQuery = (patch) => {
  if ('search' in patch && patch.search !== search.value) search.value = patch.search
  if ('itemsPerPage' in patch && patch.itemsPerPage !== itemsPerPage.value) {
    handleItemsPerPageChange(patch.itemsPerPage)
  }
}

const openDeleteDialog = (item) => {
  deleteTargetId.value = item.id
  deleteSubject.value = {
    title: `Delete account ${item.name}`,
    confirmLabel: 'Delete account',
    details: [
      { label: 'Account', value: item.name },
      { label: 'Broker', value: item.broker_name ?? '—' },
      { label: 'Securities', value: String(item.no_of_securities ?? '—') },
    ],
  }
  deleteError.value = null
  showDeleteDialog.value = true
}

const closeDeleteDialog = (value) => {
  if (deleteBusy.value && value === false) return
  showDeleteDialog.value = false
  deleteError.value = null
}

const deleteAccountConfirm = async () => {
  if (deleteTargetId.value == null || deleteBusy.value) return
  deleteBusy.value = true
  deleteError.value = null
  try {
    await deleteAccount(deleteTargetId.value)
    showDeleteDialog.value = false
    await fetchAccounts()
  } catch (error) {
    deleteError.value = handleApiError(error)
  } finally {
    deleteBusy.value = false
  }
}

const handleAccountAdded = () => {
  fetchAccounts()
}

const handleAccountUpdated = () => {
  fetchAccounts()
}

watch(
  [
    () => context.canRead,
    () => appStore.dataRefreshTrigger,
    search,
    itemsPerPage,
    currentPage,
    sortBy,
  ],
  () => {
    if (context.canRead) fetchAccounts()
  },
  { deep: true, immediate: true }
)
</script>
