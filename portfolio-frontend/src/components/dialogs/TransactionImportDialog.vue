<template>
  <v-dialog v-model="dialog" max-width="700px">
    <v-card>
      <v-card-title class="text-h5">Import Transactions</v-card-title>
      
      <v-card-text>
        <!-- Initial Method Selection -->
        <v-fade-transition>
          <v-row v-if="!importMethodSelected">
            <!-- Direct Import Card -->
            <v-col cols="6">
              <v-tooltip
                :disabled="hasConnectedBrokers"
                text="Please add broker API tokens in User Settings to enable direct import"
                location="top"
                open-delay="200"
              >
                <template v-slot:activator="{ props }">
                  <div v-bind="props">
                    <v-card
                      class="import-method-card"
                      elevation="2"
                      @click="selectMethod('api')"
                      :class="{
                        'selected': importMethod === 'api',
                        'disabled': !hasConnectedBrokers
                      }"
                      :disabled="!hasConnectedBrokers"
                    >
                      <v-card-item>
                        <v-avatar
                          color="primary"
                          size="64"
                          class="mb-4"
                        >
                          <v-icon
                            size="32"
                            icon="mdi-api"
                          ></v-icon>
                        </v-avatar>
                        <v-card-title>Direct Import</v-card-title>
                        <v-card-subtitle class="text-wrap">
                          Import transactions directly from your broker
                          <v-chip
                            size="x-small"
                            color="primary"
                            class="ml-2"
                          >Recommended</v-chip>
                        </v-card-subtitle>
                        <v-card-text>
                          <v-list density="compact">
                            <v-list-item prepend-icon="mdi-check">
                              Faster and more reliable
                            </v-list-item>
                            <v-list-item prepend-icon="mdi-check">
                              No manual file preparation
                            </v-list-item>
                            <v-list-item prepend-icon="mdi-check">
                              Automatic broker detection
                            </v-list-item>
                          </v-list>
                        </v-card-text>
                      </v-card-item>
                    </v-card>
                  </div>
                </template>
              </v-tooltip>
            </v-col>

            <!-- File Import Card -->
            <v-col cols="6">
              <v-card
                class="import-method-card"
                elevation="2"
                @click="selectMethod('file')"
                :class="{'selected': importMethod === 'file'}"
              >
                <v-card-item>
                  <v-avatar
                    color="secondary"
                    size="64"
                    class="mb-4"
                  >
                    <v-icon
                      size="32"
                      icon="mdi-file-upload"
                    ></v-icon>
                  </v-avatar>
                  <v-card-title>File Import</v-card-title>
                  <v-card-subtitle>
                    Import from Excel or CSV file
                  </v-card-subtitle>
                  <v-card-text>
                    <v-list density="compact">
                      <v-list-item prepend-icon="mdi-check">
                        Works with any broker
                      </v-list-item>
                      <v-list-item prepend-icon="mdi-check">
                        Custom file formats
                      </v-list-item>
                      <v-list-item prepend-icon="mdi-check">
                        Historical data import
                      </v-list-item>
                    </v-list>
                  </v-card-text>
                </v-card-item>
              </v-card>
            </v-col>
          </v-row>
        </v-fade-transition>

        <!-- API Import Form -->
        <v-expand-transition>
          <div v-if="importMethodSelected && importMethod === 'api'">
            <v-select
              v-model="selectedBrokerAccount"
              :items="connectedBrokerAccounts"
              item-title="name"
              :item-value="item => item"
              label="Select Broker Account"
              :error-messages="showValidation && !selectedBrokerAccount?.id ? 'Please select a broker account' : ''"
              required
              class="mb-4"
              @update:model-value="handleBrokerAccountChange"
              return-object
            ></v-select>

            <v-row>
              <v-col cols="6">
                <v-text-field
                  v-model="dateRange.from"
                  label="From Date (Optional)"
                  type="date"
                ></v-text-field>
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="dateRange.to"
                  label="To Date (Optional)"
                  type="date"
                ></v-text-field>
              </v-col>
            </v-row>
          </div>
        </v-expand-transition>

        <!-- File Import Form -->
        <v-expand-transition>
          <div v-if="importMethodSelected && importMethod === 'file'">
            <v-file-input
              v-model="file"
              label="Select Excel or CSV file to import"
              accept=".csv, .xlsx, .xls"
              :rules="[v => !!v || 'File is required']"
              @change="handleFileChange"
              :disabled="isAnalyzed"
            ></v-file-input>
            
            <v-checkbox
              v-model="isGalaxy"
              label="Galaxy"
              class="mt-2"
              :disabled="isAnalyzed"
            ></v-checkbox>

            <v-select
              v-if="isGalaxy && isAnalyzed"
              v-model="selectedCurrency"
              :items="currencies"
              label="Select Currency"
              class="mt-2"
              :rules="[v => !!v || 'Currency is required']"
            ></v-select>

            <v-alert
              v-if="isAnalyzed && accountIdentificationComplete && !isGalaxy"
              :type="accountIdentified ? 'success' : 'info'"
              class="mt-4 mb-4"
            >
              {{ accountIdentified 
                ? `Broker account "${identifiedAccount.name}" was automatically identified. Please confirm or select a different broker account.` 
                : 'Broker account could not be automatically identified. Please select a broker account below.' }}
            </v-alert>
          </div>
        </v-expand-transition>

        <!-- Common settings shown after method selection -->
        <v-expand-transition>
          <div v-if="importMethodSelected">
            <v-checkbox
              v-model="confirmEveryTransaction"
              label="Confirm every transaction manually"
              class="mt-4"
            ></v-checkbox>
          </div>
        </v-expand-transition>
      </v-card-text>

      <v-card-actions>
        <v-btn
          v-if="importMethodSelected"
          color="secondary"
          text
          @click="backToSelection"
          class="mr-auto"
        >
          <v-icon start>mdi-arrow-left</v-icon>
          Back
        </v-btn>
        <v-spacer v-else></v-spacer>
        <v-btn 
          color="error" 
          text 
          @click="closeDialog"
        >
          Cancel
        </v-btn>
        <v-btn
          v-if="!importMethodSelected"
          color="primary"
          @click="confirmMethod"
          :disabled="!importMethod"
        >
          Continue
        </v-btn>
        <v-btn 
          v-if="importMethodSelected && importMethod === 'file' && !isAnalyzed" 
          color="blue darken-1" 
          text 
          @click="submitFile" 
          :disabled="!file || isLoading"
          :loading="isLoading"
        >
          Analyze File
        </v-btn>
        <v-btn
          v-if="importMethodSelected && importMethod === 'api'"
          color="primary"
          text
          @click="startApiImport"
          :disabled="!isApiImportValid || isLoading"
          :loading="isLoading"
        >
          Import Transactions
        </v-btn>
        <v-btn
          v-if="importMethodSelected && importMethod === 'file' && isAnalyzed"
          color="blue darken-1"
          text
          @click="startImport"
          :disabled="!isAnalyzed || !selectedAccount"
        >
          Import Transactions
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <ProgressDialog
    v-model="showProgressDialog"
    :title="'Import Progress'"
    :progress="(currentImported / totalToImport) * 100"
    :current="currentImported"
    :total="totalToImport"
    :current-message="currentImportMessage"
    :error="errorMessage"
    :can-stop="canStopImport"
    @stop-import="stopImport"
    @reset="resetImport"
  >

    <v-card v-if="showSecurityMapping || showTransactionConfirmation">
      <v-card-title class="text-h5">
        <v-icon start color="primary" icon="mdi-import"></v-icon>
        Import Transaction
      </v-card-title>

      <v-card-text>
        <SecurityMappingDialog
          v-if="showSecurityMapping"
          :showSecurityMapping="showSecurityMapping"
          :security="securityToMap"
          :bestMatch="bestMatch"
          @security-selected="handleSecuritySelected"
        />

        <TransactionImportProgress
          v-if="showTransactionConfirmation"
          :showConfirmation="showTransactionConfirmation"
          :currentTransaction="currentTransaction"
          :securityMappingRequired="showSecurityMapping"
          @confirm="handleConfirm"
          @skip="handleSkip"
        />
      </v-card-text>
      <!-- <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="error" @click="handleSkip">
          <v-icon start icon="mdi-close"></v-icon>
          Skip
        </v-btn>
        <v-btn color="primary" @click="handleConfirm">
          <v-icon start icon="mdi-check"></v-icon>
          {{ showSecurityMapping ? 'Map and Confirm' : 'Confirm' }}
        </v-btn>
      </v-card-actions> -->
    </v-card>

  </ProgressDialog>

  <v-dialog v-model="showSuccessDialog" max-width="500px">
    <v-card>
      <v-card-title class="text-h5 pb-2">
        <v-icon color="success" class="mr-2">mdi-check-circle</v-icon>
        Import Completed
      </v-card-title>
      <v-card-text>
        <v-row dense>
          <v-col cols="12">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="primary" size="40">
                    <v-icon dark>mdi-database-import</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.totalTransactions }}
                </v-list-item-title>
                <v-list-item-subtitle>Total transactions processed</v-list-item-subtitle>
              </v-list-item>
            </v-card>
          </v-col>
          <v-col cols="6">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="success" size="40">
                    <v-icon dark>mdi-check-circle</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.importedTransactions }}
                </v-list-item-title>
                <v-list-item-subtitle>Successfully imported</v-list-item-subtitle>
              </v-list-item>
            </v-card>
          </v-col>
          <v-col cols="6">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="warning" size="40">
                    <v-icon dark>mdi-alert-circle</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.duplicateTransactions }}
                </v-list-item-title>
                <v-list-item-subtitle>Duplicates found</v-list-item-subtitle>
              </v-list-item>
            </v-card>
          </v-col>
          <v-col cols="6">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="error" size="40">
                    <v-icon dark>mdi-alert-circle</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.skippedTransactions }}
                </v-list-item-title>
                <v-list-item-subtitle>Skipped transactions</v-list-item-subtitle>
              </v-list-item>
            </v-card>
          </v-col>
          <v-col cols="6">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="error" size="40">
                    <v-icon dark>mdi-alert-circle</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.importErrors }}
                </v-list-item-title>
                <v-list-item-subtitle>Import Errors</v-list-item-subtitle>
              </v-list-item>
            </v-card>
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" @click="closeSuccessDialog">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="showErrorDialog" max-width="500px">
    <v-card>
      <v-card-title class="text-h5 error--text">
        <v-icon color="error" class="mr-2">mdi-alert-circle</v-icon>
        Import Error
      </v-card-title>
      <v-card-text class="pt-4 text-body-1" style="white-space: pre-wrap;">
        {{ errorMessage }}
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="error" @click="closeErrorDialog">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <SecurityFormDialog
    v-model="showSecurityDialog"
    :edit-item="securityFormData"
    :is-import="true"
    @security-added="handleSecurityAdded"
    @security-skipped="handleSecuritySkipped"
  />

  <v-dialog v-model="confirmDialog" max-width="600px">
    <v-card>
      <v-card-title>{{ confirmTitle }}</v-card-title>
      <v-card-text>
        <p>{{ confirmMessage }}</p>
        
        <!-- Show readonly security data if it exists -->
        <template v-if="securityFormData?.readonly">
          <v-list dense>
            <v-list-item>
              <v-list-item-title>Name:</v-list-item-title>
              <v-list-item-subtitle>{{ securityFormData.name }}</v-list-item-subtitle>
            </v-list-item>
            <v-list-item>
              <v-list-item-title>ISIN:</v-list-item-title>
              <v-list-item-subtitle>{{ securityFormData.ISIN }}</v-list-item-subtitle>
            </v-list-item>
            <!-- Add other relevant fields -->
          </v-list>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="error" @click="handleSecurityConfirm(false)">Skip</v-btn>
        <v-btn color="primary" @click="handleSecurityConfirm(true)">Create</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Add account selection dialog -->
  <v-dialog v-model="showAccountSelection" max-width="500px">
    <v-card>
      <v-card-title>Select Account</v-card-title>
      <v-card-text>
        <p>Please select an account to import transactions from:</p>
        <v-list>
          <v-list-item
            v-for="account in availableAccounts"
            :key="account.id"
            @click="selectAccount(account)"
          >
            <v-list-item-title>{{ account.name }}</v-list-item-title>
            <v-list-item-subtitle>
              ID: {{ account.id }} | Type: {{ account.type }}
              <br>
              Opened: {{ account.opened_date }}
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>
    </v-card>
  </v-dialog>

  <!-- Add AccountMatchingDialog -->
  <AccountMatchingDialog
    v-model="showAccountMatching"
    :broker-name="selectedBroker?.name"
    :tinkoff-accounts="tinkoffAccounts"
    :db-accounts="dbAccounts"
    @account-matched="handleAccountMatched"
    @create-account="handleAccountCreation"
  />
</template>
<script>
import { ref, watch, onUnmounted, computed, onMounted } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useImportState } from '@/composables/useImportState'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { analyzeFile, getAccounts, getBrokersWithTokens } from '@/services/api'
import ProgressDialog from './ProgressDialog.vue'
import SecurityMappingDialog from './SecurityMappingDialog.vue'
import TransactionImportProgress from '../TransactionImportProgress.vue'
import SecurityFormDialog from './SecurityFormDialog.vue'
import AccountMatchingDialog from './AccountMatchingDialog.vue'

export default {
  name: 'TransactionImportDialog',
  components: {
    ProgressDialog,
    SecurityMappingDialog,
    TransactionImportProgress,
    SecurityFormDialog,
    AccountMatchingDialog
  },
  props: {
    modelValue: Boolean,
  },
  emits: ['update:modelValue', 'import-completed'],
  setup(props, { emit }) {
    const dialog = ref(props.modelValue)
    const file = ref(null)
    const isLoading = ref(false)
    const isAnalyzed = ref(false)
    const selectedAccount = ref(null)
    const accounts = ref([])
    const fileId = ref(null)
    const accountIdentified = ref(false)
    const identifiedAccount = ref(null)
    const accountIdentificationComplete = ref(false)
    const showProgressDialog = ref(false)
    const currentImported = ref(0)
    const totalToImport = ref(0)
    const currentImportMessage = ref('')
    const importError = ref('')
    const canStopImport = ref(true)
    const showSecurityMapping = ref(false)
    const showTransactionConfirmation = ref(false)
    const securityToMap = ref('')
    const bestMatch = ref(null)
    const currentTransaction = ref({})
    const selectedSecurityId = ref(null)

    const showSuccessDialog = ref(false)
    const importStats = ref({
      totalTransactions: 0,
      importedTransactions: 0,
      skippedTransactions: 0,
      duplicateTransactions: 0,
      importErrors: 0
    })
    const errorMessage = ref('')
    const showErrorDialog = ref(false)

    const showSecurityDialog = ref(false)
    const securityFormData = ref(null)

    const confirmDialog = ref(false)
    const confirmTitle = ref('')
    const confirmMessage = ref('')

    const importState = useImportState()
    const { handleApiError } = useErrorHandler()
    const { isConnected, lastMessage, sendMessage, connect, disconnect, reset } = useWebSocket('/ws/transactions/')
    
    watch(() => props.modelValue, (newValue) => {
      dialog.value = newValue
    })

    watch(dialog, (newValue) => {
      emit('update:modelValue', newValue)
    })

    const confirmEveryTransaction = ref(false)
    const isGalaxy = ref(false)
    const galaxyType = ref('transactions')
    const selectedCurrency = ref(null)
    const currencies = [
      { title: 'USD', value: 'USD' },
      { title: 'EUR', value: 'EUR' },
      { title: 'GBP', value: 'GBP' },
      { title: 'RUB', value: 'RUB' }
    ]

    const handleFileChange = (event) => {
      file.value = event.target.files[0]
      isAnalyzed.value = false
      accountIdentified.value = false
      selectedAccount.value = null
      identifiedAccount.value = null
      accountIdentificationComplete.value = false
      fileId.value = null
    }

    const closeDialog = () => {
      resetInitialDialog()
      resetProgressDialog()
    }

    const submitFile = async () => {
      if (file.value) {
        isLoading.value = true
        importState.setState('analyzing')
        try {
          const formData = new FormData()
          formData.append('file', file.value)
          formData.append('is_galaxy', String(isGalaxy.value))
          const result = await analyzeFile(formData)
          isAnalyzed.value = true
          fileId.value = result.fileId
          accounts.value = await getAccounts()
          
          if (result.status === 'account_identified') {
            accountIdentified.value = true
            identifiedAccount.value = result.identifiedAccount
            selectedAccount.value = result.identifiedAccount.id
          }
          importState.setState('idle')
        } catch (error) {
          handleApiError(error)
          importState.setState('error', error.message)
          importState.setState('idle')
        } finally {
          isLoading.value = false
          accountIdentificationComplete.value = true
        }
      } else {
        importState.setState('error', 'No file selected')
      }
    }

    const startImport = async () => {
      reset()
      if (!fileId.value || !selectedAccount.value) {
        importState.setState('error', 'File and account must be selected')
        return
      }

      if (isGalaxy.value && !selectedCurrency.value) {
        importState.setState('error', 'Currency must be selected for Galaxy import')
        return
      }

      importState.setState('importing')
      showProgressDialog.value = true
      dialog.value = false

      if (!isConnected.value) {
        connect()
      }

      await waitForConnection()

      if (isConnected.value) {
        sendMessage({
          type: 'start_import',
          file_id: fileId.value,
          account_id: selectedAccount.value,
          confirm_every: confirmEveryTransaction.value,
          is_galaxy: isGalaxy.value,
          galaxy_type: isGalaxy.value ? galaxyType.value : null,
          currency: isGalaxy.value ? selectedCurrency.value : null
        })
      } else {
        importError.value = 'WebSocket not connected. Please try again.'
        importState.setState('error', importError.value)
      }
    }

    const waitForConnection = async () => {
      await new Promise((resolve) => {
        const checkConnection = setInterval(() => {
          if (isConnected.value) {
            clearInterval(checkConnection)
            resolve()
          }
        }, 100)
      })
    }

    const stopImport = () => {
      sendMessage({
        type: 'stop_import'
      })
      canStopImport.value = false // Disable stop button while processing
    }

    const handleWebSocketMessage = (message) => {
      console.log('Received WebSocket message in dialog:', message)
      if (message.type === 'initialization') {
        totalToImport.value = message.total_to_update
        currentImportMessage.value = message.message
      } else if (message.type === 'security_creation_needed') {
        const securityInfo = message.security_info
        // const confirmText = `Security ${securityInfo.name} (ISIN: ${securityInfo.isin}) does not exist in your portfolio.`
        
        // if (message.data.exists_in_db) {
        //   // Security exists in database but not for this user
        //   showSecurityConfirmDialog(
        //     confirmText,
        //     'This security exists in the database. Would you like to add it to your portfolio?',
        //     message.data.security_data,
        //     securityInfo
        //   )
        // } else {
          // Show empty form with prefilled data from import
        securityFormData.value = {
          name: securityInfo.name,
          ISIN: securityInfo.isin,
          currency: securityInfo.currency,
          type: 'Stock', // Default values
          exposure: 'Equity' // Default values
        }
        showSecurityDialog.value = true
        // }
      } else if (message.type === 'import_update') {
        handleImportUpdate(message.data)
      } else if (message.type === 'import_error' || message.type === 'save_error') {
        handleImportError(message.data.error)
      } else if (message.type === 'critical_error') {
        showProgressDialog.value = false
        showSuccessDialog.value = false
        showSecurityMapping.value = false
        showTransactionConfirmation.value = false
        
        errorMessage.value = message.data.error
        showErrorDialog.value = true
        
        disconnect()
        
        resetInitialDialog()
        resetProgressDialog()
        resetConfirmationState()
      } else if (message.type === 'import_complete') {
        handleImportSuccess(message.data)
      } else if (message.type === 'import_stopped') {
        handleImportStopped(message.data)
      } else if (message.type === 'transaction_confirmation') {
        handleTransactionConfirmation(message.data)
      } else if (message.type === 'account_selection_required') {
        tinkoffAccounts.value = message.data.tinkoff_accounts
        dbAccounts.value = message.data.db_accounts
        showAccountMatching.value = true
      }
    }

    const handleImportUpdate = (update) => {
      if (update.status === 'progress') {
        currentImported.value = update.current
        currentImportMessage.value = update.message
        importState.setProgress(update.progress)
        importState.setState('importing', update.message)
      } else if (update.status === 'security_mapping') {
        handleSecurityMapping(update)
      } else if (update.status === 'transaction_confirmation') {
        handleTransactionConfirmation(update)
      } else if (update.error) {
        handleImportError(update.error)
      }
    }

    const handleImportError = (error) => {
      importError.value = error
      importState.setState('error', error)
      
      handleApiError({ message: error })
    }

    const handleSecurityMapping = (data) => {
      securityToMap.value = data.mapping_data.stock_description
      bestMatch.value = data.mapping_data.best_match
      currentTransaction.value = data.transaction_data
      showSecurityMapping.value = true
      showTransactionConfirmation.value = true
    }

    const handleTransactionConfirmation = (data) => {
      currentTransaction.value = data.data
      showTransactionConfirmation.value = true
      showSecurityMapping.value = false
    }

    const handleSecuritySelected = (securityId) => {
      selectedSecurityId.value = securityId
    }

    const handleConfirm = () => {
      if (isConnected.value) {
        if (showSecurityMapping.value) {
          sendMessage({
            type: 'security_mapped',
            action: 'map',
            security_id: selectedSecurityId.value
          })
        } else {
          sendMessage({
            type: 'transaction_confirmed',
            confirmed: true
          })
        }
      }
      resetConfirmationState()
    }

    const handleSkip = () => {
      if (isConnected.value) {
        if (showSecurityMapping.value) {
          sendMessage({
          type: 'security_mapped',
          action: 'skip',
          security_id: null
        })
        } else {
          sendMessage({
            type: 'transaction_confirmed',
            confirmed: false
          })
        }
      }
      resetConfirmationState()
    }

    const resetConfirmationState = () => {
      showSecurityMapping.value = false
      showTransactionConfirmation.value = false
      currentTransaction.value = {}
      securityToMap.value = ''
      bestMatch.value = null
      selectedSecurityId.value = null
    }

    const handleImportSuccess = (result) => {
      importStats.value = result
      showSuccessDialog.value = true
      showProgressDialog.value = false
      emit('import-completed', result)
      importState.setState('complete', 'Import completed successfully')
  
      currentImported.value = 0
      totalToImport.value = 0
      currentImportMessage.value = ''
      importError.value = ''
      canStopImport.value = true
      importState.setProgress(0)
      importState.setState('idle')

      // Disconnect WebSocket without reconnection
      disconnect()
      
      // Reset states
      resetProgressDialog()
      resetConfirmationState()
      
    }

    const closeSuccessDialog = () => {
      showSuccessDialog.value = false
      file.value = null
      isAnalyzed.value = false
      accountIdentified.value = false
      identifiedAccount.value = null
      accountIdentificationComplete.value = false
      fileId.value = null
      selectedAccount.value = null

      resetProgressDialog()
    }

    const resetInitialDialog = () => {
      dialog.value = false
      file.value = null
      isAnalyzed.value = false
      accountIdentified.value = false
      identifiedAccount.value = null
      accountIdentificationComplete.value = false
      selectedCurrency.value = null
    }

    const resetProgressDialog = () => {
      currentImported.value = 0
      totalToImport.value = 0
      currentImportMessage.value = ''
      importError.value = ''
      canStopImport.value = true
      importState.setProgress(0)
      importState.setState('idle')
    }

    const handleImportStopped = (data) => {
      showProgressDialog.value = false
      currentImportMessage.value = data.message
      importStats.value = data.stats
      
      // Show a notification that import was stopped
      showErrorDialog.value = true
      errorMessage.value = 'Import process was stopped by user'
      
      // Disconnect WebSocket
      disconnect()
      
      // Reset states
      resetProgressDialog()
      resetConfirmationState()
    }

    watch(lastMessage, (newMessage) => {
      if (newMessage) {
        handleWebSocketMessage(newMessage)
      }
    })

    watch(isConnected, (newValue) => {
      console.log('WebSocket connection status:', newValue ? 'connected' : 'disconnected')
    })

    onUnmounted(() => {
      // Ensure intentional disconnect on unmount
      disconnect()
    })

    const closeErrorDialog = () => {
      showErrorDialog.value = false
      errorMessage.value = ''
      dialog.value = false // Close the main dialog as well
    }

    const handleSecurityAdded = (securityData) => {
      console.log('handleSecurityAdded called with:', securityData)
      showSecurityDialog.value = false
      securityFormData.value = null
      
      sendMessage({
        type: 'security_confirmation',
        security_id: securityData.id
      })
    }

    const handleSecuritySkipped = () => {
      console.log('handleSecuritySkipped called')
      showSecurityDialog.value = false
      securityFormData.value = null
      
      sendMessage({
        type: 'security_confirmation',
        security_id: null
      })
    }

    // const showSecurityConfirmDialog = (title, message, existingData, securityInfo) => {
    //   confirmDialog.value = true
    //   confirmTitle.value = title
    //   confirmMessage.value = message
      
    //   if (existingData) {
    //     // Show readonly security data
    //     securityFormData.value = { ...existingData, readonly: true }
    //   } else {
    //     // Show empty form with prefilled data from import
    //     securityFormData.value = {
    //       name: securityInfo.name,
    //       ISIN: securityInfo.isin,
    //       currency: securityInfo.currency,
    //       type: 'Stock',  // Default values
    //       exposure: 'Equity'
    //     }
    //   }
    // }

    const handleSecurityConfirm = (confirmed) => {
      console.log('handleSecurityConfirm called with:', confirmed)
      confirmDialog.value = false
      
      if (confirmed) {
        console.log('Security confirmed, formData:', securityFormData.value)
        if (securityFormData.value.readonly) {
          sendMessage({
            type: 'security_confirmation',
            security_id: securityFormData.value.id
          })
        } else {
          showSecurityDialog.value = true
        }
      } else {
        handleSecuritySkipped()
      }
    }

    // New refs for method selection and API import
    const importMethod = ref(null)
    const importMethodSelected = ref(false)
    const selectedBrokerAccount = ref(null)
    const connectedBrokerAccounts = ref([])
    const dateRange = ref({
      from: null,
      to: null
    })

    // Load connected broker accounts on component mount
    onMounted(async () => {
      try {
        isLoading.value = true
        const brokers = await getBrokersWithTokens()
        connectedBrokerAccounts.value = brokers.map(broker => ({
          id: broker.id,
          name: broker.name,
          // Add any other needed broker properties
        }))
      } catch (error) {
        console.error('Failed to load broker accounts:', error)
        // Handle error - maybe show a notification
      } finally {
        isLoading.value = false
      }
    })

    // Computed properties
    const hasConnectedBrokers = computed(() => 
      connectedBrokerAccounts.value.length > 0
    )
    
    const isApiImportValid = computed(() => {
      return !!selectedBrokerAccount.value
    })

    // Method selection handlers
    const selectMethod = (method) => {
      if (method === 'api' && !hasConnectedBrokers.value) return
      importMethod.value = method
    }

    const confirmMethod = () => {
      importMethodSelected.value = true
    }

    const backToSelection = () => {
      importMethodSelected.value = false
      importMethod.value = null
      // Reset form data
      file.value = null
      selectedBrokerAccount.value = null
      dateRange.value = { from: null, to: null }
    }

    // New method for API import
    const startApiImport = async () => {
      showValidation.value = true // Show validation on import attempt
      
      console.log('Starting import with account:', selectedBrokerAccount.value) // Debug import data
      
      if (!selectedBrokerAccount.value?.id) {
        errorMessage.value = 'Please select a broker account'
        return
      }

      isLoading.value = true
      showProgressDialog.value = true
      currentImportMessage.value = 'Initializing import...'
      
      try {
        // Log selected account for debugging
        console.log('Selected broker account:', selectedBrokerAccount.value)

        // Connect to WebSocket
        await connect()
        await new Promise(resolve => setTimeout(resolve, 100))
        
        if (!isConnected.value) {
          throw new Error('Failed to establish WebSocket connection')
        }
        
        currentImportMessage.value = 'Connecting to broker API...'
        
        const importData = {
          broker_account_id: selectedBrokerAccount.value.id,
          confirm_every_transaction: confirmEveryTransaction.value,
          date_from: dateRange.value?.from || null,
          date_to: dateRange.value?.to || null
        }

        console.log('Import data:', importData)

        const messageSent = sendMessage({
          type: 'start_api_import',
          data: importData
        })

        if (!messageSent) {
          throw new Error('Failed to send start message')
        }

      } catch (error) {
        console.error('API import failed:', error)
        currentImportMessage.value = ''
        errorMessage.value = error.message
        importError.value = error.message
      }
    }

    // Add watcher for selectedBrokerAccount
    watch(selectedBrokerAccount, (newValue) => {
      console.log('Selected broker account changed:', newValue)
    })

    // Add this watch in the setup function
    watch(lastMessage, (message) => {
      if (!message) return

      console.log('Received WebSocket message in dialog:', message)

      if (message.type === 'error') {
        importError.value = message.data.message
        currentImportMessage.value = '' // Clear progress message
        importState.setState('error', message.data.message)
      } else if (message.type === 'progress') {
        currentImportMessage.value = message.data.message
        if (message.data.total) {
          totalToImport.value = message.data.total
        }
        if (message.data.current) {
          currentImported.value = message.data.current
        }
      }
    })

    // const handleProgressError = (error) => {
    //   showProgressDialog.value = true
    //   currentImportMessage.value = ''
    //   errorMessage.value = error.message || 'An unknown error occurred'
    // }

    const resetImport = () => {
      // Reset all import-related state
      currentImported.value = 0
      totalToImport.value = 0
      currentImportMessage.value = ''
      errorMessage.value = ''
      importError.value = ''
      showProgressDialog.value = false
      importState.setState('idle')
    }

    // Add validation state
    const showValidation = ref(false)

    const handleBrokerAccountChange = (value) => {
      console.log('Selected broker account:', value) // Debug selected value
      selectedBrokerAccount.value = value
      showValidation.value = true
    }

    const showAccountSelection = ref(false)
    const availableAccounts = ref([])

    // Handle WebSocket messages
    watch(lastMessage, (message) => {
      if (!message) return

      if (message.type === 'account_selection_required') {
        availableAccounts.value = message.data.available_accounts
        showAccountSelection.value = true
      }
    })

    const selectAccount = (account) => {
      showAccountSelection.value = false
      sendMessage({
        type: 'select_account',
        data: {
          account_id: account.id,
          confirm_every_transaction: confirmEveryTransaction.value,
          date_from: dateRange.value?.from,
          date_to: dateRange.value?.to
        }
      })
    }

    const showAccountMatching = ref(false)
    const tinkoffAccounts = ref([])
    const dbAccounts = ref([])

    const handleAccountMatched = (selection) => {
      sendMessage({
        type: 'account_matched',
        data: {
          tinkoff_account_id: selection.tinkoffAccount.id,
          db_account_id: selection.dbAccount.id
        }
      })
    }

    const handleAccountCreation = (data) => {
      sendMessage({
        type: 'create_account',
        data: {
          tinkoff_account_id: data.tinkoffAccount.id,
          name: data.name,
          comment: data.comment
        }
      })
    }

    return {
      dialog,
      file,
      isLoading,
      isAnalyzed,
      selectedAccount,
      accounts,
      fileId,
      accountIdentified,
      identifiedAccount,
      accountIdentificationComplete,
      showSuccessDialog,
      showProgressDialog,
      currentImported,
      totalToImport,
      currentImportMessage,
      importError,
      canStopImport,
      showSecurityMapping,
      securityToMap,
      bestMatch,
      handleFileChange,
      closeDialog,
      submitFile,
      startImport,
      stopImport,
      closeSuccessDialog,
      handleSecuritySelected,
      handleConfirm,
      handleSkip,
      importState,
      importStats,
      isConnected,
      showTransactionConfirmation,
      currentTransaction,
      confirmEveryTransaction,
      isGalaxy,
      galaxyType,
      selectedCurrency,
      currencies,
      showErrorDialog,
      errorMessage,
      closeErrorDialog,
      handleSecurityAdded,
      handleSecuritySkipped,
      showSecurityDialog,
      securityFormData,
      confirmDialog,
      confirmTitle,
      confirmMessage,
      handleSecurityConfirm,
      importMethod,
      importMethodSelected,
      selectedBrokerAccount,
      connectedBrokerAccounts,
      dateRange,
      hasConnectedBrokers,
      isApiImportValid,
      selectMethod,
      confirmMethod,
      backToSelection,
      startApiImport,
      resetImport,
      showValidation,
      handleBrokerAccountChange,
      showAccountSelection,
      availableAccounts,
      selectAccount,
      showAccountMatching,
      tinkoffAccounts,
      dbAccounts,
      handleAccountMatched,
      handleAccountCreation
    }
  }
}
</script>

<style scoped>
.import-method-card {
  cursor: pointer;
  transition: all 0.3s;
  height: 100%;
  border: 2px solid transparent;
}

.import-method-card:not(.disabled):hover {
  transform: translateY(-4px);
}

.import-method-card.selected {
  border-color: rgb(var(--v-theme-primary));
}

.import-method-card.disabled {
  opacity: 0.7;
  cursor: not-allowed;
  pointer-events: auto;
}

.v-list-item {
  min-height: 32px !important;
}

.text-wrap {
  white-space: normal;
  word-wrap: break-word;
}
</style>
