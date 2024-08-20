<template>
  <v-container fluid>
    <v-row align="center" justify="space-between" class="mb-4">
      <v-col cols="auto">
        <h2>Transactions — <span id="brokerNameHeader">{{ selectedBroker }}</span></h2>
      </v-col>
      <v-col cols="auto">
        <BrokerSelection />
      </v-col>
    </v-row>

    <v-row class="mb-4">
      <v-col>
        <v-card>
          <v-card-text class="d-flex justify-end">
            <SettingsDialog />
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-row>
      <v-col>
        <v-card>
          <v-card-text>
            <v-data-table
              :headers="headers"
              :items="transactions"
              :items-per-page="itemsPerPage"
              :page="page"
              :server-items-length="totalItems"
              @update:page="updatePage"
              @update:items-per-page="updateItemsPerPage"
              class="elevation-1"
            >
              <template v-slot:top>
                <v-text-field
                  v-model="search"
                  label="Search"
                  class="mx-4"
                  @input="debouncedSearch"
                ></v-text-field>
              </template>

              <template v-slot:item="{ item }">
                <tr>
                  <td>
                    <v-checkbox v-model="selectedTransactions" :value="item.id"></v-checkbox>
                  </td>
                  <td>{{ item.date }}</td>
                  <td>
                    {{ item.type }}
                    <template v-if="item.type === 'Cash' || item.type === 'Dividend'">
                      {{ item.cash_flow }}
                    </template>
                    <template v-else-if="item.type === 'Close'">
                      {{ item.quantity }} of {{ item.security }}
                    </template>
                    <template v-else-if="item.type === 'FX'">
                      : {{ item.from_currency }} to {{ item.to_currency }} @ {{ item.exchange_rate }}
                      <span class="text-caption"> || Fee: {{ item.commission }}</span>
                    </template>
                    <template v-else>
                      {{ item.quantity }} @ {{ item.price }} of {{ item.security }}
                      <span class="text-caption"> || Fee: {{ item.commission }}</span>
                    </template>
                  </td>
                  <td>{{ item.type }}</td>
                  <td v-for="currency in currencies" :key="currency">
                    {{ getCashFlow(item, currency) }}
                  </td>
                  <td></td>
                  <td v-for="currency in currencies" :key="currency">
                    {{ item.balances[currency] }}
                  </td>
                </tr>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-overlay :model-value="loading">
      <v-progress-circular indeterminate size="64"></v-progress-circular>
    </v-overlay>
  </v-container>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { useStore } from 'vuex'
import debounce from 'lodash/debounce'
import { getTransactionsTable } from '@/services/api'
import BrokerSelection from '@/components/BrokerSelection.vue'
import SettingsDialog from '@/components/SettingsDialog.vue'

export default {
  name: 'TransactionsPage',
  components: {
    BrokerSelection,
    SettingsDialog,
  },
  setup() {
    const store = useStore()
    const transactions = ref([])
    const loading = ref(true)
    const totalItems = ref(0)
    const itemsPerPage = ref(25)
    const page = ref(1)
    const search = ref('')
    const selectedTransactions = ref([])
    const currencies = computed(() => store.state.currencies)
    const selectedBroker = computed(() => store.state.selectedBroker)

    const headers = computed(() => [
      { text: '', value: 'actions', sortable: false },
      { text: 'Date', value: 'date' },
      { text: 'Transaction', value: 'transaction' },
      { text: 'Type', value: 'type' },
      ...currencies.value.map(currency => ({ text: currency, value: `cash_flow_${currency}` })),
      { text: '', value: 'spacer', sortable: false },
      ...currencies.value.map(currency => ({ text: currency, value: `balance_${currency}` })),
    ])

    const fetchTransactions = async () => {
      loading.value = true
      try {
        const response = await getTransactionsTable({
          timespan: store.state.tableSettings.timespan,
          page: page.value,
          items_per_page: itemsPerPage.value,
          search: search.value,
        })
        transactions.value = response.transactions
        totalItems.value = response.total_items
      } catch (error) {
        console.error('Error fetching transactions:', error)
      } finally {
        loading.value = false
      }
    }

    const updatePage = (newPage) => {
      page.value = newPage
      fetchTransactions()
    }

    const updateItemsPerPage = (newItemsPerPage) => {
      itemsPerPage.value = newItemsPerPage
      fetchTransactions()
    }

    const debouncedSearch = debounce(() => {
      page.value = 1
      fetchTransactions()
    }, 300)

    const getCashFlow = (item, currency) => {
      if (item.currency === currency) {
        if (['Dividend', 'Tax', 'Interest income', 'Cash deposit', 'Cash withdrawal'].includes(item.type)) {
          return item.cash_flow
        } else if (item.type === 'Broker commission') {
          return `(${item.commission})`
        } else {
          return item.value
        }
      } else if (item.from_currency === currency) {
        return item.from_amount
      } else if (item.to_currency === currency) {
        return item.to_amount
      } else {
        return '–'
      }
    }

    onMounted(fetchTransactions)

    watch(() => store.state.tableSettings.timespan, fetchTransactions)
    watch(() => store.state.refreshTrigger, fetchTransactions)

    return {
      transactions,
      headers,
      loading,
      totalItems,
      itemsPerPage,
      page,
      search,
      selectedTransactions,
      currencies,
      selectedBroker,
      updatePage,
      updateItemsPerPage,
      debouncedSearch,
      getCashFlow,
    }
  },
}
</script>