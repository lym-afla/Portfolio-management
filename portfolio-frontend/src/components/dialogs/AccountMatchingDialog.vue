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

        <!-- Already Matched Accounts Section -->
        <v-card v-if="matchedPairs && matchedPairs.length > 0" variant="outlined" class="mb-4 pa-4">
          <div class="d-flex align-center mb-2">
            <h3 class="text-h6">Already Matched Accounts</h3>
            <v-spacer />
            <v-chip color="success" class="ml-2">{{ matchedPairs.length }} matched</v-chip>
          </div>
          
          <v-list>
            <v-list-item v-for="pair in matchedPairs" :key="`matched-${pair.tinkoff_account_id}`">
              <template v-slot:prepend>
                <v-icon color="success">mdi-check-circle</v-icon>
              </template>
              <v-list-item-title class="font-weight-bold">
                {{ pair.tinkoff_account?.name || getTinkoffAccountName(pair.tinkoff_account_id) }} → 
                {{ pair.db_account?.name || getDbAccountName(pair.db_account_id) }}
              </v-list-item-title>
              <v-list-item-subtitle>
                Tinkoff ID: {{ pair.tinkoff_account_id }} | DB ID: {{ pair.db_account_id }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
          
          <v-btn
            v-if="matchedPairs.length > 0" 
            color="success"
            variant="tonal"
            class="mt-3"
            prepend-icon="mdi-check-all"
            @click="continueWithExistingMatches"
          >
            Continue with existing matches only
          </v-btn>
        </v-card>
        
        <!-- Accounts to Match Section -->
        <div v-if="hasUnmatchedAccounts" class="mb-4">
          <h3 class="text-h6 mb-3">Match Remaining Accounts</h3>
          
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
        </div>
        
        <!-- No Remaining Accounts Message -->
        <div v-if="!hasUnmatchedAccounts && (!matchedPairs || matchedPairs.length === 0)" class="text-center pa-4">
          <v-icon size="large" color="warning">mdi-information</v-icon>
          <p class="text-h6 mt-2">No accounts available to match</p>
          <p class="text-body-1">All Tinkoff accounts are already matched or there are no accounts to match.</p>
        </div>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn color="error" variant="text" @click="closeDialog">
          Cancel
        </v-btn>
        <v-btn color="primary" :disabled="!isValid" @click="confirmSelection">
          {{ matchedPairs && matchedPairs.length > 0 ? 'Confirm New Matches' : 'Confirm' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import logger from '@/utils/logger'

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
    matchedPairs: {
      type: Array,
      default: () => [],
    },
  },

  emits: ['update:modelValue', 'accounts-matched', 'create-account', 'use-existing-matches'],

  setup(props, { emit }) {
    // Add debugging onMounted hook
    onMounted(() => {
      logger.debug('AccountMatchingDialog', 'Component mounted with data:')
      logger.debug('AccountMatchingDialog', 'matchedPairs:', props.matchedPairs)
      logger.debug('AccountMatchingDialog', 'tinkoffAccounts:', props.tinkoffAccounts)
      logger.debug('AccountMatchingDialog', 'dbAccounts:', props.dbAccounts)
      
      // Log detailed structure of matched pairs
      logMatchedPairsStructure()
      
      // Check if IDs in matchedPairs exist in the accounts arrays
      if (props.matchedPairs && props.matchedPairs.length > 0) {
        props.matchedPairs.forEach(pair => {
          const tinkoffExists = props.tinkoffAccounts.some(acc => String(acc.id) === String(pair.tinkoff_account_id))
          const dbExists = props.dbAccounts.some(acc => String(acc.id) === String(pair.db_account_id))
          
          logger.debug('AccountMatchingDialog', `Pair check - Tinkoff ID: ${pair.tinkoff_account_id} exists: ${tinkoffExists}, DB ID: ${pair.db_account_id} exists: ${dbExists}`)
          
          // Check if pair contains names directly
          if (pair.tinkoff_account?.name || pair.db_account?.name) {
            logger.info('AccountMatchingDialog', 'Found embedded names in matchedPairs:', 
                        { tinkoff: pair.tinkoff_account?.name, db: pair.db_account?.name })
          }
        })
      }
    })
    
    // Helper to log detailed structure of matched pairs
    const logMatchedPairsStructure = () => {
      if (!props.matchedPairs || props.matchedPairs.length === 0) {
        logger.debug('AccountMatchingDialog', 'No matched pairs available')
        return
      }
      
      logger.group('AccountMatchingDialog - Matched Pairs Structure')
      props.matchedPairs.forEach((pair, index) => {
        logger.debug('AccountMatchingDialog', `Pair #${index + 1}:`)
        const keys = Object.keys(pair)
        keys.forEach(key => {
          logger.debug('AccountMatchingDialog', `  ${key}: ${JSON.stringify(pair[key])}`)
        })
      })
      logger.groupEnd()
    }
    
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

    // Helper methods to get names for the already matched pairs display
    const getTinkoffAccountName = (id) => {
      // First check if the matched pair has the full tinkoff_account object
      const pair = props.matchedPairs.find(p => String(p.tinkoff_account_id) === String(id))
      if (pair && pair.tinkoff_account && pair.tinkoff_account.name) {
        return pair.tinkoff_account.name
      }
      
      // Fall back to looking up in tinkoffAccounts array
      const stringId = String(id)
      const account = props.tinkoffAccounts.find(acc => String(acc.id) === stringId)
      if (!account) {
        logger.warn('AccountMatchingDialog', 'Could not find Tinkoff account with ID:', id, 
                  'Type:', typeof id, 
                  'Available account IDs:', props.tinkoffAccounts.map(a => ({id: a.id, type: typeof a.id})))
      }
      return account ? account.name : `Account ${id}`
    }
    
    const getDbAccountName = (id) => {
      // First check if the matched pair has the full db_account object
      const pair = props.matchedPairs.find(p => String(p.db_account_id) === String(id))
      if (pair && pair.db_account && pair.db_account.name) {
        return pair.db_account.name
      }
      
      // Fall back to looking up in dbAccounts array
      const stringId = String(id)
      const account = props.dbAccounts.find(acc => String(acc.id) === stringId)
      if (!account) {
        logger.warn('AccountMatchingDialog', 'Could not find DB account with ID:', id, 
                  'Type:', typeof id, 
                  'Available account IDs:', props.dbAccounts.map(a => ({id: a.id, type: typeof a.id})))
      }
      return account ? account.name : `Account ${id}`
    }

    // Check if there are any unmatched accounts to display the matching section
    const hasUnmatchedAccounts = computed(() => {
      return remainingTinkoffAccounts.value.length > 0 || 
             availableDbAccounts(0).length > 0
    })

    // Function to check which Tinkoff accounts are available for a specific pair
    const availableTinkoffAccounts = (pairIndex) => {
      // Filter out already matched Tinkoff accounts
      const alreadyMatchedIds = (props.matchedPairs || []).map(p => p.tinkoff_account_id)
      
      return props.tinkoffAccounts.filter((account) => {
        // Check if this account is already matched
        if (alreadyMatchedIds.includes(account.id)) {
          return false
        }
        
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
      // Filter out already matched DB accounts
      const alreadyMatchedIds = (props.matchedPairs || []).map(p => p.db_account_id)
      
      return props.dbAccounts.filter((account) => {
        // Check if this account is already matched
        if (alreadyMatchedIds.includes(account.id)) {
          return false
        }
        
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
      // Filter out already matched Tinkoff accounts
      const alreadyMatchedIds = (props.matchedPairs || []).map(p => p.tinkoff_account_id)
      
      return props.tinkoffAccounts.filter((account) => {
        // Check if already matched
        if (alreadyMatchedIds.includes(account.id)) {
          return false
        }
        
        // Check if used in a current pair
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
      // If we have matched pairs and no new pairs to match, it's valid
      if (props.matchedPairs && props.matchedPairs.length > 0 && !hasUnmatchedAccounts.value) {
        return true
      }
      
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
    
    const continueWithExistingMatches = () => {
      emit('use-existing-matches', { pairs: props.matchedPairs })
      closeDialog()
    }

    const confirmSelection = () => {
      try {
        // If we have matched pairs but no new ones and no creation, use existing
        if (props.matchedPairs && 
            props.matchedPairs.length > 0 && 
            !hasUnmatchedAccounts.value && 
            !createNewAccount.value) {
          continueWithExistingMatches()
          return
        }
        
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
          // Validate that we have at least one complete pair for new matches
          if (hasUnmatchedAccounts.value && 
              !accountPairs.value.some((pair) => pair.tinkoffAccount && pair.dbAccount)) {
            if (props.matchedPairs && props.matchedPairs.length > 0) {
              // We have existing matches, ask if user wants to continue with them
              errorMessage.value = 'Please create at least one new match or use existing matches'
            } else {
              errorMessage.value = 'Please create at least one account matching pair'
            }
            return
          }

          // Format pairs as expected by the backend
          const newMatchedPairs = accountPairs.value
            .filter((pair) => pair.tinkoffAccount && pair.dbAccount)
            .map((pair) => ({
              tinkoff_account_id: pair.tinkoffAccount.id,
              db_account_id: pair.dbAccount.id,
            }))
          
          // Combine with existing matched pairs if any
          const allPairs = [
            ...(props.matchedPairs || []),
            ...newMatchedPairs
          ]

          emit('accounts-matched', {
            pairs: allPairs,
          })
        }
        closeDialog()
      } catch (error) {
        logger.error('Unknown', 'Error in confirmSelection:', error)
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
      hasUnmatchedAccounts,
      availableTinkoffAccounts,
      availableDbAccounts,
      remainingTinkoffAccounts,
      getTinkoffAccountName,
      getDbAccountName,
      addPair,
      removePair,
      handleCreateNewChange,
      confirmSelection,
      continueWithExistingMatches,
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
