<template>
  <div>
    <v-alert v-if="pricesQuery.error.value || securitiesQuery.error.value || assetTypesQuery.error.value || accountsQuery.error.value" type="error" class="mb-4">
      Unable to load prices or filters. The displayed data may be from the previous request.
      <v-btn data-testid="prices-retry" :disabled="!context.canRead" @click="retryFailedResources">Retry</v-btn>
    </v-alert>
    <WorkspaceSection
      heading-id="prices-section"
      title="Prices"
      description="Price history per security and date; each pair is quoted in the security's trading currency."
    >
      <template #actions>
        <WorkspaceActions
          :primary="{ id: 'add-price', label: 'Add Price Entry', icon: 'mdi-plus' }"
          :secondary="[{ id: 'import-prices', label: 'Import Prices', icon: 'mdi-upload' }]"
          :overflow="[{ id: 'add-security', label: 'Add Security', icon: 'mdi-plus' }]"
          @action="handleWorkspaceAction"
        />
      </template>

      <section aria-label="Price filters" class="mb-4">
        <v-row>
          <v-col cols="12" md="4">
            <v-autocomplete
              v-model="selectedAssetTypes"
              :items="assetTypes"
              label="Asset Types"
              item-title="text"
              item-value="value"
              multiple
              clearable
            >
              <template v-slot:prepend-item>
                <v-list-item
                  title="Select All"
                  @click="toggleSelectAllAssetTypes"
                >
                  <template v-slot:prepend>
                    <v-checkbox-btn
                      :model-value="assetTypesAllSelected"
                      :indeterminate="assetTypesIndeterminate"
                    />
                  </template>
                </v-list-item>
                <v-divider class="mt-2" />
              </template>
              <template v-slot:selection="{ item, index }">
                <v-chip v-if="index < 3">
                  <span>{{ item.title }}</span>
                </v-chip>
                <span
                  v-if="index === 3"
                  class="text-grey text-caption align-self-center"
                >
                  (+{{ selectedAssetTypes.length - 3 }} others)
                </span>
              </template>
            </v-autocomplete>
          </v-col>
          <v-col cols="12" md="4">
            <v-autocomplete
              v-model="selectedAccount"
              :items="accounts"
              label="Accounts"
              item-title="name"
              item-value="id"
              clearable
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-autocomplete
              v-model="selectedSecurities"
              :items="securities"
              label="Securities"
              item-title="name"
              item-value="id"
              multiple
              clearable
            >
              <template v-slot:prepend-item>
                <v-list-item
                  title="Select All"
                  @click="toggleSelectAllSecurities"
                >
                  <template v-slot:prepend>
                    <v-checkbox-btn
                      :model-value="securitiesAllSelected"
                      :indeterminate="securitiesIndeterminate"
                    />
                  </template>
                </v-list-item>
                <v-divider class="mt-2" />
              </template>
              <template v-slot:selection="{ item, index }">
                <v-chip v-if="index < 1">
                  <span>{{ item.title }}</span>
                </v-chip>
                <span
                  v-if="index === 1"
                  class="text-grey text-caption align-self-center"
                >
                  (+{{ selectedSecurities.length - 1 }} others)
                </span>
              </template>
            </v-autocomplete>
          </v-col>
        </v-row>
        <v-row class="mt-n6">
          <v-col cols="12" md="4">
            <v-text-field v-model="dateFrom" label="Start Date" type="date" />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="dateTo" label="End Date" type="date" />
          </v-col>
          <v-col cols="12" md="4" class="d-flex align-center">
            <v-btn color="primary" variant="tonal" @click="applyFilters" block>
              Apply Filters
            </v-btn>
          </v-col>
        </v-row>
      </section>

      <v-data-table
        :headers="headers"
        :items="priceData"
        :loading="tableLoading"
        :items-per-page="itemsPerPage"
        :page="currentPage"
        :items-per-page-options="itemsPerPageOptions"
        :server-items-length="totalItems"
        :sort-by="sortBy"
        @update:sort-by="handleSortChange"
        disable-sort
        no-data-text="Use 'Apply Filters' to update table"
      >
        <template #[`item.security__name`]="{ item }">
          <router-link
            :to="{ name: 'SecurityDetail', params: { id: item.security__id } }"
            class="text-primary text-decoration-none font-weight-medium"
          >
            {{ item.security__name }}
          </router-link>
        </template>
        <template #[`item.price`]="{ item }">
          <span class="editable" @click="editPrice(item)">{{
            item.price
          }}</span>
        </template>
        <template #[`item.actions`]="{ item }">
          <div class="d-flex justify-end">
            <v-btn
              icon="mdi-pencil"
              variant="text"
              size="small"
              class="workspace-row-action"
              :aria-label="`Edit price for ${item.security__name} on ${item.date}`"
              @click="editPrice(item)"
            />
            <v-btn
              icon="mdi-delete"
              variant="text"
              size="small"
              class="workspace-row-action"
              :aria-label="`Delete price for ${item.security__name} on ${item.date}`"
              @click="openDeleteDialog(item)"
            />
          </div>
        </template>
        <template v-slot:bottom>
          <v-row align="center" class="pa-4">
            <v-col cols="12" sm="4">
              <v-select
                v-model="itemsPerPage"
                :items="itemsPerPageOptions"
                label="Rows per page"
                density="compact"
                variant="outlined"
                @update:model-value="handleItemsPerPageChange"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="4" class="text-center">
              <span class="text-caption">
                Showing {{ (currentPage - 1) * itemsPerPage + 1 }} -
                {{ Math.min(currentPage * itemsPerPage, totalItems) }} of
                {{ totalItems }}
              </span>
            </v-col>
            <v-col cols="12" sm="4">
              <v-pagination
                v-model="currentPage"
                :length="pageCount"
                rounded="circle"
                :total-visible="7"
                @update:model-value="handlePageChange"
              />
            </v-col>
          </v-row>
        </template>
      </v-data-table>
    </WorkspaceSection>

    <ConfirmActionDialog
      :model-value="deleteDialog"
      :subject="deleteSubject"
      :busy="isDeleting"
      :error="deleteError"
      @update:model-value="onConfirmDialogChange"
      @confirm="confirmDelete"
    />

    <PriceFormDialog v-if="showPriceDialogMounted"
      v-model="showPriceDialog"
      :edit-item="editingPrice"
      :securities="securities"
      @price-added="handlePriceAdded"
      @price-updated="handlePriceUpdated"
    />

    <SecurityFormDialog v-if="showSecurityDialogMounted" v-model="showSecurityDialog" :edit-item="null" />

    <PriceImportDialog v-if="showImportDialogMounted"
      v-model="showImportDialog"
      @prices-imported="handlePricesImported"
    />
  </div>
</template>

<script setup>
import { defineAppDialog } from '@/composables/asyncDialog'
import { useFirstOpen } from '@/composables/useFirstOpen'
import { ref, watch, computed, onScopeDispose, inject } from 'vue'
import { useAppStore } from '@/stores/app'
import {
  getAssetTypes,
  getAccounts,
  getSecurities,
  getPrices,
  deletePrice,
  getPriceDetails,
} from '@/services/api'
import debounce from 'lodash/debounce'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { usePortfolioRequest } from '@/composables/usePortfolioRequest'
import { snapshotContext, snapshotTableQuery } from '@/types/query'
import { useTableSettings } from '@/composables/useTableSettings'
import WorkspaceSection from '@/components/workspace/WorkspaceSection.vue'
import WorkspaceActions from '@/components/workspace/WorkspaceActions.vue'
import ConfirmActionDialog from '@/components/workspace/ConfirmActionDialog.vue'
const PriceFormDialog = defineAppDialog(() => import('@/components/dialogs/PriceFormDialog.vue'))
const SecurityFormDialog = defineAppDialog(() => import('@/components/dialogs/SecurityFormDialog.vue'))
const PriceImportDialog = defineAppDialog(() => import('@/components/dialogs/PriceImportDialog.vue'))
import logger from '@/utils/logger'

const appStore = useAppStore()
const context = usePortfolioContextStore()
const {
  dateFrom,
  dateTo,
  itemsPerPage,
  currentPage,
  sortBy,
  handlePageChange,
  handleItemsPerPageChange,
  handleSortChange,
} = useTableSettings()

const assetTypes = computed(() => assetTypesQuery.data.value ?? [])
const accounts = computed(() => accountsQuery.data.value ?? [])
const securities = computed(() => securitiesQuery.data.value ?? [])
const selectedAssetTypes = ref([])
const selectedAccount = ref(null)
const selectedSecurities = ref([])
const priceData = computed(() => pricesQuery.data.value?.prices ?? [])
const tableLoading = computed(() => pricesQuery.loading.value)
const totalItems = computed(() => pricesQuery.data.value?.total_items ?? 0)
const deleteDialog = ref(false)
const deletedItem = ref({})
const deleteTargetId = ref(null)
const deleteSubject = ref(null)
const deleteError = ref(null)
const editingPrice = ref(null)
const showPriceDialog = ref(false)
const showPriceDialogMounted = useFirstOpen(showPriceDialog)
const showSecurityDialog = ref(false)
const showSecurityDialogMounted = useFirstOpen(showSecurityDialog)
const showImportDialog = ref(false)
const showImportDialogMounted = useFirstOpen(showImportDialog)
const isDeleting = ref(false)
const showError = inject('showError')

const itemsPerPageOptions = computed(() => appStore.itemsPerPageOptions)
const pageCount = computed(() =>
  Math.ceil(totalItems.value / itemsPerPage.value)
)

const headers = [
  { title: 'Date', key: 'date' },
  { title: 'Security', key: 'security__name', align: 'center' },
  { title: 'Asset Type', key: 'security__type', align: 'center' },
  { title: 'Currency', key: 'security__currency', align: 'center' },
  { title: 'Price', key: 'price' },
  { title: 'Actions', key: 'actions', sortable: false, align: 'end' },
]

const assetTypesAllSelected = computed(() => {
  return selectedAssetTypes.value.length === assetTypes.value.length
})

const assetTypesIndeterminate = computed(() => {
  return selectedAssetTypes.value.length > 0 && !assetTypesAllSelected.value
})

const securitiesAllSelected = computed(() => {
  return selectedSecurities.value.length === securities.value.length
})

const securitiesIndeterminate = computed(() => {
  return selectedSecurities.value.length > 0 && !securitiesAllSelected.value
})

const toggleSelectAllAssetTypes = () => {
  if (assetTypesAllSelected.value) {
    selectedAssetTypes.value = []
  } else {
    selectedAssetTypes.value = assetTypes.value.map((item) => item.value)
  }
}

const toggleSelectAllSecurities = () => {
  if (securitiesAllSelected.value) {
    selectedSecurities.value = []
  } else {
    selectedSecurities.value = securities.value.map((item) => item.id)
  }
}

const assetTypesQuery = usePortfolioRequest((_params, options) => getAssetTypes(options), snapshotContext)
const accountsQuery = usePortfolioRequest((_params, options) => getAccounts(options), snapshotContext)
const securitiesQuery = usePortfolioRequest((params, options) => getSecurities(params.assetTypes, params.account, options),
  (params) => Object.freeze({ ...params, context: snapshotContext(params.context), assetTypes: Object.freeze([...params.assetTypes]) }))
const pricesQuery = usePortfolioRequest((params, options) => getPrices({
  assetTypes: params.assetTypes, account: params.account, securities: params.securities,
  startDate: params.dateFrom, endDate: params.dateTo,
  page: params.page, itemsPerPage: params.itemsPerPage, sortBy: params.sortBy,
}, options), (params) => Object.freeze({
  ...snapshotTableQuery(params), assetTypes: Object.freeze([...params.assetTypes]), securities: Object.freeze([...params.securities]),
}))
const appliedFilters = ref({ assetTypes: [], account: null, securities: [] })
const fetchSecurities = debounce(() => securitiesQuery.run({
  context: context.committed, assetTypes: selectedAssetTypes.value, account: selectedAccount.value,
}), 300)
onScopeDispose(() => fetchSecurities.cancel())
watch([selectedAssetTypes, selectedAccount], () => {
  securitiesQuery.invalidate()
  fetchSecurities()
}, { flush: 'sync', deep: true })
watch(securitiesQuery.data, (available) => {
  if (!available) return
  selectedSecurities.value = selectedAccount.value
    ? available.map((item) => item.id)
    : selectedSecurities.value.filter((id) => available.some((item) => item.id === id))
}, { flush: 'sync' })
watch([() => context.canRead, () => appStore.dataRefreshTrigger], () => {
  fetchSecurities.cancel()
  if (!context.canRead) return
  assetTypesQuery.run(context.committed)
  accountsQuery.run(context.committed)
  securitiesQuery.run({ context: context.committed, assetTypes: selectedAssetTypes.value, account: selectedAccount.value })
}, { immediate: true })
const fetchPriceData = () => pricesQuery.run({
  context: context.committed, ...appliedFilters.value,
  dateFrom: dateFrom.value, dateTo: dateTo.value,
  page: currentPage.value, itemsPerPage: itemsPerPage.value,
  sortBy: sortBy.value[0] || {}, search: '',
})
const applyFilters = () => {
  appliedFilters.value = { assetTypes: [...selectedAssetTypes.value], account: selectedAccount.value, securities: [...selectedSecurities.value] }
  currentPage.value = 1
}
const retryFailedResources = () => {
  if (!context.canRead) return
  if (pricesQuery.error.value) fetchPriceData()
  if (assetTypesQuery.error.value) assetTypesQuery.run(context.committed)
  if (accountsQuery.error.value) accountsQuery.run(context.committed)
  if (securitiesQuery.error.value) securitiesQuery.run({ context: context.committed, assetTypes: selectedAssetTypes.value, account: selectedAccount.value })
}
// Presentation-only action hierarchy: the existing openers stay authoritative.
const handleWorkspaceAction = (id) => {
  if (id === 'add-price') openAddPriceDialog()
  else if (id === 'import-prices') openImportDialog()
  else if (id === 'add-security') addSecurity()
}

const openImportDialog = () => {
  showImportDialog.value = true
}

const handlePricesImported = (summary) => {
  logger.log('PricesPage', 'Prices imported:', summary)
  // Refresh your price data here
  fetchPriceData()
}

const editPrice = async (item) => {
  try {
    const priceDetails = await getPriceDetails(item.id)
    editingPrice.value = priceDetails
    showPriceDialog.value = true
  } catch (error) {
    showError(`Failed to fetch price details: ${error.message}`)
  }
}

const openDeleteDialog = (item) => {
  deletedItem.value = item
  deleteTargetId.value = item.id
  deleteSubject.value = {
    title: `Delete price for ${item.security__name} on ${item.date}`,
    confirmLabel: 'Delete price',
    details: [
      { label: 'Date', value: item.date ?? '—' },
      { label: 'Security', value: item.security__name ?? '—' },
      { label: 'Price', value: `${item.price ?? '—'} ${item.security__currency ?? ''}`.trim() },
    ],
  }
  deleteError.value = null
  deleteDialog.value = true
}

const onConfirmDialogChange = (value) => {
  if (isDeleting.value && value === false) return
  deleteDialog.value = false
  deleteError.value = null
}

const confirmDelete = async () => {
  if (deleteTargetId.value == null || isDeleting.value) return
  isDeleting.value = true
  deleteError.value = null
  try {
    await deletePrice(deleteTargetId.value)
    deleteDialog.value = false
    await fetchPriceData()
  } catch (error) {
    const errorMessage =
      error.response?.data?.message || error.message || 'Unknown error'
    deleteError.value = `Failed to delete price: ${errorMessage}`
    showError(`Failed to delete price: ${errorMessage}`)
  } finally {
    isDeleting.value = false
  }
}

const handlePriceUpdated = () => {
  fetchPriceData()
}

const openAddPriceDialog = () => {
  editingPrice.value = null
  showPriceDialog.value = true
}

const handlePriceAdded = (newPrice) => {
  logger.log('PricesPage', 'New price added:', newPrice)
  fetchPriceData()
}

const addSecurity = () => {
  showSecurityDialog.value = true
}

watch([() => context.canRead, () => appStore.dataRefreshTrigger, appliedFilters,
  dateFrom, dateTo, itemsPerPage, currentPage, sortBy], () => {
  if (context.canRead && dateTo.value) fetchPriceData()
}, { deep: true, immediate: true })

</script>
