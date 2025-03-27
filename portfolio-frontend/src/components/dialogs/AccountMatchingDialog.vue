<template>
  <v-dialog v-model="dialogModel" persistent max-width="800px">
    <v-card>
      <v-card-title class="text-h5">
        Match Accounts for {{ brokerName }}
      </v-card-title>

      <v-card-text>
        <v-alert
          v-if="errorMessage"
          type="error"
          variant="tonal"
          class="mb-4"
          closable
          @click:close="errorMessage = ''"
        >
          {{ errorMessage }}
        </v-alert>

        <p class="text-body-1 mb-4">
          Match {{ brokerName }} API accounts to your database accounts. You can
          create multiple pairs by using the + button.
        </p>

        <!-- Account Matching Pairs -->
        <div
          v-for="(pair, index) in accountPairs"
          :key="index"
          class="account-pair mb-4"
        >
          <v-card variant="outlined" class="pa-4">
            <div class="d-flex align-center mb-2">
              <h3 class="text-h6">Matching Pair #{{ index + 1 }}</h3>
              <v-spacer />
              <v-btn
                v-if="index > 0"
                icon="mdi-delete"
                variant="text"
                color="error"
                density="compact"
                @click="removePair(index)"
              />
            </div>

            <v-row>
              <!-- Tinkoff Account -->
              <v-col cols="12" md="5">
                <v-select
                  v-model="pair.tinkoffAccount"
                  :items="availableTinkoffAccounts(index)"
                  item-title="name"
                  item-value="id"
                  return-object
                  label="Tinkoff API Account"
                  :rules="[(v) => !!v || 'Please select an account']"
                >
                  <template v-slot:item="{ item, props }">
                    <v-list-item v-bind="props">
                      <template v-slot:prepend>
                        <v-icon color="primary">mdi-bank</v-icon>
                      </template>
                      <v-list-item-subtitle>
                        ID: {{ item.raw.id }} | Opened:
                        {{ item.raw.opened_date }}
                      </v-list-item-subtitle>
                    </v-list-item>
                  </template>
                </v-select>
              </v-col>

              <!-- Connection Arrow -->
              <v-col
                cols="12"
                md="2"
                class="d-flex justify-center align-center"
              >
                <v-icon size="x-large" color="primary"
                  >mdi-arrow-right-bold</v-icon
                >
              </v-col>

              <!-- Database Account -->
              <v-col cols="12" md="5">
                <v-select
                  v-model="pair.dbAccount"
                  :items="availableDbAccounts(index)"
                  item-title="name"
                  item-value="id"
                  return-object
                  label="Database Account"
                  :rules="[(v) => !!v || 'Please select an account']"
                >
                  <template v-slot:item="{ item, props }">
                    <v-list-item v-bind="props">
                      <template v-slot:prepend>
                        <v-icon color="secondary">mdi-database</v-icon>
                      </template>
                      <v-list-item-subtitle>
                        ID: {{ item.raw.id }}
                        {{ item.raw.comment ? `| ${item.raw.comment}` : '' }}
                      </v-list-item-subtitle>
                    </v-list-item>
                  </template>
                </v-select>
              </v-col>
            </v-row>
          </v-card>
        </div>

        <!-- Add More Pairs Button -->
        <v-btn
          block
          variant="outlined"
          color="primary"
          prepend-icon="mdi-plus"
          @click="addPair"
          :disabled="!canAddMorePairs"
          class="mb-4"
        >
          Add Another Mapping
        </v-btn>

        <!-- Create New Account Option -->
        <v-card variant="outlined" class="mt-4 pa-4">
          <v-checkbox
            v-model="createNewAccount"
            label="Create new account instead"
            @change="handleCreateNewChange"
          />

          <v-expand-transition>
            <div v-if="createNewAccount">
              <v-select
                v-model="newAccountTinkoffAccount"
                :items="remainingTinkoffAccounts"
                item-title="name"
                item-value="id"
                return-object
                label="Tinkoff API Account"
                :rules="[(v) => !!v || 'Please select an account']"
                class="mb-3"
              >
                <template v-slot:item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template v-slot:prepend>
                      <v-icon color="primary">mdi-bank</v-icon>
                    </template>
                    <v-list-item-subtitle>
                      ID: {{ item.raw.id }} | Opened: {{ item.raw.opened_date }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </template>
              </v-select>

              <v-text-field
                v-model="newAccountName"
                label="New Account Name"
                :rules="[(v) => !!v || 'Name is required']"
                required
              />

              <v-textarea
                v-model="newAccountComment"
                label="Comment (optional)"
                rows="2"
              />
            </div>
          </v-expand-transition>
        </v-card>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn color="error" variant="text" @click="closeDialog">
          Cancel
        </v-btn>
        <v-btn color="primary" :disabled="!isValid" @click="confirmSelection">
          Confirm
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed } from 'vue'

export default {
  name: 'AccountMatchingDialog',

  props: {
    modelValue: Boolean,
    brokerName: {
      type: String,
      default: 'Broker',
      required: false,
    },
    tinkoffAccounts: {
      type: Array,
      required: true,
    },
    dbAccounts: {
      type: Array,
      required: true,
    },
  },

  emits: ['update:modelValue', 'accounts-matched', 'create-account'],

  setup(props, { emit }) {
    // Account pairs for matching
    const accountPairs = ref([{ tinkoffAccount: null, dbAccount: null }])

    // Create new account fields
    const createNewAccount = ref(false)
    const newAccountName = ref('')
    const newAccountComment = ref('')
    const newAccountTinkoffAccount = ref(null)
    const errorMessage = ref('')

    const dialogModel = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value),
    })

    // Function to check which Tinkoff accounts are available for a specific pair
    const availableTinkoffAccounts = (pairIndex) => {
      return props.tinkoffAccounts.filter((account) => {
        // Check if this account is used in any other pair
        return !accountPairs.value.some(
          (pair, index) =>
            index !== pairIndex &&
            pair.tinkoffAccount &&
            pair.tinkoffAccount.id === account.id
        )
      })
    }

    // Function to check which DB accounts are available for a specific pair
    const availableDbAccounts = (pairIndex) => {
      return props.dbAccounts.filter((account) => {
        // Check if this account is used in any other pair
        return !accountPairs.value.some(
          (pair, index) =>
            index !== pairIndex &&
            pair.dbAccount &&
            pair.dbAccount.id === account.id
        )
      })
    }

    // Computed to get remaining Tinkoff accounts for creating new accounts
    const remainingTinkoffAccounts = computed(() => {
      return props.tinkoffAccounts.filter((account) => {
        return !accountPairs.value.some(
          (pair) => pair.tinkoffAccount && pair.tinkoffAccount.id === account.id
        )
      })
    })

    const canAddMorePairs = computed(() => {
      // Can add more pairs if there are available accounts on both sides
      return (
        remainingTinkoffAccounts.value.length > 0 &&
        availableDbAccounts(accountPairs.value.length).length > 0
      )
    })

    const isValid = computed(() => {
      if (createNewAccount.value) {
        return newAccountTinkoffAccount.value && newAccountName.value.trim()
      }

      // Check if all pairs have both accounts selected
      return (
        accountPairs.value.length > 0 &&
        accountPairs.value.every(
          (pair) => pair.tinkoffAccount && pair.dbAccount
        )
      )
    })

    const addPair = () => {
      accountPairs.value.push({ tinkoffAccount: null, dbAccount: null })
    }

    const removePair = (index) => {
      accountPairs.value.splice(index, 1)
    }

    const handleCreateNewChange = (value) => {
      if (value) {
        // Reset the pairs if switching to create mode
        newAccountTinkoffAccount.value = null
      } else {
        // Reset new account fields if switching back
        newAccountName.value = ''
        newAccountComment.value = ''
        newAccountTinkoffAccount.value = null
      }
    }

    const confirmSelection = () => {
      try {
        if (createNewAccount.value) {
          if (!newAccountTinkoffAccount.value) {
            errorMessage.value = 'Please select a Tinkoff account'
            return
          }

          emit('create-account', {
            tinkoff_account: newAccountTinkoffAccount.value,
            name: newAccountName.value,
            comment: newAccountComment.value,
          })
        } else {
          // Validate that we have at least one complete pair
          if (
            !accountPairs.value.some(
              (pair) => pair.tinkoffAccount && pair.dbAccount
            )
          ) {
            errorMessage.value =
              'Please create at least one account matching pair'
            return
          }

          // Format pairs as expected by the backend
          const matchedPairs = accountPairs.value
            .filter((pair) => pair.tinkoffAccount && pair.dbAccount)
            .map((pair) => ({
              tinkoff_account_id: pair.tinkoffAccount.id,
              db_account_id: pair.dbAccount.id,
            }))

          emit('accounts-matched', {
            pairs: matchedPairs,
          })
        }
        closeDialog()
      } catch (error) {
        console.error('Error in confirmSelection:', error)
        errorMessage.value = 'An error occurred while processing your selection'
      }
    }

    const closeDialog = () => {
      dialogModel.value = false
      accountPairs.value = [{ tinkoffAccount: null, dbAccount: null }]
      createNewAccount.value = false
      newAccountName.value = ''
      newAccountComment.value = ''
      newAccountTinkoffAccount.value = null
      errorMessage.value = ''
    }

    return {
      dialogModel,
      accountPairs,
      createNewAccount,
      newAccountName,
      newAccountComment,
      newAccountTinkoffAccount,
      errorMessage,
      isValid,
      canAddMorePairs,
      availableTinkoffAccounts,
      availableDbAccounts,
      remainingTinkoffAccounts,
      addPair,
      removePair,
      handleCreateNewChange,
      confirmSelection,
      closeDialog,
    }
  },
}
</script>

<style scoped>
.account-pair {
  position: relative;
}
</style>
