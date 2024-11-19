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
          Please select which account from {{ brokerName }} API corresponds to your database account:
        </p>

        <v-row>
          <!-- Tinkoff API Accounts -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="pa-4">
              <div class="text-h6 mb-4">{{ brokerName }} API Accounts</div>
              <v-radio-group v-model="selectedTinkoffAccount">
                <v-radio
                  v-for="account in tinkoffAccounts"
                  :key="account.id"
                  :value="account"
                  :label="account.name"
                >
                  <template v-slot:label>
                    <div>
                      <strong>{{ account.name }}</strong>
                      <div class="text-caption">
                        ID: {{ account.id }}
                        <br>
                        Type: {{ account.type }}
                        <br>
                        Opened: {{ account.opened_date }}
                      </div>
                    </div>
                  </template>
                </v-radio>
              </v-radio-group>
            </v-card>
          </v-col>

          <!-- Database Accounts -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="pa-4">
              <div class="text-h6 mb-4">Your Portfolio Accounts</div>
              <v-radio-group v-model="selectedDbAccount">
                <v-radio
                  v-for="account in dbAccounts"
                  :key="account.id"
                  :value="account"
                  :label="account.name"
                >
                  <template v-slot:label>
                    <div>
                      <strong>{{ account.name }}</strong>
                      <div class="text-caption">
                        ID: {{ account.id }}
                        <br>
                        {{ account.comment || 'No comment' }}
                        <br>
                        {{ account.native_id ? `API ID: ${account.native_id}` : 'No API ID set' }}
                      </div>
                    </div>
                  </template>
                </v-radio>
              </v-radio-group>
            </v-card>
          </v-col>
        </v-row>

        <!-- Create New Account Option -->
        <v-card variant="outlined" class="mt-4 pa-4">
          <v-checkbox
            v-model="createNewAccount"
            label="Create new account instead"
            @change="handleCreateNewChange"
          />
          
          <v-expand-transition>
            <div v-if="createNewAccount">
              <v-text-field
                v-model="newAccountName"
                label="Account Name"
                :rules="[v => !!v || 'Name is required']"
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
        <v-btn
          color="error"
          variant="text"
          @click="closeDialog"
        >
          Cancel
        </v-btn>
        <v-btn
          color="primary"
          :disabled="!isValid"
          @click="confirmSelection"
        >
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
      required: true
    },
    tinkoffAccounts: {
      type: Array,
      required: true
    },
    dbAccounts: {
      type: Array,
      required: true
    }
  },

  emits: ['update:modelValue', 'account-matched', 'create-account'],

  setup(props, { emit }) {
    const selectedTinkoffAccount = ref(null)
    const selectedDbAccount = ref(null)
    const createNewAccount = ref(false)
    const newAccountName = ref('')
    const newAccountComment = ref('')
    const errorMessage = ref('')

    const dialogModel = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value)
    })

    const isValid = computed(() => {
      if (createNewAccount.value) {
        return selectedTinkoffAccount.value && newAccountName.value.trim()
      }
      return selectedTinkoffAccount.value && selectedDbAccount.value
    })

    const handleCreateNewChange = (value) => {
      if (value) {
        selectedDbAccount.value = null
      } else {
        newAccountName.value = ''
        newAccountComment.value = ''
      }
    }

    const confirmSelection = () => {
      if (createNewAccount.value) {
        emit('create-account', {
          tinkoffAccount: selectedTinkoffAccount.value,
          name: newAccountName.value,
          comment: newAccountComment.value
        })
      } else {
        emit('account-matched', {
          tinkoffAccount: selectedTinkoffAccount.value,
          dbAccount: selectedDbAccount.value
        })
      }
      closeDialog()
    }

    const closeDialog = () => {
      dialogModel.value = false
      selectedTinkoffAccount.value = null
      selectedDbAccount.value = null
      createNewAccount.value = false
      newAccountName.value = ''
      newAccountComment.value = ''
      errorMessage.value = ''
    }

    return {
      dialogModel,
      selectedTinkoffAccount,
      selectedDbAccount,
      createNewAccount,
      newAccountName,
      newAccountComment,
      errorMessage,
      isValid,
      handleCreateNewChange,
      confirmSelection,
      closeDialog
    }
  }
}
</script> 