// Synthetic characterization fixtures for the legacy transaction-import
// protocol (D6 task 0). Every value is invented, but every object is shaped
// exactly like the real backend envelopes recorded in
// docs/design/frontend-import-workflow.md. The incumbent behavior at the D6
// base (57f251d3) is the source of truth for these objects:
//   - outgoing commands are the exact `sendMessage` arguments produced by
//     TransactionImportDialog.vue for equivalent inputs;
//   - incoming events are the exact payloads produced by
//     backend/transactions/consumers.py and the import generators.
// Money/quantity/price/rate values are strings on the wire and must never be
// converted to numbers. Progress counters are plain integers (UI counts).

// Provider-specific account objects: the matched-pairs pipeline must carry
// these through verbatim, including fields the importer itself never reads.
export const tinkoffAccount = {
  id: '222444555',
  name: 'T-Invest Brokerage',
  type: 'BROKERAGE',
  openedDate: '2024-02-01T00:00:00Z',
}
export const dbAccount = {
  id: 7,
  name: 'Tinkoff Main',
  broker: 2,
  native_id: null,
}

// account_matching_required carries matched_pairs as an OBJECT keyed by the
// Tinkoff account id (consumers.py start_api_import); the dialog transforms
// it into the pair array below, preserving both full account objects.
export const matchedPairsObject = {
  '222444555': { tinkoff_account: tinkoffAccount, db_account: dbAccount },
}
export const matchedPairsArray = [
  {
    tinkoff_account_id: '222444555',
    db_account_id: 7,
    tinkoff_account: tinkoffAccount,
    db_account: dbAccount,
  },
]

// ---------------------------------------------------------------------
// Outgoing commands: exact sendMessage arguments per send site.
// ---------------------------------------------------------------------
export const commands = {
  fileStartNonGalaxy: {
    type: 'start_file_import',
    file_id: '9f2c8ab0-1111-4ccc-8ddd-222233334444',
    account_id: 3,
    confirm_every: true,
    is_galaxy: false,
    galaxy_type: null,
    currency: null,
  },
  fileStartGalaxy: {
    type: 'start_file_import',
    file_id: '0a1b2c3d-4444-5555-6666-777788889999',
    account_id: 5,
    confirm_every: false,
    is_galaxy: true,
    galaxy_type: 'transactions',
    currency: 'USD',
  },
  // VERIFIED WIRE BEHAVIOR: the incumbent startApiImport sends date_to as
  // well (dateRange.to || null) and backend consumers.py reads it
  // (data.get("date_to")). The accepted D6 example omitted date_to; the
  // recorded discrepancy keeps it so import ranges cannot change.
  apiStartWithDates: {
    type: 'start_api_import',
    data: {
      broker_id: 11,
      confirm_every_transaction: true,
      date_from: '2026-01-01',
      date_to: '2026-06-30',
    },
  },
  apiStartNullDates: {
    type: 'start_api_import',
    data: {
      broker_id: 11,
      confirm_every_transaction: false,
      date_from: null,
      date_to: null,
    },
  },
  stop: { type: 'stop_import' },
  securityMappedMap: { type: 'security_mapped', action: 'map', security_id: 31 },
  securityMappedSkip: {
    type: 'security_mapped',
    action: 'skip',
    security_id: null,
  },
  transactionConfirmed: { type: 'transaction_confirmed', confirmed: true },
  transactionSkipped: { type: 'transaction_confirmed', confirmed: false },
  securityConfirmationCreated: {
    type: 'security_confirmation',
    security_id: 77,
    security_created: true,
    security_data: { name: 'New Synthetic Security', id: 77 },
  },
  securityConfirmationSkipped: {
    type: 'security_confirmation',
    security_id: null,
    skip_transaction: true,
  },
  securityConfirmationExisting: { type: 'security_confirmation', security_id: 42 },
  selectAccount: {
    type: 'select_account',
    data: {
      account_id: 5,
      confirm_every_transaction: true,
      date_from: '2026-01-01',
      date_to: null,
    },
  },
  accountsMatched: { type: 'accounts_matched', data: { pairs: matchedPairsArray } },
  useExistingMatches: {
    type: 'use_existing_matches',
    data: { pairs: matchedPairsArray },
  },
  createAccount: {
    type: 'create_account',
    data: {
      tinkoff_account: tinkoffAccount,
      name: 'New Synthetic Account',
      comment: 'created during import',
    },
  },
} as const

// ---------------------------------------------------------------------
// Incoming events: exact backend producer envelopes.
// ---------------------------------------------------------------------
export const transactionDisplayData = {
  date: '2026-09-01',
  type: 'Buy',
  security: { id: 3, name: 'ACME Corp' },
  quantity: '10',
  price: '115.50',
  total: 1155.0,
  cash_flow: '-1156.65',
  commission: '1.15',
}

export const events = {
  initialization: {
    type: 'initialization',
    message: 'Fetching transactions from broker API...',
    total_to_update: 42,
  },
  importUpdateTotalCount: {
    type: 'import_update',
    data: {
      status: 'total_count',
      total: 42,
      message: 'Found 42 transactions',
    },
  },
  importUpdateProgress: {
    type: 'import_update',
    data: {
      status: 'progress',
      current: 7,
      message: 'Processing transaction 7 of 42',
      progress: 17,
    },
  },
  importUpdateTransactionSaved: {
    type: 'import_update',
    data: {
      status: 'transaction_saved',
      current: 8,
      total: 42,
      message: 'Saved transaction 8 of 42',
      transaction: { count: 1 },
    },
  },
  importUpdateTransactionError: {
    type: 'import_update',
    data: {
      status: 'transaction_error',
      message: 'Error processing transaction',
      error_detail: 'synthetic row failure',
    },
  },
  importUpdateSaveError: {
    type: 'import_update',
    data: {
      status: 'save_error',
      message: 'Error saving transaction: synthetic save failure',
      error_detail: 'synthetic save failure',
    },
  },
  importUpdateSecurityMapping: {
    type: 'import_update',
    data: {
      status: 'security_mapping',
      mapping_data: {
        security_description: 'ACME Corp',
        isin: 'US0000000001',
        symbol: 'ACME',
        best_match: { match_id: 31, match_name: 'ACME Corp.', match_score: 0.87 },
      },
      transaction_data: transactionDisplayData,
    },
  },
  importUpdateTransactionConfirmation: {
    type: 'import_update',
    data: {
      status: 'transaction_confirmation',
      data: transactionDisplayData,
    },
  },
  importUpdateUnrecognizedOperation: {
    type: 'import_update',
    data: {
      status: 'unrecognized_operation',
      transaction_data: transactionDisplayData,
    },
  },
  importErrorSecurity: {
    type: 'import_error',
    data: { error: 'Security not found: ACME Corp (US0000000001)' },
  },
  importErrorPlain: {
    type: 'import_error',
    data: { error: 'synthetic import failure' },
  },
  importErrorAccountInconsistency: {
    type: 'import_error',
    data: {
      error: 'Account ID: 222444555 not matched to any database account',
    },
  },
  saveErrorTopLevel: {
    type: 'save_error',
    data: { error: 'synthetic top-level save failure' },
  },
  criticalError: {
    type: 'critical_error',
    data: { error: 'synthetic fatal import failure' },
  },
  // Backend sends TWO import_stopped shapes: the stop_import handler includes
  // stats; the process_import finally block does not.
  importStoppedWithStats: {
    type: 'import_stopped',
    data: {
      message: 'Import process was stopped by user',
      stats: {
        totalTransactions: 4,
        importedTransactions: 3,
        skippedTransactions: 1,
        duplicateTransactions: 0,
        importErrors: 0,
      },
    },
  },
  importStoppedWithoutStats: {
    type: 'import_stopped',
    data: { message: 'Import process stopped' },
  },
  importCompleteWithWarnings: {
    type: 'import_complete',
    data: {
      totalTransactions: 12,
      importedTransactions: 9,
      skippedTransactions: 2,
      duplicateTransactions: 1,
      importErrors: 0,
      warnings: [
        { endpoint: 'spot_fills', error: 'OKX HTTP 500: synthetic endpoint failure' },
        { endpoint: 'option_settlements', error: 'OKX API error: synthetic bills cap' },
      ],
    },
    message: 'Import process completed',
  },
  importCompleteWithoutWarnings: {
    type: 'import_complete',
    data: {
      totalTransactions: 3,
      importedTransactions: 3,
      skippedTransactions: 0,
      duplicateTransactions: 0,
      importErrors: 0,
    },
    message: 'Import process completed',
  },
  accountMatchingRequired: {
    type: 'account_matching_required',
    data: {
      broker_id: 11,
      broker_name: 'Tinkoff',
      matched_pairs: matchedPairsObject,
      unmatched_tinkoff: [tinkoffAccount],
      unmatched_db: [dbAccount],
      message: 'Please confirm account matches and match remaining accounts',
    },
  },
  accountSelectionRequired: {
    type: 'account_selection_required',
    data: {
      available_accounts: [
        { id: 5, name: 'Synthetic Main', type: 'BROKERAGE', opened_date: '2024-02-01' },
        { id: 6, name: 'Synthetic Secondary', type: 'BROKERAGE', opened_date: '2025-01-15' },
      ],
    },
  },
  securityCreationNeeded: {
    type: 'security_creation_needed',
    security_info: { name: 'ACME Corp', isin: 'US0000000001', currency: 'USD' },
  },
  errorWithData: {
    type: 'error',
    data: { message: 'synthetic broker token expired' },
  },
  // Bare error shape (no `data`): consumers.py sends this for invalid JSON
  // and missing keys. The incumbent watcher would crash on message.data.
  // message; the decoder must classify it as a safe protocol error instead.
  errorBare: { type: 'error', message: 'Invalid JSON data received' },
  progress: {
    type: 'progress',
    data: { message: 'Importing...', total: 42, current: 7 },
  },
  // Produced by the backend but ignored by the incumbent dialog (no branch
  // handles them): the decoder accepts both as terminal-irrelevant events.
  importWarning: {
    type: 'import_warning',
    data: { message: 'Import already in progress' },
  },
  importCancelled: {
    type: 'import_cancelled',
    data: { message: 'Import process was cancelled' },
  },
} as const

// ---------------------------------------------------------------------
// Expected state effects used by the characterization drivers.
// ---------------------------------------------------------------------
export const expected = {
  // The parent payload is the RAW import_complete data object, emitted once.
  // A warning-free completion payload keeps the exact backend shape: it has
  // NO warnings key (only the internal importStats view normalizes it).
  completionWithWarnings: events.importCompleteWithWarnings.data,
  completionWithoutWarnings: events.importCompleteWithoutWarnings.data,
  stoppedMessage: 'Import process was stopped by user',
  securityErrorStrings: [
    'Security not found',
    'Could not match security',
    'unsupported operand type',
    'NoneType',
  ],
}
