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
                        selected: importMethod === 'api',
                        disabled: !hasConnectedBrokers,
                      }"
                      :disabled="!hasConnectedBrokers"
                    >
                      <v-card-item>
                        <v-avatar color="primary" size="64" class="mb-4">
                          <v-icon size="32" icon="mdi-api" />
                        </v-avatar>
                        <v-card-title>Direct Import</v-card-title>
                        <v-card-subtitle class="text-wrap">
                          Import transactions directly from your broker
                          <v-chip size="x-small" color="primary" class="ml-2"
                            >Recommended</v-chip
                          >
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
                :class="{ selected: importMethod === 'file' }"
              >
                <v-card-item>
                  <v-avatar color="secondary" size="64" class="mb-4">
                    <v-icon size="32" icon="mdi-file-upload" />
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
              v-model="selectedBroker"
              :items="connectedBrokers"
              item-title="name"
              :item-value="(item) => item"
              label="Select Broker Account"
              :error-messages="
                showValidation && !selectedBroker?.id
                  ? 'Please select a broker account'
                  : ''
              "
              required
              class="mb-4"
              @update:model-value="handleBrokerAccountChange"
              return-object
            />

            <v-row>
              <v-col cols="6">
                <v-text-field
                  v-model="dateRange.from"
                  label="From Date (Optional)"
                  type="date"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="dateRange.to"
                  label="To Date (Optional)"
                  type="date"
                />
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
              :rules="[(v) => !!v || 'File is required']"
              @change="handleFileChange"
              :disabled="isAnalyzed"
            />

            <v-checkbox
              v-model="isGalaxy"
              label="Galaxy"
              class="mt-2"
              :disabled="isAnalyzed"
            />

            <v-select
              v-if="isGalaxy && isAnalyzed"
              v-model="selectedCurrency"
              :items="currencies"
              label="Select Currency"
              class="mt-2"
              :rules="[(v) => !!v || 'Currency is required']"
            />

            <v-alert
              v-if="isAnalyzed && accountIdentificationComplete && !isGalaxy"
              :type="accountIdentified ? 'success' : 'info'"
              class="mt-4 mb-4"
            >
              {{
                accountIdentified
                  ? `Broker account "${identifiedAccount.name}" was automatically identified. Please confirm or select a different broker account.`
                  : 'Broker account could not be automatically identified. Please select a broker account below.'
              }}
            </v-alert>

            <v-select
              v-if="isAnalyzed && accountIdentificationComplete && !isGalaxy"
              v-model="selectedAccount"
              :items="accountDisplayItems"
              item-title="title"
              item-value="id"
              label="Select Account"
              class="mt-2"
              :error-messages="
                showValidation && !selectedAccount
                  ? 'Please select an account'
                  : ''
              "
              required
            />
          </div>
        </v-expand-transition>

        <!-- Common settings shown after method selection -->
        <v-expand-transition>
          <div v-if="importMethodSelected">
            <v-checkbox
              v-model="confirmEveryTransaction"
              label="Confirm every transaction manually"
              class="mt-4"
            />
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
        <v-spacer v-else />
        <v-btn color="error" text @click="closeDialog"> Cancel </v-btn>
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
        <v-icon start color="primary" icon="mdi-import" />
        Import Transaction
      </v-card-title>

      <v-card-text>
        <SecurityMappingDialog
          v-if="showSecurityMapping"
          :showSecurityMapping="showSecurityMapping"
          :security="securityToMap"
          :bestMatch="bestMatch"
          @security-selected="handleSecuritySelected"
          @create-security="handleCreateSecurityFromMapping"
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
                <v-list-item-subtitle
                  >Total transactions processed</v-list-item-subtitle
                >
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
                <v-list-item-subtitle
                  >Successfully imported</v-list-item-subtitle
                >
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
                <v-list-item-subtitle
                  >Skipped transactions</v-list-item-subtitle
                >
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
        <v-alert
          v-if="importStats.warnings && importStats.warnings.length"
          type="warning"
          variant="tonal"
          closable
          class="mt-4"
          title="Some data sources could not be fetched"
        >
          <div class="text-body-2 mb-2">
            Import completed, but these endpoints returned errors and their data
            is not included in the results above:
          </div>
          <ul class="text-body-2 mb-0">
            <li v-for="(warning, index) in importStats.warnings" :key="index">
              <strong>{{ warning.endpoint }}</strong
              >: {{ warning.error }}
            </li>
          </ul>
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
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
      <v-card-text class="pt-4 text-body-1" style="white-space: pre-wrap">
        {{ errorMessage }}
      </v-card-text>
      <v-card-actions>
        <v-spacer />
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
              <v-list-item-subtitle>{{
                securityFormData.name
              }}</v-list-item-subtitle>
            </v-list-item>
            <v-list-item>
              <v-list-item-title>ISIN:</v-list-item-title>
              <v-list-item-subtitle>{{
                securityFormData.ISIN
              }}</v-list-item-subtitle>
            </v-list-item>
            <!-- Add other relevant fields -->
          </v-list>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="error" @click="handleSecurityConfirm(false)">Skip</v-btn>
        <v-btn color="primary" @click="handleSecurityConfirm(true)"
          >Create</v-btn
        >
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
              <br />
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
    :broker-name="selectedBroker?.name || 'Broker'"
    :tinkoff-accounts="tinkoffAccounts"
    :db-accounts="dbAccounts"
    :matched-pairs="matchedPairs"
    @accounts-matched="handleAccountsMatched"
    @create-account="handleAccountCreation"
    @use-existing-matches="handleUseExistingMatches"
    @update:model-value="(value) => !value && closeAccountMatching()"
  />
</template>
<script setup>
import { ref, watch, onUnmounted, computed, onMounted } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useImportState } from '@/composables/useImportState'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { decodeImportEvent } from '@/features/imports/legacyImportProtocol'
import { analyzeFile, getAccounts, getBrokersWithTokens } from '@/services/api'
import ProgressDialog from './ProgressDialog.vue'
import SecurityMappingDialog from './SecurityMappingDialog.vue'
import TransactionImportProgress from '../TransactionImportProgress.vue'
import SecurityFormDialog from './SecurityFormDialog.vue'
import AccountMatchingDialog from './AccountMatchingDialog.vue'
import logger from '@/utils/logger'

const props = defineProps({
  modelValue: Boolean,
})
const emit = defineEmits(['update:modelValue', 'import-completed'])

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
    const currentMappingData = ref(null)

    const showSuccessDialog = ref(false)
    const importStats = ref({
      totalTransactions: 0,
      importedTransactions: 0,
      skippedTransactions: 0,
      duplicateTransactions: 0,
      importErrors: 0,
      warnings: [],
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
    const {
      isConnected,
      lastMessage,
      sendMessage,
      connect,
      disconnect,
      reset,
    } = useWebSocket('/ws/transactions/')

    watch(
      () => props.modelValue,
      (newValue) => {
        dialog.value = newValue
      }
    )

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
      { title: 'RUB', value: 'RUB' },
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
      if (!fileId.value || !selectedAccount.value) {
        importState.setState('error', 'File and account must be selected')
        return
      }

      if (isGalaxy.value && !selectedCurrency.value) {
        importState.setState(
          'error',
          'Currency must be selected for Galaxy import'
        )
        return
      }

      importState.setState('importing')
      showProgressDialog.value = true
      dialog.value = false

      try {
        // Reset WebSocket state before attempting to connect
        // This clears intentionalClose and connectionAttempted flags
        reset()

        // Try to connect but don't block if it fails
        await connect()

        // Wait a moment for connection to establish
        await new Promise((resolve) => setTimeout(resolve, 100))

        if (isConnected.value) {
          const messageSent = sendMessage({
            type: 'start_file_import',
            file_id: fileId.value,
            account_id: selectedAccount.value,
            confirm_every: confirmEveryTransaction.value,
            is_galaxy: isGalaxy.value,
            galaxy_type: isGalaxy.value ? galaxyType.value : null,
            currency: isGalaxy.value ? selectedCurrency.value : null,
          })

          if (!messageSent) {
            throw new Error('Failed to send import start message')
          }
        } else {
          throw new Error('WebSocket not connected. Please try again.')
        }
      } catch (error) {
        logger.error('Unknown', 'Import failed:', error)
        importError.value = error.message
        importState.setState('error', error.message)
        showProgressDialog.value = false
      }
    }

    const stopImport = () => {
      sendMessage({
        type: 'stop_import',
      })
      canStopImport.value = false // Disable stop button while processing
    }

    // Single dispatch (D6 task 1 seam): every incoming frame is validated by
    // the legacy protocol boundary; this applier reproduces the former
    // two-path effects exactly.
    const applyDecodedEvent = (event) => {
      switch (event.kind) {
        case 'initialization':
          totalToImport.value = event.total
          currentImportMessage.value = event.message
          break
        case 'total-count':
          totalToImport.value = event.total
          currentImportMessage.value =
            event.message || `Found ${event.total} transactions to process`
          break
        case 'progress':
          if (event.fromImportUpdate) {
            currentImported.value = event.current
            currentImportMessage.value = event.message
            if (event.percent !== null) {
              importState.setProgress(event.percent)
            } else if (totalToImport.value > 0) {
              importState.setProgress(
                Math.round(
                  (currentImported.value / totalToImport.value) * 100
                )
              )
            }
            importState.setState('importing', event.message)
          } else {
            currentImportMessage.value = event.message
            if (event.total) {
              totalToImport.value = event.total
            }
            if (event.current) {
              currentImported.value = event.current
            }
          }
          break
        case 'transaction-saved':
          currentImported.value = event.current
          currentImportMessage.value = event.message || 'Saving transactions...'
          if (totalToImport.value > 0) {
            importState.setProgress(
              Math.round((currentImported.value / totalToImport.value) * 100)
            )
          }
          break
        case 'item-error':
          logger.error('TransactionImportDialog', 'Transaction error:', event.message)
          currentImportMessage.value = `⚠️ ${event.message}`
          break
        case 'security-mapping':
          securityToMap.value = event.description
          bestMatch.value = event.bestMatch
          currentTransaction.value = event.transaction
          currentMappingData.value = {
            security_description: event.description,
            isin: event.isin,
            symbol: event.symbol,
            best_match: event.bestMatch,
          }
          showSecurityMapping.value = true
          showTransactionConfirmation.value = true
          break
        case 'transaction-confirmation':
          currentTransaction.value = event.transaction
          showTransactionConfirmation.value = true
          showSecurityMapping.value = false
          break
        case 'import-error':
          if (event.securityRelated) {
            handleImportError(event.error)
          } else {
            showAccountMatching.value = false
            showProgressDialog.value = false
            showSuccessDialog.value = false
            showSecurityMapping.value = false
            showTransactionConfirmation.value = false
            errorMessage.value = event.error
            showErrorDialog.value = true
          }
          break
        case 'save-error':
          handleImportError(event.error)
          break
        case 'critical-error':
          showAccountMatching.value = false
          showProgressDialog.value = false
          showSuccessDialog.value = false
          showSecurityMapping.value = false
          showTransactionConfirmation.value = false

          errorMessage.value = event.error
          showErrorDialog.value = true

          // The effective incumbent path tears down via resetImport, which
          // also clears errorMessage (recorded defect D-2: dialog opens
          // empty). Preserved here until the Task 2 state owner.
          disconnect()
          resetImport()
          break
        case 'run-error':
          importError.value = event.message
          currentImportMessage.value = ''
          importState.setState('error', event.message)
          break
        case 'complete':
          handleImportSuccess(event.raw)
          break
        case 'stopped':
          handleImportStopped(event)
          break
        case 'account-matching-required':
          selectedBroker.value = {
            id: event.broker.id,
            name: event.broker.name,
          }
          tinkoffAccounts.value = event.unmatchedTinkoff
          dbAccounts.value = event.unmatchedDb
          matchedPairs.value = event.matchedPairs
          showAccountMatching.value = true
          showProgressDialog.value = false
          break
        case 'account-selection-required':
          availableAccounts.value = event.accounts
          showAccountSelection.value = true
          break
        case 'security-creation-needed':
          securityFormData.value = {
            name: event.info.name,
            ISIN: event.info.isin ?? '',
            currency: event.info.currency || 'RUB',
            type: 'Stock',
            exposure: 'Equity',
          }
          showSecurityDialog.value = true
          break
        case 'ignored':
          break
        case 'protocol-error':
          logger.warn(
            'TransactionImportDialog',
            'Ignored unrecognized import message:',
            event.reason
          )
          break
      }
    }

    const handleImportError = (error) => {
      importError.value = error
      importState.setState('error', error)

      // Check if this is a security-related error and provide options to add or skip
      if (
        error &&
        (error.includes('Security not found') ||
          error.includes('Could not match security') ||
          error.includes('unsupported operand type') ||
          error.includes('NoneType'))
      ) {
        // Try to extract security info from the current import message
        let securityName = ''
        let securityIsin = ''

        // First try to extract from the error message
        const securityMatch = error.match(/([^(]+)\(([^)]+)\)/)
        if (securityMatch && securityMatch.length >= 3) {
          securityName = securityMatch[1].trim()
          securityIsin = securityMatch[2].trim()
        }
        // If not found in error, try the current message
        else if (
          currentImportMessage.value &&
          currentImportMessage.value.includes('security')
        ) {
          const msgMatch = currentImportMessage.value.match(
            /security\s+['"]?([^'"]+)['"]?/i
          )
          if (msgMatch && msgMatch[1]) {
            securityName = msgMatch[1].trim()
          }
        }

        logger.log('TransactionImportDialog', 'Detected security error:', {
          error,
          securityName,
          securityIsin,
          currentMessage: currentImportMessage.value,
        })

        // Show dialog to create new security or skip
        confirmTitle.value = 'Unknown Security Detected'
        confirmMessage.value = securityName
          ? `The security "${securityName}" was not found in the database. Would you like to create it or skip this transaction?`
          : 'An unknown security was encountered during import. Would you like to create it or skip this transaction?'

        securityFormData.value = {
          name: securityName,
          ISIN: securityIsin,
          currency: 'RUB', // Default values
          type: 'Stock',
          exposure: 'Equity',
        }

        confirmDialog.value = true
        return
      }

      handleApiError({ message: error })
    }

    const handleCreateSecurityFromMapping = () => {
      logger.log(
        'TransactionImportDialog',
        'Creating security from mapping data:',
        currentMappingData.value
      )

      // Prepare security form data from mapping information
      securityFormData.value = {
        name: currentMappingData.value.security_description || '',
        ISIN: currentMappingData.value.isin || '',
        symbol: currentMappingData.value.symbol || '',
        currency: 'RUB', // Default value, can be adjusted based on your needs
        type: 'Stock', // Default value
        exposure: 'Equity', // Default value
      }

      // Hide progress dialog while showing the security form
      showProgressDialog.value = false
      showSecurityDialog.value = true
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
            security_id: selectedSecurityId.value,
          })
        } else {
          sendMessage({
            type: 'transaction_confirmed',
            confirmed: true,
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
            security_id: null,
          })
        } else {
          sendMessage({
            type: 'transaction_confirmed',
            confirmed: false,
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
      currentMappingData.value = null
    }

    const handleImportSuccess = (result) => {
      // Normalize warnings so the template's v-if always sees an array even
      // when the backend omits the field (e.g. clean imports, Tinkoff).
      importStats.value = { warnings: [], ...result }
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

    const handleImportStopped = (event) => {
      showProgressDialog.value = false
      currentImportMessage.value = event.message
      // Stats-less stop (the backend finally-block shape): keep the previous
      // stats view instead of crashing the result template (recorded D-1).
      if (event.stats) {
        importStats.value = event.stats
      }

      // Show a notification that import was stopped
      showErrorDialog.value = true
      errorMessage.value = 'Import process was stopped by user'

      // Disconnect WebSocket
      disconnect()

      // Reset states
      resetProgressDialog()
      resetConfirmationState()
    }

    // Matched-account inconsistency guard, checked exactly where the
    // incumbent checked it: before any dispatch, for any envelope carrying a
    // data.error string.
    const isAccountMatchingInconsistency = (message) => {
      if (
        message.data &&
        message.data.error &&
        message.data.error.includes('not matched to any database account') &&
        matchedPairs.value &&
        matchedPairs.value.length > 0
      ) {
        const accountIdMatch = message.data.error.match(/ID: (\d+)/)
        if (accountIdMatch && accountIdMatch[1]) {
          const accountId = accountIdMatch[1]
          const wasMatched = matchedPairs.value.some(
            (pair) => String(pair.tinkoff_account_id) === String(accountId)
          )
          if (wasMatched) {
            errorMessage.value =
              'Server inconsistency detected: An account you matched was not recognized during import. This is likely a server-side bug. Please try again or contact support.'
            showErrorDialog.value = true
            logger.error(
              'TransactionImportDialog',
              'Account matching inconsistency detected:',
              { accountId }
            )
            return true
          }
        }
      }
      return false
    }

    // Main watcher for WebSocket messages
    watch(lastMessage, (message) => {
      if (!message) return
      if (isAccountMatchingInconsistency(message)) return
      applyDecodedEvent(decodeImportEvent(message))
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
      logger.log(
        'TransactionImportDialog',
        'handleSecurityAdded called with:',
        securityData
      )
      logger.log(
        'TransactionImportDialog',
        'showSecurityMapping.value:',
        showSecurityMapping.value
      )
      logger.log('TransactionImportDialog', 'Security ID:', securityData?.id)

      showSecurityDialog.value = false
      securityFormData.value = null

      // Show the progress dialog again
      showProgressDialog.value = true

      // If this was created from security mapping, use it to map the security
      if (showSecurityMapping.value && securityData?.id) {
        logger.log(
          'TransactionImportDialog',
          'Mapping newly created security to transaction, ID:',
          securityData.id
        )
        sendMessage({
          type: 'security_mapped',
          action: 'map',
          security_id: securityData.id,
        })
        resetConfirmationState()
      } else if (securityData?.id) {
        // Inform the server about the newly created security for other cases
        logger.log(
          'TransactionImportDialog',
          'Sending security_confirmation for non-mapping case'
        )
        sendMessage({
          type: 'security_confirmation',
          security_id: securityData.id,
          security_created: true,
          security_data: {
            name: securityData.name,
            id: securityData.id,
          },
        })
      } else {
        logger.error(
          'TransactionImportDialog',
          'Security data missing ID:',
          securityData
        )
      }
    }

    const handleSecuritySkipped = () => {
      logger.log('TransactionImportDialog', 'handleSecuritySkipped called')
      showSecurityDialog.value = false
      securityFormData.value = null

      // Show the progress dialog again
      showProgressDialog.value = true

      // If this was from security mapping, send skip message
      if (showSecurityMapping.value) {
        logger.log(
          'TransactionImportDialog',
          'Skipping transaction due to security creation cancellation'
        )
        sendMessage({
          type: 'security_mapped',
          action: 'skip',
          security_id: null,
        })
        resetConfirmationState()
      } else {
        // Tell the server to skip this transaction for other cases
        sendMessage({
          type: 'security_confirmation',
          security_id: null,
          skip_transaction: true,
        })
      }
    }

    const handleSecurityConfirm = (confirmed) => {
      logger.log(
        'TransactionImportDialog',
        'handleSecurityConfirm called with:',
        confirmed
      )
      confirmDialog.value = false

      if (confirmed) {
        logger.log(
          'TransactionImportDialog',
          'Security confirmed, formData:',
          securityFormData.value
        )
        if (securityFormData.value.readonly) {
          // If it's a readonly object (existing security)
          sendMessage({
            type: 'security_confirmation',
            security_id: securityFormData.value.id,
          })
        } else {
          // Show the form to create a new security
          showSecurityDialog.value = true
        }
      } else {
        // User chose to skip this security/transaction
        handleSecuritySkipped()
      }

      // After handling the security confirmation, reset the error state to continue the import
      importError.value = ''
      errorMessage.value = ''

      // Show the progress dialog again
      if (!showSecurityDialog.value) {
        showProgressDialog.value = true
      }
    }

    // New refs for method selection and API import
    const importMethod = ref(null)
    const importMethodSelected = ref(false)
    const selectedBroker = ref(null)
    const connectedBrokers = ref([])
    const dateRange = ref({
      from: null,
      to: null,
    })

    // Load connected broker accounts on component mount
    onMounted(async () => {
      try {
        isLoading.value = true
        const brokers = await getBrokersWithTokens()
        connectedBrokers.value = brokers.map((broker) => ({
          id: broker.id,
          name: broker.name,
          // Add any other needed broker properties
        }))
      } catch (error) {
        logger.error('Unknown', 'Failed to load broker accounts:', error)
        // Handle error - maybe show a notification
      } finally {
        isLoading.value = false
      }
    })

    // Computed properties
    const hasConnectedBrokers = computed(
      () => connectedBrokers.value.length > 0
    )

    const isApiImportValid = computed(() => {
      return !!selectedBroker.value
    })

    const accountDisplayItems = computed(() =>
      accounts.value.map((a) => ({
        id: a.id,
        title: a.broker?.text
          ? `${a.broker.text} – ${a.name}`
          : a.name,
      }))
    )

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
      selectedBroker.value = null
      dateRange.value = { from: null, to: null }
    }

    // New method for API import
    const startApiImport = async () => {
      showValidation.value = true // Show validation on import attempt

      if (!selectedBroker.value?.id) {
        errorMessage.value = 'Please select a broker account'
        return
      }

      importState.setState('importing')
      showProgressDialog.value = true
      currentImportMessage.value = 'Initializing import...'
      dialog.value = false

      try {
        // Log selected account for debugging
        logger.log('Unknown', 'Selected broker account:', selectedBroker.value)

        // Reset WebSocket state before attempting to connect
        // This clears intentionalClose and connectionAttempted flags
        reset()

        // Try to connect but don't block if it fails
        await connect()

        // Wait a moment for connection to establish
        await new Promise((resolve) => setTimeout(resolve, 100))

        if (!isConnected.value) {
          throw new Error('Failed to establish WebSocket connection')
        }

        currentImportMessage.value = 'Connecting to broker API...'

        const importData = {
          broker_id: selectedBroker.value.id,
          confirm_every_transaction: confirmEveryTransaction.value,
          date_from: dateRange.value?.from || null,
          date_to: dateRange.value?.to || null,
        }

        logger.log('Unknown', 'Import data:', importData)

        const messageSent = sendMessage({
          type: 'start_api_import',
          data: importData,
        })

        if (!messageSent) {
          throw new Error('Failed to send start message')
        }
      } catch (error) {
        logger.error('Unknown', 'API import failed:', error)
        currentImportMessage.value = ''
        errorMessage.value = error.message
        importError.value = error.message
        importState.setState('error', error.message)
        showProgressDialog.value = false
      }
    }

    // Add watcher for selectedBroker
    watch(selectedBroker, (newValue) => {
      logger.log('Unknown', 'Selected broker account changed:', newValue)
    })

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
      logger.log('Unknown', 'Selected broker account:', value) // Debug selected value
      selectedBroker.value = value
      showValidation.value = true
    }

    const showAccountSelection = ref(false)
    const availableAccounts = ref([])

    const selectAccount = (account) => {
      showAccountSelection.value = false
      sendMessage({
        type: 'select_account',
        data: {
          account_id: account.id,
          confirm_every_transaction: confirmEveryTransaction.value,
          date_from: dateRange.value?.from,
          date_to: dateRange.value?.to,
        },
      })
    }

    const showAccountMatching = ref(false)
    const tinkoffAccounts = ref([])
    const dbAccounts = ref([])
    const matchedPairs = ref([])

    const handleAccountsMatched = (selection) => {
      logger.log('Unknown', 'Account pairs selected:', selection.pairs)

      // Validate that we have valid pairs data
      if (!selection || !selection.pairs || !Array.isArray(selection.pairs)) {
        logger.error('Unknown', 'Invalid account pairs data:', selection)
        errorMessage.value = 'Invalid account pairing data received'
        return
      }

      // Check if we have at least one pair
      if (selection.pairs.length === 0) {
        logger.error('Unknown', 'No account pairs provided')
        errorMessage.value = 'No account pairs were provided'
        return
      }

      // Send the data to the server
      try {
        sendMessage({
          type: 'accounts_matched',
          data: {
            pairs: selection.pairs,
          },
        })
        // Hide the account matching dialog and show progress
        showAccountMatching.value = false
        showProgressDialog.value = true
      } catch (error) {
        logger.error('Unknown', 'Error sending account matches:', error)
        errorMessage.value = 'Error sending account matches to server'
      }
    }

    const handleAccountCreation = (data) => {
      logger.log('Unknown', 'Creating new account with data:', data)

      // Validate the data
      if (!data || !data.tinkoff_account || !data.name) {
        logger.error('Unknown', 'Invalid account creation data:', data)
        errorMessage.value = 'Invalid account creation data'
        return
      }

      try {
        sendMessage({
          type: 'create_account',
          data: {
            tinkoff_account: data.tinkoff_account,
            name: data.name,
            comment: data.comment || '',
          },
        })
        // Hide the account matching dialog and show progress
        showAccountMatching.value = false
        showProgressDialog.value = true
      } catch (error) {
        logger.error(
          'TransactionImportDialog',
          'Error sending account creation request:',
          error
        )
        errorMessage.value = 'Error creating new account'
      }
    }

    const closeAccountMatching = () => {
      showAccountMatching.value = false
      // Reset the WebSocket connection if needed
      if (importError.value) {
        disconnect()
        resetImport()
      }
    }

    const handleUseExistingMatches = (data) => {
      logger.log(
        'TransactionImportDialog',
        'Using existing account matches:',
        data.pairs
      )

      // Validate that we have valid pairs data
      if (!data || !data.pairs || !Array.isArray(data.pairs)) {
        logger.error(
          'TransactionImportDialog',
          'Invalid existing pairs data:',
          data
        )
        errorMessage.value = 'Invalid existing account pairs data'
        return
      }

      // Check if we have at least one pair
      if (data.pairs.length === 0) {
        logger.error(
          'TransactionImportDialog',
          'No existing account pairs available'
        )
        errorMessage.value = 'No existing account pairs were found'
        return
      }

      // Log the pairs before sending
      logger.log(
        'TransactionImportDialog',
        'Sending matched pairs to server:',
        JSON.stringify(data.pairs, null, 2)
      )

      // Send the data to the server
      try {
        sendMessage({
          type: 'use_existing_matches',
          data: {
            pairs: data.pairs,
          },
        })
        // Hide the account matching dialog and show progress
        showAccountMatching.value = false
        showProgressDialog.value = true
      } catch (error) {
        logger.error(
          'TransactionImportDialog',
          'Error sending existing matches:',
          error
        )
        errorMessage.value = 'Error sending existing matches to server'
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
  min-height: 32px;
}

.text-wrap {
  white-space: normal;
  word-wrap: break-word;
}
</style>
