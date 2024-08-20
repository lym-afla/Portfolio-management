<template>
  <v-container fluid>
    <v-select
      v-model="selectedYear"
      :items="yearOptions"
      label="Year"
      @change="handleYearChange"
    ></v-select>
    <v-text-field
      v-model="search"
      label="Search"
      @input="handleSearch"
    ></v-text-field>
    <v-data-table
      :items="transactions"
      :loading="loading"
      :items-per-page="itemsPerPage"
      :page="currentPage"
      :server-items-length="totalItems"
      :search="search"
      @update:options="handleTableOptionsChange"
    >
      <template v-slot:header>
        <thead>
          <tr>
            <th></th>
            <th class="text-start">Date</th>
            <th class="text-start">Transaction</th>
            <th class="text-center">Type</th>
            <th class="text-center" :colspan="currencies.length">Cash flow</th>
            <th></th>
            <th class="text-center" :colspan="currencies.length">Balance</th>
          </tr>
          <tr>
            <th></th>
            <th></th>
            <th></th>
            <th></th>
            <th v-for="currency in currencies" :key="'cash-' + currency" class="text-center">
              {{ currency }}
            </th>
            <th></th>
            <th v-for="currency in currencies" :key="'balance-' + currency" class="text-center">
              {{ currency }}
            </th>
          </tr>
        </thead>
      </template>

      <template v-slot:item="{ item }">
        <tr>
          <td>
            <v-checkbox
              v-model="selectedTransactions"
              :value="item.id"
              hide-details
            ></v-checkbox>
          </td>
          <td class="text-start">{{ formatDate(item.date) }}</td>
          <td class="text-start text-nowrap">
            {{ item.type }}
            <template v-if="item.type.includes('Cash')">
              {{ item.cash_flow }}
            </template>
            <template v-else-if="item.type.includes('Dividend')">
              of {{ item.cash_flow }} for {{ item.security.name }}
            </template>
            <template v-else-if="item.type === 'Close'">
              {{ item.quantity }} of {{ item.security.name }}
            </template>
            <template v-else-if="item.type === 'FX'">
              : {{ item.from_currency }} to {{ item.to_currency }} @ {{ item.exchange_rate }}
              <span class="text-caption"> || Fee: {{ item.commission }}</span>
            </template>
            <template v-else>
              {{ item.quantity }}
              @ {{ item.price }} of {{ item.security.name }}
              <span class="text-caption"> || Fee: {{ item.commission }}</span>
            </template>
          </td>
          <td class="text-center">{{ item.type }}</td>
          <td v-for="currency in currencies" :key="'cash-' + currency" class="text-center">
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
          <td></td>
          <td v-for="currency in currencies" :key="'balance-' + currency" class="text-center">
            {{ item.balances[currency] }}
          </td>
        </tr>
      </template>
    </v-data-table>
  </v-container>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue'
import { debounce } from 'lodash'
import { getTransactions } from '@/services/api'
import { formatDate } from '@/utils/formatters'

export default {
  name: 'TransactionsPage',
  props: {
    pageTitle: {
      type: String,
      default: 'Transactions',
    },
  },
  emits: ['update-page-title'],
  setup(props, { emit }) {
    const transactions = ref([])
    const loading = ref(true)
    const totalItems = ref(0)
    const currentPage = ref(1)
    const itemsPerPage = ref(25)
    const search = ref('')
    const selectedYear = ref('2023')
    const yearOptions = ref(['2023', '2022', '2021'])
    const currencies = ref([])
    const selectedTransactions = ref([])

    const fetchTransactions = async () => {
      loading.value = true
      try {
        const response = await getTransactions(
          selectedYear.value,
          currentPage.value,
          itemsPerPage.value,
          search.value
        )
        transactions.value = response.transactions
        totalItems.value = response.total_items
        currencies.value = response.currencies
      } catch (error) {
        console.error('Error fetching transactions:', error)
      } finally {
        loading.value = false
      }
    }

    const handleTableOptionsChange = (options) => {
      currentPage.value = options.page
      itemsPerPage.value = options.itemsPerPage
      fetchTransactions()
    }

    const handleSearch = debounce(() => {
      currentPage.value = 1
      fetchTransactions()
    }, 300)

    const handleYearChange = () => {
      currentPage.value = 1
      fetchTransactions()
    }

    onMounted(() => {
      emit('update-page-title', props.pageTitle)
      fetchTransactions()
    })

    onUnmounted(() => {
      emit('update-page-title', '')
    })

    return {
      transactions,
      loading,
      totalItems,
      currentPage,
      itemsPerPage,
      handleTableOptionsChange,
      search,
      handleSearch,
      selectedYear,
      yearOptions,
      handleYearChange,
      currencies,
      selectedTransactions,
      formatDate,
    }
  },
}
</script>