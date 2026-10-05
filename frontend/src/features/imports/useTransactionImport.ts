// D6 orchestrator: owns transport orchestration and lifecycle safety over
// the single discriminated state owner (useImportState). Configuration
// fields are editable refs, deliberately NOT workflow state. Generation
// ownership makes starts once-only per run, invalidates late analyzer or
// socket callbacks after close/reopen, and lets only the owning generation
// transition state or emit completion.
import { ref } from 'vue'
import { useImportState } from '@/composables/useImportState'
import {
  accountsMatchedCommand,
  apiStartCommand,
  createAccountCommand,
  decodeImportEvent,
  fileStartCommand,
  securityConfirmationCreatedCommand,
  securityConfirmationExistingCommand,
  securityConfirmationSkipCommand,
  securityMappedCommand,
  selectAccountCommand,
  stopCommand,
  transactionConfirmedCommand,
  useExistingMatchesCommand,
} from './legacyImportProtocol'
import type {
  AccountMatchPair,
  ApiStartInput,
  FileStartInput,
  ImportCommand,
  ImportMethod,
  ImportResultData,
  ImportTransport,
  JsonValue,
  TransactionImportState,
} from './types'

export interface TransactionImportOptions {
  transport: ImportTransport
  analyze: (formData: FormData) => Promise<unknown>
  fetchAccounts: () => Promise<Array<Record<string, unknown>>>
  onCompleted?: (raw: Record<string, JsonValue>) => void
  // Receives raw error objects (routed to the app error handler), plain
  // strings for inline validation feedback, or {message} envelopes.
  onError?: (error: unknown) => void
}

export interface ImportConfiguration {
  file: File | null
  fileId: string | number | null
  isGalaxy: boolean
  galaxyType: string
  selectedCurrency: string | null
  confirmEveryTransaction: boolean
  selectedBroker: { id: number; name: string } | null
  dateRange: { from: string | null; to: string | null }
  selectedAccount: number | null
  accounts: Array<Record<string, unknown>>
  identifiedAccount: { id: number; name: string } | null
  accountIdentified: boolean
}

const EMPTY_STATS: ImportResultData = {
  totalTransactions: 0,
  importedTransactions: 0,
  skippedTransactions: 0,
  duplicateTransactions: 0,
  importErrors: 0,
  warnings: [],
}

const STOPPED_MESSAGE = 'Import process was stopped by user'
const DISCONNECTED_MESSAGE =
  'Connection to the server was lost. The import can no longer be followed; please start again.'

function errorMessageOf(error: unknown): string {
  if (typeof error === 'string') return error
  if (error && typeof error === 'object') {
    const candidate = error as { message?: unknown }
    if (typeof candidate.message === 'string' && candidate.message) {
      return candidate.message
    }
  }
  return 'An unexpected error occurred.'
}

function extractSecurityInfoFromError(
  error: string,
  contextMessage: string
): { name: string; isin: string } {
  let name = ''
  let isin = ''
  const match = error.match(/([^(]+)\(([^)]+)\)/)
  if (match && match.length >= 3) {
    name = match[1].trim()
    isin = match[2].trim()
  } else if (contextMessage && contextMessage.includes('security')) {
    const msgMatch = contextMessage.match(/security\s+['"]?([^'"]+)['"]?/i)
    if (msgMatch && msgMatch[1]) {
      name = msgMatch[1].trim()
    }
  }
  return { name, isin }
}

export function useTransactionImport(options: TransactionImportOptions) {
  const importState = useImportState()
  const transition = (next: TransactionImportState) => importState.transition(next)

  // Editable configuration: form fields the user owns, not state-machine
  // transitions.
  const configuration = {
    file: ref<File | null>(null),
    fileId: ref<string | number | null>(null),
    isGalaxy: ref(false),
    galaxyType: ref('transactions'),
    selectedCurrency: ref<string | null>(null),
    confirmEveryTransaction: ref(false),
    selectedBroker: ref<{ id: number; name: string } | null>(null),
    dateRange: ref<{ from: string | null; to: string | null }>({
      from: null,
      to: null,
    }),
    selectedAccount: ref<number | null>(null),
    accounts: ref<Array<Record<string, unknown>>>([]),
    identifiedAccount: ref<{ id: number; name: string } | null>(null),
    accountIdentified: ref(false),
  }

  const progress = ref(0)
  const stats = ref<ImportResultData>({ ...EMPTY_STATS, warnings: [] })
  const lastProtocolIssue = ref<string | null>(null)

  // Server-owned run data; the running state mirrors it. Updated even while
  // a decision overlay holds the state so a resolved decision restores the
  // freshest counters.
  const runData = { current: 0, total: 0, message: '' }
  let runMethod: ImportMethod = 'file'

  let generation = 0
  let stopRequested = false
  const lastConfigMethod = ref<ImportMethod>('file')

  const state = () => importState.state.value
  const sessionActive = () => {
    const kind = state().kind
    return kind === 'running' || kind === 'decision' || kind === 'stopping'
  }

  const resetRunData = () => {
    runData.current = 0
    runData.total = 0
    runData.message = ''
    progress.value = 0
  }

  const syncRunningState = () => {
    if (state().kind !== 'running') return
    transition({
      kind: 'running',
      method: runMethod,
      current: runData.current,
      total: runData.total,
      message: runData.message,
    })
  }

  const restoreRunning = () => {
    transition({
      kind: 'running',
      method: runMethod,
      current: runData.current,
      total: runData.total,
      message: runData.message,
    })
  }

  // ------------------------------------------------------------ starts

  const startFile = async (input: FileStartInput) => {
    if (sessionActive()) return
    if (!input.fileId || !input.accountId) {
      transition({
        kind: 'error',
        message: 'File and account must be selected',
        canReturnToConfiguration: true,
      })
      return
    }
    if (input.isGalaxy && !input.currency) {
      transition({
        kind: 'error',
        message: 'Currency must be selected for Galaxy import',
        canReturnToConfiguration: true,
      })
      return
    }
    // Ownership is claimed before the first await, so a duplicate click
    // lands in sessionActive() and returns without a second connect/send.
    const myGeneration = ++generation
    stopRequested = false
    runMethod = 'file'
    resetRunData()
    transition({ kind: 'running', method: 'file', current: 0, total: 0, message: '' })

    const connected = await options.transport.connect()
    if (myGeneration !== generation) return
    if (!connected) {
      transition({
        kind: 'error',
        message: 'WebSocket not connected. Please try again.',
        canReturnToConfiguration: true,
      })
      return
    }
    if (!options.transport.send(fileStartCommand(input))) {
      transition({
        kind: 'error',
        message: 'Failed to send import start message',
        canReturnToConfiguration: true,
      })
    }
  }

  const startApi = async (input: ApiStartInput) => {
    if (sessionActive()) return
    if (!input.brokerId) {
      transition({
        kind: 'error',
        message: 'Please select a broker account',
        canReturnToConfiguration: true,
      })
      return
    }
    const myGeneration = ++generation
    stopRequested = false
    runMethod = 'api'
    resetRunData()
    transition({
      kind: 'running',
      method: 'api',
      current: 0,
      total: 0,
      message: 'Initializing import...',
    })

    const connected = await options.transport.connect()
    if (myGeneration !== generation) return
    if (!connected) {
      transition({
        kind: 'error',
        message: 'Failed to establish WebSocket connection',
        canReturnToConfiguration: true,
      })
      return
    }
    if (!options.transport.send(apiStartCommand(input))) {
      transition({
        kind: 'error',
        message: 'Failed to send start message',
        canReturnToConfiguration: true,
      })
    }
  }

  // ------------------------------------------------------------ analyze

  const analyze = async (file: File) => {
    if (sessionActive()) return
    if (!file) {
      transition({
        kind: 'error',
        message: 'No file selected',
        canReturnToConfiguration: true,
      })
      return
    }
    const myGeneration = ++generation
    transition({ kind: 'analyzing', method: 'file' })
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('is_galaxy', String(configuration.isGalaxy.value))
      const result = (await options.analyze(formData)) as {
        fileId?: string | number
        status?: string
        identifiedAccount?: { id: number; name: string }
      }
      if (myGeneration !== generation) return
      configuration.fileId.value = result.fileId ?? null
      configuration.accounts.value = await options.fetchAccounts()
      if (myGeneration !== generation) return
      if (result.status === 'account_identified' && result.identifiedAccount) {
        configuration.accountIdentified.value = true
        configuration.identifiedAccount.value = result.identifiedAccount
        configuration.selectedAccount.value = result.identifiedAccount.id
      } else {
        configuration.accountIdentified.value = false
        configuration.identifiedAccount.value = null
        configuration.selectedAccount.value = null
      }
      transition({
        kind: 'review',
        method: 'file',
        accountLabel: configuration.identifiedAccount.value?.name ?? '',
      })
    } catch (error) {
      if (myGeneration !== generation) return
      options.onError?.(error)
      transition({
        kind: 'error',
        message: errorMessageOf(error),
        canReturnToConfiguration: true,
      })
    }
  }

  // ------------------------------------------------------------ navigation

  const selectMethod = (method: ImportMethod) => {
    if (state().kind !== 'choose-method') return
    lastConfigMethod.value = method
    transition({ kind: 'configure', method })
  }

  const back = () => {
    const kind = state().kind
    if (kind === 'configure') {
      configuration.file.value = null
      configuration.selectedBroker.value = null
      configuration.dateRange.value = { from: null, to: null }
      transition({ kind: 'choose-method' })
    } else if (kind === 'review') {
      configuration.selectedAccount.value = null
      transition({ kind: 'configure', method: 'file' })
    }
  }

  // Error dismissal: recoverable errors return to configuration with the
  // inputs intact; terminal ones (run failures, stop, critical) reset the
  // workflow to the method choice.
  const dismissError = () => {
    const current = state()
    if (current.kind !== 'error') return
    if (current.canReturnToConfiguration) {
      transition({ kind: 'configure', method: lastConfigMethod.value })
    } else {
      reset()
    }
  }

  // ------------------------------------------------------------ decisions

  const sendFromDecision = (command: ImportCommand): boolean => {
    if (options.transport.send(command)) {
      restoreRunning()
      return true
    }
    // Send failed: keep the decision state and payload so the user can
    // retry with the same values.
    return false
  }

  const currentSecurityPayload = ():
    | { origin: 'mapping' }
    | { origin: 'creation-needed' | 'error' }
    | null => {
    const current = state()
    if (current.kind !== 'decision' || current.decision !== 'security') return null
    const payload = current.payload as { origin?: string; description?: string }
    if (payload.origin === 'mapping' || payload.description !== undefined) {
      return { origin: 'mapping' }
    }
    return { origin: 'creation-needed' }
  }

  const resolveSecurityMapping = (securityId: number | null) => {
    if (currentSecurityPayload()?.origin !== 'mapping') return
    sendFromDecision(
      securityId === null
        ? securityMappedCommand('skip', null)
        : securityMappedCommand('map', securityId)
    )
  }

  const resolveSecurityCreated = (security: { id: number; name: string }) => {
    const origin = currentSecurityPayload()?.origin
    if (origin === 'mapping') {
      sendFromDecision(securityMappedCommand('map', security.id))
    } else if (origin) {
      sendFromDecision(securityConfirmationCreatedCommand(security))
    }
  }

  const resolveSecuritySkipped = () => {
    const origin = currentSecurityPayload()?.origin
    if (origin === 'mapping') {
      sendFromDecision(securityMappedCommand('skip', null))
    } else if (origin) {
      sendFromDecision(securityConfirmationSkipCommand())
    }
  }

  const resolveExistingSecurity = (securityId: number) => {
    if (currentSecurityPayload()?.origin) {
      sendFromDecision(securityConfirmationExistingCommand(securityId))
    }
  }

  const resolveTransaction = (confirmed: boolean) => {
    const current = state()
    if (current.kind !== 'decision' || current.decision !== 'transaction') return
    sendFromDecision(transactionConfirmedCommand(confirmed))
  }

  const resolveAccountSelection = (account: { id: number }) => {
    const current = state()
    if (
      current.kind !== 'decision' ||
      current.decision !== 'accounts' ||
      (current.payload as { variant?: string }).variant !== 'select'
    ) {
      return
    }
    sendFromDecision(
      selectAccountCommand(
        account.id,
        configuration.confirmEveryTransaction.value,
        configuration.dateRange.value.from,
        configuration.dateRange.value.to
      )
    )
  }

  const resolveAccountMatched = (pairs: AccountMatchPair[]) => {
    if (!Array.isArray(pairs)) {
      options.onError?.('Invalid account pairing data received')
      return
    }
    if (pairs.length === 0) {
      options.onError?.('No account pairs were provided')
      return
    }
    sendFromDecision(accountsMatchedCommand(pairs))
  }

  const resolveUseExistingMatches = (pairs: AccountMatchPair[]) => {
    if (!Array.isArray(pairs)) {
      options.onError?.('Invalid existing account pairs data')
      return
    }
    if (pairs.length === 0) {
      options.onError?.('No existing account pairs were found')
      return
    }
    sendFromDecision(useExistingMatchesCommand(pairs))
  }

  const resolveCreateAccount = (data: {
    tinkoffAccount: JsonValue
    name: string
    comment?: string
  }) => {
    if (!data || !data.tinkoffAccount || !data.name) {
      options.onError?.('Invalid account creation data')
      return
    }
    sendFromDecision(
      createAccountCommand(data.tinkoffAccount, data.name, data.comment || '')
    )
  }

  // ------------------------------------------------------------ stop/reset

  const requestStop = () => {
    const kind = state().kind
    // The incumbent kept Stop available while a decision overlay was
    // pending; the stop acknowledgment ends the run from either state.
    if (kind !== 'running' && kind !== 'decision') return
    if (stopRequested) return
    stopRequested = true
    if (options.transport.send(stopCommand())) {
      transition({ kind: 'stopping', method: runMethod })
    } else {
      stopRequested = false
      transition({
        kind: 'error',
        message: 'Failed to send stop request: the connection was lost',
        canReturnToConfiguration: false,
      })
    }
  }

  const notifyDisconnected = () => {
    if (!sessionActive()) return
    transition({
      kind: 'error',
      message: DISCONNECTED_MESSAGE,
      canReturnToConfiguration: true,
    })
  }

  const reset = () => {
    generation += 1
    stopRequested = false
    // Teardown owns only this workflow's connection.
    options.transport.disconnect()
    resetRunData()
    configuration.file.value = null
    configuration.fileId.value = null
    configuration.isGalaxy.value = false
    configuration.galaxyType.value = 'transactions'
    configuration.selectedCurrency.value = null
    configuration.confirmEveryTransaction.value = false
    configuration.selectedBroker.value = null
    configuration.dateRange.value = { from: null, to: null }
    configuration.selectedAccount.value = null
    configuration.accounts.value = []
    configuration.identifiedAccount.value = null
    configuration.accountIdentified.value = false
    stats.value = { ...EMPTY_STATS, warnings: [] }
    lastProtocolIssue.value = null
    transition({ kind: 'choose-method' })
  }

  // ------------------------------------------------------------ receive

  const applyComplete = (result: ImportResultData, raw: Record<string, JsonValue>) => {
    stats.value = result
    transition({ kind: 'complete', result })
    options.onCompleted?.(raw)
    options.transport.disconnect()
  }

  // Matched-account inconsistency: the backend can report an account as
  // unmatched during import even though the user just matched it. The
  // incumbent surfaced this as a dedicated message; parity is kept by
  // checking the pending accounts decision.
  const INCONSISTENCY_MESSAGE =
    'Server inconsistency detected: An account you matched was not recognized during import. This is likely a server-side bug. Please try again or contact support.'

  const matchedAccountInconsistency = (error: string): boolean => {
    if (!error.includes('not matched to any database account')) return false
    const current = state()
    if (current.kind !== 'decision' || current.decision !== 'accounts') {
      return false
    }
    const payload = current.payload as {
      variant?: string
      matchedPairs?: AccountMatchPair[]
    }
    if (payload.variant !== 'match' || !payload.matchedPairs?.length) {
      return false
    }
    const match = error.match(/ID: (\d+)/)
    if (!match) return false
    return payload.matchedPairs.some(
      (pair) => String(pair.tinkoff_account_id) === match[1]
    )
  }

  const receive = (raw: unknown) => {
    const decoded = decodeImportEvent(raw)
    switch (decoded.kind) {
      case 'protocol-error':
        // Safe and recoverable: record, never fabricate completion, never
        // disconnect; the run stays stoppable.
        lastProtocolIssue.value = decoded.reason
        return
      case 'ignored':
        return
      default:
        break
    }
    if (!sessionActive()) return

    switch (decoded.kind) {
      case 'initialization':
        runData.total = decoded.total
        runData.message = decoded.message
        syncRunningState()
        break
      case 'total-count':
        runData.total = decoded.total
        runData.message =
          decoded.message || `Found ${decoded.total} transactions to process`
        syncRunningState()
        break
      case 'progress':
        if (decoded.fromImportUpdate) {
          runData.current = decoded.current
          runData.message = decoded.message
          if (decoded.percent !== null) {
            progress.value = decoded.percent
          } else if (runData.total > 0) {
            progress.value = Math.round((runData.current / runData.total) * 100)
          }
        } else {
          runData.message = decoded.message
          if (decoded.total) runData.total = decoded.total
          if (decoded.current) runData.current = decoded.current
        }
        syncRunningState()
        break
      case 'transaction-saved':
        runData.current = decoded.current
        runData.message = decoded.message || 'Saving transactions...'
        if (runData.total > 0) {
          progress.value = Math.round((runData.current / runData.total) * 100)
        }
        syncRunningState()
        break
      case 'item-error':
        runData.message = `⚠️ ${decoded.message}`
        syncRunningState()
        break
      case 'security-mapping':
        transition({
          kind: 'decision',
          method: runMethod,
          decision: 'security',
          payload: {
            origin: 'mapping',
            description: decoded.description,
            isin: decoded.isin,
            symbol: decoded.symbol,
            bestMatch: decoded.bestMatch,
            transaction: decoded.transaction,
          },
        })
        break
      case 'transaction-confirmation':
        transition({
          kind: 'decision',
          method: runMethod,
          decision: 'transaction',
          payload: { transaction: decoded.transaction },
        })
        break
      case 'import-error':
        if (decoded.securityRelated) {
          const info = extractSecurityInfoFromError(decoded.error, runData.message)
          transition({
            kind: 'decision',
            method: runMethod,
            decision: 'security',
            payload: {
              origin: 'error',
              info: { name: info.name, isin: info.isin, currency: null },
            },
          })
        } else if (matchedAccountInconsistency(decoded.error)) {
          transition({
            kind: 'error',
            message: INCONSISTENCY_MESSAGE,
            canReturnToConfiguration: false,
          })
        } else {
          transition({
            kind: 'error',
            message: decoded.error,
            canReturnToConfiguration: false,
          })
        }
        break
      case 'save-error':
        if (decoded.securityRelated) {
          const info = extractSecurityInfoFromError(decoded.error, runData.message)
          transition({
            kind: 'decision',
            method: runMethod,
            decision: 'security',
            payload: {
              origin: 'error',
              info: { name: info.name, isin: info.isin, currency: null },
            },
          })
        } else {
          options.onError?.({ message: decoded.error })
          transition({
            kind: 'error',
            message: decoded.error,
            canReturnToConfiguration: false,
          })
        }
        break
      case 'critical-error':
        // The error message stays visible (recorded defect D-2 fixed); the
        // connection is torn down and the run can never claim completion.
        options.transport.disconnect()
        resetRunData()
        transition({
          kind: 'error',
          message: decoded.error,
          canReturnToConfiguration: false,
        })
        break
      case 'run-error':
        transition({
          kind: 'error',
          message: decoded.message,
          canReturnToConfiguration: false,
        })
        break
      case 'complete':
        applyComplete(decoded.result, decoded.raw)
        break
      case 'stopped':
        if (decoded.stats) stats.value = decoded.stats
        options.transport.disconnect()
        resetRunData()
        transition({
          kind: 'error',
          message: STOPPED_MESSAGE,
          canReturnToConfiguration: false,
        })
        break
      case 'account-matching-required':
        transition({
          kind: 'decision',
          method: runMethod,
          decision: 'accounts',
          payload: {
            variant: 'match',
            broker: decoded.broker,
            matchedPairs: decoded.matchedPairs,
            unmatchedTinkoff: decoded.unmatchedTinkoff,
            unmatchedDb: decoded.unmatchedDb,
          },
        })
        break
      case 'account-selection-required':
        transition({
          kind: 'decision',
          method: runMethod,
          decision: 'accounts',
          payload: { variant: 'select', accounts: decoded.accounts },
        })
        break
      case 'security-creation-needed':
        transition({
          kind: 'decision',
          method: runMethod,
          decision: 'security',
          payload: { origin: 'creation-needed', info: decoded.info },
        })
        break
      default:
        break
    }
  }

  return {
    state: importState.state,
    isIdle: importState.isIdle,
    isAnalyzing: importState.isAnalyzing,
    isImporting: importState.isImporting,
    isMapping: importState.isMapping,
    isComplete: importState.isComplete,
    isError: importState.isError,
    configuration,
    progress,
    stats,
    lastProtocolIssue,
    selectMethod,
    back,
    dismissError,
    analyze,
    startFile,
    startApi,
    requestStop,
    notifyDisconnected,
    receive,
    reset,
    resolveSecurityMapping,
    resolveSecurityCreated,
    resolveSecuritySkipped,
    resolveExistingSecurity,
    resolveTransaction,
    resolveAccountSelection,
    resolveAccountMatched,
    resolveUseExistingMatches,
    resolveCreateAccount,
  }
}

export type TransactionImportController = ReturnType<typeof useTransactionImport>
