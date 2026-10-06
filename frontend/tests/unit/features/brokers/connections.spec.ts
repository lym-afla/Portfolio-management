// D7 task 1 — behavioral contract of the broker request/session owner.
// RED first against the pre-extraction sources: the module under test does
// not exist yet, and several pinned behaviors (ownership-guarded busy
// release, once-only mutations, retained delete subject, log/notice secret
// hygiene) are deliberate corrections of recorded incumbent defects
// (docs/design/frontend-brokers-security.md §1.5). Synthetic credential
// literals appear only inside these test inputs.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import type { EffectScope } from 'vue'
import type {
  BrokerConnectionDisplay,
  BrokerCredentialDraft,
} from '@/features/brokers/types'
import { useBrokerConnections } from '@/features/brokers/useBrokerConnections'
import {
  deleteToken,
  getAvailableBrokers,
  getBrokerTokens,
  revokeToken,
  saveBybitToken,
  saveIBToken,
  saveOKXToken,
  saveTinkoffToken,
  testIBConnection,
  testTinkoffConnection,
} from '@/services/api'
import logger from '@/utils/logger'
import { deferred } from '../../helpers/deferred'

vi.mock('@/services/api', () => ({
  deleteToken: vi.fn(),
  getAvailableBrokers: vi.fn(),
  getBrokerTokens: vi.fn(),
  revokeToken: vi.fn(),
  saveBybitToken: vi.fn(),
  saveIBToken: vi.fn(),
  saveOKXToken: vi.fn(),
  saveTinkoffToken: vi.fn(),
  testIBConnection: vi.fn(),
  testTinkoffConnection: vi.fn(),
}))

vi.mock('@/utils/logger', () => ({
  default: { log: vi.fn(), error: vi.fn() },
}))

const flush = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

const wireTokens = () => ({
  tinkoff_tokens: [
    { id: 11, token_type: 'read_only', sandbox_mode: false, is_active: true, created_at: '2026-09-01T10:30:00Z' },
    { id: 12, token_type: 'full_access', sandbox_mode: false, is_active: false, created_at: '2026-08-01T09:00:00Z' },
  ],
  ib_tokens: [{ id: 1 }],
  bybit_tokens: [
    { id: 21, api_key: 'bybit-synthetic-key', testnet: true, is_active: true, created_at: '2026-07-15T08:00:00Z' },
  ],
  okx_tokens: [
    { id: 31, api_key: 'okx-synthetic-key', simulated_trading: true, is_active: false, created_at: '2026-06-02T12:00:00Z' },
  ],
})

interface Harness {
  owner: ReturnType<typeof useBrokerConnections>
  events: { error: string[]; success: string[]; info: string[] }
  scope: EffectScope
}

const activeScopes: EffectScope[] = []

function startOwner(): Harness {
  const events = { error: [] as string[], success: [] as string[], info: [] as string[] }
  const scope = effectScope(true)
  const owner = scope.run(() =>
    useBrokerConnections({
      emit: {
        error: (message) => events.error.push(message),
        success: (message) => events.success.push(message),
        info: (message) => events.info.push(message),
      },
    }),
  )
  if (!owner) throw new Error('owner scope did not run')
  activeScopes.push(scope)
  return { owner, events, scope }
}

const stopAll = () => {
  for (const scope of activeScopes.splice(0)) scope.stop()
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getAvailableBrokers).mockResolvedValue([
    { id: 1, name: 'Tinkoff Broker', country: 'US' },
    { id: 2, name: 'Interactive Brokers Main', country: 'US' },
    { id: 4, name: 'Bybit Unified', country: 'US' },
    { id: 5, name: 'OKX Trading', country: 'US' },
  ])
  vi.mocked(getBrokerTokens).mockResolvedValue(wireTokens())
  vi.mocked(revokeToken).mockResolvedValue({ message: 'Token revoked successfully' })
  vi.mocked(deleteToken).mockResolvedValue(undefined)
})

afterEach(stopAll)

describe('useBrokerConnections — safe display boundary', () => {
  it('exposes only the allowlisted display fields, never raw credential records', async () => {
    const { owner } = startOwner()
    await owner.refresh()
    owner.showInactive.value = true
    await flush()
    const rows: readonly BrokerConnectionDisplay[] = owner.connections.value
    expect(rows.map((row) => `${row.provider}:${row.tokenId}`)).toEqual([
      'tinkoff:11', 'tinkoff:12', 'ib:1', 'bybit:21', 'okx:31',
    ])
    const allowlist = new Set([
      'provider', 'tokenId', 'label', 'statusIcon', 'statusLabel', 'statusTone',
      'createdAtLabel', 'chips', 'canTest', 'canRevoke', 'canDelete', 'busy',
    ])
    for (const row of rows) {
      for (const key of Object.keys(row)) expect(allowlist.has(key), key).toBe(true)
    }
    // Incumbent display semantics per provider.
    expect(rows[0]).toMatchObject({
      label: 'Read Only Token', statusLabel: 'Valid token', statusTone: 'success',
      statusIcon: 'mdi-check-circle', canTest: true, canRevoke: true, canDelete: false,
    })
    expect(rows[1]).toMatchObject({
      label: 'Full Access Token', statusLabel: 'Invalid token', canDelete: true,
    })
    // IB wire carries {id} only: error status, empty account label, delete shown.
    expect(rows[2]).toMatchObject({
      label: 'Account: ', statusLabel: 'Invalid token', canTest: true, canDelete: true,
    })
    expect(rows[3]).toMatchObject({
      label: 'API key: bybit-synthetic-key', statusLabel: 'Stored token',
      canTest: false, canDelete: false,
    })
    expect(rows[4]).toMatchObject({
      label: 'API key: okx-synthetic-key', statusLabel: 'Inactive token',
      canTest: false, canDelete: true,
    })
    expect(rows[4].chips.map((chip) => chip.text)).toEqual(['Simulated Trading', 'Inactive'])
    expect(JSON.stringify(rows)).not.toContain('api_secret')
    expect(JSON.stringify(rows)).not.toContain('passphrase')
  })

  it('hides inactive rows until the toggle is set (incumbent filter, IB included)', async () => {
    const { owner } = startOwner()
    await owner.refresh()
    await flush()
    // The IB wire record has no is_active, so it is filtered out like the
    // incumbent until "show inactive" is set.
    expect(owner.connections.value.map((row) => row.tokenId)).toEqual([11, 21])
    owner.showInactive.value = true
    expect(owner.connections.value.map((row) => row.tokenId)).toEqual([11, 12, 1, 21, 31])
  })
})

describe('useBrokerConnections — command identity and payloads', () => {
  it('tests tinkoff through the exact endpoint adapter and refreshes', async () => {
    vi.mocked(testTinkoffConnection).mockResolvedValue({ valid: true, token: { id: 11, is_active: false } })
    const { owner, events } = startOwner()
    await owner.refresh()
    await flush()
    await owner.testConnection({ provider: 'tinkoff', tokenId: 11 })
    await flush()
    expect(testTinkoffConnection).toHaveBeenCalledTimes(1)
    expect(testTinkoffConnection).toHaveBeenCalledWith(11)
    expect(getBrokerTokens).toHaveBeenCalledTimes(2)
    expect(events.success).toEqual(['Connection test successful'])
  })

  it('tests ib through its own adapter and never crosses providers', async () => {
    vi.mocked(testIBConnection).mockResolvedValue({ valid: true })
    const { owner, events } = startOwner()
    await owner.refresh()
    await flush()
    await owner.testConnection({ provider: 'ib', tokenId: 1 })
    await flush()
    expect(testIBConnection).toHaveBeenCalledWith(1)
    expect(testTinkoffConnection).not.toHaveBeenCalled()
    expect(events.success).toEqual(['Connection test successful'])
  })

  it('reports unsupported testing for crypto providers without touching any endpoint', async () => {
    const { owner, events } = startOwner()
    await owner.refresh()
    await flush()
    await owner.testConnection({ provider: 'bybit', tokenId: 21 })
    await owner.testConnection({ provider: 'okx', tokenId: 31 })
    expect(events.info).toEqual([
      'Connection testing is not implemented for this broker yet',
      'Connection testing is not implemented for this broker yet',
    ])
    expect(testTinkoffConnection).not.toHaveBeenCalled()
    expect(testIBConnection).not.toHaveBeenCalled()
  })

  it('revokes with the (provider, tokenId) body identity', async () => {
    const { owner, events } = startOwner()
    await owner.refresh()
    await flush()
    await owner.revokeConnection({ provider: 'bybit', tokenId: 21 })
    expect(revokeToken).toHaveBeenCalledTimes(1)
    expect(revokeToken).toHaveBeenCalledWith('bybit', 21)
    expect(events.success).toEqual(['Token revoked successfully'])
  })

  it('deletes exactly the confirmation snapshot and names the subject', async () => {
    const { owner, events } = startOwner()
    await owner.refresh()
    owner.showInactive.value = true
    await flush()
    owner.requestDelete({ provider: 'tinkoff', tokenId: 12 })
    expect(owner.deleteCandidate.value?.key).toEqual({ provider: 'tinkoff', tokenId: 12 })
    expect(owner.deleteCandidate.value?.subject).toContain('Tinkoff')
    expect(owner.deleteCandidate.value?.subject).toContain('Full Access Token')
    await owner.confirmDelete()
    await flush()
    expect(deleteToken).toHaveBeenCalledTimes(1)
    expect(deleteToken).toHaveBeenCalledWith('tinkoff', 12)
    expect(events.success).toEqual(['Token deleted successfully'])
    expect(owner.deleteCandidate.value).toBeNull()
  })

  it('saves each provider draft with the exact incumbent wire payload', async () => {
    vi.mocked(saveTinkoffToken).mockResolvedValue({ message: 'Token saved successfully', id: 77 })
    vi.mocked(testTinkoffConnection).mockResolvedValue({ valid: true })
    const { owner } = startOwner()
    await owner.refresh()
    const tinkoff: BrokerCredentialDraft = {
      provider: 'tinkoff', brokerId: 1, token: 'synthetic-tk',
      tokenType: 'read_only', sandboxMode: false,
    }
    expect(await owner.saveConnection(tinkoff)).toBe('saved')
    expect(saveTinkoffToken).toHaveBeenCalledWith({
      broker: 1, token: 'synthetic-tk', token_type: 'read_only', sandbox_mode: false,
    })
    expect(testTinkoffConnection).toHaveBeenCalledWith(77)

    vi.mocked(saveIBToken).mockResolvedValue({ id: 1 })
    const ib: BrokerCredentialDraft = {
      provider: 'ib', brokerId: 2, token: 'synthetic-ib',
      accountId: 'U123', paperTrading: false,
    }
    expect(await owner.saveConnection(ib)).toBe('saved')
    expect(saveIBToken).toHaveBeenCalledWith({
      broker: 2, token: 'synthetic-ib', account_id: 'U123', paper_trading: false,
    })

    vi.mocked(saveBybitToken).mockResolvedValue({})
    const bybit: BrokerCredentialDraft = {
      provider: 'bybit', brokerId: 4, apiKey: 'k-synth', apiSecret: 's-synth', testnet: true,
    }
    expect(await owner.saveConnection(bybit)).toBe('saved')
    expect(saveBybitToken).toHaveBeenCalledWith({
      broker: 4, api_key: 'k-synth', api_secret: 's-synth', testnet: true,
    })

    vi.mocked(saveOKXToken).mockResolvedValue({})
    const okx: BrokerCredentialDraft = {
      provider: 'okx', brokerId: 5, apiKey: 'k-synth', apiSecret: 's-synth',
      passphrase: 'p-synth', simulatedTrading: true,
    }
    expect(await owner.saveConnection(okx)).toBe('saved')
    expect(saveOKXToken).toHaveBeenCalledWith({
      broker: 5, api_key: 'k-synth', api_secret: 's-synth',
      passphrase: 'p-synth', simulated_trading: true,
    })
  })

  it('routes already-active and reactivated save branches through the message dialog', async () => {
    vi.mocked(saveTinkoffToken).mockResolvedValueOnce({ message: 'Existing token has been reactivated', id: 12 })
    const { owner, events } = startOwner()
    await owner.refresh()
    const outcome = await owner.saveConnection({
      provider: 'tinkoff', brokerId: 1, token: 'synthetic-react',
      tokenType: 'read_only', sandboxMode: false,
    })
    expect(outcome).toBe('reactivated')
    expect(owner.messageDialog.value).toEqual({
      title: 'Token Reactivated',
      text: 'Existing token has been reactivated',
    })
    expect(events.success).toEqual([])

    vi.mocked(saveTinkoffToken).mockRejectedValueOnce({
      response: { status: 400, data: { message: 'This exact token is already active' } },
    })
    const rejected = await owner.saveConnection({
      provider: 'tinkoff', brokerId: 1, token: 'synthetic-dup',
      tokenType: 'read_only', sandboxMode: false,
    })
    expect(rejected).toBe('already-active')
    expect(owner.messageDialog.value).toEqual({
      title: 'Token Already Exists',
      text: 'This exact token is already active',
    })
  })
})

describe('useBrokerConnections — ownership and overlap', () => {
  it('keeps equal numeric token ids of different providers busy-independently', async () => {
    const tinkoffPending = deferred<Awaited<ReturnType<typeof testTinkoffConnection>>>()
    const ibPending = deferred<Awaited<ReturnType<typeof testIBConnection>>>()
    vi.mocked(testTinkoffConnection).mockReturnValueOnce(tinkoffPending.promise)
    vi.mocked(testIBConnection).mockReturnValueOnce(ibPending.promise)
    const { owner } = startOwner()
    await owner.refresh()
    const tinkoffKey = { provider: 'tinkoff' as const, tokenId: 11 }
    const ibKey = { provider: 'ib' as const, tokenId: 1 }
    void owner.testConnection(tinkoffKey)
    await flush()
    expect(owner.isBusy(tinkoffKey)).toBe(true)
    expect(owner.isBusy(ibKey)).toBe(false)
    expect(owner.connections.value.find((row) => row.provider === 'tinkoff')?.busy).toBe(true)
    void owner.testConnection(ibKey)
    await flush()
    expect(owner.isBusy(ibKey)).toBe(true)
    expect(owner.isBusy(tinkoffKey)).toBe(true)
    ibPending.resolve({})
    await flush()
    expect(owner.isBusy(ibKey)).toBe(false)
    expect(owner.isBusy(tinkoffKey)).toBe(true)
    tinkoffPending.resolve({})
    await flush()
    expect(owner.isBusy(tinkoffKey)).toBe(false)
  })

  it('drops the superseded request: no stale success/error/refresh, no busy release', async () => {
    const first = deferred<Awaited<ReturnType<typeof testTinkoffConnection>>>()
    const second = deferred<Awaited<ReturnType<typeof testTinkoffConnection>>>()
    vi.mocked(testTinkoffConnection)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const { owner, events } = startOwner()
    await owner.refresh()
    const key = { provider: 'tinkoff' as const, tokenId: 11 }
    const firstRun = owner.testConnection(key)
    void owner.testConnection(key)
    await flush()
    first.reject({ response: { status: 500, data: { error: 'older failure' } } })
    await flush()
    // The stale rejection surfaces nothing and releases nothing.
    expect(events.error).toEqual([])
    expect(events.success).toEqual([])
    expect(owner.isBusy(key)).toBe(true)
    expect(getBrokerTokens).toHaveBeenCalledTimes(1)
    second.resolve({})
    await flush()
    expect(owner.isBusy(key)).toBe(false)
    expect(events.success).toEqual(['Connection test successful'])
    expect(getBrokerTokens).toHaveBeenCalledTimes(2)
    await expect(firstRun).resolves.toEqual({ status: 'discarded' })
  })

  it('a disposed owner never releases busy state, mutates lists or emits', async () => {
    const pending = deferred<Awaited<ReturnType<typeof testTinkoffConnection>>>()
    vi.mocked(testTinkoffConnection).mockReturnValueOnce(pending.promise)
    const harness = startOwner()
    await harness.owner.refresh()
    const key = { provider: 'tinkoff' as const, tokenId: 11 }
    void harness.owner.testConnection(key)
    await flush()
    expect(harness.owner.isBusy(key)).toBe(true)
    harness.scope.stop()
    pending.resolve({})
    await flush()
    expect(harness.events.success).toEqual([])
    expect(harness.events.error).toEqual([])
    expect(harness.owner.isBusy(key)).toBe(true)
    expect(getBrokerTokens).toHaveBeenCalledTimes(1)
  })

  it('confirms a deletion at most once per snapshot', async () => {
    const pending = deferred()
    vi.mocked(deleteToken).mockReturnValueOnce(pending.promise)
    const { owner } = startOwner()
    await owner.refresh()
    owner.showInactive.value = true
    await flush()
    owner.requestDelete({ provider: 'okx', tokenId: 31 })
    const firstConfirm = owner.confirmDelete()
    await owner.confirmDelete()
    await flush()
    expect(deleteToken).toHaveBeenCalledTimes(1)
    pending.resolve(undefined)
    await firstConfirm
    await owner.confirmDelete()
    await flush()
    // The snapshot cleared after success; a stray confirm mutates nothing.
    expect(deleteToken).toHaveBeenCalledTimes(1)
  })

  it('retains the delete subject after a rejection so a retry targets the same token', async () => {
    vi.mocked(deleteToken).mockRejectedValueOnce({
      response: { status: 400, data: { error: 'Cannot delete active token. Deactivate it first.' } },
    })
    const { owner, events } = startOwner()
    await owner.refresh()
    owner.requestDelete({ provider: 'tinkoff', tokenId: 11 })
    await owner.confirmDelete()
    await flush()
    expect(events.error).toEqual(['Cannot delete active token. Deactivate it first.'])
    expect(owner.deleteCandidate.value?.key).toEqual({ provider: 'tinkoff', tokenId: 11 })
    vi.mocked(deleteToken).mockResolvedValueOnce(undefined)
    await owner.confirmDelete()
    await flush()
    expect(deleteToken).toHaveBeenLastCalledWith('tinkoff', 11)
    expect(owner.deleteCandidate.value).toBeNull()
  })

  it('suppresses a rejected superseded save and keeps exactly one adapter call per save', async () => {
    const first = deferred<Awaited<ReturnType<typeof saveTinkoffToken>>>()
    vi.mocked(saveTinkoffToken)
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({ message: 'Token saved successfully', id: 78 })
    vi.mocked(testTinkoffConnection).mockResolvedValue({ valid: true })
    const { owner, events } = startOwner()
    await owner.refresh()
    const draft = {
      provider: 'tinkoff' as const, brokerId: 1, token: 'synthetic-1',
      tokenType: 'read_only' as const, sandboxMode: false,
    }
    const firstSave = owner.saveConnection(draft)
    const secondSave = owner.saveConnection(draft)
    await flush()
    first.reject(new Error('stale network failure'))
    await flush()
    expect(events.error).toEqual([])
    expect(saveTinkoffToken).toHaveBeenCalledTimes(2)
    expect(await secondSave).toBe('saved')
    expect(await firstSave).toBe('rejected')
    expect(events.error).toEqual([])
    expect(events.success.filter((m) => m === 'Token saved successfully')).toHaveLength(1)
  })

  it('applies only the latest list load when refreshes race', async () => {
    const stale = deferred<Awaited<ReturnType<typeof getBrokerTokens>>>()
    vi.mocked(getBrokerTokens)
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce({ tinkoff_tokens: [], ib_tokens: [], bybit_tokens: [], okx_tokens: [] })
      .mockResolvedValue(wireTokens())
    const { owner } = startOwner()
    const first = owner.refresh()
    const second = owner.refresh()
    await flush()
    stale.resolve(wireTokens())
    await Promise.all([first, second])
    await flush()
    // The LATEST load's (empty) payload wins over the older delayed response.
    expect(owner.connections.value).toEqual([])
    expect(owner.loading.value).toBe(false)
  })
})

describe('useBrokerConnections — credential hygiene', () => {
  it('never surfaces synthetic secrets from a rejection in notices, dialogs or logs', async () => {
    const secret = 'synthetic-secret-DOES-NOT-LEAK'
    vi.mocked(saveTinkoffToken).mockRejectedValueOnce({
      response: {
        status: 400,
        data: { token: [`Invalid value ${secret}`] },
      },
    })
    const { owner, events } = startOwner()
    await owner.refresh()
    const outcome = await owner.saveConnection({
      provider: 'tinkoff', brokerId: 1, token: secret,
      tokenType: 'read_only', sandboxMode: false,
    })
    expect(outcome).toBe('rejected')
    expect(events.error).toEqual(['An unexpected error occurred'])
    expect(owner.messageDialog.value).toBeNull()
    const logged = JSON.stringify([
      vi.mocked(logger.log).mock.calls,
      vi.mocked(logger.error).mock.calls,
    ])
    expect(logged).not.toContain(secret)
    expect(vi.mocked(logger.log).mock.calls.flat().join(' ')).not.toContain(secret)
  })

  it('redacts short credential values from echoed error text', async () => {
    const shortPassphrase = 'ab1'
    vi.mocked(saveOKXToken).mockRejectedValueOnce({
      response: { status: 400, data: { error: `Invalid passphrase ${shortPassphrase}` } },
    })
    const { owner, events } = startOwner()
    await owner.refresh()
    const outcome = await owner.saveConnection({
      provider: 'okx', brokerId: 5, apiKey: 'k', apiSecret: 's',
      passphrase: shortPassphrase, simulatedTrading: false,
    })
    expect(outcome).toBe('rejected')
    expect(events.error).toEqual(['Invalid passphrase [redacted]'])
    expect(events.error.join(' ')).not.toContain('ab1')
  })

  it('sanitizes tinkoff success and reactivation messages that echo the token', async () => {
    const secret = 'synthetic-secret-SUCCESS-ECHO'
    vi.mocked(saveTinkoffToken).mockResolvedValueOnce({
      message: `Token saved: ${secret}`,
      id: 55,
    })
    vi.mocked(testTinkoffConnection).mockResolvedValue({ valid: true })
    const { owner, events } = startOwner()
    await owner.refresh()
    const outcome = await owner.saveConnection({
      provider: 'tinkoff', brokerId: 1, token: secret,
      tokenType: 'read_only', sandboxMode: false,
    })
    expect(outcome).toBe('saved')
    // The post-save auto-test appends its own success message.
    expect(events.success[0]).toBe('Token saved: [redacted]')
    expect(events.success.join(' ')).not.toContain(secret)

    vi.mocked(saveTinkoffToken).mockResolvedValueOnce({
      message: `Existing token has been reactivated: ${secret}`,
      id: 12,
    })
    const reactivated = await owner.saveConnection({
      provider: 'tinkoff', brokerId: 1, token: secret,
      tokenType: 'read_only', sandboxMode: false,
    })
    expect(reactivated).toBe('reactivated')
    expect(owner.messageDialog.value).toEqual({
      title: 'Token Reactivated',
      text: 'Existing token has been reactivated: [redacted]',
    })
  })

  it('sanitizes server error text that echoes the submitted secret', async () => {
    const secret = 'synthetic-secret-SANITIZE-ME'
    vi.mocked(saveTinkoffToken).mockRejectedValueOnce({
      response: { status: 400, data: { error: `Invalid token ${secret}` } },
    })
    const { owner, events } = startOwner()
    await owner.refresh()
    const outcome = await owner.saveConnection({
      provider: 'tinkoff', brokerId: 1, token: secret,
      tokenType: 'read_only', sandboxMode: false,
    })
    expect(outcome).toBe('rejected')
    // The notice is the user-visible surface for save failures; row-scoped
    // errors belong to the row commands (test/revoke/delete), not saves.
    expect(events.error).toEqual(['Invalid token [redacted]'])
    expect(events.error.join(' ')).not.toContain(secret)
  })

  it('sanitizes every submitted credential field in echoed error text', async () => {
    const apiKey = 'synthetic-key-ECHOED'
    const apiSecret = 'synthetic-secret-ECHOED'
    vi.mocked(saveBybitToken).mockRejectedValueOnce({
      response: {
        status: 400,
        data: { error: `key ${apiKey} / secret ${apiSecret} rejected` },
      },
    })
    const { owner, events } = startOwner()
    await owner.refresh()
    const outcome = await owner.saveConnection({
      provider: 'bybit', brokerId: 4, apiKey, apiSecret, testnet: false,
    })
    expect(outcome).toBe('rejected')
    expect(events.error).toEqual(['key [redacted] / secret [redacted] rejected'])
    expect(events.error.join(' ')).not.toContain(apiKey)
    expect(events.error.join(' ')).not.toContain(apiSecret)
  })

  it('keeps server error text that names no field values and stops body logging', async () => {
    vi.mocked(saveTinkoffToken).mockRejectedValueOnce({
      response: { status: 400, data: { error: 'Token verification failed' } },
    })
    const { owner, events } = startOwner()
    await owner.refresh()
    const outcome = await owner.saveConnection({
      provider: 'tinkoff', brokerId: 1, token: 'synthetic-x',
      tokenType: 'read_only', sandboxMode: false,
    })
    expect(outcome).toBe('rejected')
    expect(events.error).toEqual(['Token verification failed'])
    // No request/response body logging anywhere on the save path.
    for (const call of vi.mocked(logger.error).mock.calls) {
      expect(JSON.stringify(call)).not.toContain('synthetic-x')
    }
    expect(vi.mocked(logger.error).mock.calls).toHaveLength(0)
  })
})

describe('useBrokerConnections — error mapping (incumbent parity)', () => {
  it.each([
    [{ response: { status: 403 } }, 'You do not have permission to perform this action'],
    [{ request: {} }, 'The server did not respond. Please check your internet connection'],
    [{ message: 'boom' }, 'boom'],
    [new Error('boom'), 'boom'],
    ['string failure', 'An unexpected error occurred'],
  ])('maps %j to the incumbent message', async (cause, expected) => {
    vi.mocked(revokeToken).mockRejectedValueOnce(cause)
    const { owner, events } = startOwner()
    await owner.refresh()
    await owner.revokeConnection({ provider: 'tinkoff', tokenId: 11 })
    expect(events.error).toEqual([expected])
  })

  it('maps tinkoff test permission failures through the adapter messages', async () => {
    vi.mocked(testTinkoffConnection).mockRejectedValueOnce(new Error('Token has insufficient privileges.'))
    const { owner, events } = startOwner()
    await owner.refresh()
    await owner.testConnection({ provider: 'tinkoff', tokenId: 11 })
    expect(events.error).toEqual(['Token has insufficient privileges.'])
    // The incumbent refreshes after a failed test too.
    expect(getBrokerTokens).toHaveBeenCalledTimes(2)
    expect(owner.rowError({ provider: 'tinkoff', tokenId: 11 })).toBe(
      'Token has insufficient privileges.',
    )
  })
})

describe('useBrokerConnections — confirmation ownership', () => {
  it('a stale successful delete must not clear a newer confirmation', async () => {
    const stale = deferred()
    vi.mocked(deleteToken)
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(undefined)
    const { owner, events } = startOwner()
    await owner.refresh()
    await flush()
    // Confirm delete A; while it is in flight, cancel and open B.
    owner.requestDelete({ provider: 'tinkoff', tokenId: 11 })
    const staleConfirm = owner.confirmDelete()
    await flush()
    owner.cancelDelete()
    owner.requestDelete({ provider: 'tinkoff', tokenId: 12 })
    expect(owner.deleteCandidate.value?.key).toEqual({ provider: 'tinkoff', tokenId: 12 })
    // Stale A succeeds now: B's confirmation must survive untouched.
    stale.resolve(undefined)
    await staleConfirm
    await flush()
    expect(events.success).toEqual([])
    expect(owner.deleteCandidate.value?.key).toEqual({ provider: 'tinkoff', tokenId: 12 })
    // B still deletes exactly the snapshotted token and then clears.
    await owner.confirmDelete()
    await flush()
    expect(deleteToken).toHaveBeenLastCalledWith('tinkoff', 12)
    expect(events.success).toEqual(['Token deleted successfully'])
    expect(owner.deleteCandidate.value).toBeNull()
  })

  it('a newer confirmation may delete while an older delete is still in flight', async () => {
    const stale = deferred()
    vi.mocked(deleteToken)
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(undefined)
    const { owner, events } = startOwner()
    await owner.refresh()
    await flush()
    owner.requestDelete({ provider: 'bybit', tokenId: 21 })
    void owner.confirmDelete()
    await flush()
    // Cancel A's dialog and open B while A is in flight.
    owner.cancelDelete()
    owner.requestDelete({ provider: 'okx', tokenId: 31 })
    await owner.confirmDelete()
    await flush()
    expect(deleteToken).toHaveBeenCalledTimes(2)
    expect(deleteToken).toHaveBeenLastCalledWith('okx', 31)
    stale.resolve(undefined)
    await flush()
    // B's success cleared the candidate; the stale A completion afterwards
    // emits and clears nothing.
    expect(events.success).toEqual(['Token deleted successfully'])
    expect(owner.deleteCandidate.value).toBeNull()
  })
})
