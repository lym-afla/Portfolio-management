import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import {
  configurePortfolioContextBackend,
  type ContextValues,
  type PortfolioContextBackend,
} from '@/services/api/context'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { ApiError } from '@/services/http/errors'

vi.mock('@/services/http/client', () => ({
  apiGet: vi.fn(async (url: string) =>
    url.includes('get_account_choices')
      ? {
          options: [
            ['All', { type: 'all', id: null }],
            [
              'Accounts',
              [1, 2, 3].map((id) => [String(id), { type: 'account', id }]),
            ],
            ['Broker', { type: 'broker', id: 4 }],
            ['Group', { type: 'group', id: 5 }],
          ],
        }
      : {
          choices: {
            default_currency: [
              ['USD', 'Dollar'],
              ['EUR', 'Euro'],
            ],
          },
        }
  ),
}))
export function deferred<T = void>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
let backend: PortfolioContextBackend
let canonical: ContextValues
beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  canonical = {
    accountSelection: { type: 'account', id: 1 },
    effectiveCurrentDate: '2026-09-08',
    currency: 'USD',
    digits: 2,
  }
  backend = {
    read: vi.fn(async () => structuredClone(canonical)),
    updateAccount: vi.fn(async (selection) => {
      canonical.accountSelection = selection
    }),
    updateSettings: vi.fn(async (settings) => {
      Object.assign(canonical, settings)
    }),
  }
  configurePortfolioContextBackend(backend)
})
describe('portfolioContext', () => {
  it('retains committed values on a definite rejection and exposes the actual error', async () => {
    const store = usePortfolioContextStore()
    await store.reconcileContext()
    const error = new ApiError(
      'Account denied',
      400,
      'context_mutation_rejected'
    )
    vi.mocked(backend.updateAccount).mockRejectedValueOnce(error)
    await expect(
      store.changeContext({ accountSelection: { type: 'account', id: 2 } })
    ).rejects.toThrow('Account denied')
    expect(store.committed.accountSelection).toEqual({ type: 'account', id: 1 })
    expect(store.transitionError?.message).toBe('Account denied')
    expect(store.isReady).toBe(true)
  })
  it('invalidates synchronously and commits the entire settings tuple only after refresh/readback', async () => {
    const store = usePortfolioContextStore()
    await store.reconcileContext()
    const revision = store.committed.revision
    const refresh = deferred()
    vi.mocked(backend.updateSettings).mockImplementationOnce(
      async (settings) => {
        await refresh.promise
        Object.assign(canonical, settings)
      }
    )
    const pending = store.changeContext({
      effectiveCurrentDate: '2025-12-31',
      currency: 'EUR',
      digits: 4,
    })
    expect(store.isTransitioning).toBe(true)
    expect(store.committed.revision).toBe(revision + 1)
    expect(store.committed).toMatchObject({ currency: 'USD', digits: 2 })
    refresh.resolve()
    await pending
    expect(store.committed).toMatchObject({
      revision: revision + 1,
      effectiveCurrentDate: '2025-12-31',
      currency: 'EUR',
      digits: 4,
    })
  })
  it.each([
    { type: 'all', id: null },
    { type: 'account', id: 2 },
    { type: 'broker', id: 4 },
    { type: 'group', id: 5 },
  ] as const)('commits canonical $type selections', async (selection) => {
    const store = usePortfolioContextStore()
    await store.reconcileContext()
    await store.changeContext({ accountSelection: selection })
    expect(store.committed.accountSelection).toEqual(selection)
  })
  it('copies caller patches, serializes rapid changes, and continues after rejection', async () => {
    const store = usePortfolioContextStore()
    await store.reconcileContext()
    const first = deferred()
    const patch = { accountSelection: { type: 'account' as const, id: 2 } }
    vi.mocked(backend.updateAccount).mockImplementationOnce(async () => {
      await first.promise
      throw new ApiError('Rejected', 400, 'context_mutation_rejected')
    })
    const one = store.changeContext(patch)
    const rejected = expect(one).rejects.toThrow('Rejected')
    patch.accountSelection.id = 999
    const two = store.changeContext({
      accountSelection: { type: 'broker', id: 4 },
    })
    await Promise.resolve()
    expect(backend.updateAccount).toHaveBeenCalledTimes(1)
    expect(backend.updateAccount).toHaveBeenCalledWith({
      type: 'account',
      id: 2,
    })
    first.resolve()
    await rejected
    await two
    expect(store.committed.accountSelection).toEqual({ type: 'broker', id: 4 })
  })
  it('reconciles ambiguous outcomes without writing a rollback', async () => {
    const store = usePortfolioContextStore()
    await store.reconcileContext()
    vi.mocked(backend.updateAccount).mockImplementationOnce(
      async (selection) => {
        canonical.accountSelection = selection
        throw new Error('Connection lost')
      }
    )
    await expect(
      store.changeContext({ accountSelection: { type: 'account', id: 2 } })
    ).rejects.toThrow('Connection lost')
    expect(store.committed.accountSelection.id).toBe(2)
    expect(store.isReady).toBe(true)
    expect(backend.updateAccount).toHaveBeenCalledTimes(1)
  })
  it('blocks further writes until failed reconciliation recovers', async () => {
    const store = usePortfolioContextStore()
    await store.reconcileContext()
    vi.mocked(backend.updateAccount).mockRejectedValueOnce(
      new Error('Connection lost')
    )
    vi.mocked(backend.read).mockRejectedValue(new Error('Offline'))
    await expect(
      store.changeContext({ accountSelection: { type: 'account', id: 2 } })
    ).rejects.toThrow('Connection lost')
    expect(store.isReady).toBe(false)
    await expect(
      store.changeContext({ accountSelection: { type: 'account', id: 3 } })
    ).rejects.toThrow('Offline')
    expect(backend.updateAccount).toHaveBeenCalledTimes(1)
    vi.mocked(backend.read).mockResolvedValue(canonical)
    await store.reconcileContext()
    expect(store.isReady).toBe(true)
  })
  it('does not resurrect context or execute queued mutations after logout', async () => {
    const store = usePortfolioContextStore()
    await store.reconcileContext()
    const mutation = deferred()
    vi.mocked(backend.updateAccount).mockReturnValueOnce(mutation.promise)
    const one = store.changeContext({
      accountSelection: { type: 'account', id: 2 },
    })
    const two = store.changeContext({
      accountSelection: { type: 'account', id: 3 },
    })
    const done = Promise.allSettled([one, two])
    await Promise.resolve()
    store.resetContext()
    mutation.resolve()
    await done
    expect(store.isReady).toBe(false)
    expect(store.committed.accountSelection).toEqual({ type: 'all', id: null })
    expect(backend.updateAccount).toHaveBeenCalledTimes(1)
  })
  it('discards malformed cached selections', () => {
    localStorage.setItem('accountSelection', '{broken')
    expect(() => usePortfolioContextStore()).not.toThrow()
    expect(usePortfolioContextStore().isReady).toBe(false)
  })
  it.each([
    { accountSelection: { type: 'account', id: 999 } },
    { effectiveCurrentDate: '2025-02-30' },
    { currency: '$' },
    { digits: 7 },
  ])('validates before sending %j', async (patch) => {
    const store = usePortfolioContextStore()
    await store.reconcileContext()
    await expect(store.changeContext(patch as never)).rejects.toThrow()
    expect(backend.updateAccount).not.toHaveBeenCalled()
    expect(backend.updateSettings).not.toHaveBeenCalled()
  })
})

it('treats an account readback HTTP rejection as ambiguous after the write', async () => {
  const store = usePortfolioContextStore()
  await store.reconcileContext()
  vi.mocked(backend.updateAccount).mockImplementationOnce(async (selection) => {
    canonical.accountSelection = selection
    throw new ApiError('Readback unavailable', 400)
  })
  await expect(
    store.changeContext({ accountSelection: { type: 'account', id: 2 } })
  ).rejects.toThrow('Readback unavailable')
  expect(store.committed.accountSelection.id).toBe(2)
})
it('serializes two successful rapid changes and reconciles publicly behind them', async () => {
  const store = usePortfolioContextStore(); await store.reconcileContext()
  const first = deferred(); const order: string[] = []
  vi.mocked(backend.updateAccount).mockImplementationOnce(async account => { order.push('account-start'); await first.promise; canonical.accountSelection = account; order.push('account-end') })
  vi.mocked(backend.updateSettings).mockImplementationOnce(async settings => { order.push('settings'); Object.assign(canonical, settings) })
  const one = store.changeContext({ accountSelection: { type: 'account', id: 2 } })
  const two = store.changeContext({ currency: 'EUR', digits: 4 })
  const reconciled = store.reconcileContext()
  expect(store.committed.currency).toBe('USD'); expect(backend.updateSettings).not.toHaveBeenCalled()
  first.resolve(); await Promise.all([one, two, reconciled])
  expect(order).toEqual(['account-start', 'account-end', 'settings'])
  expect(store.committed).toMatchObject({ accountSelection: { type: 'account', id: 2 }, currency: 'EUR', digits: 4 }); expect(store.canRead).toBe(true)
})
