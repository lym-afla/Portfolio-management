<template>
  <v-dialog v-model="dialog" max-width="700px">
    <v-card>
      <v-card-title class="text-h5">Import Transactions</v-card-title>

      <v-card-text>
        <!-- Initial Method Selection -->
        <v-fade-transition>
          <ImportMethodStep
            v-if="!importMethodSelected"
            :selected="importMethod"
            :has-connected-brokers="hasConnectedBrokers"
            @select="selectMethod"
          />
        </v-fade-transition>

        <!-- Method-specific configuration and the post-analysis review -->
        <ImportSourceStep
          v-if="importMethodSelected"
          :method="importMethod"
          :brokers="connectedBrokers"
          :selected-broker="selectedBroker"
          :date-range="dateRange"
          :file="file"
          :is-galaxy="isGalaxy"
          :confirm-every-transaction="confirmEveryTransaction"
          :validation="showValidation"
          :busy="isAnalyzed || isLoading"
          @update:selected-broker="selectedBroker = $event"
          @update:date-range="dateRange = $event"
          @update:is-galaxy="isGalaxy = $event"
          @update:confirm-every-transaction="confirmEveryTransaction = $event"
          @file-changed="handleFileChange"
        />
        <ImportReviewStep
          v-if="isAnalyzed"
          :identified="accountIdentified"
          :identified-name="identifiedAccount?.name ?? null"
          :accounts="accountDisplayItems"
          :selected-account="selectedAccount"
          :validation="showValidation"
          :show-currency="isGalaxy"
          :show-account="!isGalaxy"
          :currency="selectedCurrency"
          :currencies="currencies"
          @update:selected-account="selectedAccount = $event"
          @update:currency="selectedCurrency = $event"
        />
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
        <ImportResult :result="importStats" />
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
import ImportMethodStep from '@/features/imports/ImportMethodStep.vue'
import ImportSourceStep from '@/features/imports/ImportSourceStep.vue'
import ImportReviewStep from '@/features/imports/ImportReviewStep.vue'
import ImportResult from '@/features/imports/ImportResult.vue'
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
// interface (Boolean(await connect())). The adapter preserves the incumbent
// restart rule of clearing intentionalClose/connectionAttempted before each
// connect attempt so a later run can reconnect after a teardown; no second
// socket or reconnect logic is introduced. Every connect first closes the
// previous socket, so an orphaned old server session cannot keep feeding
// events into a replacement run.
const {
  isConnected,
  lastMessage,
  sendMessage,
  connect,
  disconnect,
  reset: resetTransportFlags,
} = useWebSocket('/ws/transactions/')

// Disconnections we caused ourselves (teardown, close-before-reconnect) are
// not service losses; only an unexpected remote close notifies the run.
let selfDisconnected = false
const transport = {
  connect: async () => {
    selfDisconnected = true
    disconnect()
    resetTransportFlags()
    const connected = Boolean(await connect())
    if (connected) selfDisconnected = false
    return connected
  },
  send: (command) => Boolean(sendMessage(command)),
  disconnect: () => {
    selfDisconnected = true
    disconnect()
  },
  causedDisconnect: () => selfDisconnected,
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
  lastRunError,
  selectMethod: selectWorkflowMethod,
  back,
  analyze,
  startFile,
  startApi,
  requestStop,
  notifyDisconnected,
  receive,
  reset,
  dispose,
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
const isAnalyzingState = computed(() => stateKind.value === 'analyzing')

const brokersLoading = ref(false)
const isLoading = computed(() => isAnalyzingState.value || brokersLoading.value)

// Terminal errors come from the error state; recoverable in-run errors
// (row-level import_error etc.) surface through lastRunError while the run
// keeps tracking.
const errorMessage = computed(() =>
  stateKind.value === 'error'
    ? state.value.message
    : (lastRunError.value ?? '')
)
const showErrorDialog = computed(
  () => stateKind.value === 'error' || lastRunError.value !== null
)

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
const canStopImport = computed(() =>
  ['running', 'decision'].includes(stateKind.value)
)

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

// Security creation form: opened directly for creation-needed decisions,
// after the create/skip confirmation for error-origin decisions, and via
// "Create New Security" from a mapping decision (name/ISIN/symbol carried
// over from the mapping payload).
const securityFormRequested = ref(false)
const showSecurityDialog = computed(() => {
  const origin = securityDecisionOrigin.value
  if (origin === 'creation-needed') return true
  return origin !== null && securityFormRequested.value
})
const securityFormData = computed(() => {
  const origin = securityDecisionOrigin.value
  if (origin === 'creation-needed') {
    const info = decisionPayload.value.info
    return {
      name: info.name,
      ISIN: info.isin ?? '',
      currency: info.currency || 'RUB',
      type: 'Stock',
      exposure: 'Equity',
    }
  }
  if (origin === 'error') {
    const info = decisionPayload.value.info
    return {
      name: info.name,
      ISIN: info.isin ?? '',
      currency: 'RUB',
      type: 'Stock',
      exposure: 'Equity',
    }
  }
  if (origin === 'mapping' && securityFormRequested.value) {
    const payload = decisionPayload.value
    return {
      name: payload.description ?? '',
      ISIN: payload.isin ?? '',
      symbol: payload.symbol ?? '',
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
  // Only a USER-initiated close (Esc, overlay) cancels the run: the server
  // cannot proceed without a matching answer, so the owned connection is
  // torn down instead of lingering. The model flip caused by the decision
  // resolving (state leaves accounts-match) is not a cancel.
  const current = state.value
  const awaitingMatch =
    current.kind === 'decision' &&
    current.decision === 'accounts' &&
    current.payload.variant === 'match'
  if (!awaitingMatch) return
  reset()
}

const closeSuccessDialog = () => {
  reset()
}

const closeErrorDialog = () => {
  if (stateKind.value === 'error') {
    dismissError()
  } else {
    // Recoverable in-run error: dismiss the notice; the run keeps tracking.
    lastRunError.value = null
  }
}

const resetImport = () => {
  reset()
}

// Messages are only owned while a connection is open: frames that straggle
// in from a socket we just closed (or during a reconnect window) must not
// reach the workflow.
watch(lastMessage, (message) => {
  if (!message) return
  if (!isConnected.value) return
  receive(message)
})

watch(isConnected, (connected) => {
  if (!connected && !transport.causedDisconnect()) {
    notifyDisconnected()
  }
})

// A new decision clears presentation leftovers from the previous one: the
// mapping selection must never leak into the next confirmation.
watch(decision, () => {
  selectedSecurityId.value = null
  securityFormRequested.value = false
})

onUnmounted(() => {
  // Final teardown: invalidates every pending await (a pending connect can
  // no longer send its start) and closes the owned connection.
  dispose()
})
</script>


<style scoped>
.v-list-item {
  min-height: 32px;
}

.text-wrap {
  white-space: normal;
  word-wrap: break-word;
}
</style>
