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
        ></v-autocomplete>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue darken-1" text @click="closeDialog">Cancel</v-btn>
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
          :disabled="!selectedBroker"
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
    v-model="showProgressDialog"
    :title="'Importing Transactions'"
    :progress="importProgress"
    :current="currentImported"
    :total="totalToImport"
    :current-message="currentImportMessage"
    :error="importError"
    :can-stop="canStopImport"
    @stop-import="stopImport"
    @reset="resetProgressDialog"
  />

  <SecurityMappingDialog
    v-model="showSecurityMappingDialog"
    :security="securityToMap"
    :best-match="bestMatch"
    @security-mapped="handleSecurityMapped"
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
          <v-col cols="6">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="warning" size="40">
                    <v-icon dark>mdi-help-circle</v-icon>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-h6">
                  {{ importStats.unrecognizedSecurities.length }}
                </v-list-item-title>
                <v-list-item-subtitle>Unrecognized securities</v-list-item-subtitle>
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

  <v-dialog v-model="showUnrecognizedSecuritiesDialog" max-width="600px">
    <v-card>
      <v-card-title>Unrecognized Securities</v-card-title>
      <v-card-text>
        <p>The following securities were not recognized. Please map them to existing securities or create new ones:</p>
        <v-list>
          <v-list-item v-for="security in unrecognizedSecurities" :key="security">
            <v-list-item-title>{{ security }}</v-list-item-title>
            <template v-slot:append>
              <v-autocomplete
                v-model="securityMappings[security]"
                :items="existingSecurities"
                item-title="name"
                item-value="id"
                label="Select existing security"
                clearable
                style="max-width: 300px;"
              ></v-autocomplete>
              <v-btn v-if="!securityMappings[security]" @click="createNewSecurity(security)" color="primary" text>
                Create New Security
              </v-btn>
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" @click="confirmSecurityMappings">Confirm and Import</v-btn>
      </v-card-actions>
    </v-card>

    <v-alert v-if="error" type="error" dismissible>
      {{ error }}
    </v-alert>

  </v-dialog>
</template>

<script>
import { ref, computed, watch, onUnmounted } from 'vue'
import { analyzeFile, getBrokers, importTransactions } from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'
import ProgressDialog from '@/components/dialogs/ProgressDialog.vue'
import SecurityMappingDialog from '@/components/dialogs/SecurityMappingDialog.vue'
import { useStore } from 'vuex';

export default {
  name: 'TransactionImportDialog',
  components: {
    ProgressDialog,
    SecurityMappingDialog
  },
  props: {
    modelValue: Boolean,
  },
  emits: ['update:modelValue', 'import-completed'],
  setup(props, { emit }) {
    const dialog = computed({
      get: () => props.modelValue,
      set: (value) => {
        emit('update:modelValue', value)
        if (!value) {
          // Only reset certain parts of the dialog when closing
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
      newSecurities: 0,
      unrecognizedSecurities: []
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

    const socket = ref(null)
    const error = ref(null)

    const { handleApiError } = useErrorHandler()
    const store = useStore();

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
        } catch (error) {
          handleApiError(error)
        } finally {
          isLoading.value = false
          brokerIdentificationComplete.value = true
        }
      } else {
        console.error('No file selected')
      }
    }

    const startImport = () => {
      error.value = null  // Clear any previous errors
      const token = store.state.token
      const wsScheme = window.location.protocol === "https:" ? "wss" : "ws"
      const wsUrl = `${wsScheme}://${window.location.host}/ws/transactions/?token=${token}`
      
      console.log('Attempting to connect to WebSocket:', wsUrl)
      
      socket.value = new WebSocket(wsUrl)
      
      socket.value.onopen = () => {
        console.log('WebSocket connection opened')
        socket.value.send(JSON.stringify({
          type: 'start_import',
          file_id: fileId.value,
          broker_id: selectedBroker.value
        }))
      }

      socket.value.onerror = (event) => {
        console.error('WebSocket error:', event)
        error.value = 'An error occurred with the WebSocket connection.'
      }

      socket.value.onclose = (event) => {
        console.log('WebSocket connection closed:', event)
        if (!error.value) {
          error.value = 'WebSocket connection closed unexpectedly.'
        }
      }

      socket.value.onmessage = (event) => {
        console.log('Received message:', event.data)
        const data = JSON.parse(event.data)
        if (data.type === 'import_error') {
          error.value = data.data.error
        } else if (data.type === 'import_update') {
          handleImportUpdate(data.data)
        }
      }
    }

    const handleImportUpdate = (update) => {
      if (update.status === 'progress') {
        importProgress.value = update.progress
        currentImported.value = update.current
        totalToImport.value = update.total
        currentImportMessage.value = update.message
      } else if (update.status === 'security_mapping') {
        securityToMap.value = update.security
        bestMatch.value = update.best_match
        showSecurityMappingDialog.value = true
      } else if (update.status === 'complete') {
        handleImportSuccess(update.data)
      }
    }

    const handleSecurityMapped = (securityId) => {
      showSecurityMappingDialog.value = false
      if (socket.value && socket.value.readyState === WebSocket.OPEN) {
        socket.value.send(JSON.stringify({
          type: 'security_mapped',
          security_id: securityId
        }))
      }
    }

    const confirmSecurityMappings = async () => {
      try {
        const result = await importTransactions(fileId.value, selectedBroker.value, securityMappings.value)
        handleImportSuccess(result)
      } catch (error) {
        handleApiError(error)
      } finally {
        showUnrecognizedSecuritiesDialog.value = false
      }
    }

    const createNewSecurity = async (securityName) => {
      console.log('Creating new security:', securityName)
      // Implement logic to create a new security
      // This could open a new dialog or navigate to a new security creation page
      // After creation, update the securityMappings
    }

    const handleImportSuccess = (result) => {
      importStats.value = result.importResults
      showSuccessDialog.value = true
      emit('import-completed', result.importResults)
    }

    const stopImport = () => {
      // Implement stop import logic here
      showProgressDialog.value = false
      importError.value = 'Import stopped by user'
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
      showProgressDialog.value = false
      importProgress.value = 0
      currentImported.value = 0
      totalToImport.value = 0
      currentImportMessage.value = ''
      importError.value = ''
      canStopImport.value = true
    }

    onUnmounted(() => {
      if (socket.value) {
        socket.value.close()
      }
    })

    watch(() => props.modelValue, (newValue) => {
      if (!newValue) {
        resetDialogPartial()
      }
    })

    return {
      dialog,
      file,
      isLoading,
      isAnalyzed,
      selectedBroker,
      brokers,
      brokerIdentified,
      identifiedBroker,
      brokerIdentificationComplete,
      showSuccessDialog,
      showProgressDialog,
      importStats,
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
      confirmSecurityMappings,
      createNewSecurity,
      stopImport,
      closeSuccessDialog,
      resetProgressDialog,
      handleSecurityMapped,
      error
    }
  }
}
</script>