<template>
  <div>
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
    </v-overlay>

    <v-card class="mb-4">
      <v-card-text>
        <v-row align="center" justify="space-between">
          <v-col cols="auto">
            <v-btn color="primary" @click="openAddDialog">
              <v-icon left>mdi-plus</v-icon>
              Add Account
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-data-table
      :headers="headers"
      :items="accounts"
      :loading="tableLoading"
      :items-per-page="itemsPerPage"
      :page="currentPage"
      :server-items-length="totalItems"
      :sort-by="sortBy"
      @update:sort-by="handleSortChange"
      density="compact"
      disable-sort
      class="elevation-1 nowrap-table"
    >
      <template #top>
        <v-toolbar flat class="bg-grey-lighten-4 border-b">
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
          <v-col cols="12" sm="4" md="3" lg="2" class="ml-auto">
            <v-select
              v-model="itemsPerPage"
              :items="itemsPerPageOptions"
              label="Rows per page"
              density="compact"
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
          <td :class="`text-${headerAlignments.name}`">{{ item.name }}</td>
          <td :class="`text-${headerAlignments.broker_name}`">{{ item.broker_name }}</td>
          <td :class="`text-${headerAlignments.no_of_securities}`">{{ item.no_of_securities }}</td>
          <td :class="`text-${headerAlignments.first_investment}`">{{ item.first_investment }}</td>
          <td :class="`text-${headerAlignments.nav}`">{{ item.nav }}</td>
          <td v-for="currency in currencies" :key="`cash-${currency}`" :class="`text-${headerAlignments[`cash_${currency}`]}`">
            {{ item.cash[currency] }}
          </td>
          <td :class="`text-${headerAlignments.irr} font-italic`">{{ item.irr }}</td>
          <td :class="`text-${headerAlignments.actions}`">
            <v-icon small class="mr-2" @click="editAccount(item)">
              mdi-pencil
            </v-icon>
            <v-icon small @click="processDeleteAccount(item)">
              mdi-delete
            </v-icon>
          </td>
        </tr>
      </template>
      <template #tfoot>
        <tfoot>
          <tr class="font-weight-bold">
            <td v-for="header in flattenedHeaders" :key="header.key" :class="['text-' + header.align, header.key === 'irr' ? 'font-italic' : '']">
              <template v-if="header.key === 'name'">
                TOTAL
              </template>
              <template v-else-if="['no_of_securities', 'nav', 'irr'].includes(header.key)">
                {{ totals[header.key] }}
              </template>
              <!-- <template v-else>
                -
              </template> -->
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
          ></v-pagination>
        </div>
      </template>
    </v-data-table>

    <AccountFormDialog
      v-model="showAccountDialog"
      :edit-item="editingAccount"
      @account-added="handleAccountAdded"
      @account-updated="handleAccountUpdated"
    />
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { useStore } from 'vuex'
import AccountFormDialog from '@/components/dialogs/AccountFormDialog.vue'
import { getAccountsTable, deleteAccount, getAccountDetails } from '@/services/api'
import { useTableSettings } from '@/composables/useTableSettings'
import { useErrorHandler } from '@/composables/useErrorHandler'

export default {
  name: 'AccountsPage',
  components: {
    AccountFormDialog
  },
  setup() {
    const store = useStore()
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

    const accounts = ref([])
    const loading = ref(false)
    const tableLoading = ref(false)

    const currencies = ref([])
    const totalItems = ref(0)
    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
    const pageCount = computed(() => Math.ceil(totalItems.value / itemsPerPage.value))

    const headers = computed(() => [
      { title: 'Name', key: 'name', align: 'start', sortable: true },
      { title: 'Broker', key: 'broker_name', align: 'center', sortable: true },
      { title: 'Number of securities', key: 'no_of_securities', align: 'center', sortable: true },
      { title: 'First investment', key: 'first_investment', align: 'center', sortable: true },
      { title: 'Current NAV', key: 'nav', align: 'center', sortable: true },
      {
        title: 'Cash balance',
        key: 'cash',
        align: 'center',
        sortable: false,
        children: currencies.value.map(currency => ({
          title: currency,
          key: `cash_${currency}`,
          align: 'center',
          sortable: true
        })),
      },
      { title: 'IRR', key: 'irr', align: 'center', sortable: true },
      { title: 'Actions', key: 'actions', align: 'end', sortable: false },
    ])

    const headerAlignments = computed(() => {
      const alignments = {};
      headers.value.forEach(header => {
        alignments[header.key] = header.align || 'start';
        if (header.children) {
          header.children.forEach(child => {
            alignments[child.key] = child.align || 'start';
          });
        }
      });
      return alignments;
    });

    const totals = ref({})

    const flattenedHeaders = computed(() => {
      const flattened = []
      headers.value.forEach(header => {
        if (header.children) {
          header.children.forEach(child => {
            flattened.push(child)
          })
        } else {
          flattened.push(header)
        }
      })
      return flattened
    })

    const fetchAccounts = async () => {
      tableLoading.value = true
      try {
        const response = await getAccountsTable({
          page: currentPage.value,
          itemsPerPage: itemsPerPage.value,
          sortBy: sortBy.value[0] || {},
          search: search.value
        })
        accounts.value = response.accounts
        totalItems.value = response.total_items
        currencies.value = [...new Set(accounts.value.flatMap(account => Object.keys(account.cash)))]
        totals.value = response.totals
      } catch (error) {
        handleApiError(error)
      } finally {
        tableLoading.value = false
      }
    }

    const openAddDialog = () => {
      editingAccount.value = null
      showAccountDialog.value = true
    }

    const editAccount = async (item) => {
      try {
        const accountDetails = await getAccountDetails(item.id)
        editingAccount.value = accountDetails
        showAccountDialog.value = true
      } catch (error) {
        handleApiError(error)
      }
    }

    const processDeleteAccount = async (item) => {
      const confirm = window.confirm('Are you sure you want to delete this account?')
      if (confirm) {
        try {
          await deleteAccount(item.id)
          fetchAccounts()
        } catch (error) {
          handleApiError(error)
        }
      }
    }

    const handleAccountAdded = () => {
      fetchAccounts()
    }

    const handleAccountUpdated = () => {
      fetchAccounts()
    }

    onMounted(() => {
      fetchAccounts()
    })

    watch(
      [
        () => store.state.dataRefreshTrigger,
        search,
        itemsPerPage,
        currentPage,
        sortBy
      ],
      () => {
        fetchAccounts()
      },
      { deep: true }
    )

    const showAccountDialog = ref(false)
    const editingAccount = ref(null)

    const addAccount = () => {
      editingAccount.value = null
      showAccountDialog.value = true
    }

    return {
      accounts: accounts,
      loading,
      tableLoading,
      headers,
      itemsPerPage,
      currentPage,
      totalItems,
      sortBy,
      search,
      itemsPerPageOptions,
      pageCount,
      handlePageChange,
      handleItemsPerPageChange,
      handleSortChange,
      openAddDialog,
      editAccount: editAccount,
      processDeleteAccount: processDeleteAccount,
      currencies,
      handleAccountAdded,
      handleAccountUpdated: handleAccountUpdated,
      headerAlignments,
      totals,
      flattenedHeaders,
      showAccountDialog,
      editingAccount,
      addAccount,
    }
  }
}
</script>