<template>
  <div>
    <v-card class="mb-4">
      <v-card-text>
        <v-row align="center" justify="space-between">
          <v-col cols="auto">
            <v-btn color="primary" @click="addSecurity">
              <v-icon left>mdi-plus</v-icon>
              Add Security
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-data-table
      :headers="headers"
      :items="securities"
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
          <td
            v-for="header in headers"
            :key="header.key"
            :class="`text-${headerAlignments[header.key]} ${header.key === 'irr' ? 'font-italic' : ''}`"
          >
            <template v-if="header.key === 'actions'">
              <v-icon small class="mr-2" @click="editSecurity(item)">
                mdi-pencil
              </v-icon>
              <v-icon small @click="processDeleteSecurity(item)">
                mdi-delete
              </v-icon>
            </template>
            <template v-else-if="header.key === 'name'">
              <router-link
                :to="{ name: 'SecurityDetail', params: { id: item.id } }"
                class="text-primary text-decoration-none font-weight-medium"
              >
                {{ item.name }}
              </router-link>
            </template>
            <template v-else>
              {{ item[header.key] }}
            </template>
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
          />
        </div>
      </template>
    </v-data-table>

    <SecurityFormDialog
      v-model="showSecurityDialog"
      :edit-item="editingSecurity"
      @security-added="handleSecurityAdded"
      @security-updated="handleSecurityUpdated"
    />
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { useStore } from 'vuex'
import SecurityFormDialog from '@/components/dialogs/SecurityFormDialog.vue'
import {
  getSecuritiesForDatabase,
  deleteSecurity,
  getSecurityDetails,
} from '@/services/api'
import { useTableSettings } from '@/composables/useTableSettings'
import { useErrorHandler } from '@/composables/useErrorHandler'

export default {
  name: 'SecuritiesPage',
  components: {
    SecurityFormDialog,
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

    const securities = ref([])
    const loading = ref(false)
    const tableLoading = ref(false)
    const dialog = ref(false)
    const editedIndex = ref(-1)
    const editedItem = ref({
      name: '',
      type: '',
      ISIN: '',
      currency: '',
    })
    const defaultItem = {
      name: '',
      type: '',
      ISIN: '',
      currency: '',
    }

    const headers = ref([
      { title: 'Type', key: 'type', align: 'start', sortable: true },
      { title: 'ISIN', key: 'ISIN', align: 'start', sortable: true },
      { title: 'Name', key: 'name', align: 'start', sortable: true },
      {
        title: 'First Investment',
        key: 'first_investment',
        align: 'center',
        sortable: true,
      },
      { title: 'Currency', key: 'currency', align: 'center', sortable: true },
      {
        title: 'Open Position',
        key: 'open_position',
        align: 'center',
        sortable: true,
      },
      {
        title: 'Current Value',
        key: 'current_value',
        align: 'center',
        sortable: true,
      },
      { title: 'Realised', key: 'realized', align: 'center', sortable: true },
      {
        title: 'Unrealised',
        key: 'unrealized',
        align: 'center',
        sortable: true,
      },
      {
        title: 'Capital Distribution',
        key: 'capital_distribution',
        align: 'center',
        sortable: true,
      },
      { title: 'IRR', key: 'irr', align: 'center', sortable: true },
      { title: 'Actions', key: 'actions', align: 'center', sortable: false },
    ])

    const headerAlignments = computed(() => {
      const alignments = {}
      headers.value.forEach((header) => {
        alignments[header.key] = header.align || 'start'
      })
      return alignments
    })

    const formTitle = computed(() => {
      return editedIndex.value === -1 ? 'New Security' : 'Edit Security'
    })

    const totalItems = ref(0)
    const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
    const pageCount = computed(() =>
      Math.ceil(totalItems.value / itemsPerPage.value)
    )

    const fetchSecurities = async () => {
      tableLoading.value = true
      console.log(
        'fetching securities',
        currentPage.value,
        itemsPerPage.value,
        sortBy.value,
        search.value
      )
      try {
        const response = await getSecuritiesForDatabase({
          page: currentPage.value,
          itemsPerPage: itemsPerPage.value,
          sortBy: sortBy.value[0] || {},
          search: search.value,
        })
        securities.value = response.securities
        totalItems.value = response.total_items
      } catch (error) {
        handleApiError(error)
      } finally {
        tableLoading.value = false
      }
    }

    const showSecurityDialog = ref(false)
    const editingSecurity = ref(null)

    const addSecurity = () => {
      editingSecurity.value = null
      showSecurityDialog.value = true
    }

    const editSecurity = async (item) => {
      try {
        const securityDetails = await getSecurityDetails(item.id)
        editingSecurity.value = securityDetails
        showSecurityDialog.value = true
      } catch (error) {
        handleApiError(error)
      }
    }

    const handleSecurityAdded = (newSecurity) => {
      console.log('newSecurity added:', newSecurity)
      fetchSecurities()
    }

    const handleSecurityUpdated = (updatedSecurity) => {
      console.log('updatedSecurity:', updatedSecurity)
      fetchSecurities()
    }

    const processDeleteSecurity = async (item) => {
      const confirm = window.confirm(
        'Are you sure you want to delete this security?'
      )
      if (confirm) {
        try {
          await deleteSecurity(item.id)
          fetchSecurities()
        } catch (error) {
          handleApiError(error)
        }
      }
    }

    onMounted(() => {
      fetchSecurities()
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
        fetchSecurities()
      },
      { deep: true }
    )

    return {
      securities,
      loading,
      tableLoading,
      dialog,
      editedIndex,
      editedItem,
      defaultItem,
      headers,
      formTitle,
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
      showSecurityDialog,
      editingSecurity,
      addSecurity,
      editSecurity,
      handleSecurityAdded,
      handleSecurityUpdated,
      processDeleteSecurity,
      headerAlignments,
    }
  },
}
</script>
