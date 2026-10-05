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
// D6 task 2: the dialog is the compatible entrypoint. Workflow state,
// transport orchestration and lifecycle safety live in useTransactionImport
// over the discriminated useImportState owner; the bindings below are
// projections of that state plus editable configuration refs, and the
// handler methods are thin intent adapters kept for the reviewed template
// until task 3 splits the steps into components.
import { ref, watch, onUnmounted, computed, onMounted, inject } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useTransactionImport } from '@/features/imports/useTransactionImport'
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

watch(
  () => props.modelValue,
  (newValue) => {
    dialog.value = newValue
  }
)

watch(dialog, (newValue) => {
  emit('update:modelValue', newValue)
})

// Existing WebSocket composable, normalized behind the D6 ImportTransport
// interface (Boolean(await connect())); no second socket or reconnect logic.
const {
  isConnected,
  lastMessage,
  sendMessage,
  connect,
  disconnect,
} = useWebSocket('/ws/transactions/')

const transport = {
  connect: async () => Boolean(await connect()),
  send: (command) => Boolean(sendMessage(command)),
  disconnect,
}

const { handleApiError } = useErrorHandler()
// Plain-string payloads are inline validation feedback (e.g. empty pair
// lists); they go straight to the app toast instead of the error mapper.
const showError = inject('showError')

const importer = useTransactionImport({
  transport,
  analyze: analyzeFile,
  fetchAccounts: getAccounts,
  onCompleted: (raw) => emit('import-completed', raw),
  onError: (error) =>
    typeof error === 'string' ? showError?.(error) : handleApiError(error),
})

const {
  state,
  configuration,
  stats,
  selectMethod: selectWorkflowMethod,
  back,
  analyze,
  startFile,
  startApi,
  requestStop,
  notifyDisconnected,
  receive,
  reset,
  dismissError,
  resolveSecurityMapping,
  resolveSecurityCreated,
  resolveSecuritySkipped,
  resolveTransaction,
  resolveAccountSelection,
  resolveAccountMatched,
  resolveUseExistingMatches,
  resolveCreateAccount,
} = importer

// ---------------------------------------------------------------------
// State projections (computed views; the state owner is the authority).
// ---------------------------------------------------------------------
const stateKind = computed(() => state.value.kind)
const stateMethod = computed(() =>
  ['configure', 'analyzing', 'review', 'running', 'stopping'].includes(
    stateKind.value
  )
    ? state.value.method
    : null
)
const decision = computed(() =>
  stateKind.value === 'decision' ? state.value : null
)
const decisionPayload = computed(() =>
  decision.value ? decision.value.payload : null
)
const securityDecisionOrigin = computed(() =>
  decision.value && decision.value.decision === 'security'
    ? decisionPayload.value.origin ?? 'mapping'
    : null
)

const importMethodSelected = computed(() =>
  ['configure', 'analyzing', 'review'].includes(stateKind.value)
)
// Pending card selection before Continue; the workflow method once chosen.
const pendingMethod = ref(null)
const importMethod = computed(
  () => stateMethod.value ?? pendingMethod.value
)

const isAnalyzed = computed(() => stateKind.value === 'review')
const accountIdentificationComplete = computed(() => stateKind.value === 'review')
const isAnalyzingState = computed(() => stateKind.value === 'analyzing')

const brokersLoading = ref(false)
const isLoading = computed(() => isAnalyzingState.value || brokersLoading.value)

const importError = computed(() =>
  stateKind.value === 'error' ? state.value.message : ''
)
const errorMessage = importError
const showErrorDialog = computed(() => stateKind.value === 'error')

// The main configuration dialog closes while a run owns the flow; it
// reopens when the workflow returns to a configurable state (recoverable
// errors keep it open so the user can retry with the inputs intact).
watch(stateKind, (kind, prev) => {
  if (['running', 'decision', 'stopping', 'complete'].includes(kind)) {
    dialog.value = false
    return
  }
  if (kind === 'error') {
    dialog.value = state.value.canReturnToConfiguration
    return
  }
  if (['running', 'decision', 'stopping', 'error'].includes(prev ?? '')) {
    dialog.value = true
  }
})

const showProgressDialog = computed(() => {
  if (stateKind.value === 'running' || stateKind.value === 'stopping') {
    return true
  }
  if (stateKind.value === 'decision') {
    // Accounts decisions render their own dialogs instead of the progress
    // dialog; security/transaction decisions render inside its slot.
    const current = decision.value
    return current.decision === 'security' || current.decision === 'transaction'
  }
  return false
})
const runningState = computed(() =>
  stateKind.value === 'running' ? state.value : null
)
const currentImported = computed(() => runningState.value?.current ?? 0)
const totalToImport = computed(() => runningState.value?.total ?? 0)
const currentImportMessage = computed(() => runningState.value?.message ?? '')
const canStopImport = computed(() => stateKind.value === 'running')

const showSecurityMapping = computed(
  () => securityDecisionOrigin.value === 'mapping'
)
const showTransactionConfirmation = computed(
  () =>
    decision.value !== null &&
    (decision.value.decision === 'transaction' || showSecurityMapping.value)
)
const securityToMap = computed(() =>
  showSecurityMapping.value ? decisionPayload.value.description : ''
)
const bestMatch = computed(() =>
  showSecurityMapping.value ? decisionPayload.value.bestMatch : null
)
const currentTransaction = computed(() => {
  if (!decision.value) return {}
  if (decision.value.decision === 'transaction') {
    return decisionPayload.value.transaction
  }
  if (showSecurityMapping.value) return decisionPayload.value.transaction
  return {}
})

const showSuccessDialog = computed(() => stateKind.value === 'complete')
const importStats = computed(() => stats.value)

// Security creation form: opened directly for creation-needed decisions or
// after the create/skip confirmation for error-origin decisions.
const securityFormRequested = ref(false)
const showSecurityDialog = computed(() => {
  if (securityDecisionOrigin.value === 'creation-needed') return true
  return (
    securityDecisionOrigin.value === 'error' && securityFormRequested.value
  )
})
const securityFormData = computed(() => {
  if (securityDecisionOrigin.value === 'creation-needed') {
    const info = decisionPayload.value.info
    return {
      name: info.name,
      ISIN: info.isin ?? '',
      currency: info.currency || 'RUB',
      type: 'Stock',
      exposure: 'Equity',
    }
  }
  if (securityDecisionOrigin.value === 'error') {
    const info = decisionPayload.value.info
    return {
      name: info.name,
      ISIN: info.isin ?? '',
      currency: 'RUB',
      type: 'Stock',
      exposure: 'Equity',
    }
  }
  return null
})
const confirmDialog = computed(
  () => securityDecisionOrigin.value === 'error' && !securityFormRequested.value
)
const confirmTitle = computed(() =>
  confirmDialog.value ? 'Unknown Security Detected' : ''
)
const confirmMessage = computed(() => {
  if (!confirmDialog.value) return ''
  const name = decisionPayload.value.info.name
  return name
    ? `The security "${name}" was not found in the database. Would you like to create it or skip this transaction?`
    : 'An unknown security was encountered during import. Would you like to create it or skip this transaction?'
})

// Account matching/selection overlays derive from accounts decisions.
const showAccountSelection = computed(
  () =>
    decision.value !== null &&
    decision.value.decision === 'accounts' &&
    decisionPayload.value.variant === 'select'
)
const availableAccounts = computed(() =>
  showAccountSelection.value ? decisionPayload.value.accounts : []
)
const showAccountMatching = computed(
  () =>
    decision.value !== null &&
    decision.value.decision === 'accounts' &&
    decisionPayload.value.variant === 'match'
)
const tinkoffAccounts = computed(() =>
  showAccountMatching.value ? decisionPayload.value.unmatchedTinkoff : []
)
const dbAccounts = computed(() =>
  showAccountMatching.value ? decisionPayload.value.unmatchedDb : []
)
const matchedPairs = computed(() =>
  showAccountMatching.value ? decisionPayload.value.matchedPairs : []
)

// ---------------------------------------------------------------------
// Configuration (editable) and local presentation refs.
// ---------------------------------------------------------------------
const {
  file,
  fileId,
  isGalaxy,
  galaxyType,
  selectedCurrency,
  confirmEveryTransaction,
  selectedBroker,
  dateRange,
  selectedAccount,
  accounts,
  identifiedAccount,
  accountIdentified,
} = configuration

const currencies = [
  { title: 'USD', value: 'USD' },
  { title: 'EUR', value: 'EUR' },
  { title: 'GBP', value: 'GBP' },
  { title: 'RUB', value: 'RUB' },
]

const selectedSecurityId = ref(null)
const showValidation = ref(false)

const connectedBrokers = ref([])
onMounted(async () => {
  try {
    brokersLoading.value = true
    const brokers = await getBrokersWithTokens()
    connectedBrokers.value = brokers.map((broker) => ({
      id: broker.id,
      name: broker.name,
    }))
  } catch (error) {
    logger.error('Unknown', 'Failed to load broker accounts:', error)
  } finally {
    brokersLoading.value = false
  }
})

const hasConnectedBrokers = computed(() => connectedBrokers.value.length > 0)
const isApiImportValid = computed(() => !!selectedBroker.value?.id)

const accountDisplayItems = computed(() =>
  accounts.value.map((a) => ({
    id: a.id,
    title: a.broker?.text ? `${a.broker.text} – ${a.name}` : a.name,
  }))
)

// ---------------------------------------------------------------------
// Intent adapters (kept until the task 3 step components).
// ---------------------------------------------------------------------
const handleFileChange = (event) => {
  file.value = event.target.files[0]
  // A new file invalidates the previous analysis.
  fileId.value = null
  accountIdentified.value = false
  identifiedAccount.value = null
  selectedAccount.value = null
}

const closeDialog = () => {
  reset()
  pendingMethod.value = null
  dialog.value = false
}

const submitFile = async () => {
  if (!file.value) return
  await analyze(file.value)
}

const startImport = async () => {
  await startFile({
    fileId: fileId.value,
    accountId: selectedAccount.value,
    confirmEvery: confirmEveryTransaction.value,
    isGalaxy: isGalaxy.value,
    galaxyType: galaxyType.value,
    currency: selectedCurrency.value,
  })
}

const startApiImport = async () => {
  showValidation.value = true
  if (!selectedBroker.value?.id) return
  await startApi({
    brokerId: selectedBroker.value.id,
    confirmEvery: confirmEveryTransaction.value,
    dateFrom: dateRange.value?.from || null,
    dateTo: dateRange.value?.to || null,
  })
}

const stopImport = () => {
  requestStop()
}

const selectMethod = (method) => {
  if (method === 'api' && !hasConnectedBrokers.value) return
  pendingMethod.value = method
}

const confirmMethod = () => {
  if (!pendingMethod.value) return
  selectWorkflowMethod(pendingMethod.value)
}

const backToSelection = () => {
  back()
  pendingMethod.value = null
}

const handleSecuritySelected = (securityId) => {
  selectedSecurityId.value = securityId
}

const handleConfirm = () => {
  if (showSecurityMapping.value) {
    resolveSecurityMapping(selectedSecurityId.value)
  } else {
    resolveTransaction(true)
  }
}

const handleSkip = () => {
  if (showSecurityMapping.value) {
    resolveSecurityMapping(null)
  } else {
    resolveTransaction(false)
  }
}

const handleCreateSecurityFromMapping = () => {
  securityFormRequested.value = true
}

const handleSecurityAdded = (securityData) => {
  securityFormRequested.value = false
  if (securityData?.id) {
    resolveSecurityCreated({ id: securityData.id, name: securityData.name })
  }
}

const handleSecuritySkipped = () => {
  securityFormRequested.value = false
  resolveSecuritySkipped()
}

const handleSecurityConfirm = (confirmed) => {
  if (confirmed) {
    securityFormRequested.value = true
  } else {
    securityFormRequested.value = false
    resolveSecuritySkipped()
  }
}

const selectAccount = (account) => {
  resolveAccountSelection(account)
}

const handleAccountsMatched = (selection) => {
  if (!selection || !Array.isArray(selection.pairs)) {
    return
  }
  resolveAccountMatched(selection.pairs)
}

const handleAccountCreation = (data) => {
  if (!data || !data.tinkoff_account || !data.name) {
    return
  }
  resolveCreateAccount({
    tinkoffAccount: data.tinkoff_account,
    name: data.name,
    comment: data.comment,
  })
}

const handleUseExistingMatches = (data) => {
  if (!data || !Array.isArray(data.pairs)) {
    return
  }
  resolveUseExistingMatches(data.pairs)
}

const closeAccountMatching = () => {
  // Closing the matching overlay cancels the run: the server cannot proceed
  // without a matching answer, so the owned connection is torn down instead
  // of lingering (recorded incumbent deviation).
  reset()
}

const closeSuccessDialog = () => {
  reset()
}

const closeErrorDialog = () => {
  dismissError()
}

const resetImport = () => {
  reset()
}

const handleBrokerAccountChange = (value) => {
  selectedBroker.value = value
  showValidation.value = true
}

watch(lastMessage, (message) => {
  if (!message) return
  receive(message)
})

watch(isConnected, (connected) => {
  if (!connected) notifyDisconnected()
})

onUnmounted(() => {
  // Intentional disconnect on unmount: teardown owns this connection.
  disconnect()
})
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
