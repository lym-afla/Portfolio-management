<template>
  <v-container fluid class="pa-0">
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
    </v-overlay>

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
  </v-container>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useStore } from 'vuex'
import { format } from 'date-fns'
import { getTransactions } from '@/services/api'
import { useTableSettings } from '@/composables/useTableSettings'
import DateRangeSelector from '@/components/DateRangeSelector.vue'

export default {
  name: "TransactionsPage",
  components: {
    DateRangeSelector
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const store = useStore()

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

    const dateRangeModel = ref({
      dateRange: 'ytd',
      dateFrom: dateFrom.value,
      dateTo: dateTo.value
    })

    const handleDateRangeChange = (newDateRange) => {
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

    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
    const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)

    const pageCount = computed(() => Math.ceil(totalItems.value / itemsPerPage.value))

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

    const fetchTransactions = async () => {
      tableLoading.value = true
      console.log('[TransactionsPage] fetchTransactions called with:', {
        dateFrom: dateFrom.value,
        dateTo: dateTo.value,
        currentPage: currentPage.value,
        itemsPerPage: itemsPerPage.value,
        search: search.value,
        sortBy: sortBy.value[0] || {},
      })
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
        console.log('[TransactionsPage] Updated transactions:', transactions.value)
      } catch (error) {
        console.error('Error fetching transactions:', error)
      } finally {
        tableLoading.value = false
      }
    }

    const formatDate = (date) => {
      return format(new Date(date), 'yyyy-MM-dd')
    }

    watch(
      [
        () => store.state.dataRefreshTrigger,
        itemsPerPage,
        currentPage,
        sortBy,
        search
      ],
      () => {
        fetchTransactions()
      },
      { deep: true }
    )

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
    }
  }
}
</script>