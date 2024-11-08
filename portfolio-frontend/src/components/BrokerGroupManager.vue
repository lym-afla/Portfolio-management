<template>
  <v-card class="mb-4">
    <v-card-title class="d-flex align-center">
      Broker Groups
      <v-spacer></v-spacer>
      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        @click="showAddGroupDialog = true"
      >
        Add Group
      </v-btn>
    </v-card-title>

    <v-card-text>
      <v-progress-linear
        v-if="loading"
        indeterminate
        color="primary"
      ></v-progress-linear>

      <v-expansion-panels v-else>
        <v-expansion-panel
          v-for="(group, groupId) in brokerGroups"
          :key="groupId"
        >
          <v-expansion-panel-title>
            <v-icon start>mdi-account-group</v-icon>
            {{ group.name }} ({{ group.brokers.length }} brokers)
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="d-flex align-center mb-4">
              <v-btn
                prepend-icon="mdi-pencil"
                variant="tonal"
                @click="openRenameDialog(groupId, group.name)"
                class="mr-2"
              >
                Rename
              </v-btn>

              <v-btn
                prepend-icon="mdi-plus"
                variant="tonal"
                @click="showAddBrokerDialog(groupId)"
                class="mr-2"
              >
                Add Broker
              </v-btn>

              <v-tooltip location="top">
                <template v-slot:activator="{ props }">
                  <v-btn
                    v-bind="props"
                    icon="mdi-delete"
                    color="error"
                    variant="tonal"
                    @click="deleteGroup(groupId)"
                  ></v-btn>
                </template>
                Delete group
              </v-tooltip>
            </div>

            <v-list>
              <v-list-item
                v-for="brokerId in group.brokers"
                :key="brokerId"
              >
                <v-list-item-title>
                  {{ getBrokerName(brokerId) }}
                </v-list-item-title>
                
                <template v-slot:append>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        @click="removeBrokerFromGroup(groupId, brokerId)"
                      ></v-btn>
                    </template>
                    Remove broker from group
                  </v-tooltip>
                </template>
              </v-list-item>
            </v-list>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card-text>

    <!-- Add Group Dialog -->
    <v-dialog v-model="showAddGroupDialog" max-width="500px">
      <v-card>
        <v-card-title>Add New Group</v-card-title>
        <v-card-text>
          <v-form ref="groupForm" v-model="isGroupFormValid">
            <v-text-field
              v-model="newGroup.name"
              label="Group Name"
              required
              :rules="[v => !!v || 'Group name is required']"
            ></v-text-field>

            <v-select
              v-model="newGroup.brokers"
              :items="availableBrokers"
              label="Select Brokers"
              multiple
              chips
              required
              :rules="[v => v.length > 0 || 'Select at least one broker']"
            ></v-select>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn
            color="primary"
            text
            @click="saveGroup"
            :loading="isSaving"
            :disabled="!isGroupFormValid"
          >
            Save
          </v-btn>
          <v-btn
            color="error"
            text
            @click="showAddGroupDialog = false"
          >
            Cancel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add Broker to Group Dialog -->
    <v-dialog v-model="showAddBrokerToGroupDialog" max-width="500px">
      <v-card>
        <v-card-title>Add Broker to "{{ selectedGroupName }}"</v-card-title>
        <v-card-text>
          <v-select
            v-model="selectedBrokers"
            :items="availableBrokersForGroup"
            label="Select Brokers"
            multiple
            chips
            required
            :rules="[v => v.length > 0 || 'Select at least one broker']"
          ></v-select>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn
            color="primary"
            text
            @click="addBrokersToGroup"
            :loading="isAddingBroker"
          >
            Add
          </v-btn>
          <v-btn
            color="error"
            text
            @click="showAddBrokerToGroupDialog = false"
          >
            Cancel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Rename Group Dialog -->
    <v-dialog v-model="showRenameDialog" max-width="500px">
      <v-card>
        <v-card-title>Rename Group</v-card-title>
        <v-card-text>
          <v-form ref="renameForm" v-model="isRenameFormValid">
            <v-text-field
              v-model="renameData.newName"
              label="New Group Name"
              required
              :rules="[v => !!v || 'Group name is required']"
            ></v-text-field>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn
            color="primary"
            text
            @click="renameGroup"
            :loading="isRenaming"
            :disabled="!isRenameFormValid"
          >
            Save
          </v-btn>
          <v-btn
            color="error"
            text
            @click="showRenameDialog = false"
          >
            Cancel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add confirmation dialog -->
    <v-dialog v-model="showDeleteConfirmation" max-width="400px">
      <v-card>
        <v-card-title class="text-h5">Delete Group</v-card-title>
        <v-card-text>
          Are you sure you want to delete the group "{{ groupToDelete?.name }}"?
          <div class="text-subtitle-2 mt-2 text-red">This action cannot be undone.</div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn
            color="primary"
            variant="text"
            @click="showDeleteConfirmation = false"
          >
            Cancel
          </v-btn>
          <v-btn
            color="error"
            variant="text"
            @click="confirmDeleteGroup"
            :loading="isDeleting"
          >
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script>
import { getBrokerGroups, saveBrokerGroup, deleteBrokerGroup, updateBrokerGroup, getBrokers } from '@/services/api'

export default {
  name: 'BrokerGroupManager',
  
  emits: ['error', 'success'],
  
  data() {
    return {
      loading: true,
      brokerGroups: {},
      availableBrokers: [], // Will be populated with user's brokers
      showAddGroupDialog: false,
      showAddBrokerToGroupDialog: false,
      isGroupFormValid: false,
      isSaving: false,
      isAddingBroker: false,
      selectedGroup: null,
      selectedGroupName: '',
      selectedBrokers: [],
      newGroup: {
        name: '',
        brokers: []
      },
      showRenameDialog: false,
      isRenameFormValid: false,
      isRenaming: false,
      renameData: {
        groupId: null,
        newName: ''
      },
      showDeleteConfirmation: false,
      groupToDelete: null,
      isDeleting: false,
    }
  },

  computed: {
    availableBrokersForGroup() {
      if (!this.selectedGroup) return this.availableBrokers
      const currentBrokers = new Set(this.brokerGroups[this.selectedGroup].brokers)
      return this.availableBrokers.filter(broker => !currentBrokers.has(broker.value))
    }
  },

  methods: {
    handleError(error) {
      let errorMessage = 'An unexpected error occurred.'
      if (error.response?.data?.error) {
        errorMessage = error.response.data.error
      } else if (error.message) {
        errorMessage = error.message
      }
      this.$emit('error', errorMessage)
    },

    async fetchGroups() {
      this.loading = true
      try {
        // Fetch broker groups
        const groupsResponse = await getBrokerGroups()
        this.brokerGroups = groupsResponse.groups

        // Fetch available brokers
        const brokersResponse = await getBrokers()
        this.availableBrokers = brokersResponse.map(broker => ({
          value: broker.id,
          title: broker.name
        }))
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },

    async saveGroup() {
      this.isSaving = true
      try {
        await saveBrokerGroup({
          name: this.newGroup.name,
          brokers: this.newGroup.brokers
        })
        await this.fetchGroups()
        this.showAddGroupDialog = false
        this.$refs.groupForm?.reset()
        this.$emit('success', 'Group saved successfully')
      } catch (error) {
        this.handleError(error)
      } finally {
        this.isSaving = false
      }
    },

    deleteGroup(groupId) {
      this.groupToDelete = {
        id: groupId,
        name: this.brokerGroups[groupId].name
      }
      this.showDeleteConfirmation = true
    },

    async confirmDeleteGroup() {
      if (!this.groupToDelete) return

      this.isDeleting = true
      try {
        await deleteBrokerGroup(this.groupToDelete.id)
        await this.fetchGroups()
        this.$emit('success', 'Group deleted successfully')
        this.showDeleteConfirmation = false
      } catch (error) {
        this.handleError(error)
      } finally {
        this.isDeleting = false
        this.groupToDelete = null
      }
    },

    showAddBrokerDialog(groupId) {
      this.selectedGroup = groupId
      this.selectedGroupName = this.brokerGroups[groupId].name
      this.selectedBrokers = []
      this.showAddBrokerToGroupDialog = true
    },

    async addBrokersToGroup() {
      this.isAddingBroker = true
      try {
        const group = this.brokerGroups[this.selectedGroup]
        await updateBrokerGroup({
          id: this.selectedGroup,
          name: group.name,
          brokers: [...group.brokers, ...this.selectedBrokers]
        })
        await this.fetchGroups()
        this.showAddBrokerToGroupDialog = false
        this.$emit('success', 'Brokers added successfully')
      } catch (error) {
        this.handleError(error)
      } finally {
        this.isAddingBroker = false
      }
    },

    async removeBrokerFromGroup(groupId, brokerId) {
      try {
        const group = this.brokerGroups[groupId]
        const updatedBrokers = group.brokers.filter(id => id !== brokerId)
        await updateBrokerGroup({
          id: groupId,
          name: group.name,
          brokers: updatedBrokers
        })
        await this.fetchGroups()
        this.$emit('success', 'Broker removed from group')
      } catch (error) {
        this.handleError(error)
      }
    },

    getBrokerName(brokerId) {
      const broker = this.availableBrokers.find(b => b.value === brokerId)
      return broker ? broker.title : `Broker ${brokerId}`
    },

    openRenameDialog(groupId, currentName) {
      this.renameData.groupId = groupId
      this.renameData.newName = currentName
      this.showRenameDialog = true
    },

    async renameGroup() {
      this.isRenaming = true
      try {
        const group = this.brokerGroups[this.renameData.groupId]
        await updateBrokerGroup({
          id: this.renameData.groupId,
          name: this.renameData.newName,
          brokers: group.brokers
        })
        await this.fetchGroups()
        this.showRenameDialog = false
        this.$emit('success', 'Group renamed successfully')
      } catch (error) {
        this.handleError(error)
      } finally {
        this.isRenaming = false
      }
    }
  },

  async mounted() {
    await this.fetchGroups()
  }
}
</script> 