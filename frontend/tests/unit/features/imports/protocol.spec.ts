// D6 task 1 — typed legacy protocol boundary. Builders must reproduce the
// Task-0 command fixtures byte-for-byte; the decoder must classify every
// real backend envelope (Task-0 event fixtures) and degrade unknown or
// malformed input to a safe recoverable protocol error without fabricating
// completion.
import { describe, expect, it } from 'vitest'

import {
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
  accountsMatchedCommand,
} from '@/features/imports/legacyImportProtocol'
import type {
  AccountMatchPair,
  ApiStartInput,
  FileStartInput,
} from '@/features/imports/types'
import {
  commands,
  dbAccount,
  events,
  matchedPairsArray,
  tinkoffAccount,
  transactionDisplayData,
} from './fixtures'

const fileInput: FileStartInput = {
  fileId: '9f2c8ab0-1111-4ccc-8ddd-222233334444',
  accountId: 3,
  confirmEvery: true,
  isGalaxy: false,
  galaxyType: 'transactions',
  currency: null,
}

describe('start command builders', () => {
  it('file start: non-galaxy nulls galaxy_type and currency', () => {
    expect(fileStartCommand(fileInput)).toEqual(commands.fileStartNonGalaxy)
  })

  it('file start: galaxy variant carries type and currency verbatim', () => {
    expect(
      fileStartCommand({
        fileId: '0a1b2c3d-4444-5555-6666-777788889999',
        accountId: 5,
        confirmEvery: false,
        isGalaxy: true,
        galaxyType: 'transactions',
        currency: 'USD',
      })
    ).toEqual(commands.fileStartGalaxy)
  })

  it('api start: keeps BOTH dates on the wire (recorded discrepancy)', () => {
    const input: ApiStartInput = {
      brokerId: 11,
      confirmEvery: true,
      dateFrom: '2026-01-01',
      dateTo: '2026-06-30',
    }
    expect(apiStartCommand(input)).toEqual(commands.apiStartWithDates)
  })

  it('api start: unset dates serialize as nulls', () => {
    expect(
      apiStartCommand({ brokerId: 11, confirmEvery: false, dateFrom: null, dateTo: null })
    ).toEqual(commands.apiStartNullDates)
  })
})

describe('decision and account command builders', () => {
  it('stop', () => {
    expect(stopCommand()).toEqual(commands.stop)
  })

  it('security mapping map/skip', () => {
    expect(securityMappedCommand('map', 31)).toEqual(commands.securityMappedMap)
    expect(securityMappedCommand('skip', null)).toEqual(
      commands.securityMappedSkip
    )
  })

  it('transaction confirm/skip', () => {
    expect(transactionConfirmedCommand(true)).toEqual(
      commands.transactionConfirmed
    )
    expect(transactionConfirmedCommand(false)).toEqual(
      commands.transactionSkipped
    )
  })

  it('security_confirmation: created, skipped and existing shapes are exact', () => {
    expect(
      securityConfirmationCreatedCommand({
        id: 77,
        name: 'New Synthetic Security',
      })
    ).toEqual(commands.securityConfirmationCreated)
    expect(securityConfirmationSkipCommand()).toEqual(
      commands.securityConfirmationSkipped
    )
    expect(securityConfirmationExistingCommand(42)).toEqual(
      commands.securityConfirmationExisting
    )
  })

  it('select_account: confirm flag and both dates pass through', () => {
    expect(selectAccountCommand(5, true, '2026-01-01', null)).toEqual(
      commands.selectAccount
    )
  })

  it('account pair commands preserve provider-specific extras', () => {
    const pairs: AccountMatchPair[] = structuredClone(matchedPairsArray)
    expect(accountsMatchedCommand(pairs)).toEqual(commands.accountsMatched)
    expect(useExistingMatchesCommand(pairs)).toEqual(
      commands.useExistingMatches
    )
  })

  it('create_account: full tinkoff object, name and defaulted comment', () => {
    expect(
      createAccountCommand(tinkoffAccount, 'New Synthetic Account', 'created during import')
    ).toEqual(commands.createAccount)
  })
})

describe('incoming decoder — every real backend envelope', () => {
  it('initialization', () => {
    expect(decodeImportEvent(structuredClone(events.initialization))).toEqual({
      kind: 'initialization',
      message: 'Fetching transactions from broker API...',
      total: 42,
    })
  })

  it('import_update statuses', () => {
    expect(
      decodeImportEvent(structuredClone(events.importUpdateTotalCount))
    ).toEqual({ kind: 'total-count', total: 42, message: 'Found 42 transactions' })
    expect(
      decodeImportEvent(structuredClone(events.importUpdateProgress))
    ).toEqual({
      kind: 'progress',
      current: 7,
      total: null,
      percent: 17,
      message: 'Processing transaction 7 of 42',
      fromImportUpdate: true,
    })
    expect(
      decodeImportEvent(structuredClone(events.importUpdateTransactionSaved))
    ).toEqual({
      kind: 'transaction-saved',
      current: 8,
      total: 42,
      message: 'Saved transaction 8 of 42',
    })
    expect(
      decodeImportEvent(structuredClone(events.importUpdateTransactionError))
    ).toEqual({
      kind: 'item-error',
      message: 'Error processing transaction',
      detail: 'synthetic row failure',
    })
    expect(
      decodeImportEvent(structuredClone(events.importUpdateSaveError))
    ).toEqual({
      kind: 'item-error',
      message: 'Error saving transaction: synthetic save failure',
      detail: 'synthetic save failure',
    })
  })

  it('security_mapping keeps the display transaction and match verbatim', () => {
    const decoded = decodeImportEvent(
      structuredClone(events.importUpdateSecurityMapping)
    )
    expect(decoded.kind).toBe('security-mapping')
    if (decoded.kind === 'security-mapping') {
      expect(decoded.description).toBe('ACME Corp')
      expect(decoded.isin).toBe('US0000000001')
      expect(decoded.symbol).toBe('ACME')
      expect(decoded.bestMatch).toEqual({
        match_id: 31,
        match_name: 'ACME Corp.',
        match_score: 0.87,
      })
      expect(decoded.transaction).toEqual(transactionDisplayData)
    }
  })

  it('transaction_confirmation carries the display transaction', () => {
    const decoded = decodeImportEvent(
      structuredClone(events.importUpdateTransactionConfirmation)
    )
    expect(decoded).toEqual({
      kind: 'transaction-confirmation',
      transaction: transactionDisplayData,
    })
  })

  it('top-level progress and error envelopes', () => {
    expect(decodeImportEvent(structuredClone(events.progress))).toEqual({
      kind: 'progress',
      current: 7,
      total: 42,
      percent: null,
      message: 'Importing...',
      fromImportUpdate: false,
    })
    expect(decodeImportEvent(structuredClone(events.errorWithData))).toEqual({
      kind: 'run-error',
      message: 'synthetic broker token expired',
    })
  })

  it('import_error/save_error classify security strings', () => {
    expect(decodeImportEvent(structuredClone(events.importErrorSecurity))).toEqual({
      kind: 'import-error',
      error: 'Security not found: ACME Corp (US0000000001)',
      securityRelated: true,
    })
    expect(decodeImportEvent(structuredClone(events.importErrorPlain))).toEqual({
      kind: 'import-error',
      error: 'synthetic import failure',
      securityRelated: false,
    })
    expect(decodeImportEvent(structuredClone(events.saveErrorTopLevel))).toEqual({
      kind: 'save-error',
      error: 'synthetic top-level save failure',
      securityRelated: false,
    })
  })

  it('critical_error', () => {
    expect(decodeImportEvent(structuredClone(events.criticalError))).toEqual({
      kind: 'critical-error',
      error: 'synthetic fatal import failure',
    })
  })

  it('import_complete validates counters and normalizes optional warnings', () => {
    expect(
      decodeImportEvent(structuredClone(events.importCompleteWithWarnings))
    ).toEqual({
      kind: 'complete',
      result: {
        totalTransactions: 12,
        importedTransactions: 9,
        skippedTransactions: 2,
        duplicateTransactions: 1,
        importErrors: 0,
        warnings: [
          { endpoint: 'spot_fills', error: 'OKX HTTP 500: synthetic endpoint failure' },
          {
            endpoint: 'option_settlements',
            error: 'OKX API error: synthetic bills cap',
          },
        ],
      },
      raw: events.importCompleteWithWarnings.data,
    })
    expect(
      decodeImportEvent(structuredClone(events.importCompleteWithoutWarnings))
    ).toEqual({
      kind: 'complete',
      result: {
        totalTransactions: 3,
        importedTransactions: 3,
        skippedTransactions: 0,
        duplicateTransactions: 0,
        importErrors: 0,
        warnings: [],
      },
      raw: events.importCompleteWithoutWarnings.data,
    })
  })

  it('import_stopped with and without stats', () => {
    expect(
      decodeImportEvent(structuredClone(events.importStoppedWithStats))
    ).toEqual({
      kind: 'stopped',
      message: 'Import process was stopped by user',
      stats: {
        totalTransactions: 4,
        importedTransactions: 3,
        skippedTransactions: 1,
        duplicateTransactions: 0,
        importErrors: 0,
        warnings: [],
      },
    })
    expect(
      decodeImportEvent(structuredClone(events.importStoppedWithoutStats))
    ).toEqual({
      kind: 'stopped',
      message: 'Import process stopped',
      stats: null,
    })
  })

  it('account_matching_required transforms the pairs object, keeping extras', () => {
    const decoded = decodeImportEvent(
      structuredClone(events.accountMatchingRequired)
    )
    expect(decoded).toEqual({
      kind: 'account-matching-required',
      broker: { id: 11, name: 'Tinkoff' },
      matchedPairs: matchedPairsArray,
      unmatchedTinkoff: [tinkoffAccount],
      unmatchedDb: [dbAccount],
    })
  })

  it('account_selection_required and security_creation_needed', () => {
    expect(
      decodeImportEvent(structuredClone(events.accountSelectionRequired))
    ).toEqual({
      kind: 'account-selection-required',
      accounts: events.accountSelectionRequired.data.available_accounts,
    })
    expect(
      decodeImportEvent(structuredClone(events.securityCreationNeeded))
    ).toEqual({
      kind: 'security-creation-needed',
      info: { name: 'ACME Corp', isin: 'US0000000001', currency: 'USD' },
    })
  })

  it('backend-produced but frontend-ignored envelopes stay nonterminal', () => {
    expect(decodeImportEvent(structuredClone(events.importWarning))).toEqual({
      kind: 'ignored',
    })
    expect(decodeImportEvent(structuredClone(events.importCancelled))).toEqual({
      kind: 'ignored',
    })
    expect(
      decodeImportEvent(structuredClone(events.importUpdateUnrecognizedOperation))
    ).toEqual({ kind: 'ignored' })
  })
})

describe('incoming decoder — safe degradation', () => {
  it('bare error envelope (no data) becomes a protocol error, never a crash', () => {
    expect(decodeImportEvent(structuredClone(events.errorBare))).toEqual({
      kind: 'protocol-error',
      reason: 'error envelope without data.message',
    })
  })

  it('malformed input degrades to protocol errors', () => {
    for (const raw of [null, 42, 'x', {}, [], { type: 42 }]) {
      const decoded = decodeImportEvent(raw)
      expect(decoded.kind).toBe('protocol-error')
    }
    expect(decodeImportEvent({ type: 'totally_unknown' }).kind).toBe(
      'protocol-error'
    )
    expect(
      decodeImportEvent({ type: 'import_update', data: { status: 'future_status' } }).kind
    ).toBe('protocol-error')
  })

  it('fabricated completion shapes are rejected', () => {
    expect(
      decodeImportEvent({ type: 'import_complete', data: { importedTransactions: 'many' } })
        .kind
    ).toBe('protocol-error')
    expect(decodeImportEvent({ type: 'import_complete' }).kind).toBe(
      'protocol-error'
    )
  })

  it('protocol errors never echo raw payloads', () => {
    const decoded = decodeImportEvent({
      type: 'import_complete',
      data: { importedTransactions: 'many', secret: 'token abc' },
    })
    if (decoded.kind === 'protocol-error') {
      expect(JSON.stringify(decoded)).not.toContain('token abc')
    } else {
      throw new Error('expected protocol-error')
    }
  })
})
