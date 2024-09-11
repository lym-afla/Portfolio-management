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
                  {{ importStats.totalImported }}
                </v-list-item-title>
                <v-list-item-subtitle>Total transactions imported</v-list-item-subtitle>
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
                  {{ importStats.failedTransactions }}
                </v-list-item-title>
                <v-list-item-subtitle>Failed transactions</v-list-item-subtitle>
              </v-list-item>
            </v-card>
          </v-col>
          <v-col cols="6">
            <v-card outlined>
              <v-list-item>
                <template v-slot:prepend>
                  <v-avatar color="success" size="40">
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
import { ref, computed, watch } from 'vue'
import { analyzeFile, getBrokers, importTransactions } from '@/services/api'
import { useErrorHandler } from '@/composables/useErrorHandler'
import ProgressDialog from '@/components/dialogs/ProgressDialog.vue'

export default {
  name: 'TransactionImportDialog',
  components: {
    ProgressDialog
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
    const showSuccessDialog = ref(false)
    const showProgressDialog = ref(false)
    const importStats = ref({
      totalImported: 0,
      failedTransactions: 0,
      newSecurities: 0
    })

    // Progress dialog related refs
    const importProgress = ref(0)
    const currentImported = ref(0)
    const totalToImport = ref(0)
    const currentImportMessage = ref('')
    const importError = ref('')
    const canStopImport = ref(true)

    const { handleApiError } = useErrorHandler()

    const handleFileChange = () => {
      isAnalyzed.value = false
      selectedBroker.value = null
      brokerIdentified.value = false
      identifiedBroker.value = null
      brokerIdentificationComplete.value = false
      fileId.value = null  // Reset fileId when a new file is selected
    }

    const closeDialog = () => {
      dialog.value = false
    }

    const submitFile = async () => {
      if (file.value) {
        isLoading.value = true
        try {
          const result = await analyzeFile(file.value)
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
      }
    }

    const startImport = () => {
      if (fileId.value && selectedBroker.value) {
        dialog.value = false
        showProgressDialog.value = true
        processImportTransactions()
      } else {
        console.error('File ID or selected broker is missing')
      }
    }

    const processImportTransactions = async () => {
      try {
        console.log('Importing with fileId:', fileId.value, 'and brokerId:', selectedBroker.value)
        const result = await importTransactions(fileId.value, selectedBroker.value)
        // Simulating progress updates
        totalToImport.value = 100
        for (let i = 1; i <= totalToImport.value; i++) {
          currentImported.value = i
          importProgress.value = (i / totalToImport.value) * 100
          currentImportMessage.value = `Importing transaction ${i}`
          await new Promise(resolve => setTimeout(resolve, 50)) // Simulating delay
        }

        importStats.value = {
          totalImported: result.importResults.importedTransactions,
          failedTransactions: result.importResults.failedTransactions,
          newSecurities: result.importResults.newSecurities
        }
        showProgressDialog.value = false
        showSuccessDialog.value = true
        emit('import-completed', result.importResults)
      } catch (error) {
        handleApiError(error)
        importError.value = 'An error occurred during import'
      }
    }

    const stopImport = () => {
      // Implement stop import logic here
      showProgressDialog.value = false
      importError.value = 'Import stopped by user'
    }

    const closeSuccessDialog = () => {
      showSuccessDialog.value = false
      resetDialogFull()  // Full reset after successful import
      closeDialog()
    }

    const resetDialogPartial = () => {
      // Reset only visual states, keep fileId and selectedBroker
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
      handleFileChange,
      closeDialog,
      submitFile,
      startImport,
      stopImport,
      closeSuccessDialog,
      resetProgressDialog
    }
  }
}
</script>