<template>
  <div>
    <v-alert v-if="tableQuery.error.value" type="error" class="mb-4">
      Unable to load this table. The displayed rows may be from the previous request.
      <v-btn data-testid="table-retry" variant="text" color="white" :disabled="!context.canRead" @click="fetchBrokers">Retry</v-btn>
    </v-alert>

    <WorkspaceSection
      heading-id="brokers-section"
      title="Brokers"
      description="Brokers you invest through, with portfolio totals per broker."
    >
      <template #actions>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          data-testid="add-broker"
          @click="openAddDialog"
        >
          Add Broker
        </v-btn>
      </template>

      <WorkspaceTableToolbar
        class="mb-2"
        :query="{ search: search, page: currentPage, itemsPerPage: itemsPerPage }"
        :search-label="'Search'"
        search-placeholder="Search brokers"
        :rows-per-page-options="itemsPerPageOptions"
        @update:query="onToolbarQuery"
      />

      <v-data-table
        :headers="headers"
        :items="brokers"
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
            <td :class="`text-${headerAlignments.country}`">
              {{ item.country }}
            </td>
            <td class="text-center workspace-number">
              {{ item.no_of_accounts }}
            </td>
            <td class="text-center workspace-number">
              {{ item.no_of_securities }}
            </td>
            <td :class="`text-${headerAlignments.first_investment}`">
              {{ item.first_investment }}
            </td>
            <td class="text-center workspace-number">{{ item.nav }}</td>
            <td class="text-center workspace-number">{{ item.cash }}</td>
            <td class="text-center workspace-number">{{ item.irr }}</td>
            <td class="text-end">
              <div class="d-flex justify-end">
                <v-btn
                  icon="mdi-pencil"
                  variant="text"
                  size="small"
                  class="workspace-row-action"
                  :aria-label="`Edit broker ${item.name}`"
                  @click="editBroker(item)"
                />
                <v-btn
                  icon="mdi-delete"
                  variant="text"
                  size="small"
                  class="workspace-row-action"
                  :aria-label="`Delete broker ${item.name}`"
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
                v-for="header in headers"
                :key="header.key"
                :class="['text-' + header.align]"
              >
                <template v-if="header.key === 'name'">TOTAL</template>
                <template
                  v-else-if="
                    [
                      'no_of_accounts',
                      'no_of_securities',
                      'nav',
                      'cash',
                      'irr',
                    ].includes(header.key)
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

    <BrokerFormDialog v-if="showBrokerDialogMounted"
      v-model="showBrokerDialog"
      :edit-item="editingBroker"
      @broker-added="handleBrokerAdded"
      @broker-updated="handleBrokerUpdated"
    />

    <ConfirmActionDialog
      :model-value="showDeleteDialog"
      :subject="deleteSubject"
      :busy="deleteBusy"
      :error="deleteError"
      @update:model-value="closeDeleteDialog"
      @confirm="deleteBrokerConfirm"
    />
  </div>
</template>

<script setup>
import { defineAppDialog } from '@/composables/asyncDialog'
import { useFirstOpen } from '@/composables/useFirstOpen'
import { ref, watch, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { getBrokersTable, deleteBroker } from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotTableQuery } from '@/types/query'
import { useTableSettings } from '@/composables/useTableSettings'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import WorkspaceTableToolbar from '@/components/workspace/WorkspaceTableToolbar.vue'
import ConfirmActionDialog from '@/components/workspace/ConfirmActionDialog.vue'
const BrokerFormDialog = defineAppDialog(() => import('@/components/dialogs/BrokerFormDialog.vue'))

const appStore = useAppStore()
const context = usePortfolioContextStore()
const tableQuery = usePortfolioRequest((params, options) => getBrokersTable({ page: params.page, itemsPerPage: params.itemsPerPage, sortBy: params.sortBy, search: params.search }, options), snapshotTableQuery)
const { handleApiError } = useErrorHandler()

const {
  itemsPerPage,
  currentPage,
  sortBy,
  search,
  handlePageChange,
  handleItemsPerPageChange,
  handleSortChange,
} = useTableSettings()

const tableLoading = tableQuery.loading
const brokers = computed(() => tableQuery.data.value?.items ?? [])
const totalItems = computed(() => tableQuery.data.value?.total_items ?? 0)
const showBrokerDialog = ref(false)
const showBrokerDialogMounted = useFirstOpen(showBrokerDialog)
const editingBroker = ref(null)
const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)
const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)
const totals = computed(() => tableQuery.data.value?.totals ?? {})

const showDeleteDialog = ref(false)
const deleteSubject = ref(null)
const deleteTargetId = ref(null)
const deleteBusy = ref(false)
const deleteError = ref(null)

const headers = [
  { title: 'Name', key: 'name', align: 'start', sortable: true },
  { title: 'Country', key: 'country', align: 'center', sortable: true },
  {
    title: 'Accounts',
    key: 'no_of_accounts',
    align: 'center',
    sortable: true,
  },
  {
    title: 'Securities',
    key: 'no_of_securities',
    align: 'center',
    sortable: true,
  },
  {
    title: 'First Investment',
    key: 'first_investment',
    align: 'center',
    sortable: true,
  },
  { title: 'Total NAV', key: 'nav', align: 'center', sortable: true },
  { title: 'Cash', key: 'cash', align: 'center', sortable: true },
  { title: 'IRR', key: 'irr', align: 'center', sortable: true },
  { title: 'Actions', key: 'actions', align: 'end', sortable: false },
]

const headerAlignments = computed(() => {
  const alignments = {}
  headers.forEach((header) => {
    alignments[header.key] = header.align || 'start'
  })
  return alignments
})

const onToolbarQuery = (patch) => {
  if ('search' in patch && patch.search !== search.value) search.value = patch.search
  if ('itemsPerPage' in patch && patch.itemsPerPage !== itemsPerPage.value) {
    handleItemsPerPageChange(patch.itemsPerPage)
  }
}

const fetchBrokers = async () => {
  await tableQuery.run({
    context: context.committed, dateFrom: null, dateTo: context.committed.effectiveCurrentDate,
    page: currentPage.value, itemsPerPage: itemsPerPage.value,
    sortBy: sortBy.value[0] || {}, search: search.value,
  })
}
const openAddDialog = () => {
  editingBroker.value = null
  showBrokerDialog.value = true
}

const editBroker = (item) => {
  editingBroker.value = item
  showBrokerDialog.value = true
}

const openDeleteDialog = (item) => {
  deleteTargetId.value = item.id
  deleteSubject.value = {
    title: `Delete broker ${item.name}`,
    confirmLabel: 'Delete broker',
    details: [
      { label: 'Broker', value: item.name },
      { label: 'Country', value: item.country ?? '—' },
      { label: 'Accounts', value: String(item.no_of_accounts ?? '—') },
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

const deleteBrokerConfirm = async () => {
  if (deleteTargetId.value == null || deleteBusy.value) return
  deleteBusy.value = true
  deleteError.value = null
  try {
    await deleteBroker(deleteTargetId.value)
    showDeleteDialog.value = false
    await fetchBrokers()
  } catch (error) {
    deleteError.value = handleApiError(error)
  } finally {
    deleteBusy.value = false
  }
}

const handleBrokerAdded = () => {
  fetchBrokers()
}

const handleBrokerUpdated = () => {
  fetchBrokers()
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
    if (context.canRead) fetchBrokers()
  },
  { deep: true, immediate: true }
)
</script>

<style scoped>
.nowrap-table :deep(td) {
  white-space: nowrap;
}
</style>
