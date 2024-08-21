<template>
  <v-container fluid class="pa-0">
    <v-progress-circular
      v-if="loading"
      color="primary"
      indeterminate
      size="64"
    ></v-progress-circular>

    <v-row no-gutters>
      <v-col cols="12">
        <v-data-table
          :headers="headers"
          :items="transactions"
          :loading="tableLoading"
          :search="search"
          :items-per-page="itemsPerPage"
          class="elevation-1 nowrap-table"
          density="compact"
          :server-items-length="totalItems"
          :items-length="totalItems"
          disable-sort
        >
          <template #top>
            <v-toolbar flat class="bg-grey-lighten-4 border-b">
              <v-btn icon elevation="2" @click="openDateDialog">
                <v-icon>mdi-calendar</v-icon>
              </v-btn>
              <!-- <v-divider vertical class="mx-2"></v-divider> -->
              <v-col cols="12" sm="6" md="7" lg="8">
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
              <v-col cols="12" sm="3" md="3" lg="2">
                <v-select
                  v-model="itemsPerPage"
                  :items="itemsPerPageOptions"
                  label="Rows per page"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="mr-2 rows-per-page-select"
                  @update:model-value="handleItemsPerPageChange"
                  bg-color="white"
                ></v-select>
              </v-col>
            </v-toolbar>
          </template>

          <template #header>
            <tr>
              <th v-for="header in headers"
              :key="header.key"
              :colspan="header.children ? header.children.length : 1"
              :rowspan="header.children ? 1 : 2"
              :class="['text-' + header.align]">
                {{ header.title }}
              </th>
            </tr>
            <tr>
              <template v-for="header in headers" :key="header.key">
                <th v-for="subHeader in header.children" :key="subHeader.key" :class="['text-' + subHeader.align]">
                  {{ subHeader.title }}
                </th>
              </template>
            </tr>
          </template>

          <template #item="{ item }">
            <tr>
              <td>
                <!-- <v-checkbox
                  v-model="selectedItems"
                  :value="item"
                  hide-details
                ></v-checkbox> -->
              </td>
              <td>{{ item.date }}</td>
              <td class="text-start text-nowrap">
                {{ item.type }}
                <template v-if="item.type.includes('Cash') || item.type === 'Dividend'">
                  {{ item.cash_flow }} {{ item.type === 'Dividend' ? `for ${item.security}` : '' }}
                </template>
                <template v-else-if="item.type === 'Close'">
                  {{ item.quantity }} of {{ item.security }}
                </template>
                <template v-else-if="item.type === 'FX'">
                  : {{ item.from_currency }} to {{ item.to_currency }} @ {{ item.exchange_rate }}
                  <span v-if="item.commission" class="text-caption text-grey"> || Fee: {{ item.commission }}</span>
                </template>
                <template v-else-if="!['Broker commission', 'Tax', 'Interest income'].includes(item.type)">
                  {{ item.quantity }}
                  @ {{ item.price }} of {{ item.security }}
                  <span v-if="item.commission" class="text-caption text-grey"> || Fee: {{ item.commission }}</span>
                </template>
              </td>
              <td class="text-center">{{ item.type }}</td>
              <td v-for="currency in currencies" :key="`cash_flow-${currency}`" class="text-center">
                <template v-if="item.currency === currency">
                  <template v-if="['Dividend', 'Tax'].includes(item.type) || item.type.includes('Interest') || item.type.includes('Cash')">
                    {{ item.cash_flow }}
                  </template>
                  <template v-else-if="item.type === 'Broker commission'">
                    ({{ item.commission }})
                  </template>
                  <template v-else>
                    {{ item.value }}
                  </template>
                </template>
                <template v-else-if="item.from_currency === currency">
                  {{ item.from_amount }}
                </template>
                <template v-else-if="item.to_currency === currency">
                  {{ item.to_amount }}
                </template>
                <template v-else>
                  –
                </template>
              </td>
              <td class="text-center"></td>
              <td v-for="currency in currencies" :key="`balance-${currency}`" class="text-center">
                {{ item.balances[currency] }}
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

    <!-- Main Date Range Dialog -->
    <v-dialog v-model="dateDialog" max-width="400px">
      <v-card>
        <v-card-title class="text-h5">Select Date Range</v-card-title>
        <v-card-text>
          <v-select
            v-model="selectedDateRange"
            :items="dateRangeOptions"
            label="Predefined Ranges"
            @update:model-value="handlePredefinedRange"
          ></v-select>
          <v-row>
            <v-col cols="2" class="d-flex justify-center pr-0 pl-0">
              <v-btn icon @click="openFromDatePicker">
                <v-icon>mdi-calendar</v-icon>
              </v-btn>
            </v-col>
            <v-col cols="10">
              <v-text-field
                v-model="dateFrom"
                label="From"
                type="date"
              ></v-text-field>
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="2" class="d-flex justify-center pr-0 pl-0">
              <v-btn icon @click="openToDatePicker">
                <v-icon>mdi-calendar</v-icon>
              </v-btn>
            </v-col>
            <v-col cols="10">
              <v-text-field
                v-model="dateTo"
                label="To"
                type="date"
              ></v-text-field>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue-darken-1" variant="text" @click="closeDateDialog">Cancel</v-btn>
          <v-btn color="blue-darken-1" variant="text" @click="applyDateRange">Apply</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- From Date Picker Dialog -->
    <v-dialog v-model="fromDatePickerDialog" max-width="300px">
      <v-date-picker 
        @update:model-value="closeFromDatePicker" 
        show-adjacent-months
      ></v-date-picker>
    </v-dialog>

    <!-- To Date Picker Dialog -->
    <v-dialog v-model="toDatePickerDialog" max-width="300px">
      <v-date-picker 
        @update:model-value="closeToDatePicker" 
        show-adjacent-months
      ></v-date-picker>
    </v-dialog>
  </v-container>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useStore } from 'vuex'
import { format, subMonths, subYears, startOfDay, parseISO } from 'date-fns'
import { getTransactions } from '@/services/api'

export default {
  name: "TransactionsPage",
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()

    const dateDialog = ref(false)
    const fromDatePickerDialog = ref(false)
    const toDatePickerDialog = ref(false)
    const dateFrom = ref('')
    const dateTo = ref('')
    const loading = ref(false)
    const tableLoading = ref(false)
    const transactions = ref([])
    const totalItems = ref(0)
    const search = ref('')

    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
  
    const currentPage = computed({
      get: () => store.state.tableSettings.page,
      set: (value) => store.dispatch('updateTableSettings', { page: value })
    })

    const itemsPerPage = computed({
      get: () => store.state.tableSettings.itemsPerPage,
      set: (value) => store.dispatch('updateTableSettings', { itemsPerPage: value })
    })

    const pageCount = computed(() => Math.ceil(totalItems.value / itemsPerPage.value))

    const selectedDateRange = ref('')
    const dateRangeOptions = [
      { title: 'Custom', value: 'custom' },
      { title: 'Last 1 Month', value: 'last1m' },
      { title: 'Last 3 Months', value: 'last3m' },
      { title: 'Last 6 Months', value: 'last6m' },
      { title: 'Last 12 Months', value: 'last12m' },
      { title: 'Last 3 Years', value: 'last3y' },
      { title: 'Last 5 Years', value: 'last5y' },
      { title: 'All', value: 'all' },
    ]

    const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)
    const currencies = ref([])

    const headers = computed(() => [
      { title: '', key: 'actions', align: 'center', sortable: false },
      { title: 'Date', key: 'date', align: 'start', sortable: true },
      { title: 'Transaction', key: 'transaction', align: 'start', sortable: false },
      { title: 'Type', key: 'type', align: 'center', sortable: false },
      {
        title: 'Cash flow',
        key: 'cash_flow',
        align: 'center',
        sortable: false,
        children: currencies.value.map(currency => ({
          title: currency,
          key: `cash_flow_${currency}`,
          align: 'center',
          sortable: false
        })),
      },
      { title: '', key: 'spacer', align: 'center', sortable: false },
      {
        title: 'Balance',
        key: 'balance',
        align: 'center',
        sortable: false,
        children: currencies.value.map(currency => ({
          title: currency,
          key: `balance_${currency}`,
          align: 'center',
          sortable: false
        })),
      },
    ])

    const openDateDialog = () => {
      dateDialog.value = true
    }

    const closeDateDialog = () => {
      dateDialog.value = false
    }

    const openFromDatePicker = () => {
      fromDatePickerDialog.value = true
    }

    const closeFromDatePicker = (pickerDateFrom) => {
      dateFrom.value = formatDate(pickerDateFrom)
      fromDatePickerDialog.value = false
    }

    const openToDatePicker = () => {
      toDatePickerDialog.value = true
    }

    const closeToDatePicker = (pickerDateTo) => {
      dateTo.value = formatDate(pickerDateTo)
      toDatePickerDialog.value = false
    }
    
    const applyDateRange = () => {
      console.log('Date range:', dateFrom.value, dateTo.value)
      console.log('Selected range:', selectedDateRange.value)
      closeDateDialog()
      fetchTransactions()
    }

    const handleItemsPerPageChange = (newItemsPerPage) => {
      itemsPerPage.value = newItemsPerPage
      currentPage.value = 1
      fetchTransactions()
    }

    const handlePageChange = (newPage) => {
      currentPage.value = newPage
      fetchTransactions()
    }

    const fetchTransactions = async () => {
      tableLoading.value = true
      console.log('[TransactionsPage] fetchTransactions called with:', {
        dateFrom: dateFrom.value,
        dateTo: dateTo.value,
        currentPage: currentPage.value,
        itemsPerPage: itemsPerPage.value,
        search: search.value,
      })
      try {
        const response = await getTransactions(
          dateFrom.value,
          dateTo.value,
          currentPage.value,
          itemsPerPage.value,
          search.value,
        )
        transactions.value = response.transactions
        totalItems.value = response.total_items
        currencies.value = response.currencies || []
      } catch (error) {
        console.error('Error fetching transactions:', error)
      } finally {
        tableLoading.value = false
      }
    }

    const formatDate = (date) => {
      return format(new Date(date), 'yyyy-MM-dd')
    }

    const handlePredefinedRange = async (value) => {
      let currentDate = effectiveCurrentDate.value
      
      if (!currentDate) {
        await store.dispatch('fetchEffectiveCurrentDate')
        currentDate = store.state.effectiveCurrentDate
      }

      if (!currentDate) {
        console.error('Failed to fetch effective current date')
        return
      }

      const effectiveDate = parseISO(currentDate)
      let fromDate

      switch (value) {
        case 'last1m':
          fromDate = subMonths(effectiveDate, 1)
          break
        case 'last3m':
          fromDate = subMonths(effectiveDate, 3)
          break
        case 'last6m':
          fromDate = subMonths(effectiveDate, 6)
          break
        case 'last12m':
          fromDate = subMonths(effectiveDate, 12)
          break
        case 'last3y':
          fromDate = subYears(effectiveDate, 3)
          break
        case 'last5y':
          fromDate = subYears(effectiveDate, 5)
          break
        case 'all':
          fromDate = new Date(0) // Beginning of time
          break
        default:
          return // Do nothing for custom
      }

      dateFrom.value = formatDate(startOfDay(fromDate))
      dateTo.value = formatDate(effectiveDate)
    }

    const selectedItems = ref([])

    watch(
        () => store.state.dataRefreshTrigger,
        () => {
            fetchTransactions()
        },
        { deep: true }
    )

    onMounted(() => {
      emit('update-page-title', 'Transactions')
      if (!effectiveCurrentDate.value) {
        store.dispatch('fetchEffectiveCurrentDate')
      }
      fetchTransactions()
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    return {
      dateDialog,
      fromDatePickerDialog,
      toDatePickerDialog,
      dateFrom,
      dateTo,
      loading,
      tableLoading,
      transactions,
      totalItems,
      currentPage,
      itemsPerPage,
      itemsPerPageOptions,
      pageCount,
      search,
      headers,
      currencies,
      openDateDialog,
      closeDateDialog,
      openFromDatePicker,
      openToDatePicker,
      applyDateRange,
      handleItemsPerPageChange,
      handlePageChange,
      fetchTransactions,
      closeFromDatePicker,
      closeToDatePicker,
      selectedDateRange,
      dateRangeOptions,
      handlePredefinedRange,
      effectiveCurrentDate,
      formatDate,
      selectedItems,
    }
  }
}
</script>