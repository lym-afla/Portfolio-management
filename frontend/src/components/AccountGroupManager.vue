<template>
  <v-card class="mb-4">
    <v-card-title class="d-flex align-center">
      Broker Account Groups
      <v-spacer />
      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        @click="showAddGroupDialog = true"
      >
        Add Group
      </v-btn>
    </v-card-title>

    <v-card-text>
      <v-progress-linear v-if="loading" indeterminate color="primary" />

      <v-expansion-panels v-else>
        <v-expansion-panel
          v-for="(group, groupId) in accountGroups"
          :key="groupId"
        >
          <v-expansion-panel-title>
            <v-icon start>mdi-account-group</v-icon>
            {{ group.name }} ({{ group.accounts.length }} accounts)
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
                @click="showAddAccountDialog(groupId)"
                class="mr-2"
              >
                Add Account
              </v-btn>

              <v-tooltip location="top">
                <template v-slot:activator="{ props }">
                  <v-btn
                    v-bind="props"
                    icon="mdi-delete"
                    color="error"
                    variant="tonal"
                    @click="deleteGroup(groupId)"
                  />
                </template>
                Delete group
              </v-tooltip>
            </div>

            <v-list>
              <v-list-item v-for="account in group.accounts" :key="account.id">
                <v-list-item-title>
                  {{ account.name }}
                </v-list-item-title>

                <template v-slot:append>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon="mdi-delete"
                        variant="text"
                        color="error"
                        @click="removeAccountFromGroup(groupId, account.id)"
                      />
                    </template>
                    Remove account from group
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
              :rules="[(v) => !!v || 'Group name is required']"
            />

            <v-select
              v-model="newGroup.accounts"
              :items="availableAccounts"
              label="Select Accounts"
              multiple
              chips
              required
              :rules="[(v) => v.length > 0 || 'Select at least one account']"
            />
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            color="primary"
            text
            @click="saveGroup"
            :loading="isSaving"
            :disabled="!isGroupFormValid"
          >
            Save
          </v-btn>
          <v-btn color="error" text @click="showAddGroupDialog = false">
            Cancel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add Account to Group Dialog -->
    <v-dialog v-model="showAddAccountToGroupDialog" max-width="500px">
      <v-card>
        <v-card-title> Add Accounts to {{ selectedGroupName }} </v-card-title>
        <v-card-text>
          <v-select
            v-model="selectedAccounts"
            :items="filteredAvailableAccounts"
            item-title="title"
            item-value="value"
            label="Select accounts"
            multiple
            chips
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            color="primary"
            :loading="isAddingAccount"
            @click="addAccountsToGroup"
          >
            Add
          </v-btn>
          <v-btn @click="showAddAccountToGroupDialog = false">Cancel</v-btn>
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
              :rules="[(v) => !!v || 'Group name is required']"
            />
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            color="primary"
            text
            @click="renameGroup"
            :loading="isRenaming"
            :disabled="!isRenameFormValid"
          >
            Save
          </v-btn>
          <v-btn color="error" text @click="showRenameDialog = false">
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
          <div class="text-subtitle-2 mt-2 text-red">
            This action cannot be undone.
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
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
import {
  getAccountGroups,
  saveAccountGroup,
  deleteAccountGroup,
  updateAccountGroup,
} from '@/services/api'

export default {
  name: 'AccountGroupManager',

  emits: ['error', 'success'],

  data() {
    return {
      loading: true,
      accountGroups: {},
      availableAccounts: [], // Will be populated with user's accounts
      showAddGroupDialog: false,
      showAddAccountToGroupDialog: false,
      isGroupFormValid: false,
      isSaving: false,
      isAddingAccount: false,
      selectedGroup: null,
      selectedGroupName: '',
      selectedAccounts: [],
      newGroup: {
        name: '',
        accounts: [],
      },
      showRenameDialog: false,
      isRenameFormValid: false,
      isRenaming: false,
      renameData: {
        groupId: null,
        newName: '',
      },
      showDeleteConfirmation: false,
      groupToDelete: null,
      isDeleting: false,
    }
  },

  computed: {
    availableAccountsForGroup() {
      if (!this.selectedGroup) return this.availableAccounts
      const currentAccounts = new Set(
        this.accountGroups[this.selectedGroup].accounts
      )
      return this.availableAccounts.filter(
        (account) => !currentAccounts.has(account.value)
      )
    },
    filteredAvailableAccounts() {
      if (
        !this.selectedGroup ||
        !this.accountGroups ||
        !this.availableAccounts
      ) {
        return []
      }

      const currentGroup = this.accountGroups[this.selectedGroup]
      if (!currentGroup) {
        return this.availableAccounts
      }

      // Get IDs of accounts already in the group
      const existingAccountIds = new Set(
        currentGroup.accounts.map((account) => account.id)
      )

      // Filter out accounts that are already in the group
      return this.availableAccounts.filter(
        (account) => !existingAccountIds.has(account.value)
      )
    },
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
        // Fetch account groups
        const response = await getAccountGroups()
        this.accountGroups = response.groups

        // Update available accounts from response
        this.availableAccounts = response.available_accounts
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },

    async saveGroup() {
      this.isSaving = true
      try {
        await saveAccountGroup({
          name: this.newGroup.name,
          accounts: this.newGroup.accounts,
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
        name: this.accountGroups[groupId].name,
      }
      this.showDeleteConfirmation = true
    },

    async confirmDeleteGroup() {
      if (!this.groupToDelete) return

      this.isDeleting = true
      try {
        await deleteAccountGroup(this.groupToDelete.id)
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

    showAddAccountDialog(groupId) {
      this.selectedGroup = groupId
      this.selectedGroupName = this.accountGroups[groupId].name
      this.selectedAccounts = []
      this.showAddAccountToGroupDialog = true
    },

    async addAccountsToGroup() {
      this.isAddingAccount = true
      try {
        const group = this.accountGroups[this.selectedGroup]
        const currentAccountIds = group.accounts.map((account) => account.id)
        await updateAccountGroup({
          id: this.selectedGroup,
          name: group.name,
          accounts: [...currentAccountIds, ...this.selectedAccounts],
        })
        await this.fetchGroups()
        this.showAddAccountToGroupDialog = false
        this.$emit('success', 'Accounts added successfully')
      } catch (error) {
        this.handleError(error)
      } finally {
        this.isAddingAccount = false
      }
    },

    async removeAccountFromGroup(groupId, accountId) {
      try {
        const group = this.accountGroups[groupId]
        const updatedAccounts = group.accounts
          .filter((account) => account.id !== accountId)
          .map((account) => account.id)

        await updateAccountGroup({
          id: groupId,
          name: group.name,
          accounts: updatedAccounts,
        })
        await this.fetchGroups()
        this.$emit('success', 'Account removed from group')
      } catch (error) {
        this.handleError(error)
      }
    },

    openRenameDialog(groupId, currentName) {
      this.renameData.groupId = groupId
      this.renameData.newName = currentName
      this.showRenameDialog = true
    },

    async renameGroup() {
      this.isRenaming = true
      try {
        const group = this.accountGroups[this.renameData.groupId]
        await updateAccountGroup({
          id: this.renameData.groupId,
          name: this.renameData.newName,
          accounts: group.accounts.map((account) => account.id),
        })
        await this.fetchGroups()
        this.showRenameDialog = false
        this.$emit('success', 'Group renamed successfully')
      } catch (error) {
        this.handleError(error)
      } finally {
        this.isRenaming = false
      }
    },
  },

  async mounted() {
    await this.fetchGroups()
  },
}
</script>
