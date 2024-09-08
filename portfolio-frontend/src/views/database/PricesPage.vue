<template>
  <div>
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
    </v-overlay>

    <v-card class="mb-4">
      <v-card-text class="pa-4">
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
                    ></v-checkbox-btn>
                  </template>
                </v-list-item>
                <v-divider class="mt-2"></v-divider>
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
              v-model="selectedBroker"
              :items="brokers"
              label="Brokers"
              item-title="name"
              item-value="id"
              clearable
            ></v-autocomplete>
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
                    ></v-checkbox-btn>
                  </template>
                </v-list-item>
                <v-divider class="mt-2"></v-divider>
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
            <v-text-field
              v-model="dateFrom"
              label="Start Date"
              type="date"
            ></v-text-field>
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="dateTo"
              label="End Date"
              type="date"
            ></v-text-field>
          </v-col>
          <v-col cols="12" md="4" class="d-flex align-center">
            <v-btn color="primary" @click="applyFilters" block>
              Apply Filters
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="mb-4">
      <v-card-text>
        <v-row align="center" justify="space-between">
          <v-col cols="auto">
            <v-row>
              <v-col cols="auto">
                <v-btn color="primary" @click="addSecurity">
                  <v-icon left>mdi-plus</v-icon>
                  Add Security
                </v-btn>
              </v-col>
              <v-col cols="auto">
                <v-btn color="primary" @click="openAddPriceDialog">
                  <v-icon left>mdi-plus</v-icon>
                  Add Price Entry
                </v-btn>
              </v-col>
            </v-row>
          </v-col>
          <v-col cols="auto">
            <v-btn color="success" @click="openImportDialog">
              Import Prices
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="mb-4">
      <v-card-text>
        <PriceChart v-if="priceData.length > 0" :prices="priceData" />
        <p v-else>No price data available. Please apply filters.</p>
      </v-card-text>
    </v-card>

    <v-card>
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
        <template #[`item.price`]="{ item }">
          <span class="editable" @click="editPrice(item)">{{ item.price }}</span>
        </template>
        <template #[`item.actions`]="{ item }">
          <v-icon small class="mr-2" @click="editPrice(item)">
            mdi-pencil
          </v-icon>
          <v-icon small @click="openDeleteDialog(item)">
            mdi-delete
          </v-icon>
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
              ></v-select>
            </v-col>
            <v-col cols="12" sm="4" class="text-center">
              <span class="text-caption">
                Showing {{ ((currentPage - 1) * itemsPerPage) + 1 }} - {{ Math.min(currentPage * itemsPerPage, totalItems) }} of {{ totalItems }}
              </span>
            </v-col>
            <v-col cols="12" sm="4">
              <v-pagination
                v-model="currentPage"
                :length="pageCount"
                rounded="circle"
                :total-visible="7"
                @update:model-value="handlePageChange"
              ></v-pagination>
            </v-col>
          </v-row>
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="deleteDialog" max-width="500px">
      <v-card>
        <v-card-title>Delete Price Entry</v-card-title>
        <v-card-text>
          Are you sure you want to delete this price entry?
          <v-list dense>
            <v-list-item>
              <v-list-item-title>Date:</v-list-item-title>
              <v-list-item-subtitle>{{ deletedItem.date }}</v-list-item-subtitle>
            </v-list-item>
            <v-list-item>
              <v-list-item-title>Security:</v-list-item-title>
              <v-list-item-subtitle>{{ deletedItem.security__name }}</v-list-item-subtitle>
            </v-list-item>
            <v-list-item>
              <v-list-item-title>Price:</v-list-item-title>
              <v-list-item-subtitle>{{ deletedItem.price }} {{ deletedItem.security__currency }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue darken-1" text @click="closeDeleteDialog" :disabled="isDeleting">Cancel</v-btn>
          <v-btn color="red darken-1" text @click="confirmDelete" :loading="isDeleting" :disabled="isDeleting">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <PriceFormDialog
      v-model="showPriceDialog"
      :edit-item="editingPrice"
      :securities="securities"
      @price-added="handlePriceAdded"
      @price-updated="handlePriceUpdated"
    />

    <SecurityFormDialog
      v-model="showSecurityDialog"
      :edit-item="null"
    />

    <PriceImportDialog
      v-model="showImportDialog"
      @prices-imported="handlePricesImported"
    />

  </div>
</template>

<script>
import { ref, watch, computed, onMounted, inject } from 'vue'
import { useStore } from 'vuex'
import { getAssetTypes, getBrokers, getSecurities, getPrices, deletePrice, getPriceDetails } from '@/services/api'
import PriceChart from '@/components/charts/PriceChart.vue'
import debounce from 'lodash/debounce'
import { useTableSettings } from '@/composables/useTableSettings'
import PriceFormDialog from '@/components/dialogs/PriceFormDialog.vue'
import SecurityFormDialog from '@/components/dialogs/SecurityFormDialog.vue'
import PriceImportDialog from '@/components/dialogs/PriceImportDialog.vue'

export default {
  name: 'PricesPage',
  components: {
    PriceChart,
    PriceFormDialog,
    SecurityFormDialog,
    PriceImportDialog,
  },
  setup() {
    const store = useStore()
    const {
      dateFrom,
      dateTo,
      itemsPerPage,
      currentPage,
      sortBy,
      handlePageChange,
      handleItemsPerPageChange,
      handleSortChange,
      handleTimespanChange
    } = useTableSettings()

    const assetTypes = ref([])
    const brokers = ref([])
    const securities = ref([])
    const selectedAssetTypes = ref([])
    const selectedBroker = ref(null)
    const selectedSecurities = ref([])
    const priceData = ref([])
    const loading = ref(false)
    const tableLoading = ref(false)
    const totalItems = ref(0)
    const deleteDialog = ref(false)
    const deletedItem = ref({})
    const editingPrice = ref(null)
    const showPriceDialog = ref(false)
    const showSecurityDialog = ref(false)
    const showImportDialog = ref(false)
    const isDeleting = ref(false)
    const showError = inject('showError')

    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
    const pageCount = computed(() => Math.ceil(totalItems.value / itemsPerPage.value))

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
        selectedAssetTypes.value = assetTypes.value.map(item => item.value)
      }
    }

    const toggleSelectAllSecurities = () => {
      if (securitiesAllSelected.value) {
        selectedSecurities.value = []
      } else {
        selectedSecurities.value = securities.value.map(item => item.id)
      }
    }

    onMounted(async () => {
      try {
        const [assetTypesData, brokersData, securitiesData] = await Promise.all([
          getAssetTypes(),
          getBrokers(),
          getSecurities(),
        ])
        console.log('brokersData', brokersData)
        console.log('securitiesData', securitiesData)
        console.log('assetTypesData', assetTypesData)
        assetTypes.value = assetTypesData
        brokers.value = brokersData
        securities.value = securitiesData

        await handleTimespanChange('ytd')

      } catch (error) {
        console.error('Error fetching initial data:', error)
      }
    })

    const fetchSecurities = debounce(async () => {
      try {
        securities.value = await getSecurities(selectedAssetTypes.value, selectedBroker.value)
        // Reset securities if they are no longer in the list
        selectedSecurities.value = selectedSecurities.value.filter(id =>
          securities.value.some(security => security.id === id)
        )
        // Automatically select all securities if a broker is selected
        if (selectedBroker.value) {
          selectedSecurities.value = securities.value.map(item => item.id);
        }
      } catch (error) {
        console.error('Error fetching securities:', error)
      }
    }, 300) // 300ms debounce

    watch([selectedAssetTypes, selectedBroker], () => {
      fetchSecurities()
    })

    const fetchPriceData = async () => {
      tableLoading.value = true
      try {
        const response = await getPrices({
          assetTypes: selectedAssetTypes.value,
          broker: selectedBroker.value,
          securities: selectedSecurities.value,
          startDate: dateFrom.value,
          endDate: dateTo.value,
          page: currentPage.value,
          itemsPerPage: itemsPerPage.value,
          sortBy: sortBy.value[0] || {}
        })
        console.log('API Response:', response) // Log the response
        priceData.value = response.prices
        totalItems.value = response.total_items
      } catch (error) {
        console.error('Error fetching price data:', error)
      } finally {
        tableLoading.value = false
        isApplyingFilters.value = false
      }
    }

    const isApplyingFilters = ref(false)

    const applyFilters = () => {
      isApplyingFilters.value = true
      currentPage.value = 1
      fetchPriceData()
    }

    const openImportDialog = () => {
      showImportDialog.value = true
    }

    const handlePricesImported = (summary) => {
      console.log('Prices imported:', summary)
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
      deleteDialog.value = true
    }

    const closeDeleteDialog = () => {
      if (!isDeleting.value) {
        deleteDialog.value = false
        deletedItem.value = {}
      }
    }

    const confirmDelete = async () => {
      isDeleting.value = true
      try {
        await deletePrice(deletedItem.value.id)
        await fetchPriceData()
      } catch (error) {
        const errorMessage = error.response?.data?.message || error.message || 'Unknown error'
        showError(`Failed to delete price: ${errorMessage}`)
      } finally {
        isDeleting.value = false
        closeDeleteDialog()
      }
    }

    const handlePriceUpdated = (updatedPrice) => {
      const index = priceData.value.findIndex(p => p.id === updatedPrice.id)
      if (index !== -1) {
        priceData.value[index] = updatedPrice
      }
      fetchPriceData()
    }

    const openAddPriceDialog = () => {
      editingPrice.value = null
      showPriceDialog.value = true
    }

    const handlePriceAdded = (newPrice) => {
      console.log('New price added:', newPrice)
      fetchPriceData()
    }

    const addSecurity = () => {
      showSecurityDialog.value = true
    }

    watch(
      [
        () => store.state.dataRefreshTrigger,
        itemsPerPage,
        currentPage,
        sortBy,
      ],
      () => {
        if (!isApplyingFilters.value) {
          fetchPriceData()
        }
        isApplyingFilters.value = false
      },
      { deep: true }
    )

    return {
      assetTypes,
      brokers,
      securities,
      selectedAssetTypes,
      selectedBroker,
      selectedSecurities,
      dateFrom,
      dateTo,
      applyFilters,
      headers,
      priceData,
      loading,
      tableLoading,
      totalItems,
      itemsPerPage,
      currentPage,
      sortBy,
      deleteDialog,
      deletedItem,
      handlePageChange,
      handleItemsPerPageChange,
      handleSortChange,
      fetchPriceData,
      editPrice,
      openDeleteDialog,
      closeDeleteDialog,
      confirmDelete,
      assetTypesAllSelected,
      assetTypesIndeterminate,
      securitiesAllSelected,
      securitiesIndeterminate,
      toggleSelectAllAssetTypes,
      toggleSelectAllSecurities,
      fetchSecurities,
      itemsPerPageOptions,
      pageCount,
      editingPrice,
      handlePriceUpdated,
      showPriceDialog,
      openAddPriceDialog,
      handlePriceAdded,
      isDeleting,
      addSecurity,
      showSecurityDialog,
      showImportDialog,
      openImportDialog,
      handlePricesImported,
    }
  },
}
</script>