// D6 typed legacy-protocol boundary. Outgoing builders reproduce the
// incumbent wire commands byte-for-byte (verified by the Task-0 fixtures);
// the incoming decoder accepts `unknown` and returns a discriminated,
// validated event or a safe recoverable protocol error. It never throws,
// never fabricates completion, and never echoes raw payloads in errors.
// The full envelope inventory lives in docs/design/frontend-import-workflow.md.
import type {
  AccountMatchPair,
  ApiStartInput,
  FileStartInput,
  ImportCommand,
  ImportResultData,
  ImportWarning,
  JsonValue,
} from './types'

// ---------------------------------------------------------------
// Outgoing commands
// ---------------------------------------------------------------

export function fileStartCommand(input: FileStartInput): ImportCommand {
  return {
    type: 'start_file_import',
    file_id: input.fileId,
    account_id: input.accountId,
    confirm_every: input.confirmEvery,
    is_galaxy: input.isGalaxy,
    galaxy_type: input.isGalaxy ? input.galaxyType : null,
    currency: input.isGalaxy ? input.currency : null,
  }
}

// Recorded discrepancy vs the accepted example: the incumbent sends date_to
// and backend consumers.py reads it, so the verified wire behavior keeps it.
export function apiStartCommand(input: ApiStartInput): ImportCommand {
  return {
    type: 'start_api_import',
    data: {
      broker_id: input.brokerId,
      confirm_every_transaction: input.confirmEvery,
      date_from: input.dateFrom,
      date_to: input.dateTo,
    },
  }
}

export function stopCommand(): ImportCommand {
  return { type: 'stop_import' }
}

export function securityMappedCommand(
  action: 'map',
  securityId: number
): ImportCommand
export function securityMappedCommand(action: 'skip', securityId: null): ImportCommand
export function securityMappedCommand(
  action: 'map' | 'skip',
  securityId: number | null
): ImportCommand {
  return action === 'map'
    ? { type: 'security_mapped', action, security_id: securityId as number }
    : { type: 'security_mapped', action, security_id: null }
}

export function transactionConfirmedCommand(confirmed: boolean): ImportCommand {
  return { type: 'transaction_confirmed', confirmed }
}

export function securityConfirmationCreatedCommand(security: {
  id: number
  name: string
}): ImportCommand {
  return {
    type: 'security_confirmation',
    security_id: security.id,
    security_created: true,
    security_data: { name: security.name, id: security.id },
  }
}

export function securityConfirmationSkipCommand(): ImportCommand {
  return { type: 'security_confirmation', security_id: null, skip_transaction: true }
}

export function securityConfirmationExistingCommand(
  securityId: number
): ImportCommand {
  return { type: 'security_confirmation', security_id: securityId }
}

export function selectAccountCommand(
  accountId: number,
  confirmEveryTransaction: boolean,
  dateFrom: string | null,
  dateTo: string | null
): ImportCommand {
  return {
    type: 'select_account',
    data: {
      account_id: accountId,
      confirm_every_transaction: confirmEveryTransaction,
      date_from: dateFrom,
      date_to: dateTo,
    },
  }
}

export function accountsMatchedCommand(
  pairs: readonly AccountMatchPair[]
): ImportCommand {
  return { type: 'accounts_matched', data: { pairs } }
}

export function useExistingMatchesCommand(
  pairs: readonly AccountMatchPair[]
): ImportCommand {
  return { type: 'use_existing_matches', data: { pairs } }
}

export function createAccountCommand(
  tinkoffAccount: JsonValue,
  name: string,
  comment: string
): ImportCommand {
  return { type: 'create_account', data: { tinkoff_account: tinkoffAccount, name, comment } }
}

// ---------------------------------------------------------------
// Incoming events
// ---------------------------------------------------------------

export type DecodedImportEvent =
  | { kind: 'initialization'; message: string; total: number }
  | {
      kind: 'progress'
      current: number
      total: number | null
      percent: number | null
      message: string
      // import_update/progress drives the running state; the bare top-level
      // progress envelope only updates counters/message (incumbent split).
      fromImportUpdate: boolean
    }
  | { kind: 'total-count'; total: number; message: string }
  | { kind: 'transaction-saved'; current: number; total: number | null; message: string }
  | { kind: 'item-error'; message: string; detail: string | null }
  | {
      kind: 'security-mapping'
      description: string
      isin: string | null
      symbol: string | null
      bestMatch: Record<string, JsonValue> | null
      transaction: Record<string, JsonValue>
    }
  | { kind: 'transaction-confirmation'; transaction: Record<string, JsonValue> }
  | { kind: 'import-error'; error: string; securityRelated: boolean }
  | { kind: 'save-error'; error: string; securityRelated: boolean }
  | { kind: 'critical-error'; error: string }
  | { kind: 'run-error'; message: string }
  | { kind: 'complete'; result: ImportResultData; raw: Record<string, JsonValue> }
  | { kind: 'stopped'; message: string; stats: ImportResultData | null }
  | {
      kind: 'account-matching-required'
      broker: { id: number; name: string }
      matchedPairs: AccountMatchPair[]
      unmatchedTinkoff: JsonValue[]
      unmatchedDb: JsonValue[]
    }
  | { kind: 'account-selection-required'; accounts: JsonValue[] }
  | {
      kind: 'security-creation-needed'
      info: { name: string; isin: string | null; currency: string | null }
    }
  | { kind: 'ignored' }
  | { kind: 'protocol-error'; reason: string }

const SECURITY_ERROR_MARKERS = [
  'Security not found',
  'Could not match security',
  'unsupported operand type',
  'NoneType',
]

export function isSecurityRelatedError(error: string): boolean {
  return SECURITY_ERROR_MARKERS.some((marker) => error.includes(marker))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asStringOrEmpty(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function isJsonObjectValue(value: unknown): value is Record<string, JsonValue> {
  return isRecord(value)
}

function normalizeWarnings(value: unknown): ImportWarning[] | null {
  if (value === undefined || value === null) return []
  if (!Array.isArray(value)) return null
  const warnings: ImportWarning[] = []
  for (const entry of value) {
    if (!isRecord(entry)) return null
    const endpoint = asStringOrEmpty(entry.endpoint)
    const error = asStringOrEmpty(entry.error)
    if (endpoint === null || error === null) return null
    warnings.push({ endpoint, error })
  }
  return warnings
}

// Counters are optional (the backend's StopAsyncIteration path completes with
// a message-only payload) but must be finite numbers when present. Absent
// counters normalize to 0 for the typed view; the parent emit still carries
// the raw payload.
function normalizeCounters(
  data: Record<string, unknown>
): Omit<ImportResultData, 'warnings'> | null {
  const names = [
    'totalTransactions',
    'importedTransactions',
    'skippedTransactions',
    'duplicateTransactions',
    'importErrors',
  ] as const
  const counters: Omit<ImportResultData, 'warnings'> = {
    totalTransactions: 0,
    importedTransactions: 0,
    skippedTransactions: 0,
    duplicateTransactions: 0,
    importErrors: 0,
  }
  for (const name of names) {
    const value = asFiniteNumber(data[name])
    if (data[name] !== undefined && data[name] !== null && value === null) {
      return null
    }
    counters[name] = value ?? 0
  }
  return counters
}

function decodeImportComplete(
  data: unknown
): Extract<DecodedImportEvent, { kind: 'complete' }> | ProtocolError {
  if (!isRecord(data)) return protocolError('import_complete without data object')
  const counters = normalizeCounters(data)
  if (counters === null) return protocolError('import_complete with invalid counters')
  const warnings = normalizeWarnings(data.warnings)
  if (warnings === null) return protocolError('import_complete with invalid warnings')
  return {
    kind: 'complete',
    result: { ...counters, warnings },
    // Compatibility: the parent emit carries the RAW completion payload.
    raw: data as Record<string, JsonValue>,
  }
}

interface ProtocolError {
  kind: 'protocol-error'
  reason: string
}

function protocolError(reason: string): ProtocolError {
  return { kind: 'protocol-error', reason }
}

function decodeImportUpdate(data: unknown): DecodedImportEvent {
  if (!isRecord(data)) return protocolError('import_update without data object')
  const status = data.status
  if (typeof status !== 'string') {
    return protocolError('import_update without string status')
  }
  switch (status) {
    case 'total_count': {
      const total = asFiniteNumber(data.total)
      if (data.total !== undefined && data.total !== null && total === null) {
        return protocolError('total_count with invalid total')
      }
      return {
        kind: 'total-count',
        total: total ?? 0,
        message: asStringOrEmpty(data.message) ?? '',
      }
    }
    case 'progress': {
      const current = asFiniteNumber(data.current)
      const total = asFiniteNumber(data.total)
      const percent = asFiniteNumber(data.progress)
      return {
        kind: 'progress',
        current: current ?? 0,
        total,
        percent,
        message: asStringOrEmpty(data.message) ?? '',
        fromImportUpdate: true,
      }
    }
    case 'transaction_saved': {
      const current = asFiniteNumber(data.current)
      const total = asFiniteNumber(data.total)
      return {
        kind: 'transaction-saved',
        current: current ?? 0,
        total,
        message: asStringOrEmpty(data.message) ?? '',
      }
    }
    case 'transaction_error':
    case 'save_error': {
      const message = asStringOrEmpty(data.message)
      const detail = asStringOrEmpty(data.error_detail)
      return {
        kind: 'item-error',
        message: message ?? detail ?? 'Error processing transaction',
        detail,
      }
    }
    case 'security_mapping': {
      const mapping = data.mapping_data
      if (!isRecord(mapping)) return protocolError('security_mapping without mapping_data')
      const description = asStringOrEmpty(mapping.security_description)
      if (description === null) {
        return protocolError('security_mapping without security_description')
      }
      if (!isJsonObjectValue(data.transaction_data)) {
        return protocolError('security_mapping without transaction_data object')
      }
      const bestMatch =
        isRecord(mapping.best_match) ? (mapping.best_match as Record<string, JsonValue>) : null
      return {
        kind: 'security-mapping',
        description,
        isin: asStringOrEmpty(mapping.isin),
        symbol: asStringOrEmpty(mapping.symbol),
        bestMatch,
        transaction: data.transaction_data,
      }
    }
    case 'transaction_confirmation': {
      if (!isJsonObjectValue(data.data)) {
        return protocolError('transaction_confirmation without data object')
      }
      return { kind: 'transaction-confirmation', transaction: data.data }
    }
    case 'unrecognized_operation':
      // The incumbent ignores this status (no branch); the backend only
      // logs it. Nonterminal, no UI effect.
      return { kind: 'ignored' }
    default:
      return protocolError('unknown import_update status')
  }
}

function decodeAccountMatching(data: unknown): DecodedImportEvent {
  if (!isRecord(data)) return protocolError('account_matching_required without data')
  const brokerId = asFiniteNumber(data.broker_id)
  const brokerName = asStringOrEmpty(data.broker_name)
  if (brokerId === null || brokerName === null) {
    return protocolError('account_matching_required without broker identity')
  }
  if (!Array.isArray(data.unmatched_tinkoff) || !Array.isArray(data.unmatched_db)) {
    return protocolError('account_matching_required without unmatched lists')
  }
  // The backend sends matched_pairs as an object keyed by Tinkoff account id;
  // the incumbent transform keeps exactly the four canonical pair keys.
  const rawPairs = data.matched_pairs ?? {}
  if (!isRecord(rawPairs)) return protocolError('account_matching_required with invalid matched_pairs')
  const matchedPairs: AccountMatchPair[] = []
  for (const [tinkoffAccountId, pairData] of Object.entries(rawPairs)) {
    if (!isRecord(pairData) || !isRecord(pairData.db_account)) {
      return protocolError('account_matching_required with invalid pair')
    }
    const dbAccountId = asFiniteNumber(pairData.db_account.id)
    if (dbAccountId === null) {
      return protocolError('account_matching_required with invalid db account id')
    }
    matchedPairs.push({
      tinkoff_account_id: tinkoffAccountId,
      db_account_id: dbAccountId,
      tinkoff_account: (pairData.tinkoff_account ?? null) as JsonValue,
      db_account: pairData.db_account as JsonValue,
    })
  }
  return {
    kind: 'account-matching-required',
    broker: { id: brokerId, name: brokerName },
    matchedPairs,
    unmatchedTinkoff: data.unmatched_tinkoff as JsonValue[],
    unmatchedDb: data.unmatched_db as JsonValue[],
  }
}

export function decodeImportEvent(raw: unknown): DecodedImportEvent {
  if (!isRecord(raw)) return protocolError('envelope without an object body')
  const type = raw.type
  if (typeof type !== 'string') return protocolError('envelope without a string type')

  switch (type) {
    case 'initialization': {
      const total = asFiniteNumber(raw.total_to_update)
      return {
        kind: 'initialization',
        message: asStringOrEmpty(raw.message) ?? '',
        total: total ?? 0,
      }
    }
    case 'import_update':
      return decodeImportUpdate(raw.data)
    case 'import_error': {
      const data = raw.data
      const error = isRecord(data) ? asStringOrEmpty(data.error) : null
      if (error === null) return protocolError('import_error without data.error')
      return { kind: 'import-error', error, securityRelated: isSecurityRelatedError(error) }
    }
    case 'save_error': {
      // Top-level save_error reaches the legacy secondary dispatcher, whose
      // effect differs from the watcher-routed import_error (handleImportError).
      const data = raw.data
      const error = isRecord(data) ? asStringOrEmpty(data.error) : null
      if (error === null) return protocolError('save_error without data.error')
      return { kind: 'save-error', error, securityRelated: isSecurityRelatedError(error) }
    }
    case 'critical_error': {
      const data = raw.data
      const error = isRecord(data) ? asStringOrEmpty(data.error) : null
      if (error === null) return protocolError('critical_error without data.error')
      return { kind: 'critical-error', error }
    }
    case 'error': {
      const data = raw.data
      const message = isRecord(data) ? asStringOrEmpty(data.message) : null
      if (message === null) return protocolError('error envelope without data.message')
      return { kind: 'run-error', message }
    }
    case 'progress': {
      const data = raw.data
      if (!isRecord(data)) return protocolError('progress without data object')
      const total = asFiniteNumber(data.total)
      const current = asFiniteNumber(data.current)
      return {
        kind: 'progress',
        current: current ?? 0,
        total,
        percent: null,
        message: asStringOrEmpty(data.message) ?? '',
        fromImportUpdate: false,
      }
    }
    case 'import_complete':
      return decodeImportComplete(raw.data)
    case 'import_stopped': {
      const data = raw.data
      if (!isRecord(data)) return protocolError('import_stopped without data object')
      const message = asStringOrEmpty(data.message) ?? ''
      if (data.stats === undefined || data.stats === null) {
        return { kind: 'stopped', message, stats: null }
      }
      if (!isRecord(data.stats)) return protocolError('import_stopped with invalid stats')
      const counters = normalizeCounters(data.stats)
      if (counters === null) return protocolError('import_stopped with invalid counters')
      const warnings = normalizeWarnings(data.stats.warnings)
      if (warnings === null) return protocolError('import_stopped with invalid warnings')
      return { kind: 'stopped', message, stats: { ...counters, warnings } }
    }
    case 'account_matching_required':
      return decodeAccountMatching(raw.data)
    case 'account_selection_required': {
      const data = raw.data
      if (!isRecord(data) || !Array.isArray(data.available_accounts)) {
        return protocolError('account_selection_required without available_accounts')
      }
      return { kind: 'account-selection-required', accounts: data.available_accounts as JsonValue[] }
    }
    case 'security_creation_needed': {
      const info = raw.security_info
      if (!isRecord(info) || typeof info.name !== 'string') {
        return protocolError('security_creation_needed without security_info')
      }
      return {
        kind: 'security-creation-needed',
        info: {
          name: info.name,
          isin: asStringOrEmpty(info.isin),
          currency: asStringOrEmpty(info.currency),
        },
      }
    }
    case 'transaction_confirmation':
      // Dead branch: the backend never produces this top-level type (it sends
      // transaction_confirmation inside import_update). Nonterminal.
      return { kind: 'ignored' }
    case 'import_warning':
    case 'import_cancelled':
      // Produced by the backend, ignored by the incumbent dialog.
      return { kind: 'ignored' }
    default:
      return protocolError('unknown message type')
  }
}
