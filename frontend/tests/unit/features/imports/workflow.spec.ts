// D6 task 2 — lifecycle-safe orchestration over the typed state owner.
// These tests pin generation ownership (once-only starts/completion), stale
// callback containment across close/reopen, stop-pending-until-acknowledged,
// and the decision surface with reject paths that preserve retryable values.
import { describe, expect, it, vi } from 'vitest'

import { useTransactionImport } from '@/features/imports/useTransactionImport'
import type { ImportCommand, ImportTransport } from '@/features/imports/types'
import {
  commands,
  events,
  matchedPairsArray,
  tinkoffAccount,
} from './fixtures'

function makeTransport() {
  const sent: ImportCommand[] = []
  let connectResult = true
  let sendResult = true
  const connect = vi.fn(async () => connectResult)
  const send = vi.fn((command: ImportCommand) => {
    if (!sendResult) return false
    sent.push(structuredClone(command))
    return true
  })
  const disconnect = vi.fn()
  const transport: ImportTransport = { connect, send, disconnect }
  return {
    transport,
    sent,
    connect,
    disconnect,
    failConnect: () => {
      connectResult = false
    },
    failSend: () => {
      sendResult = false
    },
  }
}

function makeHarness() {
  const world = makeTransport()
  const completed: unknown[] = []
  const errors: string[] = []
  const analyze = vi.fn()
  const fetchAccounts = vi.fn(async () => [
    { id: 3, name: 'Main account' },
    { id: 9, name: 'Secondary account' },
  ])
  const orchestrator = useTransactionImport({
    transport: world.transport,
    analyze,
    fetchAccounts,
    onCompleted: (raw) => completed.push(raw),
    onError: (message) => errors.push(message),
  })
  return { ...world, orchestrator, completed, errors, analyze, fetchAccounts }
}

const lastState = (orchestrator: ReturnType<typeof useTransactionImport>) =>
  orchestrator.state.value

describe('workflow state transitions', () => {
  it('starts at choose-method and moves through configure and review', async () => {
    const h = makeHarness()
    expect(lastState(h.orchestrator).kind).toBe('choose-method')

    h.orchestrator.selectMethod('file')
    expect(lastState(h.orchestrator)).toEqual({ kind: 'configure', method: 'file' })

    h.analyze.mockResolvedValue({
      status: 'account_identified',
      fileId: 'abc',
      identifiedAccount: { id: 3, name: 'Main account' },
    })
    await h.orchestrator.analyze(new Blob(['x']) as unknown as File)

    expect(lastState(h.orchestrator)).toEqual({
      kind: 'review',
      method: 'file',
      accountLabel: 'Main account',
    })
    expect(h.orchestrator.configuration.fileId.value).toBe('abc')
    expect(h.orchestrator.configuration.selectedAccount.value).toBe(3)
    expect(h.fetchAccounts).toHaveBeenCalledTimes(1)
  })

  it('analyze failure is a recoverable error that can return to configuration', async () => {
    const h = makeHarness()
    h.orchestrator.selectMethod('file')
    h.analyze.mockRejectedValue({ message: 'synthetic analyze failure' })
    await h.orchestrator.analyze(new Blob(['x']) as unknown as File)

    expect(lastState(h.orchestrator)).toEqual({
      kind: 'error',
      message: 'synthetic analyze failure',
      canReturnToConfiguration: true,
    })
    expect(h.errors).toEqual([{ message: 'synthetic analyze failure' }])
  })

  it('back returns to method choice and clears the file session data', async () => {
    const h = makeHarness()
    h.orchestrator.selectMethod('api')
    h.orchestrator.configuration.selectedBroker.value = { id: 11, name: 'T' }
    h.orchestrator.back()
    expect(lastState(h.orchestrator).kind).toBe('choose-method')
    expect(h.orchestrator.configuration.selectedBroker.value).toBe(null)
  })

  it('galaxy file start without currency is rejected before any connection', async () => {
    const h = makeHarness()
    h.orchestrator.configuration.fileId.value = 'abc'
    await h.orchestrator.startFile({
      fileId: 'abc',
      accountId: 3,
      confirmEvery: false,
      isGalaxy: true,
      galaxyType: 'transactions',
      currency: null,
    })
    expect(h.connect).not.toHaveBeenCalled()
    expect(lastState(h.orchestrator).kind).toBe('error')
  })
})

describe('once-only starts and generation ownership', () => {
  it('file start connects once, sends the exact command once, enters running', async () => {
    const h = makeHarness()
    await h.orchestrator.startFile({
      fileId: '9f2c8ab0-1111-4ccc-8ddd-222233334444',
      accountId: 3,
      confirmEvery: true,
      isGalaxy: false,
      galaxyType: 'transactions',
      currency: null,
    })
    expect(h.connect).toHaveBeenCalledTimes(1)
    expect(h.sent).toEqual([commands.fileStartNonGalaxy])
    expect(lastState(h.orchestrator).kind).toBe('running')
  })

  it('duplicate start while connect is pending sends nothing twice', async () => {
    const h = makeHarness()
    let releaseConnect: (value: boolean) => void = () => {}
    h.connect.mockImplementation(
      () => new Promise<boolean>((resolve) => {
        releaseConnect = resolve
      })
    )
    const first = h.orchestrator.startFile({
      fileId: 'abc',
      accountId: 3,
      confirmEvery: false,
      isGalaxy: false,
      galaxyType: 'transactions',
      currency: null,
    })
    const second = h.orchestrator.startFile({
      fileId: 'abc',
      accountId: 3,
      confirmEvery: false,
      isGalaxy: false,
      galaxyType: 'transactions',
      currency: null,
    })
    releaseConnect(true)
    await Promise.all([first, second])

    expect(h.connect).toHaveBeenCalledTimes(1)
    expect(h.sent).toHaveLength(1)
  })

  it('api start preserves both dates and the initializing message', async () => {
    const h = makeHarness()
    await h.orchestrator.startApi({
      brokerId: 11,
      confirmEvery: true,
      dateFrom: '2026-01-01',
      dateTo: '2026-06-30',
    })
    expect(h.sent).toEqual([commands.apiStartWithDates])
    const state = lastState(h.orchestrator)
    expect(state.kind).toBe('running')
    if (state.kind === 'running') {
      expect(state.message).toBe('Initializing import...')
      expect(state.method).toBe('api')
    }
  })

  it('failed connect never enters running and stays recoverable', async () => {
    const h = makeHarness()
    h.failConnect()
    await h.orchestrator.startApi({
      brokerId: 11,
      confirmEvery: false,
      dateFrom: null,
      dateTo: null,
    })
    expect(h.sent).toHaveLength(0)
    const state = lastState(h.orchestrator)
    expect(state.kind).toBe('error')
    if (state.kind === 'error') expect(state.canReturnToConfiguration).toBe(true)
  })

  it('failed start send does not fake a running import', async () => {
    const h = makeHarness()
    h.failSend()
    await h.orchestrator.startApi({
      brokerId: 11,
      confirmEvery: false,
      dateFrom: null,
      dateTo: null,
    })
    expect(lastState(h.orchestrator).kind).toBe('error')
  })
})

describe('incoming events and decisions', () => {
  const startFileRun = async (h: ReturnType<typeof makeHarness>) => {
    await h.orchestrator.startFile({
      fileId: 'abc',
      accountId: 3,
      confirmEvery: true,
      isGalaxy: false,
      galaxyType: 'transactions',
      currency: null,
    })
    h.sent.length = 0
  }

  it('progress updates the running state fields', async () => {
    const h = makeHarness()
    await startFileRun(h)
    h.orchestrator.receive(structuredClone(events.importUpdateTotalCount))
    h.orchestrator.receive(structuredClone(events.importUpdateProgress))
    const state = lastState(h.orchestrator)
    expect(state).toMatchObject({
      kind: 'running',
      current: 7,
      total: 42,
      message: 'Processing transaction 7 of 42',
    })
  })

  it('security mapping decision resolves to map and skip commands', async () => {
    const h = makeHarness()
    await startFileRun(h)
    h.orchestrator.receive(structuredClone(events.importUpdateSecurityMapping))
    expect(lastState(h.orchestrator).kind).toBe('decision')

    h.orchestrator.resolveSecurityMapping(31)
    expect(h.sent).toEqual([commands.securityMappedMap])
    expect(lastState(h.orchestrator).kind).toBe('running')

    h.orchestrator.receive(structuredClone(events.importUpdateSecurityMapping))
    h.orchestrator.resolveSecurityMapping(null)
    expect(h.sent[1]).toEqual(commands.securityMappedSkip)
  })

  it('a failed decision send keeps the decision state and its values', async () => {
    const h = makeHarness()
    await startFileRun(h)
    h.orchestrator.receive(structuredClone(events.importUpdateTransactionConfirmation))
    h.failSend()
    h.orchestrator.resolveTransaction(true)
    expect(lastState(h.orchestrator).kind).toBe('decision')

    h.sent.length = 0
    const send = h.transport.send as ReturnType<typeof vi.fn>
    send.mockImplementation((command: ImportCommand) => {
      h.sent.push(command)
      return true
    })
    h.orchestrator.resolveTransaction(true)
    expect(h.sent).toEqual([commands.transactionConfirmed])
    expect(lastState(h.orchestrator).kind).toBe('running')
  })

  it('transaction confirmation resolves confirmed and skipped', async () => {
    const h = makeHarness()
    await startFileRun(h)
    h.orchestrator.receive(structuredClone(events.importUpdateTransactionConfirmation))
    h.orchestrator.resolveTransaction(false)
    expect(h.sent).toEqual([commands.transactionSkipped])

    h.orchestrator.receive(structuredClone(events.importUpdateTransactionConfirmation))
    h.orchestrator.resolveTransaction(true)
    expect(h.sent[1]).toEqual(commands.transactionConfirmed)
  })

  it('security creation and skip outside mapping use security_confirmation', async () => {
    const h = makeHarness()
    await startFileRun(h)
    h.orchestrator.receive(structuredClone(events.securityCreationNeeded))
    expect(lastState(h.orchestrator).kind).toBe('decision')

    h.orchestrator.resolveSecurityCreated({ id: 77, name: 'New Synthetic Security' })
    expect(h.sent).toEqual([commands.securityConfirmationCreated])

    h.orchestrator.receive(structuredClone(events.securityCreationNeeded))
    h.orchestrator.resolveSecuritySkipped()
    expect(h.sent[1]).toEqual(commands.securityConfirmationSkipped)
  })

  it('security error decision extracts the name for the create/skip flow', async () => {
    const h = makeHarness()
    await startFileRun(h)
    h.orchestrator.receive(structuredClone(events.importErrorSecurity))
    const state = lastState(h.orchestrator)
    expect(state.kind).toBe('decision')
    if (state.kind === 'decision' && state.decision === 'security') {
      const payload = state.payload as { info?: { name?: string } }
      expect(payload.info?.name).toContain('ACME Corp')
    }
    h.orchestrator.resolveSecuritySkipped()
    expect(h.sent).toEqual([commands.securityConfirmationSkipped])
  })

  it('account matching decision sends verbatim pairs and rejects empty lists', async () => {
    const h = makeHarness()
    await startFileRun(h)
    h.orchestrator.receive(structuredClone(events.accountMatchingRequired))
    expect(lastState(h.orchestrator).kind).toBe('decision')

    h.orchestrator.resolveUseExistingMatches(structuredClone(matchedPairsArray))
    expect(h.sent).toEqual([commands.useExistingMatches])

    h.orchestrator.receive(structuredClone(events.accountMatchingRequired))
    h.orchestrator.resolveAccountMatched([])
    expect(h.sent).toHaveLength(1)
    expect(h.errors).toEqual(['No account pairs were provided'])
    expect(lastState(h.orchestrator).kind).toBe('decision')

    h.orchestrator.resolveAccountMatched(structuredClone(matchedPairsArray))
    expect(h.sent[1]).toEqual(commands.accountsMatched)
    expect(lastState(h.orchestrator).kind).toBe('running')
  })

  it('account selection uses the separate command contract with both dates', async () => {
    const h = makeHarness()
    await startFileRun(h)
    h.orchestrator.receive(structuredClone(events.accountSelectionRequired))
    h.orchestrator.configuration.dateRange.value = { from: '2026-01-01', to: null }
    h.orchestrator.configuration.confirmEveryTransaction.value = true

    h.orchestrator.resolveAccountSelection({ id: 5 })
    expect(h.sent).toEqual([commands.selectAccount])
  })
})

describe('completion, stop and stale-event containment', () => {
  const startRun = async (h: ReturnType<typeof makeHarness>) => {
    await h.orchestrator.startApi({
      brokerId: 11,
      confirmEvery: false,
      dateFrom: null,
      dateTo: null,
    })
    h.sent.length = 0
  }

  it('completion emits the raw payload once with all counters and warnings', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.receive(structuredClone(events.importCompleteWithWarnings))

    expect(h.completed).toHaveLength(1)
    expect(h.completed[0]).toEqual(events.importCompleteWithWarnings.data)
    expect(lastState(h.orchestrator)).toEqual({
      kind: 'complete',
      result: {
        totalTransactions: 12,
        importedTransactions: 9,
        skippedTransactions: 2,
        duplicateTransactions: 1,
        importErrors: 0,
        warnings: events.importCompleteWithWarnings.data.warnings,
      },
    })
    expect(h.disconnect).toHaveBeenCalled()

    h.orchestrator.receive(structuredClone(events.importCompleteWithWarnings))
    expect(h.completed).toHaveLength(1)
  })

  it('unknown messages never complete a run', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.receive({ type: 'import_complete', data: 'garbage' })
    h.orchestrator.receive({ type: 'mystery' })
    expect(h.completed).toHaveLength(0)
    expect(lastState(h.orchestrator).kind).toBe('running')
  })

  it('requestStop sends once and waits in stopping for the acknowledgment', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.requestStop()
    expect(h.sent).toEqual([commands.stop])
    expect(lastState(h.orchestrator).kind).toBe('stopping')

    h.orchestrator.requestStop()
    expect(h.sent).toHaveLength(1)

    h.orchestrator.receive(structuredClone(events.importStoppedWithStats))
    const state = lastState(h.orchestrator)
    expect(state.kind).toBe('error')
    expect(h.completed).toHaveLength(0)
    expect(h.disconnect).toHaveBeenCalled()
  })

  it('a failed stop send does not claim stopped', async () => {
    const h = makeHarness()
    await startRun(h)
    h.failSend()
    h.orchestrator.requestStop()
    expect(h.sent).toHaveLength(0)
    expect(lastState(h.orchestrator).kind).toBe('error')
  })

  it('stop can be requested while a decision overlay is pending', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.receive(structuredClone(events.importUpdateTransactionConfirmation))
    h.orchestrator.requestStop()
    // Incumbent parity: Stop stays available during decisions; the pending
    // decision is discarded and the run persists in stopping until the
    // acknowledgment.
    expect(h.sent).toEqual([commands.stop])
    expect(lastState(h.orchestrator).kind).toBe('stopping')

    // The discarded decision can no longer resolve.
    h.sent.length = 0
    h.orchestrator.resolveTransaction(true)
    expect(h.sent).toHaveLength(0)
    expect(lastState(h.orchestrator).kind).toBe('stopping')

    // A late decision event cannot reopen a decision while stopping.
    h.orchestrator.receive(structuredClone(events.importUpdateTransactionConfirmation))
    h.orchestrator.receive(structuredClone(events.importUpdateSecurityMapping))
    h.orchestrator.receive(structuredClone(events.accountMatchingRequired))
    expect(lastState(h.orchestrator).kind).toBe('stopping')
    expect(h.sent).toHaveLength(0)

    // The acknowledgment still ends the run with the stopped outcome.
    h.orchestrator.receive(structuredClone(events.importStoppedWithStats))
    expect(lastState(h.orchestrator).kind).toBe('error')
    expect(h.completed).toHaveLength(0)
  })

  it('recoverable import errors keep the run tracked end to end', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.receive(structuredClone(events.importErrorPlain))
    // Non-fatal: the run keeps tracking, Stop stays available.
    expect(lastState(h.orchestrator).kind).toBe('running')
    expect(h.orchestrator.lastRunError.value).toBe('synthetic import failure')

    h.orchestrator.receive(structuredClone(events.importUpdateProgress))
    expect(lastState(h.orchestrator)).toMatchObject({ kind: 'running', current: 7 })

    h.orchestrator.requestStop()
    expect(h.sent).toEqual([commands.stop])
    expect(lastState(h.orchestrator).kind).toBe('stopping')
  })

  it('a completion after recoverable errors still reaches the parent once', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.receive(structuredClone(events.importErrorPlain))
    h.orchestrator.receive(structuredClone(events.importCompleteWithWarnings))

    expect(h.completed).toHaveLength(1)
    expect(h.completed[0]).toEqual(events.importCompleteWithWarnings.data)
    expect(h.orchestrator.lastRunError.value).toBe(null)
    expect(lastState(h.orchestrator).kind).toBe('complete')
  })

  it('consumer error envelopes surface without leaving the session', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.receive(structuredClone(events.errorWithData))
    expect(h.orchestrator.lastRunError.value).toBe('synthetic broker token expired')
    expect(lastState(h.orchestrator).kind).toBe('running')

    h.orchestrator.receive(structuredClone(events.importCompleteWithWarnings))
    expect(h.completed).toHaveLength(1)
  })

  it('account resolvers are inert after reset', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.receive(structuredClone(events.accountMatchingRequired))
    expect(lastState(h.orchestrator).kind).toBe('decision')

    h.orchestrator.reset()
    h.sent.length = 0

    h.orchestrator.resolveAccountMatched(structuredClone(matchedPairsArray))
    h.orchestrator.resolveUseExistingMatches(structuredClone(matchedPairsArray))
    h.orchestrator.resolveCreateAccount({
      tinkoffAccount: tinkoffAccount,
      name: 'New Synthetic Account',
    })
    h.orchestrator.resolveAccountSelection({ id: 5 })

    expect(h.sent).toHaveLength(0)
    expect(lastState(h.orchestrator).kind).toBe('choose-method')
  })

  it('late account loading cannot mutate reset configuration', async () => {
    const h = makeHarness()
    h.orchestrator.selectMethod('file')
    let releaseAccounts: (value: Array<Record<string, unknown>>) => void = () => {}
    h.analyze.mockResolvedValue({
      status: 'account_identified',
      fileId: 'late-accounts',
      identifiedAccount: { id: 3, name: 'Main account' },
    })
    h.fetchAccounts.mockImplementation(
      () => new Promise((resolve) => {
        releaseAccounts = resolve
      })
    )
    const pending = h.orchestrator.analyze(new Blob(['x']) as unknown as File)
    // Wait until the workflow is actually parked on the account fetch so
    // the reset races the LATE lookup, not the analyzer response.
    await vi.waitFor(() => expect(h.fetchAccounts).toHaveBeenCalled())
    expect(h.orchestrator.configuration.fileId.value).toBe('late-accounts')
    h.orchestrator.reset()
    releaseAccounts([{ id: 3, name: 'Main account' }])
    await pending

    expect(lastState(h.orchestrator).kind).toBe('choose-method')
    expect(h.orchestrator.configuration.fileId.value).toBe(null)
    expect(h.orchestrator.configuration.accounts.value).toEqual([])
    expect(h.orchestrator.configuration.selectedAccount.value).toBe(null)
  })

  it('dispose invalidates a pending connection so no start is sent', async () => {
    const h = makeHarness()
    let releaseConnect: (value: boolean) => void = () => {}
    h.connect.mockImplementation(
      () => new Promise<boolean>((resolve) => {
        releaseConnect = resolve
      })
    )
    const pending = h.orchestrator.startApi({
      brokerId: 11,
      confirmEvery: false,
      dateFrom: null,
      dateTo: null,
    })
    h.orchestrator.dispose()
    releaseConnect(true)
    await pending

    expect(h.sent).toHaveLength(0)
    expect(h.disconnect).toHaveBeenCalled()
    expect(h.completed).toHaveLength(0)
  })

  it('stale events after reset cannot repopulate or complete the next run', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.reset()
    expect(lastState(h.orchestrator).kind).toBe('choose-method')
    expect(h.disconnect).toHaveBeenCalled()

    h.orchestrator.receive(structuredClone(events.importCompleteWithWarnings))
    h.orchestrator.receive(structuredClone(events.accountMatchingRequired))
    expect(h.completed).toHaveLength(0)
    expect(lastState(h.orchestrator).kind).toBe('choose-method')

    await startRun(h)
    expect(lastState(h.orchestrator).kind).toBe('running')
    expect(h.orchestrator.configuration.fileId.value).toBe(null)
  })

  it('late analyzer responses after close are discarded', async () => {
    const h = makeHarness()
    h.orchestrator.selectMethod('file')
    let release: (value: Record<string, unknown>) => void = () => {}
    h.analyze.mockImplementation(
      () => new Promise((resolve) => {
        release = resolve
      })
    )
    const pending = h.orchestrator.analyze(new Blob(['x']) as unknown as File)
    h.orchestrator.reset()
    release({
      status: 'account_identified',
      fileId: 'late',
      identifiedAccount: { id: 3, name: 'Late account' },
    })
    await pending

    expect(lastState(h.orchestrator).kind).toBe('choose-method')
    expect(h.orchestrator.configuration.fileId.value).toBe(null)
  })

  it('disconnection during a run is an error, never a completion', () => {
    const h = makeHarness()
    h.orchestrator.notifyDisconnected()
    expect(h.completed).toHaveLength(0)
    const state = lastState(h.orchestrator)
    expect(state.kind).toBe('choose-method')
  })

  it('disconnection during an active run surfaces a recoverable error', async () => {
    const h = makeHarness()
    await startRun(h)
    h.orchestrator.notifyDisconnected()
    expect(h.completed).toHaveLength(0)
    const state = lastState(h.orchestrator)
    expect(state.kind).toBe('error')
    if (state.kind === 'error') {
      expect(state.message).not.toContain('complet')
    }
  })
})
