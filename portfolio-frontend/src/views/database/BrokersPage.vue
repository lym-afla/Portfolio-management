<template>
  <div>
    <v-overlay :model-value="loading" class="align-center justify-center">
      <v-progress-circular color="primary" indeterminate size="64" />
    </v-overlay>

    <v-card class="mb-4">
      <v-card-text>
        <v-row align="center" justify="space-between">
          <v-col cols="auto">
            <v-btn color="primary" @click="openAddDialog">
              <v-icon left>mdi-plus</v-icon>
              Add Broker
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-data-table
      :headers="headers"
      :items="brokers"
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
            />
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
            />
          </v-col>
        </v-toolbar>
      </template>

      <template #item="{ item }">
        <tr>
          <td :class="`text-${headerAlignments.name}`">{{ item.name }}</td>
          <td :class="`text-${headerAlignments.country}`">
            {{ item.country }}
          </td>
          <td :class="`text-${headerAlignments.no_of_accounts}`">
            {{ item.no_of_accounts }}
          </td>
          <td :class="`text-${headerAlignments.no_of_securities}`">
            {{ item.no_of_securities }}
          </td>
          <td :class="`text-${headerAlignments.first_investment}`">
            {{ item.first_investment }}
          </td>
          <td :class="`text-${headerAlignments.nav}`">{{ item.nav }}</td>
          <td :class="`text-${headerAlignments.cash}`">{{ item.cash }}</td>
          <td :class="`text-${headerAlignments.irr} font-italic`">
            {{ item.irr }}
          </td>
          <td :class="`text-${headerAlignments.actions}`">
            <v-icon small class="mr-2" @click="editBroker(item)">
              mdi-pencil
            </v-icon>
            <v-icon small @click="processDeleteBroker(item)">
              mdi-delete
            </v-icon>
          </td>
        </tr>
      </template>

      <template #tfoot>
        <tfoot>
          <tr class="font-weight-bold">
            <td
              v-for="header in headers"
              :key="header.key"
              :class="[
                'text-' + header.align,
                header.key === 'irr' ? 'font-italic' : '',
              ]"
            >
              <template v-if="header.key === 'name'"> TOTAL </template>
              <template
                v-else-if="
                  [
                    'no_of_accounts',
                    'no_of_securities',
                    'nav',
                    'cash',
                    'irr',
                  ].includes(header.key)
                "
              >
                {{ totals[header.key] }}
              </template>
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
          />
        </div>
      </template>
    </v-data-table>

    <BrokerFormDialog
      v-model="showBrokerDialog"
      :edit-item="editingBroker"
      @broker-added="handleBrokerAdded"
      @broker-updated="handleBrokerUpdated"
    />
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { useStore } from 'vuex'
import { getBrokersTable, deleteBroker } from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useTableSettings } from '@/composables/useTableSettings'
import BrokerFormDialog from '@/components/dialogs/BrokerFormDialog.vue'

export default {
  name: 'BrokersPage',
  components: {
    BrokerFormDialog,
  },
  setup() {
    const store = useStore()
    const { handleApiError } = useErrorHandler()

    const {
      itemsPerPage,
      currentPage,
      sortBy,
      search,
      handlePageChange,
      handleItemsPerPageChange,
      handleSortChange,
    } = useTableSettings()

    const loading = ref(false)
    const tableLoading = ref(false)
    const brokers = ref([])
    const totalItems = ref(0)
    const showBrokerDialog = ref(false)
    const editingBroker = ref(null)
    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
    const pageCount = computed(() =>
      Math.ceil(totalItems.value / itemsPerPage.value)
    )
    const totals = ref({})

    const headers = [
      { title: 'Name', key: 'name', align: 'start', sortable: true },
      { title: 'Country', key: 'country', align: 'center', sortable: true },
      {
        title: 'Accounts',
        key: 'no_of_accounts',
        align: 'center',
        sortable: true,
      },
      {
        title: 'Securities',
        key: 'no_of_securities',
        align: 'center',
        sortable: true,
      },
      {
        title: 'First Investment',
        key: 'first_investment',
        align: 'center',
        sortable: true,
      },
      { title: 'Total NAV', key: 'nav', align: 'center', sortable: true },
      { title: 'Cash', key: 'cash', align: 'center', sortable: true },
      { title: 'IRR', key: 'irr', align: 'center', sortable: true },
      { title: 'Actions', key: 'actions', align: 'end', sortable: false },
    ]

    const headerAlignments = computed(() => {
      const alignments = {}
      headers.forEach((header) => {
        alignments[header.key] = header.align || 'start'
      })
      return alignments
    })

    const fetchBrokers = async () => {
      tableLoading.value = true
      try {
        const response = await getBrokersTable({
          page: currentPage.value,
          itemsPerPage: itemsPerPage.value,
          sortBy: sortBy.value[0] || {},
          search: search.value,
        })
        brokers.value = response.items
        totalItems.value = response.total_items
        totals.value = response.totals
      } catch (error) {
        handleApiError(error)
      } finally {
        tableLoading.value = false
      }
    }

    const openAddDialog = () => {
      editingBroker.value = null
      showBrokerDialog.value = true
    }

    const editBroker = (item) => {
      editingBroker.value = item
      showBrokerDialog.value = true
    }

    const processDeleteBroker = async (item) => {
      if (confirm(`Are you sure you want to delete broker "${item.name}"?`)) {
        try {
          await deleteBroker(item.id)
          await fetchBrokers()
        } catch (error) {
          handleApiError(error)
        }
      }
    }

    const handleBrokerAdded = () => {
      fetchBrokers()
    }

    const handleBrokerUpdated = () => {
      fetchBrokers()
    }

    onMounted(() => {
      fetchBrokers()
    })

    watch(
      [
        () => store.state.dataRefreshTrigger,
        search,
        itemsPerPage,
        currentPage,
        sortBy,
      ],
      () => {
        fetchBrokers()
      },
      { deep: true }
    )

    return {
      loading,
      tableLoading,
      brokers,
      headers,
      itemsPerPage,
      currentPage,
      totalItems,
      sortBy,
      search,
      itemsPerPageOptions,
      pageCount,
      handlePageChange,
      showBrokerDialog,
      editingBroker,
      handleItemsPerPageChange,
      handleSortChange,
      openAddDialog,
      editBroker,
      processDeleteBroker,
      handleBrokerAdded,
      handleBrokerUpdated,
      headerAlignments,
      totals,
    }
  },
}
</script>

<style scoped>
.nowrap-table :deep(td) {
  white-space: nowrap;
}
</style>
