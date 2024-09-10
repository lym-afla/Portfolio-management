<template>
  <v-container fluid class="pa-0">
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
    </v-overlay>

    <v-card class="mb-4">
      <v-card-text>
        <v-btn
          color="primary"
          @click="openAddFXDialog"
          prepend-icon="mdi-plus"
          class="mr-2"
        >
          Add FX Rate
        </v-btn>
        <v-btn
          color="secondary"
          @click="showImportDialog = true"
          prepend-icon="mdi-upload"
        >
          Import FX Rates
        </v-btn>
      </v-card-text>
    </v-card>

    <v-row no-gutters>
      <v-col cols="12">
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
          <template #top>
            <v-toolbar flat class="bg-grey-lighten-4 border-b px-2">
              <DateRangeSelector
                v-model="dateRangeForSelector"
                @update:model-value="handleDateRangeChange"
              />
              <v-col cols="12" sm="5" md="6" lg="7" class="px-8">
                <v-text-field
                  v-model="search"
                  append-icon="mdi-magnify"
                  label="Search"
                  single-line
                  hide-details
                  density="compact"
                  bg-color="white"
                  class="rounded-lg"
                ></v-text-field>
              </v-col>
              <v-spacer></v-spacer>
              <v-col cols="12" sm="4" md="3" lg="2" class="d-flex align-center justify-end px-2">
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
                ></v-select>
              </v-col>
            </v-toolbar>
          </template>

          <template #item="{ item }">
            <tr>
              <td>{{ item.date }}</td>
              <td v-for="currency in currencies" :key="currency" class="text-center">{{ item[currency] }}</td>
              <td class="text-end">
                <v-icon small class="mr-2" @click="editItem(item)">mdi-pencil</v-icon>
                <v-icon small @click="deleteItem(item)">mdi-delete</v-icon>
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
              ></v-pagination>
            </div>
          </template>
        </v-data-table>
      </v-col>
    </v-row>

    <!-- Add dialog components -->
    <FXDialog
      v-model="showFXDialog"
      :edit-item="editedItem"
      @fx-added="fetchFXData"
      @fx-updated="fetchFXData"
    />
    <FXImportDialog v-model="showImportDialog" @import-completed="fetchFXData" @refresh-table="fetchFXData" />

    <!-- Add confirmation dialog for delete -->
    <v-dialog v-model="showDeleteDialog" max-width="300px">
      <v-card>
        <v-card-title class="text-h5">Confirm Delete</v-card-title>
        <v-card-text>Are you sure you want to delete this FX rate?</v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue darken-1" text @click="showDeleteDialog = false">Cancel</v-btn>
          <v-btn color="red darken-1" text @click="confirmDelete" :loading="deleteLoading">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
import { ref, computed, watch, watchEffect } from 'vue'
import { useStore } from 'vuex'
import { getFXData, deleteFXRate, getFXDetails } from '@/services/api'
import { useTableSettings } from '@/composables/useTableSettings'
import DateRangeSelector from '@/components/DateRangeSelector.vue'
import { calculateDateRange } from '@/utils/dateRangeUtils'
import FXDialog from '@/components/dialogs/FXDialog.vue'
import FXImportDialog from '@/components/dialogs/FXImportDialog.vue'
import { useErrorHandler } from '@/composables/useErrorHandler'

export default {
  name: 'FXPage',
  components: { DateRangeSelector, FXDialog, FXImportDialog },
  setup() {
    const store = useStore()

    const dateRange = ref('ytd')
    const {
      dateFrom,
      dateTo,
      itemsPerPage,
      currentPage,
      sortBy,
      search,
      handlePageChange,
      handleItemsPerPageChange,
      handleSortChange
    } = useTableSettings()

    const { handleApiError } = useErrorHandler()

    const loading = ref(true)
    const tableLoading = ref(false)
    const deleteLoading = ref(false)
    const fxData = ref([])
    const totalItems = ref(0)
    const currencies = ref([])

    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
    const pageCount = computed(() => Math.ceil(totalItems.value / itemsPerPage.value))
    const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)

    const headers = computed(() => [
      { title: 'Date', key: 'date', align: 'start', sortable: true },
      ...currencies.value.map(currency => ({ title: currency, key: currency, align: 'center', sortable: true })),
      { title: 'Actions', key: 'actions', align: 'end', sortable: false }
    ])

    const fetchFXData = async () => {

      console.log('Fetching FX data with:', {
        startDate: dateFrom.value,
        endDate: dateTo.value,
        page: currentPage.value,
        itemsPerPage: itemsPerPage.value,
        sortBy: sortBy.value[0] || {},
        search: search.value
      })
      tableLoading.value = true
      try {
        const response = await getFXData({
          startDate: dateFrom.value,
          endDate: dateTo.value,
          page: currentPage.value,
          itemsPerPage: itemsPerPage.value,
          sortBy: sortBy.value[0] || {},
          search: search.value
        })
        console.log('FX data received:', response)
        fxData.value = response.results
        totalItems.value = response.count
        currencies.value = response.currencies
      } catch (error) {
        handleApiError(error)
      } finally {
        tableLoading.value = false
      }
    }

    const initializeDateRange = () => {
      console.log('Initializing date range')
      console.log('effectiveCurrentDate:', effectiveCurrentDate.value)
      console.log('dateRange:', dateRange.value)
      
      if (effectiveCurrentDate.value) {
        const { from, to } = calculateDateRange(dateRange.value, effectiveCurrentDate.value)
        console.log('Calculated date range:', { from, to })
        
        dateFrom.value = from
        dateTo.value = to
        
        console.log('Date range initialized:', {
          dateFrom: dateFrom.value,
          dateTo: dateTo.value,
          dateRange: dateRange.value,
          effectiveCurrentDate: effectiveCurrentDate.value
        })
      } else {
        console.log('effectiveCurrentDate is not set')
      }
    }

    const handleDateRangeChange = (newDateRange) => {
      dateRange.value = newDateRange.dateRange
      dateFrom.value = newDateRange.dateFrom
      dateTo.value = newDateRange.dateTo
      console.log('Date range changed:', { dateRange: dateRange.value, dateFrom: dateFrom.value, dateTo: dateTo.value })
      fetchFXData()
    }

    watchEffect(async () => {
      if (effectiveCurrentDate.value) {
        initializeDateRange()
        loading.value = false
      }
    })

    watch([loading, currentPage, itemsPerPage, sortBy, search], () => {
      if (!loading.value && dateFrom.value && dateTo.value) {
        fetchFXData()
      }
    })

    // onMounted(() => {
    //   console.log('Mounting FXPage')
    // })

    const showFXDialog = ref(false)
    const showImportDialog = ref(false)
    const showDeleteDialog = ref(false)
    const editedItem = ref(null)
    const itemToDelete = ref(null)

    const openAddFXDialog = () => {
      editedItem.value = null
      showFXDialog.value = true
    }

    const editItem = async (item) => {
      console.log('Editing item:', item)
      try {
        const fxDetails = await getFXDetails(item.id)
        editedItem.value = fxDetails
        showFXDialog.value = true
      } catch (error) {
        handleApiError(error)
      }
    }

    const deleteItem = async (item) => {
      console.log('Deleting item:', item)
      itemToDelete.value = item
      showDeleteDialog.value = true
    }

    const confirmDelete = async () => {
      deleteLoading.value = true
      try {
        await deleteFXRate(itemToDelete.value.id)
        await fetchFXData()
      } catch (error) {
        handleApiError(error)
      } finally {
        showDeleteDialog.value = false
        itemToDelete.value = null
        deleteLoading.value = false
      }
    }

    return {
      loading,
      tableLoading,
      fxData,
      totalItems,
      currentPage,
      itemsPerPage,
      itemsPerPageOptions,
      pageCount,
      sortBy,
      search,
      headers,
      currencies,
      dateRangeForSelector: computed(() => ({
        dateRange: dateRange.value,
        dateFrom: dateFrom.value,
        dateTo: dateTo.value
      })),
      handleDateRangeChange,
      handleItemsPerPageChange,
      handlePageChange,
      handleSortChange,
      showFXDialog,
      showImportDialog,
      showDeleteDialog,
      editedItem,
      openAddFXDialog,
      editItem,
      deleteItem,
      deleteLoading,
      confirmDelete,
      fetchFXData
    }
  }
}
</script>