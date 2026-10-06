// C4 Task 1 integration: the breakdown composable follows the C2/C3 NAV
// lifecycle (one request for all three documents, latest-wins, bounded
// mismatch reconciliation), and the D7 security owner negotiates the two
// histories through the shared transport while its characterized triggers,
// legacy projections and single-owner semantics stay untouched.
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import type { Ref } from 'vue'
import type { EffectScope } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { AxiosInstance } from 'axios'
import { configureApiTransport } from '@/services/http/client'
import { configureContextFixture } from '../../../../tests/unit/context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'
import { deferred } from '../../../../tests/unit/helpers/deferred'
import type { AllocationResult, ChartDocument } from '../contracts'
import { allocationFixture, securityFixture } from './fixtures'
import { ChartContextMismatchError } from '../chartApi'
import { useBreakdownChart } from '../useBreakdownChart'
import { useSecurityDetail } from '@/features/securities/useSecurityDetail'
import { getChartOptions } from '@/config/chartConfig'

vi.mock('@/config/chartConfig', () => ({
  getChartOptions: vi.fn(),
  colorPalette: ['#0F4C81', '#5C6B7A'],
}))
vi.mock('chartjs-adapter-date-fns', () => ({}))

type TransportCall = { url: string; params: Record<string, unknown>; signal: AbortSignal }

let transportCalls: TransportCall[] = []
let respondBreakdown: (() => Promise<{ data: unknown }>) | null = null
let respondSecurity: ((call: TransportCall) => Promise<{ data: unknown }>) | null = null

function allocationDocumentFor(dimension: 'asset_type' | 'asset_class' | 'currency'): ChartDocument {
  const document = allocationFixture({ dimension })
  return {
    ...document,
    context: {
      accountSelection: { type: 'all', id: null },
      accountIds: [7],
      effectiveDate: '2026-09-30',
      currency: 'USD',
      digits: 2,
    },
  }
}

function breakdownEnvelopeWithContext(): Record<string, unknown> {
  const assetType = allocationDocumentFor('asset_type')
  return {
    assetType: { data: { Stocks: '$62.00' }, percentage: { Stocks: '62%' } },
    assetClass: { data: { Equity: '$70.00' }, percentage: { Equity: '70%' } },
    currency: { data: { USD: '$68.00' }, percentage: { USD: '68%' } },
    totalNAV: '$100.00',
    chartV2: {
      assetType,
      assetClass: allocationDocumentFor('asset_class'),
      currency: allocationDocumentFor('currency'),
    },
  }
}

function mismatchBreakdownEnvelope(): Record<string, unknown> {
  const envelope = breakdownEnvelopeWithContext() as {
    chartV2: Record<string, { context: { effectiveDate: string } }>
  }
  for (const document of Object.values(envelope.chartV2)) {
    document.context.effectiveDate = '2026-01-31'
  }
  return envelope as Record<string, unknown>
}

function securityWire(
  kind: 'price' | 'position',
  corrupt?: (document: ChartDocument) => void,
): Record<string, unknown> {
  const document = securityFixture(
    kind,
    kind === 'price' ? 'percent_of_nominal' : 'quantity',
    kind === 'price' ? '98.500000' : '0.000116590',
  )
  // The owner queries the route security (id 1); retarget the fixture identity.
  const withContext: ChartDocument = {
    ...document,
    security: { id: 1, instrumentType: document.security?.instrumentType ?? 'Bond' },
    series: document.series.map((series) => ({ ...series, id: series.id.replace('security:9:', 'security:1:') })),
    periods: document.periods.map((period) => ({ ...period, key: period.key.replace('security:9:', 'security:1:') })),
    context: {
      accountSelection: { type: 'all', id: null },
      accountIds: [],
      effectiveDate: '2026-09-30',
      currency: 'USD',
      digits: 2,
    },
  }
  corrupt?.(withContext)
  return {
    legacy: kind === 'price' ? [{ date: '2026-01-31', price: 98.5 }] : [{ date: '2026-01-31', position: '0.000116590' }],
    chartV2: withContext,
  }
}

beforeEach(async () => {
  transportCalls = []
  respondBreakdown = null
  respondSecurity = null
  vi.mocked(getChartOptions).mockResolvedValue({ navChartOptions: {} } as Awaited<ReturnType<typeof getChartOptions>>)
  const pinia = createPinia()
  setActivePinia(pinia)
  configureContextFixture('2026-09-30')
  configureApiTransport({
    get: async (url: string, config?: { params?: Record<string, unknown>; signal?: AbortSignal }) => {
      const call = { url, params: config?.params ?? {}, signal: config?.signal as AbortSignal }
      if (url === '/dashboard/api/get-breakdown/') {
        transportCalls.push(call)
        return respondBreakdown ? respondBreakdown() : { data: breakdownEnvelopeWithContext() }
      }
      if (/\/database\/api\/securities\/\d+\/(price|position)-history\/$/.test(url)) {
        transportCalls.push(call)
        if (respondSecurity) return respondSecurity(call)
        const kind = url.includes('price-history') ? 'price' : 'position'
        return { data: securityWire(kind) }
      }
      if (/\/database\/api\/securities\/\d+\/$/.test(url)) {
        return {
          data: {
            id: 1, name: 'One', instrument_type: 'Stock', ISIN: 'ISIN-1',
            currency: 'USD', first_investment: '01-Jan-26', open_position: '1',
            current_value: '$1.00', realized: '–', unrealized: '–',
            capital_distribution: '$0.00', irr: 'NA',
          },
        }
      }
      if (/\/database\/api\/securities\/\d+\/transactions\/$/.test(url)) {
        return { data: { transactions: [], total_items: 0 } }
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

describe('useBreakdownChart lifecycle', () => {
  it('issues exactly one breakdown request carrying chart_contract=2 and accepts the three documents', async () => {
    const scope = effectScope()
    const api = scope.run(() => useBreakdownChart())!
    const context = usePortfolioContextStore()
    const result = await api.run({ context: context.committed as never })
    expect(transportCalls).toHaveLength(1)
    expect(transportCalls[0].url).toBe('/dashboard/api/get-breakdown/')
    expect(transportCalls[0].params).toEqual({ chart_contract: 2 })
    if (result.status !== 'accepted') throw new Error('expected acceptance')
    const data = result.data as AllocationResult
    expect(data.capability).toBe('v2')
    if (data.capability === 'v2') {
      expect(data.documents.assetType.kind).toBe('allocation')
      expect(data.legacy.totalNAV).toBe('$100.00')
    }
    scope.stop()
  })

  it('lets B win over a pending A even when the transport ignores abort', async () => {
    const scope = effectScope()
    const api = scope.run(() => useBreakdownChart())!
    const context = usePortfolioContextStore()
    const a = deferred<{ data: unknown }>()
    const b = deferred<{ data: unknown }>()
    respondBreakdown = () => a.promise
    const runA = api.run({ context: context.committed as never })
    respondBreakdown = () => b.promise
    const runB = api.run({ context: context.committed as never })
    b.resolve({ data: breakdownEnvelopeWithContext() })
    await runB.then((result) => expect(result.status).toBe('accepted'))
    a.resolve({ data: breakdownEnvelopeWithContext() })
    const lateA = await runA
    expect(lateA.status).toBe('discarded')
    expect(api.loading.value).toBe(false)
    expect((api.data.value as AllocationResult | null)?.capability).toBe('v2')
    expect(transportCalls).toHaveLength(2)
    scope.stop()
  })

  it('reconciles a current mismatch once per episode through the existing store', async () => {
    const scope = effectScope()
    const api = scope.run(() => useBreakdownChart())!
    const context = usePortfolioContextStore()
    const spy = vi.spyOn(context, 'reconcileContext')
    respondBreakdown = () => Promise.resolve({ data: mismatchBreakdownEnvelope() })
    const failure = await api.run({ context: context.committed as never })
    expect(failure.status).toBe('failed')
    if (failure.status === 'failed') {
      expect(failure.error).toBeInstanceOf(ChartContextMismatchError)
    }
    await Promise.resolve()
    await Promise.resolve()
    expect(spy).toHaveBeenCalledTimes(1)
    expect(transportCalls).toHaveLength(1)
    // Same disagreement again: still no second reconciliation in the episode.
    await api.run({ context: context.committed as never })
    await Promise.resolve()
    await Promise.resolve()
    expect(spy).toHaveBeenCalledTimes(1)
    // An accepted result lifts the suppression.
    respondBreakdown = null
    const accepted = await api.run({ context: context.committed as never })
    expect(accepted.status).toBe('accepted')
    respondBreakdown = () => Promise.resolve({ data: mismatchBreakdownEnvelope() })
    await api.run({ context: context.committed as never })
    await Promise.resolve()
    await Promise.resolve()
    expect(spy).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('discards runs after the owning scope is disposed', async () => {
    const scope = effectScope()
    const api = scope.run(() => useBreakdownChart())!
    const context = usePortfolioContextStore()
    scope.stop()
    const result = await api.run({ context: context.committed as never })
    expect(result.status).toBe('discarded')
    expect(transportCalls).toHaveLength(0)
  })
})

describe('useSecurityDetail over the v2 history transport', () => {
  const activeScopes: EffectScope[] = []
  afterEach(() => {
    for (const scope of activeScopes.splice(0)) scope.stop()
  })

  async function startOwner() {
    const pinia = setActivePinia(createPinia())
    const context = usePortfolioContextStore(pinia)
    await context.reconcileContext()
    useAppStore(pinia)
    const securityId = ref(1) as Ref<number>
    const refreshTick = ref(0)
    const scope = effectScope(true)
    const detail = scope.run(() =>
      useSecurityDetail({
        securityId: () => securityId.value,
        canRead: () => context.canRead,
        refreshTrigger: () => refreshTick.value,
        committed: () => context.committed,
      }),
    )
    if (!detail) throw new Error('owner scope did not run')
    activeScopes.push(scope)
    return { detail, securityId, refreshTick }
  }

  it('negotiates one v2 request per history and projects the characterized legacy rows', async () => {
    const { detail } = await startOwner()
    await flushPromises()
    const priceCalls = transportCalls.filter((call) => call.url.endsWith('/price-history/'))
    const positionCalls = transportCalls.filter((call) => call.url.endsWith('/position-history/'))
    expect(priceCalls).toHaveLength(1)
    expect(positionCalls).toHaveLength(1)
    expect(priceCalls[0].params).toEqual({ chart_contract: 2, period: '1Y' })
    expect(positionCalls[0].params).toEqual({ chart_contract: 2, period: '1Y' })
    // Legacy projections stay identical for the incumbent charts.
    expect(detail.priceHistory.value).toEqual([{ date: '2026-01-31', price: 98.5 }])
    expect(detail.positionHistory.value).toEqual([{ date: '2026-01-31', position: '0.000116590' }])
  })

  it('sends the local account filter to the position request only, on the next trigger', async () => {
    const { detail } = await startOwner()
    await flushPromises()
    detail.selectedAccount.value = { type: 'account', id: 7 }
    await flushPromises()
    const priceCalls = transportCalls.filter((call) => call.url.endsWith('/price-history/'))
    const positionCalls = transportCalls.filter((call) => call.url.endsWith('/position-history/'))
    expect(priceCalls).toHaveLength(2)
    expect(positionCalls).toHaveLength(2)
    for (const call of priceCalls) expect(call.params.account_id).toBeUndefined()
    expect(positionCalls[1].params.account_id).toBe(7)
    expect(positionCalls[1].params.period).toBe('1Y')
  })

  it('surfaces a history context mismatch as an owner error without reconciling or retrying', async () => {
    const { detail } = await startOwner()
    await flushPromises()
    expect(detail.loadError.value).toBeNull()
    const spy = vi.spyOn(usePortfolioContextStore(), 'reconcileContext')
    // The next price response disagrees with the committed effective date.
    respondSecurity = (call) => Promise.resolve({
      data: call.url.endsWith('/price-history/')
        ? securityWire('price', (document) => { document.context.effectiveDate = '2026-01-01' })
        : securityWire('position'),
    })
    detail.selectedPeriod.value = 'All'
    await flushPromises()
    expect(detail.loadError.value).toBeInstanceOf(ChartContextMismatchError)
    const priceCalls = transportCalls.filter((call) => call.url.endsWith('/price-history/'))
    const positionCalls = transportCalls.filter((call) => call.url.endsWith('/position-history/'))
    expect(priceCalls).toHaveLength(2)
    expect(positionCalls).toHaveLength(2)
    // Bounded: the owner never reconciles a security mismatch behind the
    // user's back — the error stays until an explicit retry.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(spy).not.toHaveBeenCalled()
  })
})
