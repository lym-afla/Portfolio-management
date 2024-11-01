<template>
  <v-dialog v-model="dialog" max-width="500px">
    <v-card>
      <v-card-title class="text-h5">Import Transactions</v-card-title>
      <v-card-text>
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
          v-if="isAnalyzed && brokerIdentificationComplete && !isGalaxy"
          :type="brokerIdentified ? 'success' : 'info'"
          class="mt-4 mb-4"
        >
          {{ brokerIdentified 
            ? `Broker "${identifiedBroker.name}" was automatically identified. Please confirm or select a different broker.` 
            : 'Broker could not be automatically identified. Please select a broker below.' }}
        </v-alert>
        <v-autocomplete
          v-if="isAnalyzed"
          v-model="selectedBroker"
          :items="brokers"
          item-title="name"
          item-value="id"
          label="Select Broker"
          class="mt-4"
          :hint="brokerIdentified ? 'Suggested broker based on file analysis' : ''"
          persistent-hint
        ></v-autocomplete>

        <v-radio-group
          v-if="isGalaxy && isAnalyzed"
          v-model="galaxyType"
          inline
          class="mt-4"
        >
          <v-radio
            label="Cash"
            value="cash"
          ></v-radio>
          <v-radio
            label="Transactions"
            value="transactions"
          ></v-radio>
        </v-radio-group>

        <v-checkbox
          v-model="confirmEveryTransaction"
          label="Confirm every transaction manually"
        ></v-checkbox>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="error" text @click="closeDialog">Cancel</v-btn>
        <v-btn 
          v-if="!isAnalyzed" 
          color="blue darken-1" 
          text 
          @click="submitFile" 
          :disabled="!file || isLoading"
          :loading="isLoading"
        >
          Analyze File
        </v-btn>
        <v-btn
          v-if="isAnalyzed"
          color="blue darken-1"
          text
          @click="startImport"
          :disabled="!isAnalyzed || !selectedBroker"
        >
          Import Transactions
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <ProgressDialog
    v-model="showProgressDialog"
    :title="'Importing Transactions'"
    :progress="importState.progress.value"
    :current="currentImported"
    :total="totalToImport"
    :currentMessage="currentImportMessage"
    :error="importError"
    :canStop="canStopImport"
    @stop-import="stopImport"
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
          :brokerId="selectedBroker"
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
</template>

<script>
import { ref, watch, onUnmounted } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useImportState } from '@/composables/useImportState'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { analyzeFile, getBrokers } from '@/services/api'
import ProgressDialog from './ProgressDialog.vue'
import SecurityMappingDialog from './SecurityMappingDialog.vue'
import TransactionImportProgress from '../TransactionImportProgress.vue'
import SecurityFormDialog from './SecurityFormDialog.vue'

export default {
  name: 'TransactionImportDialog',
  components: {
    ProgressDialog,
    SecurityMappingDialog,
    TransactionImportProgress,
    SecurityFormDialog,
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
    const selectedBroker = ref(null)
    const brokers = ref([])
    const fileId = ref(null)
    const brokerIdentified = ref(false)
    const identifiedBroker = ref(null)
    const brokerIdentificationComplete = ref(false)
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
    const { isConnected, lastMessage, sendMessage, connect, disconnect } = useWebSocket('/ws/transactions/')
    
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
      brokerIdentified.value = false
      selectedBroker.value = null
      identifiedBroker.value = null
      brokerIdentificationComplete.value = false
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
          brokers.value = await getBrokers()
          
          if (result.status === 'broker_identified') {
            brokerIdentified.value = true
            identifiedBroker.value = result.identifiedBroker
            selectedBroker.value = result.identifiedBroker.id
          }
          importState.setState('idle')
        } catch (error) {
          handleApiError(error)
          importState.setState('error', error.message)
          importState.setState('idle')
        } finally {
          isLoading.value = false
          brokerIdentificationComplete.value = true
        }
      } else {
        importState.setState('error', 'No file selected')
      }
    }

    const startImport = async () => {
      if (!fileId.value || !selectedBroker.value) {
        importState.setState('error', 'File and broker must be selected')
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
          broker_id: selectedBroker.value,
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

      // Disconnect WebSocket
      disconnect()
      
      // Reset states
      resetProgressDialog()
      resetConfirmationState()
      
    }

    const closeSuccessDialog = () => {
      showSuccessDialog.value = false
      file.value = null
      isAnalyzed.value = false
      brokerIdentified.value = false
      identifiedBroker.value = null
      brokerIdentificationComplete.value = false
      fileId.value = null
      selectedBroker.value = null

      resetProgressDialog()
    }

    const resetInitialDialog = () => {
      dialog.value = false
      file.value = null
      isAnalyzed.value = false
      brokerIdentified.value = false
      identifiedBroker.value = null
      brokerIdentificationComplete.value = false
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

    return {
      dialog,
      file,
      isLoading,
      isAnalyzed,
      selectedBroker,
      brokers,
      fileId,
      brokerIdentified,
      identifiedBroker,
      brokerIdentificationComplete,
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
    }
  }
}
</script>