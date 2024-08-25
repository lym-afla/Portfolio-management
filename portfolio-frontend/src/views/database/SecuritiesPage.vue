<template>
    <div>
      <v-card class="mb-4">
        <v-card-text>
          <v-row align="center" justify="space-between">
            <v-col cols="auto">
              <AddSecurityButton @add-security="openAddDialog" />
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
            <td v-for="header in headers" :key="header.key" :class="`text-${headerAlignments[header.key]} ${header.key === 'irr' ? 'font-italic' : ''}`">
              <template v-if="header.key === 'actions'">
                <v-icon small class="mr-2" @click="editSecurity(item)">
                  mdi-pencil
                </v-icon>
                <v-icon small @click="processDeleteSecurity(item)">
                  mdi-delete
                </v-icon>
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
            ></v-pagination>
          </div>
        </template>
      </v-data-table>
  
      <!-- Add Security Dialog -->
      <v-dialog v-model="dialog" max-width="500px">
        <v-card>
          <v-card-title>
            <span class="text-h5">{{ formTitle }}</span>
          </v-card-title>
          <v-card-text>
            <v-container>
              <v-row>
                <v-col cols="12" sm="6" md="4">
                  <v-text-field v-model="editedItem.name" label="Name"></v-text-field>
                </v-col>
                <v-col cols="12" sm="6" md="4">
                  <v-text-field v-model="editedItem.type" label="Type"></v-text-field>
                </v-col>
                <v-col cols="12" sm="6" md="4">
                  <v-text-field v-model="editedItem.ISIN" label="ISIN"></v-text-field>
                </v-col>
                <v-col cols="12" sm="6" md="4">
                  <v-text-field v-model="editedItem.currency" label="Currency"></v-text-field>
                </v-col>
              </v-row>
            </v-container>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn color="blue darken-1" text @click="close">Cancel</v-btn>
            <v-btn color="blue darken-1" text @click="save">Save</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>
  </template>
  
  <script>
  import { ref, computed, onMounted, watch } from 'vue'
  import { useStore } from 'vuex'
  import AddSecurityButton from '@/components/buttons/AddSecurity.vue'
  import { getSecuritiesForDatabase, createSecurity, updateSecurity, deleteSecurity } from '@/services/api'
  import { useTableSettings } from '@/composables/useTableSettings'
  import { useErrorHandler } from '@/composables/useErrorHandler'
  
  export default {
    name: 'SecuritiesPage',
    components: {
      AddSecurityButton
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
        currency: ''
      })
      const defaultItem = {
        name: '',
        type: '',
        ISIN: '',
        currency: ''
      }
  
      const headers = ref([
        { title: 'Type', key: 'type', align: 'start', sortable: true },
        { title: 'ISIN', key: 'ISIN', align: 'start', sortable: true },
        { title: 'Name', key: 'name', align: 'start', sortable: true },
        { title: 'First Investment', key: 'first_investment', align: 'center', sortable: true },
        { title: 'Currency', key: 'currency', align: 'center', sortable: true },
        { title: 'Open Position', key: 'open_position', align: 'center', sortable: true },
        { title: 'Current Value', key: 'current_value', align: 'center', sortable: true },
        { title: 'Realised', key: 'realized', align: 'center', sortable: true },
        { title: 'Unrealised', key: 'unrealized', align: 'center', sortable: true },
        { title: 'Capital Distribution', key: 'capital_distribution', align: 'center', sortable: true },
        { title: 'IRR', key: 'irr', align: 'center', sortable: true },
        { title: 'Actions', key: 'actions', align: 'center', sortable: false },
      ])
  
      const headerAlignments = computed(() => {
        const alignments = {};
        headers.value.forEach(header => {
          alignments[header.key] = header.align || 'start';
        });
        return alignments;
      });
  
      const formTitle = computed(() => {
        return editedIndex.value === -1 ? 'New Security' : 'Edit Security'
      })
  
      const totalItems = ref(0)
      const itemsPerPageOptions = computed(() => store.state.itemsPerPageOptions)
      const pageCount = computed(() => Math.ceil(totalItems.value / itemsPerPage.value))
  
      const fetchSecurities = async () => {
        tableLoading.value = true
        try {
          const response = await getSecuritiesForDatabase({
            page: currentPage.value,
            itemsPerPage: itemsPerPage.value,
            sortBy: sortBy.value[0] || {},
            search: search.value
          })
          securities.value = response.securities
          totalItems.value = response.total_items
        } catch (error) {
          handleApiError(error)
        } finally {
          tableLoading.value = false
        }
      }
  
      const openAddDialog = () => {
        editedIndex.value = -1
        editedItem.value = Object.assign({}, defaultItem)
        dialog.value = true
      }
  
      const editSecurity = (item) => {
        editedIndex.value = securities.value.indexOf(item)
        editedItem.value = Object.assign({}, item)
        dialog.value = true
      }
  
      const processDeleteSecurity = async (item) => {
        const confirm = window.confirm('Are you sure you want to delete this security?')
        if (confirm) {
          try {
            await deleteSecurity(item.id)
            fetchSecurities()
          } catch (error) {
            handleApiError(error)
          }
        }
      }
  
      const close = () => {
        dialog.value = false
        editedIndex.value = -1
        editedItem.value = Object.assign({}, defaultItem)
      }
  
      const save = async () => {
        try {
          if (editedIndex.value > -1) {
            await updateSecurity(editedItem.value.id, editedItem.value)
          } else {
            await createSecurity(editedItem.value)
          }
          close()
          fetchSecurities()
        } catch (error) {
          handleApiError(error)
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
          sortBy
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
        openAddDialog,
        editSecurity,
        processDeleteSecurity,
        close,
        save,
        headerAlignments,
      }
    }
  }
  </script>