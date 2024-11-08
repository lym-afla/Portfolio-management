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
      class="elevation-1"
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
          <td>{{ item.name }}</td>
          <td>{{ item.country }}</td>
          <td>{{ item.comment }}</td>
          <td class="text-right">
            <v-icon small class="mr-2" @click="editBroker(item)">
              mdi-pencil
            </v-icon>
            <v-icon small @click="processDeleteBroker(item)">
              mdi-delete
            </v-icon>
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
import BrokerFormDialog from '@/components/dialogs/BrokerFormDialog.vue'

export default {
  name: 'BrokersPage',
  components: {
    BrokerFormDialog
  },
  setup() {
    const store = useStore()
    const { handleApiError } = useErrorHandler()

    const loading = ref(false)
    const tableLoading = ref(false)
    const brokers = ref([])
    const totalItems = ref(0)
    const currentPage = ref(1)
    const itemsPerPage = ref(10)
    const search = ref('')
    const sortBy = ref([])
    const showBrokerDialog = ref(false)
    const editingBroker = ref(null)

    const headers = [
      { title: 'Name', key: 'name', align: 'start' },
      { title: 'Country', key: 'country', align: 'start' },
      { title: 'Comment', key: 'comment', align: 'start' },
      { title: 'Actions', key: 'actions', align: 'end', sortable: false }
    ]

    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)

    const pageCount = computed(() => Math.ceil(totalItems.value / itemsPerPage.value))

    const handlePageChange = (value) => {
      currentPage.value = value
    }

    const fetchBrokers = async () => {
      tableLoading.value = true
      try {
        const response = await getBrokersTable({
          page: currentPage.value,
          itemsPerPage: itemsPerPage.value,
          search: search.value,
          sortBy: sortBy.value
        })
        brokers.value = response.items
        totalItems.value = response.total_items
      } catch (error) {
        handleApiError(error)
      } finally {
        tableLoading.value = false
      }
    }

    const handleItemsPerPageChange = (value) => {
      itemsPerPage.value = value
      currentPage.value = 1
    }

    const handleSortChange = (value) => {
      sortBy.value = value
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
        sortBy
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
      handleBrokerUpdated
    }
  }
}
</script>

<style scoped>
.nowrap-table :deep(td) {
  white-space: nowrap;
}
</style> 
