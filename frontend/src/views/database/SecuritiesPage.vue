<template>
  <div>
    <v-alert v-if="tableQuery.error.value" type="error" class="mb-4">
      Unable to load this table. The displayed rows may be from the previous request.
      <v-btn data-testid="table-retry" variant="text" color="white" :disabled="!context.canRead" @click="fetchSecurities">Retry</v-btn>
    </v-alert>

    <WorkspaceSection
      heading-id="securities-section"
      title="Securities"
      description="The security catalog: identifiers, types, current values and detail pages."
    >
      <template #actions>
        <div class="d-flex flex-wrap align-center ga-2">
          <v-btn
            color="primary"
            prepend-icon="mdi-plus"
            data-testid="add-security"
            @click="addSecurity"
          >
            Add Security
          </v-btn>
          <v-btn
            color="secondary"
            variant="tonal"
            prepend-icon="mdi-swap-horizontal"
            data-testid="record-merger"
            @click="showMergerDialog = true"
          >
            Record Merger
          </v-btn>
          <MergerDialog v-if="showMergerDialogMounted" v-model="showMergerDialog" @created="onMergerCreated" />
        </div>
      </template>

      <WorkspaceTableToolbar
        class="mb-2"
        :query="{ search: search, page: currentPage, itemsPerPage: itemsPerPage }"
        :search-label="'Search'"
        search-placeholder="Search securities"
        :rows-per-page-options="itemsPerPageOptions"
        @update:query="onToolbarQuery"
      />

      <v-data-table
        :headers="headers"
        :items="securities"
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
            <td
              v-for="header in headers"
              :key="header.key"
              :class="`text-${headerAlignments[header.key]}`"
            >
              <template v-if="header.key === 'actions'">
                <div class="d-flex justify-center">
                  <v-btn
                    icon="mdi-pencil"
                    variant="text"
                    size="small"
                    class="workspace-row-action"
                    :aria-label="`Edit security ${item.name}`"
                    @click="editSecurity(item)"
                  />
                  <v-btn
                    icon="mdi-delete"
                    variant="text"
                    size="small"
                    class="workspace-row-action"
                    :aria-label="`Delete security ${item.name}`"
                    @click="openDeleteDialog(item)"
                  />
                </div>
              </template>
              <template v-else-if="header.key === 'name'">
                <router-link
                  :to="{ name: 'SecurityDetail', params: { id: item.id } }"
                  class="text-primary text-decoration-none font-weight-medium"
                >
                  {{ item.name }}
                </router-link>
              </template>
              <template v-else>
                {{ item[header.key] }}
              </template>
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
              @update:model-value="handlePageChange"
            />
          </div>
        </template>
      </v-data-table>
    </WorkspaceSection>

    <SecurityFormDialog v-if="showSecurityDialogMounted"
      v-model="showSecurityDialog"
      :edit-item="editingSecurity"
      @security-added="handleSecurityAdded"
      @security-updated="handleSecurityUpdated"
    />

    <ConfirmActionDialog
      :model-value="showDeleteDialog"
      :subject="deleteSubject"
      :busy="deleteBusy"
      :error="deleteError"
      @update:model-value="closeDeleteDialog"
      @confirm="deleteSecurityConfirm"
    />
  </div>
</template>

<script setup>
import { defineAppDialog } from '@/composables/asyncDialog'
import { useFirstOpen } from '@/composables/useFirstOpen'
import { ref, computed, watch } from 'vue'
import { useAppStore } from '@/stores/app'
const SecurityFormDialog = defineAppDialog(() => import('@/components/dialogs/SecurityFormDialog.vue'))
const MergerDialog = defineAppDialog(() => import('@/components/dialogs/MergerDialog.vue'))
import {
  getSecuritiesForDatabase,
  deleteSecurity,
  getSecurityDetails,
} from '@/services/api'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotTableQuery } from '@/types/query'
import { useTableSettings } from '@/composables/useTableSettings'
import { useErrorHandler } from '@/composables/useErrorHandler'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import WorkspaceTableToolbar from '@/components/workspace/WorkspaceTableToolbar.vue'
import ConfirmActionDialog from '@/components/workspace/ConfirmActionDialog.vue'
import logger from '@/utils/logger'

const appStore = useAppStore()
const context = usePortfolioContextStore()
const showMergerDialog = ref(false)
const showMergerDialogMounted = useFirstOpen(showMergerDialog)
const tableQuery = usePortfolioRequest((params, options) => getSecuritiesForDatabase({ page: params.page, itemsPerPage: params.itemsPerPage, sortBy: params.sortBy, search: params.search }, options), snapshotTableQuery)
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

const securities = computed(() => tableQuery.data.value?.securities ?? [])
const tableLoading = tableQuery.loading

const headers = ref([
  { title: 'Type', key: 'type', align: 'start', sortable: true },
  { title: 'ISIN', key: 'ISIN', align: 'start', sortable: true },
  { title: 'Name', key: 'name', align: 'start', sortable: true },
  {
    title: 'First Investment',
    key: 'first_investment',
    align: 'center',
    sortable: true,
  },
  { title: 'Currency', key: 'currency', align: 'center', sortable: true },
  {
    title: 'Open Position',
    key: 'open_position',
    align: 'center',
    sortable: true,
  },
  {
    title: 'Current Value',
    key: 'current_value',
    align: 'center',
    sortable: true,
  },
  { title: 'Realised', key: 'realized', align: 'center', sortable: true },
  {
    title: 'Unrealised',
    key: 'unrealized',
    align: 'center',
    sortable: true,
  },
  {
    title: 'Capital Distribution',
    key: 'capital_distribution',
    align: 'center',
    sortable: true,
  },
  { title: 'IRR', key: 'irr', align: 'center', sortable: true },
  { title: 'Actions', key: 'actions', align: 'center', sortable: false },
])

const headerAlignments = computed(() => {
  const alignments = {}
  headers.value.forEach((header) => {
    alignments[header.key] = header.align || 'start'
  })
  return alignments
})

const totalItems = computed(() => tableQuery.data.value?.total_items ?? 0)
const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)
const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)

const fetchSecurities = async () => {
  await tableQuery.run({
    context: context.committed, dateFrom: null, dateTo: context.committed.effectiveCurrentDate,
    page: currentPage.value, itemsPerPage: itemsPerPage.value,
    sortBy: sortBy.value[0] || {}, search: search.value,
  })
}
const showSecurityDialog = ref(false)
const showSecurityDialogMounted = useFirstOpen(showSecurityDialog)
const editingSecurity = ref(null)

const showDeleteDialog = ref(false)
const deleteSubject = ref(null)
const deleteTargetId = ref(null)
const deleteBusy = ref(false)
const deleteError = ref(null)

const addSecurity = () => {
  editingSecurity.value = null
  showSecurityDialog.value = true
}

const editSecurity = async (item) => {
  try {
    const securityDetails = await getSecurityDetails(item.id)
    editingSecurity.value = securityDetails
    showSecurityDialog.value = true
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
    title: `Delete security ${item.name}`,
    confirmLabel: 'Delete security',
    details: [
      { label: 'Security', value: item.name },
      { label: 'Type', value: item.type ?? '—' },
      { label: 'ISIN', value: item.ISIN || '—' },
      { label: 'Currency', value: item.currency ?? '—' },
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

const deleteSecurityConfirm = async () => {
  if (deleteTargetId.value == null || deleteBusy.value) return
  deleteBusy.value = true
  deleteError.value = null
  try {
    await deleteSecurity(deleteTargetId.value)
    showDeleteDialog.value = false
    await fetchSecurities()
  } catch (error) {
    deleteError.value = handleApiError(error)
  } finally {
    deleteBusy.value = false
  }
}

const handleSecurityAdded = (newSecurity) => {
  logger.log('Unknown', 'newSecurity added:', newSecurity)
  fetchSecurities()
}

const onMergerCreated = (mergerResult) => {
  logger.log('Unknown', 'Merger created:', mergerResult)
  fetchSecurities()
}

const handleSecurityUpdated = (updatedSecurity) => {
  logger.log('Unknown', 'updatedSecurity:', updatedSecurity)
  fetchSecurities()
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
    if (context.canRead) fetchSecurities()
  },
  { deep: true, immediate: true }
)
</script>
