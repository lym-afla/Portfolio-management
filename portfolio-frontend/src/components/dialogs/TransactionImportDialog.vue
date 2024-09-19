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
        <v-alert
          v-if="isAnalyzed && brokerIdentificationComplete"
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
    <v-alert v-if="error" type="error" dismissible>
      {{ error }}
    </v-alert>
  </v-dialog>

  <ProgressDialog
    v-if="showProgressDialog"
    v-model="showProgressDialog"
    :title="'Importing Transactions'"
    :progress="importProgress"
    :current="currentImported"
    :total="totalToImport"
    :currentMessage="currentImportMessage"
    :error="importError"
    :canStop="canStopImport"
    @stop-import="stopImport"
  />

  <SecurityMappingDialog
    v-model="showSecurityMappingDialog"
    :security="securityToMap"
    :bestMatch="bestMatch"
    :brokerId="selectedBroker"
    @security-mapped="handleSecurityMapped"
  />

  <TransactionConfirmationDialog
    v-model="showTransactionConfirmationDialog"
    :transaction="currentTransaction"
    :index="currentTransactionIndex"
    :total="totalTransactions"
    @confirm="confirmTransaction"
    @skip="skipTransaction"
  />

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
                  <v-avatar color="info" size="40">
                    <v-icon dark>mdi-plus-circle</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.newSecurities }}
                </v-list-item-title>
                <v-list-item-subtitle>New securities added</v-list-item-subtitle>
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
</template>

<script>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useImportState } from '@/composables/useImportState'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { analyzeFile, getBrokers } from '@/services/api'
import ProgressDialog from './ProgressDialog.vue'
import SecurityMappingDialog from './SecurityMappingDialog.vue'
import TransactionConfirmationDialog from './TransactionConfirmationDialog.vue'

export default {
  name: 'TransactionImportDialog',
  components: {
    ProgressDialog,
    SecurityMappingDialog,
    TransactionConfirmationDialog,
  },
  props: {
    modelValue: Boolean,
  },
  emits: ['update:modelValue', 'import-completed'],
  setup(props, { emit }) {
    const { handleApiError } = useErrorHandler()
    const { isConnected, lastMessage, sendMessage, connect, disconnect } = useWebSocket('/ws/transactions/')
    const importState = useImportState()

    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => {
        emit('update:modelValue', value)
        if (!value) {
          resetDialogPartial()
        }
      }
    })

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
    const showSuccessDialog = ref(false)
    const importStats = ref({
      totalTransactions: 0,
      importedTransactions: 0,
      skippedTransactions: 0,
      // newSecurities: 0,
      // unrecognizedSecurities: []
    })
    const importProgress = ref(0)
    const currentImported = ref(0)
    const totalToImport = ref(0)
    const currentImportMessage = ref('')
    const importError = ref('')
    const canStopImport = ref(true)

    const unrecognizedSecurities = ref([])
    const securityMappings = ref({})
    const showUnrecognizedSecuritiesDialog = ref(false)
    const existingSecurities = ref([])

    const showSecurityMappingDialog = ref(false)
    const securityToMap = ref('')
    const bestMatch = ref(null)

    const error = ref(null)

    const showTransactionConfirmationDialog = ref(false)
    const currentTransaction = ref(null)
    const currentTransactionIndex = ref(0)
    const totalTransactions = ref(0)

    const handleFileChange = (event) => {
      file.value = event.target.files[0]
      isAnalyzed.value = false
      brokerIdentified.value = false
      selectedBroker.value = null
      identifiedBroker.value = null
      brokerIdentificationComplete.value = false
      fileId.value = null
      console.log('File changed:', file.value)
    }

    const closeDialog = () => {
      dialog.value = false
      resetDialogPartial()
    }

    const submitFile = async () => {
      if (file.value) {
        isLoading.value = true
        importState.setState('analyzing')
        try {
          const formData = new FormData()
          formData.append('file', file.value)
          console.log('Submitting file:', file.value)
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
        } finally {
          isLoading.value = false
          brokerIdentificationComplete.value = true
        }
      } else {
        console.error('No file selected')
        importState.setState('error', 'No file selected')
      }
    }

    const handleWebSocketMessage = (message) => {
      if (message.type === 'import_update') {
        handleImportUpdate(message.data)
      } else if (message.type === 'import_error') {
        handleImportError(message.data.error)
      } else if (message.type === 'import_complete') {
        handleImportSuccess(message.data)
      } else if (message.type === 'transaction_confirmation') {
        handleTransactionConfirmation(message.data)
      }
    }

    const handleImportUpdate = (update) => {
      console.log('[TransactionImportDialog] Import update:', update)
      if (update.status === 'progress') {
        importProgress.value = update.progress
        currentImported.value = update.current
        totalToImport.value = update.total
        currentImportMessage.value = update.message
        importState.setProgress(update.progress)
        importState.setState('importing', update.message)
      } else if (update.status === 'security_mapping') {
        handleSecurityMapping(update)
      } else if (update.status === 'transaction_confirmation') {
        handleTransactionConfirmation(update)
      } else if (update.status === 'complete') {
        handleImportSuccess(update.data)
      } else if (update.error) {
        importError.value = update.error
        importState.setState('error', update.error)
      }
    }

    const handleImportError = (error) => {
      importError.value = error
      importState.setState('error', error)
    }

    const handleSecurityMapping = (data) => {
      securityToMap.value = data.security
      bestMatch.value = data.best_match
      showSecurityMappingDialog.value = true
      importState.setSecurityToMap(data.security)
    }

    const handleSecurityMapped = (securityId) => {
      showSecurityMappingDialog.value = false
      if (isConnected.value) {
        sendMessage({
          type: 'security_mapped',
          security_id: securityId
        })
      }
    }

    const handleTransactionConfirmation = (data) => {
      currentTransaction.value = data.data
      currentTransactionIndex.value = data.index
      totalTransactions.value = data.total
      showTransactionConfirmationDialog.value = true
    }

    const confirmTransaction = () => {
      showTransactionConfirmationDialog.value = false
      console.log('[TransactionImportDialog] Confirming transaction:', isConnected.value)
      if (isConnected.value) {
        sendMessage({
          type: 'transaction_confirmed',
          confirmed: true
        })
      }
    }

    const skipTransaction = () => {
      showTransactionConfirmationDialog.value = false
      console.log('[TransactionImportDialog] Skipping transaction:', isConnected.value)
      if (isConnected.value) {
        sendMessage({
          type: 'transaction_confirmed',
          confirmed: false
        })
      }
    }

    const handleImportSuccess = (result) => {
      importState.setState('complete', 'Import completed successfully')
      importStats.value = result
      showSuccessDialog.value = true
      emit('import-completed', result)
    }

    const startImport = async () => {
      if (!fileId.value || !selectedBroker.value) {
        importState.setState('error', 'File and broker must be selected')
        return
      }

      importState.setState('importing')
      showProgressDialog.value = true
      dialog.value = false // Close the main dialog

      connect()

      // Wait for connection
      await new Promise((resolve) => {
        const checkConnection = setInterval(() => {
          if (isConnected.value) {
            clearInterval(checkConnection)
            resolve()
          }
        }, 100)
      })

      if (isConnected.value) {
        console.log('WebSocket connected, sending start_import message')
        sendMessage({
          type: 'start_import',
          file_id: fileId.value,
          broker_id: selectedBroker.value
        })
      } else {
        console.error('WebSocket not connected')
        importError.value = 'WebSocket not connected. Please try again.'
        importState.setState('error', importError.value)
      }
    }

    const stopImport = () => {
      if (isConnected.value) {
        sendMessage({ type: 'stop_import' })
      }
      importState.setState('idle')
      showProgressDialog.value = false
    }

    const closeSuccessDialog = () => {
      showSuccessDialog.value = false
      resetDialogFull()
      closeDialog()
    }

    const resetDialogPartial = () => {
      file.value = null
      isAnalyzed.value = false
      brokerIdentified.value = false
      identifiedBroker.value = null
      brokerIdentificationComplete.value = false
      resetProgressDialog()
    }

    const resetDialogFull = () => {
      resetDialogPartial()
      fileId.value = null
      selectedBroker.value = null
    }

    const resetProgressDialog = () => {
      importProgress.value = 0
      currentImported.value = 0
      totalToImport.value = 0
      currentImportMessage.value = ''
      importError.value = ''
      canStopImport.value = true
      importState.setProgress(0)
      importState.setState('idle')
    }

    watch(lastMessage, (newMessage) => {
      if (newMessage) {
        handleWebSocketMessage(newMessage)
      }
    })

    watch(isConnected, (newValue) => {
      if (newValue) {
        console.log('WebSocket is connected')
      } else {
        console.log('WebSocket is not connected')
      }
    })

    onUnmounted(() => {
      disconnect()
    })

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
      importProgress,
      currentImported,
      totalToImport,
      currentImportMessage,
      importError,
      canStopImport,
      unrecognizedSecurities,
      securityMappings,
      showUnrecognizedSecuritiesDialog,
      existingSecurities,
      showSecurityMappingDialog,
      securityToMap,
      bestMatch,
      handleFileChange,
      closeDialog,
      submitFile,
      startImport,
      stopImport,
      closeSuccessDialog,
      resetProgressDialog,
      handleSecurityMapped,
      error,
      importState,
      importStats,
      isConnected,
      showTransactionConfirmationDialog,
      currentTransaction,
      currentTransactionIndex,
      totalTransactions,
      confirmTransaction,
      skipTransaction,
    }
  }
}
</script>