<template>
  <v-container fluid class="pa-0">
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
    </v-overlay>

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
              <v-spacer></v-spacer>
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
  </v-container>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { useStore } from 'vuex'
import { getFXData } from '@/services/api'
import { useTableSettings } from '@/composables/useTableSettings'
import DateRangeSelector from '@/components/DateRangeSelector.vue'
import { calculateDateRange } from '@/utils/dateRangeUtils'

export default {
  name: 'FXPage',
  components: { DateRangeSelector },
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

    const loading = ref(false)
    const tableLoading = ref(false)
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
      if (!dateFrom.value || !dateTo.value) {
        console.log('Date range not set, skipping fetch')
        return
      }

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
        console.error('Error fetching FX data:', error)
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

    watch(effectiveCurrentDate, () => {
      initializeDateRange()
    })

    watch([dateFrom, dateTo], () => {
      if (dateFrom.value && dateTo.value) {
        fetchFXData()
      }
    })

    watch([currentPage, itemsPerPage, sortBy, search], () => {
      if (dateFrom.value && dateTo.value) {
        fetchFXData()
      }
    })

    onMounted(() => {
      initializeDateRange()
      fetchFXData()
    })

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
      handleSortChange
    }
  }
}
</script>
