// D6 typed units for the transaction import workflow. The shapes follow the
// accepted D6 design (docs/superpowers/plans/2026-09-08-frontend-design-workflows.md,
// section "D6"), with one recorded discrepancy: ApiStartInput carries dateTo
// because the incumbent wire command sends `date_to` and the backend consumer
// reads it (see docs/design/frontend-import-workflow.md, section 2).

export type ImportMethod = 'file' | 'api'
export type ImportDecision = 'accounts' | 'security' | 'transaction'
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }

export interface ImportWarning {
  endpoint: string
  error: string
}

export interface ImportResultData {
  totalTransactions: number
  importedTransactions: number
  skippedTransactions: number
  duplicateTransactions: number
  importErrors: number
  warnings: ImportWarning[]
}

export type TransactionImportState =
  | { kind: 'choose-method' }
  | { kind: 'configure'; method: ImportMethod }
  | { kind: 'analyzing'; method: 'file' }
  | { kind: 'review'; method: ImportMethod; accountLabel: string }
  | {
      kind: 'running'
      method: ImportMethod
      current: number
      total: number
      message: string
    }
  | { kind: 'decision'; method: ImportMethod; decision: ImportDecision; payload: unknown }
  | { kind: 'stopping'; method: ImportMethod }
  | { kind: 'complete'; result: ImportResultData }
  | { kind: 'error'; message: string; canReturnToConfiguration: boolean }

export interface FileStartInput {
  fileId: string | number
  accountId: number
  confirmEvery: boolean
  isGalaxy: boolean
  galaxyType: string
  currency: string | null
}

export interface ApiStartInput {
  brokerId: number
  confirmEvery: boolean
  dateFrom: string | null
  dateTo: string | null
}

export interface AccountMatchPair {
  tinkoff_account_id: string | number
  db_account_id: string | number
  [key: string]: JsonValue
}

export type ImportCommand =
  | {
      type: 'start_file_import'
      file_id: string | number
      account_id: number
      confirm_every: boolean
      is_galaxy: boolean
      galaxy_type: string | null
      currency: string | null
    }
  | {
      type: 'start_api_import'
      data: {
        broker_id: number
        confirm_every_transaction: boolean
        date_from: string | null
        date_to: string | null
      }
    }
  | { type: 'stop_import' }
  | { type: 'security_mapped'; action: 'map'; security_id: number }
  | { type: 'security_mapped'; action: 'skip'; security_id: null }
  | { type: 'transaction_confirmed'; confirmed: boolean }
  | {
      type: 'security_confirmation'
      security_id: number
      security_created?: true
      security_data?: { name: string; id: number }
    }
  | { type: 'security_confirmation'; security_id: null; skip_transaction: true }
  | {
      type: 'select_account'
      data: {
        account_id: number
        confirm_every_transaction: boolean
        date_from?: string | null
        date_to?: string | null
      }
    }
  | { type: 'accounts_matched' | 'use_existing_matches'; data: { pairs: readonly AccountMatchPair[] } }
  | { type: 'create_account'; data: { tinkoff_account: JsonValue; name: string; comment: string } }

export interface ImportTransport {
  connect(): Promise<boolean>
  send(command: ImportCommand): boolean
  disconnect(): void
}

// Validated decision payloads the orchestrator stores inside the
// 'decision' state. They mirror what the legacy dialogs receive.
export interface SecurityMappingPayload {
  description: string
  isin: string | null
  symbol: string | null
  bestMatch: { match_id?: number | string; match_name?: string; match_score?: number | string } | null
  transaction: Record<string, JsonValue>
}

export interface TransactionConfirmationPayload {
  transaction: Record<string, JsonValue>
}

export interface AccountMatchingPayload {
  variant: 'match'
  broker: { id: number; name: string }
  matchedPairs: AccountMatchPair[]
  unmatchedTinkoff: JsonValue[]
  unmatchedDb: JsonValue[]
}

export interface AccountSelectionPayload {
  variant: 'select'
  accounts: JsonValue[]
}

export interface SecurityCreationPayload {
  origin: 'creation-needed' | 'error'
  info: { name: string; isin: string | null; currency: string | null }
}
