// D6 task 0 — characterization of the INCUMBENT transaction import workflow
// at the extraction base. Every assertion here records verified behavior of
// TransactionImportDialog.vue as it exists today (base 57f251d3), driven
// through the same fixtures the post-extraction protocol/workflow suites
// reuse. Nothing in this file asserts invented financial outcomes: all
// money/quantity/rate values pass through as exact strings.
import { mount } from '@vue/test-utils'
import {
  afterAll,
  beforeAll,
  beforeEach,
  afterEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'
import { nextTick, ref } from 'vue'
import { generateVuetifyStubs } from '../../test-utils'

import TransactionImportDialog from '@/components/dialogs/TransactionImportDialog.vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { analyzeFile, getAccounts, getBrokersWithTokens } from '@/services/api'
import {
  commands,
  dbAccount,
  events,
  expected,
  matchedPairsArray,
  tinkoffAccount,
  transactionDisplayData,
} from './fixtures'

vi.mock('@/services/api', () => ({
  analyzeFile: vi.fn(),
  getAccounts: vi.fn(),
  getBrokersWithTokens: vi.fn(),
  getSecurities: vi.fn(),
  createSecurity: vi.fn(),
  updateSecurity: vi.fn(),
  getSecurityFormStructure: vi.fn(),
  isSecurityConflictPayload: vi.fn(),
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}))

const originalConsoleWarn = console.warn
const originalConsoleError = console.error
const originalLog = console.log

beforeAll(() => {
  console.warn = vi.fn()
  console.error = vi.fn()
  console.log = vi.fn()
})

afterAll(() => {
  console.warn = originalConsoleWarn
  console.error = originalConsoleError
  console.log = originalLog
})

let wrapper
let sendMock
let connectMock
let disconnectMock
let isConnected
let lastMessage

const mountDialog = () => {
  const div = document.createElement('div')
  div.id = 'app'
  document.body.appendChild(div)
  wrapper = mount(TransactionImportDialog, {
    attachTo: '#app',
    props: { modelValue: true },
    global: {
      stubs: {
        ...generateVuetifyStubs(),
        'v-tooltip': {
          template:
            '<div class="v-tooltip"><slot name="activator" :props="{}"/></div>',
        },
      },
    },
  })
  return wrapper
}

const feed = async (event) => {
  lastMessage.value = structuredClone(event)
  await nextTick()
  await nextTick()
}

const sends = () => sendMock.mock.calls.map((call) => call[0])
const lastSend = () => sends()[sends().length - 1]

beforeEach(() => {
  vi.clearAllMocks()
  getBrokersWithTokens.mockResolvedValue([
    { id: 1, name: 'Tinkoff Broker' },
    { id: 2, name: 'Interactive Brokers' },
  ])
  getAccounts.mockResolvedValue([
    { id: 3, name: 'Main account', broker: { text: 'Tinkoff' } },
    { id: 9, name: 'Secondary account' },
  ])
  analyzeFile.mockResolvedValue({
    status: 'account_identified',
    message: 'Broker account was automatically identified.',
    fileId: '9f2c8ab0-1111-4ccc-8ddd-222233334444',
    identifiedAccount: { id: 3, name: 'Main account' },
  })
  isConnected = ref(false)
  lastMessage = ref(null)
  sendMock = vi.fn(() => true)
  connectMock = vi.fn()
  disconnectMock = vi.fn()
  useWebSocket.mockReturnValue({
    isConnected,
    lastMessage,
    sendMessage: sendMock,
    connect: connectMock,
    disconnect: disconnectMock,
    reset: vi.fn(),
  })
})

afterEach(() => {
  document.body.innerHTML = ''
  if (wrapper) wrapper.unmount()
  wrapper = null
})

describe('incumbent outgoing start commands', () => {
  it('file start: exact wire object, non-galaxy nulls galaxy_type/currency', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.fileId = commands.fileStartNonGalaxy.file_id
    vm.selectedAccount = commands.fileStartNonGalaxy.account_id
    vm.confirmEveryTransaction = true
    vm.isGalaxy = false
    connectMock.mockResolvedValue(true)
    isConnected.value = true

    await vm.startImport()

    expect(connectMock).toHaveBeenCalledTimes(1)
    expect(sends()).toHaveLength(1)
    expect(lastSend()).toEqual(commands.fileStartNonGalaxy)
    expect(vm.showProgressDialog).toBe(true)
    expect(vm.dialog).toBe(false)
  })

  it('file start, galaxy variant: carries galaxy_type and currency verbatim', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.fileId = commands.fileStartGalaxy.file_id
    vm.selectedAccount = commands.fileStartGalaxy.account_id
    vm.confirmEveryTransaction = false
    vm.isGalaxy = true
    vm.galaxyType = 'transactions'
    vm.selectedCurrency = 'USD'
    connectMock.mockResolvedValue(true)
    isConnected.value = true

    await vm.startImport()

    expect(sends()).toHaveLength(1)
    expect(lastSend()).toEqual(commands.fileStartGalaxy)
  })

  it('file start with failed connect: state error, progress hidden, no send', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.fileId = 'f1'
    vm.selectedAccount = 3
    connectMock.mockResolvedValue(false)
    isConnected.value = false

    await vm.startImport()

    expect(sends()).toHaveLength(0)
    expect(vm.importError).toBe('WebSocket not connected. Please try again.')
    expect(vm.showProgressDialog).toBe(false)
  })

  it('api start: date_from AND date_to ride the wire (verified discrepancy)', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.selectedBroker = { id: 11, name: 'Tinkoff' }
    vm.dateRange = { from: '2026-01-01', to: '2026-06-30' }
    vm.confirmEveryTransaction = true
    connectMock.mockResolvedValue(true)
    isConnected.value = true

    await vm.startApiImport()

    expect(sends()).toHaveLength(1)
    expect(lastSend()).toEqual(commands.apiStartWithDates)
  })

  it('api start with unset dates: both date fields serialize as null', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.selectedBroker = { id: 11, name: 'Tinkoff' }
    vm.dateRange = { from: null, to: null }
    connectMock.mockResolvedValue(true)
    isConnected.value = true

    await vm.startApiImport()

    expect(lastSend()).toEqual(commands.apiStartNullDates)
  })

  it('api start without broker: validation error, no send, no progress dialog', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.selectedBroker = null

    await vm.startApiImport()

    expect(sends()).toHaveLength(0)
    expect(vm.errorMessage).toBe('Please select a broker account')
    expect(vm.showProgressDialog).toBe(false)
  })

  it('api start with failed connect: recoverable error, no send', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    vm.selectedBroker = { id: 11, name: 'Tinkoff' }
    connectMock.mockResolvedValue(false)
    isConnected.value = false

    await vm.startApiImport()

    expect(sends()).toHaveLength(0)
    expect(vm.importError).toBe('Failed to establish WebSocket connection')
    expect(vm.showProgressDialog).toBe(false)
  })
})

describe('incumbent stop and decision commands', () => {
  it('stop: exact payload, sent regardless of connection state, stop disabled', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = false

    vm.stopImport()

    expect(lastSend()).toEqual(commands.stop)
    expect(vm.canStopImport).toBe(false)
  })

  it('security mapping confirm: security_mapped map with selected id', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.showSecurityMapping = true
    vm.handleSecuritySelected(31)

    vm.handleConfirm()

    expect(lastSend()).toEqual(commands.securityMappedMap)
    expect(vm.showSecurityMapping).toBe(false)
    expect(vm.currentTransaction).toEqual({})
  })

  it('security mapping skip: security_mapped skip with null id', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.showSecurityMapping = true

    vm.handleSkip()

    expect(lastSend()).toEqual(commands.securityMappedSkip)
  })

  it('plain transaction confirm/skip: transaction_confirmed booleans', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.showSecurityMapping = false

    vm.handleConfirm()
    expect(lastSend()).toEqual(commands.transactionConfirmed)

    vm.handleSkip()
    expect(lastSend()).toEqual(commands.transactionSkipped)
  })

  it('decisions are not sent while disconnected', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = false
    vm.showSecurityMapping = false

    vm.handleConfirm()
    vm.handleSkip()

    expect(sends()).toHaveLength(0)
  })

  it('security created from mapping flow: maps with the new id', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.showSecurityMapping = true

    vm.handleSecurityAdded({ id: 77, name: 'New Synthetic Security' })

    expect(lastSend()).toEqual({
      type: 'security_mapped',
      action: 'map',
      security_id: 77,
    })
  })

  it('security created outside mapping: security_confirmation with created flag', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.showSecurityMapping = false

    vm.handleSecurityAdded({ id: 77, name: 'New Synthetic Security' })

    expect(lastSend()).toEqual(commands.securityConfirmationCreated)
  })

  it('security added without an id sends nothing', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.showSecurityMapping = false

    vm.handleSecurityAdded({ name: 'id-less' })

    expect(sends()).toHaveLength(0)
  })

  it('security skipped from mapping vs outside mapping', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true

    vm.showSecurityMapping = true
    vm.handleSecuritySkipped()
    expect(lastSend()).toEqual(commands.securityMappedSkip)

    vm.showSecurityMapping = false
    vm.handleSecuritySkipped()
    expect(lastSend()).toEqual(commands.securityConfirmationSkipped)
  })

  it('readonly security confirm: bare security_confirmation', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.securityFormData = { readonly: true, id: 42, name: 'Existing' }
    vm.confirmDialog = true

    vm.handleSecurityConfirm(true)

    expect(lastSend()).toEqual(commands.securityConfirmationExisting)
    expect(vm.confirmDialog).toBe(false)
  })

  it('editable security confirm: opens the creation form, sends nothing yet', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.securityFormData = { name: 'Draft', ISIN: 'US1' }

    vm.handleSecurityConfirm(true)

    expect(sends()).toHaveLength(0)
    expect(vm.showSecurityDialog).toBe(true)
  })

  it('select_account: passes confirm flag and both dates through', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true
    vm.confirmEveryTransaction = true
    vm.dateRange = { from: '2026-01-01', to: null }

    vm.selectAccount({ id: 5, name: 'Synthetic Main', type: 'BROKERAGE' })

    expect(lastSend()).toEqual(commands.selectAccount)
    expect(vm.showAccountSelection).toBe(false)
  })

  it('accounts_matched: full provider objects preserved verbatim', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true

    vm.handleAccountsMatched({ pairs: structuredClone(matchedPairsArray) })

    expect(lastSend()).toEqual(commands.accountsMatched)
    expect(lastSend().data.pairs[0].tinkoff_account).toEqual(tinkoffAccount)
    expect(lastSend().data.pairs[0].db_account).toEqual(dbAccount)
    expect(vm.showAccountMatching).toBe(false)
    expect(vm.showProgressDialog).toBe(true)
  })

  it('accounts_matched rejects missing and empty pair lists without sending', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true

    vm.handleAccountsMatched({})
    expect(vm.errorMessage).toBe('Invalid account pairing data received')
    vm.handleAccountsMatched({ pairs: [] })
    expect(vm.errorMessage).toBe('No account pairs were provided')
    expect(sends()).toHaveLength(0)
  })

  it('use_existing_matches: exact payload with full objects', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true

    vm.handleUseExistingMatches({ pairs: structuredClone(matchedPairsArray) })

    expect(lastSend()).toEqual(commands.useExistingMatches)
  })

  it('create_account: tinkoff object, name and defaulted comment', async () => {
    mountDialog()
    await nextTick()
    const vm = wrapper.vm
    isConnected.value = true

    vm.handleAccountCreation({
      tinkoff_account: tinkoffAccount,
      name: 'New Synthetic Account',
      comment: 'created during import',
    })
    expect(lastSend()).toEqual(commands.createAccount)

    vm.handleAccountCreation({ tinkoff_account: tinkoffAccount, name: 'X' })
    expect(lastSend().data.comment).toBe('')
  })
})

describe('incumbent incoming event handling', () => {
  it('initialization sets totals and message from top-level fields', async () => {
    mountDialog()
    await feed(events.initialization)
    expect(wrapper.vm.totalToImport).toBe(42)
    expect(wrapper.vm.currentImportMessage).toBe(
      'Fetching transactions from broker API...'
    )
  })

  it('import_update total_count sets total and fallback message', async () => {
    mountDialog()
    await feed(events.importUpdateTotalCount)
    expect(wrapper.vm.totalToImport).toBe(42)
    expect(wrapper.vm.currentImportMessage).toBe('Found 42 transactions')
  })

  it('import_update progress advances counters and message', async () => {
    mountDialog()
    wrapper.vm.totalToImport = 42
    await feed(events.importUpdateProgress)
    expect(wrapper.vm.currentImported).toBe(7)
    expect(wrapper.vm.currentImportMessage).toBe(
      'Processing transaction 7 of 42'
    )
  })

  it('import_update transaction_saved advances the saved counter', async () => {
    mountDialog()
    wrapper.vm.totalToImport = 42
    await feed(events.importUpdateTransactionSaved)
    expect(wrapper.vm.currentImported).toBe(8)
    expect(wrapper.vm.currentImportMessage).toBe('Saved transaction 8 of 42')
  })

  it('import_update transaction_error surfaces inline and keeps going', async () => {
    mountDialog()
    await feed(events.importUpdateTransactionError)
    expect(wrapper.vm.currentImportMessage).toBe(
      '⚠️ Error processing transaction'
    )
    expect(wrapper.vm.showErrorDialog).toBe(false)
    expect(wrapper.vm.importStats.importErrors).toBe(0)
  })

  it('security_mapping opens both overlays with display data intact', async () => {
    mountDialog()
    await feed(events.importUpdateSecurityMapping)
    expect(wrapper.vm.showSecurityMapping).toBe(true)
    expect(wrapper.vm.showTransactionConfirmation).toBe(true)
    expect(wrapper.vm.securityToMap).toBe('ACME Corp')
    expect(wrapper.vm.bestMatch).toEqual(
      events.importUpdateSecurityMapping.data.mapping_data.best_match
    )
    expect(wrapper.vm.currentTransaction).toEqual(transactionDisplayData)
  })

  it('transaction_confirmation shows the transaction without mapping', async () => {
    mountDialog()
    await feed(events.importUpdateTransactionConfirmation)
    expect(wrapper.vm.showTransactionConfirmation).toBe(true)
    expect(wrapper.vm.showSecurityMapping).toBe(false)
    expect(wrapper.vm.currentTransaction).toEqual(transactionDisplayData)
  })

  it('import_complete emits the raw payload once with exact counters and warnings', async () => {
    mountDialog()
    wrapper.vm.totalToImport = 12
    await feed(events.importCompleteWithWarnings)

    const completions = wrapper.emitted('import-completed')
    expect(completions).toHaveLength(1)
    expect(completions[0][0]).toEqual(expected.completionWithWarnings)
    expect(wrapper.vm.importStats).toEqual({
      totalTransactions: 12,
      importedTransactions: 9,
      skippedTransactions: 2,
      duplicateTransactions: 1,
      importErrors: 0,
      warnings: events.importCompleteWithWarnings.data.warnings,
    })
    expect(wrapper.vm.showSuccessDialog).toBe(true)
    expect(wrapper.vm.showProgressDialog).toBe(false)
    expect(disconnectMock).toHaveBeenCalled()
    expect(wrapper.vm.canStopImport).toBe(true)
    expect(wrapper.html()).toContain('Some data sources could not be fetched')
    expect(wrapper.html()).toContain('spot_fills')
  })

  it('import_complete without a warnings field normalizes to an empty list', async () => {
    mountDialog()
    await feed(events.importCompleteWithoutWarnings)

    expect(wrapper.emitted('import-completed')).toHaveLength(1)
    expect(wrapper.emitted('import-completed')[0][0]).toEqual(
      expected.completionWithoutWarnings
    )
    expect(wrapper.vm.importStats.warnings).toEqual([])
    expect(wrapper.html()).not.toContain(
      'Some data sources could not be fetched'
    )
  })

  it('import_stopped with stats shows the stopped outcome, never completion', async () => {
    mountDialog()
    wrapper.vm.showProgressDialog = true
    await feed(events.importStoppedWithStats)

    expect(wrapper.emitted('import-completed')).toBeUndefined()
    expect(wrapper.vm.showErrorDialog).toBe(true)
    expect(wrapper.vm.errorMessage).toBe(expected.stoppedMessage)
    expect(wrapper.vm.importStats).toEqual(
      events.importStoppedWithStats.data.stats
    )
    expect(wrapper.vm.showProgressDialog).toBe(false)
    expect(disconnectMock).toHaveBeenCalled()
  })

  it('import_stopped without stats still stops and disconnects', async () => {
    mountDialog()
    wrapper.vm.showProgressDialog = true
    // Recorded incumbent defect: stats-less import_stopped (the shape the
    // backend's process_import finally block sends) overwrites importStats
    // with undefined and the result template crashes reading .warnings.
    await expect(feed(events.importStoppedWithoutStats)).rejects.toThrow(
      /warnings/
    )
    expect(wrapper.emitted('import-completed')).toBeUndefined()
    expect(disconnectMock).toHaveBeenCalled()
  })

  it('critical_error tears the run down and never completes', async () => {
    mountDialog()
    wrapper.vm.showProgressDialog = true
    wrapper.vm.showSecurityMapping = true
    await feed(events.criticalError)

    expect(wrapper.emitted('import-completed')).toBeUndefined()
    expect(wrapper.vm.showErrorDialog).toBe(true)
    // Recorded incumbent defect: the branch sets the error message, then the
    // teardown's resetProgressDialog() clears it, so the error dialog opens
    // with an empty body.
    expect(wrapper.vm.errorMessage).toBe('')
    expect(wrapper.vm.showProgressDialog).toBe(false)
    expect(wrapper.vm.showSecurityMapping).toBe(false)
    expect(wrapper.vm.showTransactionConfirmation).toBe(false)
    expect(disconnectMock).toHaveBeenCalled()
  })

  it('import_error with a security string opens the create/skip dialog', async () => {
    mountDialog()
    await feed(events.importErrorSecurity)

    expect(wrapper.vm.confirmDialog).toBe(true)
    expect(wrapper.vm.confirmTitle).toBe('Unknown Security Detected')
    expect(wrapper.vm.securityFormData).toEqual({
      name: 'Security not found: ACME Corp',
      ISIN: 'US0000000001',
      currency: 'RUB',
      type: 'Stock',
      exposure: 'Equity',
    })
    expect(wrapper.vm.importError).toBe(
      'Security not found: ACME Corp (US0000000001)'
    )
  })

  it('import_error without a security string shows the error dialog directly', async () => {
    mountDialog()
    await feed(events.importErrorPlain)

    expect(wrapper.vm.confirmDialog).toBe(false)
    // Recorded incumbent behavior: the main watcher branch shows the error
    // dialog via errorMessage and never routes plain import_error through
    // handleImportError, so importError stays empty.
    expect(wrapper.vm.errorMessage).toBe('synthetic import failure')
    expect(wrapper.vm.showErrorDialog).toBe(true)
    expect(wrapper.vm.importError).toBe('')
  })

  it('top-level save_error is handled like import_error', async () => {
    mountDialog()
    await feed(events.saveErrorTopLevel)
    expect(wrapper.vm.importError).toBe('synthetic top-level save failure')
  })

  it('account_matching_required transforms the pairs object, keeping full objects', async () => {
    mountDialog()
    wrapper.vm.showProgressDialog = true
    await feed(events.accountMatchingRequired)

    expect(wrapper.vm.selectedBroker).toEqual({ id: 11, name: 'Tinkoff' })
    expect(wrapper.vm.tinkoffAccounts).toEqual([tinkoffAccount])
    expect(wrapper.vm.dbAccounts).toEqual([dbAccount])
    expect(wrapper.vm.matchedPairs).toEqual(matchedPairsArray)
    expect(wrapper.vm.showAccountMatching).toBe(true)
    expect(wrapper.vm.showProgressDialog).toBe(false)
  })

  it('account_selection_required lists accounts for the selection dialog', async () => {
    mountDialog()
    await feed(events.accountSelectionRequired)
    expect(wrapper.vm.availableAccounts).toEqual(
      events.accountSelectionRequired.data.available_accounts
    )
    expect(wrapper.vm.showAccountSelection).toBe(true)
  })

  it('security_creation_needed pre-fills the security form', async () => {
    mountDialog()
    await feed(events.securityCreationNeeded)
    expect(wrapper.vm.securityFormData).toEqual({
      name: 'ACME Corp',
      ISIN: 'US0000000001',
      currency: 'USD',
      type: 'Stock',
      exposure: 'Equity',
    })
    expect(wrapper.vm.showSecurityDialog).toBe(true)
  })

  it('error with data sets the import error and clears the progress message', async () => {
    mountDialog()
    wrapper.vm.currentImportMessage = 'Working...'
    await feed(events.errorWithData)
    expect(wrapper.vm.importError).toBe('synthetic broker token expired')
    expect(wrapper.vm.currentImportMessage).toBe('')
  })

  it('matched-account inconsistency shows the server-inconsistency error', async () => {
    mountDialog()
    wrapper.vm.matchedPairs = structuredClone(matchedPairsArray)
    await feed(events.importErrorAccountInconsistency)

    expect(wrapper.vm.showErrorDialog).toBe(true)
    expect(wrapper.vm.errorMessage).toBe(
      'Server inconsistency detected: An account you matched was not recognized during import. This is likely a server-side bug. Please try again or contact support.'
    )
    expect(wrapper.vm.confirmDialog).toBe(false)
  })

  it('unrecognized_operation updates are ignored without state changes', async () => {
    mountDialog()
    await feed(events.importUpdateUnrecognizedOperation)
    expect(wrapper.vm.showTransactionConfirmation).toBe(false)
    expect(wrapper.vm.showErrorDialog).toBe(false)
    expect(wrapper.emitted('import-completed')).toBeUndefined()
  })

  it('import_warning and import_cancelled are ignored by the incumbent', async () => {
    mountDialog()
    await feed(events.importWarning)
    await feed(events.importCancelled)
    expect(sends()).toHaveLength(0)
    expect(wrapper.emitted('import-completed')).toBeUndefined()
    expect(wrapper.vm.showErrorDialog).toBe(false)
    expect(wrapper.vm.showProgressDialog).toBe(false)
  })
})

describe('incumbent file analysis', () => {
  it('analyze_file success preselects the identified account', async () => {
    mountDialog()
    const vm = wrapper.vm
    vm.file = { name: 'synthetic.csv' }
    await vm.submitFile()
    await nextTick()

    expect(analyzeFile).toHaveBeenCalledTimes(1)
    expect(vm.isAnalyzed).toBe(true)
    expect(vm.fileId).toBe('9f2c8ab0-1111-4ccc-8ddd-222233334444')
    expect(vm.accountIdentified).toBe(true)
    expect(vm.identifiedAccount).toEqual({ id: 3, name: 'Main account' })
    expect(vm.selectedAccount).toBe(3)
    expect(vm.accountIdentificationComplete).toBe(true)
  })

  it('analyze_file failure is recoverable and returns to configuration', async () => {
    mountDialog()
    const vm = wrapper.vm
    analyzeFile.mockRejectedValue({ message: 'synthetic analyze failure' })
    vm.file = { name: 'synthetic.csv' }
    await vm.submitFile()
    await nextTick()

    expect(vm.isAnalyzed).toBe(false)
    expect(vm.accountIdentificationComplete).toBe(true)
    expect(vm.isLoading).toBe(false)
  })

  it('analyze without a file records the no-file error', async () => {
    mountDialog()
    const vm = wrapper.vm
    await vm.submitFile()
    expect(vm.isAnalyzed).toBe(false)
  })
})

describe('incumbent lifecycle', () => {
  it('cancel closes the dialog, emits v-model false, keeps method selection', async () => {
    mountDialog()
    const vm = wrapper.vm
    vm.importMethod = 'file'
    vm.importMethodSelected = true
    vm.file = { name: 'synthetic.csv' }

    vm.closeDialog()
    await nextTick()

    expect(vm.dialog).toBe(false)
    expect(wrapper.emitted('update:modelValue')?.flat()).toContain(false)
    expect(vm.file).toBe(null)
    // Recorded incumbent quirk: closeDialog never resets the method
    // selection (importMethod/importMethodSelected survive Cancel).
    expect(vm.importMethod).toBe('file')
    expect(vm.importMethodSelected).toBe(true)
  })

  it('unmount disconnects the socket', async () => {
    mountDialog()
    wrapper.unmount()
    wrapper = null
    expect(disconnectMock).toHaveBeenCalled()
  })

  it('closeSuccessDialog clears the analyzed file state', async () => {
    mountDialog()
    const vm = wrapper.vm
    vm.file = { name: 'synthetic.csv' }
    vm.isAnalyzed = true
    vm.fileId = 'abc'
    vm.selectedAccount = 3

    vm.closeSuccessDialog()

    expect(vm.file).toBe(null)
    expect(vm.isAnalyzed).toBe(false)
    expect(vm.fileId).toBe(null)
    expect(vm.selectedAccount).toBe(null)
  })
})
