// C2 Task 4: shared request lifecycle over the real runner and committed
// context. Deferred promises prove latest-wins behavior (even when a fetcher
// ignores abort), immutable query snapshots, and that only a CURRENT failed
// context mismatch may ask the existing store to reconcile — never an old,
// unmounted or logged-out one, and never a retry loop.
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import type { AxiosInstance } from 'axios'
import { configureApiTransport } from '@/services/http/client'
import { configureContextFixture } from '../../../../tests/unit/context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { deferred } from '../../../../tests/unit/helpers/deferred'
import type { NavQuery, NavResult } from '../contracts'
import { navFixture } from './fixtures'

import {
  ChartContextMismatchError,
} from '../chartApi'
import {
  requireReadyChartContext,
  snapshotNavQuery,
  useNavChart,
} from '../useNavChart'

const clone = <T>(value: T): T => structuredClone(value)

type ChartCall = { params: Record<string, unknown>; signal: AbortSignal }

let chartCalls: ChartCall[] = []
let respond: ((call: ChartCall) => Promise<{ data: unknown }>) | null = null

function successEnvelope(): ReturnType<typeof navFixture> {
  const envelope = clone(navFixture())
  envelope.chartV2.context = {
    accountSelection: { type: 'all', id: null },
    accountIds: [],
    effectiveDate: '2026-01-31',
    currency: 'USD',
    digits: 2,
  }
  return envelope
}

function mismatchEnvelope(): ReturnType<typeof navFixture> {
  const envelope = successEnvelope()
  envelope.chartV2.context.effectiveDate = '2026-09-30'
  return envelope
}

beforeEach(async () => {
  chartCalls = []
  respond = null
  const pinia = createPinia()
  setActivePinia(pinia)
  configureContextFixture('2026-09-30')
  configureApiTransport({
    get: async (url: string, config?: { params?: Record<string, unknown>; signal?: AbortSignal }) => {
      if (url === '/dashboard/api/get-nav-chart-data/') {
        const call = { params: config?.params ?? {}, signal: config?.signal as AbortSignal }
        chartCalls.push(call)
        return respond ? respond(call) : { data: successEnvelope() }
      }
      if (url.includes('get_account_choices')) return { data: { options: [['All accounts', { type: 'all', id: null }]] } }
      if (url.includes('dashboard_settings')) return { data: { choices: { default_currency: [['USD', 'Dollar'], ['EUR', 'Euro']] } } }
      throw new Error(`unexpected transport url: ${url}`)
    },
  } as unknown as AxiosInstance)
  await usePortfolioContextStore().reconcileContext()
})

afterEach(() => {
  vi.restoreAllMocks()
})

function makeQuery(overrides: Partial<NavQuery> = {}): NavQuery {
  const context = usePortfolioContextStore()
  return {
    context: requireReadyChartContext(context.committed),
    mode: 'none',
    frequency: 'M',
    fromDate: '2026-01-01',
    toDate: '2026-01-31',
    ...overrides,
  }
}

function mountNavChart() {
  const scope = effectScope()
  const api = scope.run(() => useNavChart())!
  return { scope, api }
}

describe('useNavChart latest-request behavior', () => {
  it('lets B win over A even when A ignores abort', async () => {
    const { scope, api } = mountNavChart()
    const a = deferred<{ data: unknown }>()
    const b = deferred<{ data: unknown }>()
    respond = () => a.promise
    const runA = api.run(makeQuery())
    respond = () => b.promise
    const runB = api.run(makeQuery({ frequency: 'W' }))
    b.resolve({ data: successEnvelope() })
    await runB.then((result) => expect(result.status).toBe('accepted'))
    a.resolve({ data: successEnvelope() })
    const lateA = await runA
    expect(lateA.status).toBe('discarded')
    expect(api.loading.value).toBe(false)
    expect(api.data.value?.capability).toBe('v2')
    scope.stop()
  })

  it('discards a late failure after a newer success and keeps the newer data', async () => {
    const { scope, api } = mountNavChart()
    const a = deferred<{ data: unknown }>()
    respond = () => a.promise
    const runA = api.run(makeQuery())
    respond = () => Promise.resolve({ data: successEnvelope() })
    await api.run(makeQuery({ frequency: 'Q' }))
    a.reject(new ChartContextMismatchError('stale mismatch'))
    expect((await runA).status).toBe('discarded')
    expect(api.error.value).toBeNull()
    expect(api.data.value?.capability).toBe('v2')
    scope.stop()
  })

  it('clears the local error after a successful retry of the same query', async () => {
    const { scope, api } = mountNavChart()
    respond = () => Promise.reject(new Error('network down'))
    const failed = await api.run(makeQuery())
    expect(failed.status).toBe('failed')
    expect(api.error.value?.message).toBe('network down')
    respond = () => Promise.resolve({ data: successEnvelope() })
    const retried = await api.run(makeQuery())
    expect(retried.status).toBe('accepted')
    expect(api.error.value).toBeNull()
    expect(api.loading.value).toBe(false)
    scope.stop()
  })

  it('invalidation aborts the in-flight request and clears state', async () => {
    const { scope, api } = mountNavChart()
    const hold = deferred<{ data: unknown }>()
    respond = () => hold.promise
    const pending = api.run(makeQuery())
    expect(api.loading.value).toBe(true)
    api.invalidate()
    expect(api.loading.value).toBe(false)
    expect(api.data.value).toBeNull()
    expect(chartCalls[0].signal.aborted).toBe(true)
    hold.resolve({ data: successEnvelope() })
    expect((await pending).status).toBe('discarded')
    scope.stop()
  })

  it('logout resets context, discards the old query and blocks further runs', async () => {
    const { scope, api } = mountNavChart()
    const context = usePortfolioContextStore()
    const capturedQuery = makeQuery()
    const hold = deferred<{ data: unknown }>()
    respond = () => hold.promise
    const pending = api.run(capturedQuery)
    context.resetContext()
    expect(api.data.value).toBeNull()
    expect(api.loading.value).toBe(false)
    hold.resolve({ data: successEnvelope() })
    expect((await pending).status).toBe('discarded')
    const after = await api.run(capturedQuery)
    expect(after.status).toBe('discarded')
    expect(chartCalls).toHaveLength(1)
    scope.stop()
  })

  it('unmount disposes the runner; late replies and post-disposal runs do nothing', async () => {
    const { scope, api } = mountNavChart()
    const hold = deferred<{ data: unknown }>()
    respond = () => hold.promise
    const pending = api.run(makeQuery())
    scope.stop()
    hold.resolve({ data: successEnvelope() })
    expect((await pending).status).toBe('discarded')
    const after = await api.run(makeQuery())
    expect(after.status).toBe('discarded')
    expect(api.data.value).toBeNull()
    expect(chartCalls).toHaveLength(1)
  })

  it('retains prior data under loading for a same-context refresh', async () => {
    const { scope, api } = mountNavChart()
    respond = () => Promise.resolve({ data: successEnvelope() })
    await api.run(makeQuery())
    const first = api.data.value as Extract<NavResult, { capability: 'v2' }>
    const hold = deferred<{ data: unknown }>()
    respond = () => hold.promise
    const pending = api.run(makeQuery({ frequency: 'Y' }))
    expect(api.loading.value).toBe(true)
    expect(api.data.value).toBe(first)
    hold.resolve({ data: successEnvelope() })
    await pending
    expect(api.data.value).not.toBe(first)
    expect(api.loading.value).toBe(false)
    scope.stop()
  })

  it('a context transition clears old data before new labels apply', async () => {
    const { scope, api } = mountNavChart()
    respond = () => Promise.resolve({ data: successEnvelope() })
    await api.run(makeQuery())
    expect(api.data.value).not.toBeNull()
    const context = usePortfolioContextStore()
    await context.changeContext({ currency: 'EUR' })
    expect(api.data.value).toBeNull()
    scope.stop()
  })

  it('runs nothing while the context cannot read or lacks date/currency', async () => {
    const { scope, api } = mountNavChart()
    const context = usePortfolioContextStore()
    const readyQuery = makeQuery()
    context.resetContext()
    const unready = await api.run(readyQuery)
    expect(unready.status).toBe('discarded')
    const nullDate = await api.run({
      ...readyQuery,
      context: {
        revision: 9, accountSelection: { type: 'all', id: null },
        effectiveCurrentDate: null, currency: null, digits: 2,
      } as NavQuery['context'],
    })
    expect(nullDate.status).toBe('discarded')
    expect(chartCalls).toHaveLength(0)
    scope.stop()
  })
})

describe('snapshotNavQuery immutability', () => {
  it('detaches and recursively freezes the captured query', () => {
    const query = makeQuery()
    const snapshot = snapshotNavQuery(query)
    expect(Object.isFrozen(snapshot)).toBe(true)
    expect(Object.isFrozen(snapshot.context)).toBe(true)
    expect(Object.isFrozen(snapshot.context.accountSelection)).toBe(true)
    query.context.currency = 'EUR'
    query.mode = 'account'
    query.frequency = 'Y'
    expect(snapshot.context.currency).toBe('USD')
    expect(snapshot.mode).toBe('none')
    expect(snapshot.frequency).toBe('M')
    expect(query.mode).toBe('account')
  })

  it('keeps the transport observing the snapshot after caller mutation', async () => {
    const { scope, api } = mountNavChart()
    const hold = deferred<{ data: unknown }>()
    respond = (call) => { expect(call.params.breakdown).toBe('none'); return hold.promise }
    const query = makeQuery()
    const pending = api.run(query)
    query.mode = 'asset_type'
    query.frequency = 'Q'
    hold.resolve({ data: successEnvelope() })
    expect((await pending).status).toBe('accepted')
    expect(chartCalls[0].params).toMatchObject({ breakdown: 'none', frequency: 'M' })
    scope.stop()
  })
})

describe('context mismatch reconciliation', () => {
  it('reconciles once for a current failed mismatch through the existing store', async () => {
    const { scope, api } = mountNavChart()
    const context = usePortfolioContextStore()
    const spy = vi.spyOn(context, 'reconcileContext')
    respond = () => Promise.resolve({ data: mismatchEnvelope() })
    const failure = await api.run(makeQuery())
    expect(failure.status).toBe('failed')
    if (failure.status === 'failed') {
      expect(failure.error).toBeInstanceOf(ChartContextMismatchError)
    }
    await Promise.resolve()
    await Promise.resolve()
    expect(spy).toHaveBeenCalledTimes(1)
    expect(chartCalls).toHaveLength(1)
    scope.stop()
  })

  it('never reconciles twice in one divergence episode; success lifts the suppression', async () => {
    const { scope, api } = mountNavChart()
    const context = usePortfolioContextStore()
    const spy = vi.spyOn(context, 'reconcileContext')
    respond = () => Promise.resolve({ data: mismatchEnvelope() })
    await api.run(makeQuery())
    await Promise.resolve()
    await Promise.resolve()
    expect(spy).toHaveBeenCalledTimes(1)
    // Let the fired reconciliation finish before observing the episode.
    for (let attempt = 0; !context.canRead && attempt < 50; attempt++) await Promise.resolve()
    // The reconciliation refresh refetches and still mismatches (the fixture
    // keeps disagreeing): no second reconciliation may fire.
    const queries = chartCalls.length
    respond = () => Promise.resolve({ data: mismatchEnvelope() })
    await api.run(makeQuery())
    await Promise.resolve()
    await Promise.resolve()
    expect(spy).toHaveBeenCalledTimes(1)
    expect(chartCalls.length).toBe(queries + 1)
    // An accepted result resets the episode; a later mismatch reconciles again.
    respond = () => Promise.resolve({ data: successEnvelope() })
    await api.run(makeQuery())
    respond = () => Promise.resolve({ data: mismatchEnvelope() })
    await api.run(makeQuery())
    await Promise.resolve()
    await Promise.resolve()
    expect(spy).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('never reconcines for ordinary transport failures', async () => {
    const { scope, api } = mountNavChart()
    const context = usePortfolioContextStore()
    const spy = vi.spyOn(context, 'reconcileContext')
    respond = () => Promise.reject(new Error('plain failure'))
    const failure = await api.run(makeQuery())
    expect(failure.status).toBe('failed')
    expect(spy).not.toHaveBeenCalled()
    scope.stop()
  })

  it('ignores an old mismatch that lands after a newer query', async () => {
    const { scope, api } = mountNavChart()
    const context = usePortfolioContextStore()
    const spy = vi.spyOn(context, 'reconcileContext')
    const a = deferred<{ data: unknown }>()
    respond = () => a.promise
    const runA = api.run(makeQuery())
    respond = () => Promise.resolve({ data: successEnvelope() })
    await api.run(makeQuery({ frequency: 'W' }))
    a.resolve({ data: mismatchEnvelope() })
    expect((await runA).status).toBe('discarded')
    expect(spy).not.toHaveBeenCalled()
    scope.stop()
  })

  it('ignores a mismatch after unmount or logout', async () => {
    const unmountScope = effectScope()
    const unmounted = unmountScope.run(() => useNavChart())!
    unmountScope.stop()
    const hold = deferred<{ data: unknown }>()
    respond = () => hold.promise
    const context = usePortfolioContextStore()
    const spy = vi.spyOn(context, 'reconcileContext')
    const pending = unmounted.run(makeQuery())
    hold.resolve({ data: mismatchEnvelope() })
    const result = await pending
    expect(result.status).toBe('discarded')
    expect(spy).not.toHaveBeenCalled()

    const { scope, api } = mountNavChart()
    const logoutHold = deferred<{ data: unknown }>()
    respond = () => logoutHold.promise
    const logoutRun = api.run(makeQuery())
    usePortfolioContextStore().resetContext()
    logoutHold.resolve({ data: mismatchEnvelope() })
    expect((await logoutRun).status).toBe('discarded')
    expect(spy).not.toHaveBeenCalled()
    scope.stop()
  })
})
