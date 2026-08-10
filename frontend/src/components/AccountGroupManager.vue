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

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  getAccountGroups,
  saveAccountGroup,
  deleteAccountGroup,
  updateAccountGroup,
} from '@/services/api'

const emit = defineEmits(['error', 'success'])

const groupForm = ref(null)
const renameForm = ref(null)

const loading = ref(true)
const accountGroups = ref({})
const availableAccounts = ref([]) // Will be populated with user's accounts
const showAddGroupDialog = ref(false)
const showAddAccountToGroupDialog = ref(false)
const isGroupFormValid = ref(false)
const isSaving = ref(false)
const isAddingAccount = ref(false)
const selectedGroup = ref(null)
const selectedGroupName = ref('')
const selectedAccounts = ref([])
const newGroup = ref({
  name: '',
  accounts: [],
})
const showRenameDialog = ref(false)
const isRenameFormValid = ref(false)
const isRenaming = ref(false)
const renameData = ref({
  groupId: null,
  newName: '',
})
const showDeleteConfirmation = ref(false)
const groupToDelete = ref(null)
const isDeleting = ref(false)

const availableAccountsForGroup = computed(() => {
  if (!selectedGroup.value) return availableAccounts.value
  const currentAccounts = new Set(
    accountGroups.value[selectedGroup.value].accounts
  )
  return availableAccounts.value.filter(
    (account) => !currentAccounts.has(account.value)
  )
})
const filteredAvailableAccounts = computed(() => {
  if (
    !selectedGroup.value ||
    !accountGroups.value ||
    !availableAccounts.value
  ) {
    return []
  }

  const currentGroup = accountGroups.value[selectedGroup.value]
  if (!currentGroup) {
    return availableAccounts.value
  }

  // Get IDs of accounts already in the group
  const existingAccountIds = new Set(
    currentGroup.accounts.map((account) => account.id)
  )

  // Filter out accounts that are already in the group
  return availableAccounts.value.filter(
    (account) => !existingAccountIds.has(account.value)
  )
})

function handleError(error) {
  let errorMessage = 'An unexpected error occurred.'
  if (error.response?.data?.error) {
    errorMessage = error.response.data.error
  } else if (error.message) {
    errorMessage = error.message
  }
  emit('error', errorMessage)
}

async function fetchGroups() {
  loading.value = true
  try {
    // Fetch account groups
    const response = await getAccountGroups()
    accountGroups.value = response.groups

    // Update available accounts from response
    availableAccounts.value = response.available_accounts
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

async function saveGroup() {
  isSaving.value = true
  try {
    await saveAccountGroup({
      name: newGroup.value.name,
      accounts: newGroup.value.accounts,
    })
    await fetchGroups()
    showAddGroupDialog.value = false
    groupForm.value?.reset()
    emit('success', 'Group saved successfully')
  } catch (error) {
    handleError(error)
  } finally {
    isSaving.value = false
  }
}

function deleteGroup(groupId) {
  groupToDelete.value = {
    id: groupId,
    name: accountGroups.value[groupId].name,
  }
  showDeleteConfirmation.value = true
}

async function confirmDeleteGroup() {
  if (!groupToDelete.value) return

  isDeleting.value = true
  try {
    await deleteAccountGroup(groupToDelete.value.id)
    await fetchGroups()
    emit('success', 'Group deleted successfully')
    showDeleteConfirmation.value = false
  } catch (error) {
    handleError(error)
  } finally {
    isDeleting.value = false
    groupToDelete.value = null
  }
}

function showAddAccountDialog(groupId) {
  selectedGroup.value = groupId
  selectedGroupName.value = accountGroups.value[groupId].name
  selectedAccounts.value = []
  showAddAccountToGroupDialog.value = true
}

async function addAccountsToGroup() {
  isAddingAccount.value = true
  try {
    const group = accountGroups.value[selectedGroup.value]
    const currentAccountIds = group.accounts.map((account) => account.id)
    await updateAccountGroup({
      id: selectedGroup.value,
      name: group.name,
      accounts: [...currentAccountIds, ...selectedAccounts.value],
    })
    await fetchGroups()
    showAddAccountToGroupDialog.value = false
    emit('success', 'Accounts added successfully')
  } catch (error) {
    handleError(error)
  } finally {
    isAddingAccount.value = false
  }
}

async function removeAccountFromGroup(groupId, accountId) {
  try {
    const group = accountGroups.value[groupId]
    const updatedAccounts = group.accounts
      .filter((account) => account.id !== accountId)
      .map((account) => account.id)

    await updateAccountGroup({
      id: groupId,
      name: group.name,
      accounts: updatedAccounts,
    })
    await fetchGroups()
    emit('success', 'Account removed from group')
  } catch (error) {
    handleError(error)
  }
}

function openRenameDialog(groupId, currentName) {
  renameData.value.groupId = groupId
  renameData.value.newName = currentName
  showRenameDialog.value = true
}

async function renameGroup() {
  isRenaming.value = true
  try {
    const group = accountGroups.value[renameData.value.groupId]
    await updateAccountGroup({
      id: renameData.value.groupId,
      name: renameData.value.newName,
      accounts: group.accounts.map((account) => account.id),
    })
    await fetchGroups()
    showRenameDialog.value = false
    emit('success', 'Group renamed successfully')
  } catch (error) {
    handleError(error)
  } finally {
    isRenaming.value = false
  }
}

onMounted(async () => {
  await fetchGroups()
})
</script>
