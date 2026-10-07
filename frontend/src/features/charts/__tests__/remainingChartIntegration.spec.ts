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
import { allocationFixture } from './fixtures'
import { securityFixture as securityDocumentFixture } from './securityFixtures'
import { ChartContextMismatchError } from '../chartApi'
import { useBreakdownChart } from '../useBreakdownChart'
import { useSecurityDetail } from '@/features/securities/useSecurityDetail'
import { getChartOptions } from '@/config/chartConfig'
import DashboardPage from '@/views/DashboardPage.vue'
import SecurityDetailPage from '@/views/database/SecurityDetailPage.vue'
import { mount, flushPromises as flush } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as vuetifyComponents from 'vuetify/components'
import * as vuetifyDirectives from 'vuetify/directives'

// DashboardPage's summary widgets go through services/api (the broad axios
// instance); mock only those two functions and keep every other export real —
// the security transports stay on the configured shared transport.
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '1' } }),
  useRouter: () => ({ push: vi.fn() }),
  createRouter: () => ({ beforeEach() {}, afterEach() {}, onError() {} }),
  createWebHistory: () => ({}),
  RouterLink: { name: 'RouterLink', template: '<a><slot /></a>' },
  RouterView: { name: 'RouterView', template: '<div><slot /></div>' },
}))

const dashboardWidgets = vi.hoisted(() => ({
  getDashboardSummary: vi.fn(),
  getDashboardSummaryOverTime: vi.fn(),
  getSecurityDetail: vi.fn(),
  getSecurityTransactions: vi.fn(),
  getAccountChoices: vi.fn(),
}))
vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>()
  return {
    ...actual,
    getDashboardSummary: dashboardWidgets.getDashboardSummary,
    getDashboardSummaryOverTime: dashboardWidgets.getDashboardSummaryOverTime,
    // The security page's non-chart resources also ride the broad axios
    // instance; only the two chart histories stay on the shared transport.
    getSecurityDetail: dashboardWidgets.getSecurityDetail,
    getSecurityTransactions: dashboardWidgets.getSecurityTransactions,
    getAccountChoices: dashboardWidgets.getAccountChoices,
  }
})

vi.mock('@/config/chartConfig', () => ({
  getChartOptions: vi.fn(),
  colorPalette: ['#0F4C81', '#5C6B7A'],
}))
vi.mock('chartjs-adapter-date-fns', () => ({}))
// The dashboard section mounts the real BreakdownChart with the gated modern
// composition; both chart runtimes are stubbed at the wrapper boundary.
const pieState = vi.hoisted(() => ({ captured: [] as unknown[] }))
vi.mock('vue-chartjs', () => ({
  Bar: { name: 'Bar', template: '<div class="bar-stub" />' },
  Line: { name: 'Line', props: ['data', 'options'], template: '<div class="bar-stub" />' },
}))
vi.mock('vue-echarts', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: ['option', 'updateOptions', 'autoresize', 'theme'],
      setup(props: { option: Record<string, unknown> }) {
        pieState.captured.push(props)
        return () => h('div', { class: 'pie-stub' })
      },
    },
  }
})

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
  // The price history carries three observations so the plotted axis (with
  // the carry-forward endpoint) has four keys for the zoom-mapping cases.
  const document = securityDocumentFixture({
    kind,
    unit: kind === 'price' ? 'percent_of_nominal' : 'quantity',
    value: kind === 'price' ? '98.500000' : '0.000116590',
    points: kind === 'price'
      ? [
          { value: '98.125000', plotValue: '98.125000', status: 'ok', reason: 'observed', display: '98.125% of nominal' },
          { value: '98.500000', plotValue: '98.500000', status: 'ok', reason: 'observed', display: '98.5% of nominal' },
          { value: '99.125000', plotValue: '99.125000', status: 'ok', reason: 'observed', display: '99.125% of nominal' },
        ]
      : undefined,
  })
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
    legacy: kind === 'price'
      ? [
          { date: '2026-01-31', price: 98.125 },
          { date: '2026-01-31', price: 98.5 },
          { date: '2026-01-31', price: 99.125 },
        ]
      : [{ date: '2026-01-31', position: '0.000116590' }],
    chartV2: withContext,
  }
}

beforeEach(async () => {
  transportCalls = []
  respondBreakdown = null
  respondSecurity = null
  dashboardWidgets.getSecurityDetail.mockResolvedValue({
    id: 1, name: 'One', instrument_type: 'Stock', ISIN: 'ISIN-1',
    currency: 'USD', first_investment: '01-Jan-26', open_position: '1',
    current_value: '$1.00', realized: '–', unrealized: '–',
    capital_distribution: '$0.00', irr: 'NA',
  })
  dashboardWidgets.getSecurityTransactions.mockResolvedValue({ transactions: [], total_items: 0 })
  dashboardWidgets.getAccountChoices.mockResolvedValue({ options: [] })
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
      if (url === '/dashboard/api/get-nav-chart-data/') {
        return { data: { labels: [], datasets: [], currency: 'USDk' } }
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
    expect(detail.priceHistory.value).toEqual([
      { date: '2026-01-31', price: 98.125 },
      { date: '2026-01-31', price: 98.5 },
      { date: '2026-01-31', price: 99.125 },
    ])
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


describe('DashboardPage allocation wiring', () => {
  const vuetify = createVuetify({ components: vuetifyComponents, directives: vuetifyDirectives })

  async function mountDashboard() {
    const pinia = createPinia()
    await usePortfolioContextStore(pinia).reconcileContext()
    const wrapper = mount(DashboardPage, {
      global: {
        plugins: [vuetify, pinia],
        provide: { showError: vi.fn(), clearErrors: vi.fn() },
        stubs: {
          SummaryOverTimeTable: true,
          NAVChart: { template: '<div data-testid="nav-chart" />' },
        },
      },
    })
    // The pie renderer is an async component; settle its loader.
    for (let attempt = 0; attempt < 200; attempt += 1) {
      await flushPromises()
      await new Promise((resolve) => setTimeout(resolve, 10))
      if (
        pieState.captured.length >= 3 ||
        (wrapper.find('[data-testid="allocation-capability-notice"]').exists() &&
          wrapper.findAll('.bar-stub').length >= 3) ||
        wrapper.find('[data-testid="allocation-assetType-error"]').exists() ||
        wrapper.findAll('.bar-stub').length >= 3
      ) break
    }
    return wrapper
  }

  beforeEach(() => {
    pieState.captured = []
    respondBreakdown = null
    dashboardWidgets.getDashboardSummary.mockReset()
    dashboardWidgets.getDashboardSummaryOverTime.mockReset()
    dashboardWidgets.getDashboardSummary.mockResolvedValue({
      'Current NAV': '$1,000.00', Invested: '$900.00', 'Cash-out': '$0.00', total_return: '11.11%', irr: 'N/R',
    })
    dashboardWidgets.getDashboardSummaryOverTime.mockResolvedValue({ lines: [], years: [], currentYear: 2026 })
    dashboardWidgets.getSecurityDetail.mockReset()
    dashboardWidgets.getSecurityTransactions.mockReset()
    dashboardWidgets.getAccountChoices.mockReset()
  })

  it('keeps the incumbent cards and one negotiated request while the gate is off', async () => {
    // C5a: absent flags are the default-on candidate; the rollback path is
    // tested with an EXPLICIT all-false build configuration.
    vi.stubEnv('VITE_ALLOCATION_ECHARTS_ENABLED', 'false')
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'false')
    const breakdownCalls = () => transportCalls.filter((call) => call.url === '/dashboard/api/get-breakdown/')
    const wrapper = await mountDashboard()
    expect(breakdownCalls()).toHaveLength(1)
    expect(breakdownCalls()[0].params).toEqual({ chart_contract: 2 })
    expect(pieState.captured).toHaveLength(0)
    expect(wrapper.findAll('.bar-stub')).toHaveLength(3)
    expect(wrapper.find('[data-testid="allocation-capability-notice"]').exists()).toBe(false)
    wrapper.unmount()
    vi.unstubAllEnvs()
  }, 20000)

  it('renders one solid pie per card from the same request when the gate is on', async () => {
    vi.stubEnv('VITE_ALLOCATION_ECHARTS_ENABLED', 'true')
    try {
      const wrapper = await mountDashboard()
      const breakdownCalls = transportCalls.filter((call) => call.url === '/dashboard/api/get-breakdown/')
      expect(breakdownCalls).toHaveLength(1)
      expect(pieState.captured).toHaveLength(3)
      // v-window renders only the active tab: switch the first card to its
      // exact table and read the server-certified totals there.
      await wrapper.findAll('[data-testid^="allocation-"][data-testid$="-card"] .v-tab')[1].trigger('click')
      await flushPromises()
      const table = wrapper.get('[data-testid="allocation-data-table"]')
      expect(table.text()).toContain('USD 100.00')
      expect(table.text()).toContain('100.0%')
      expect(wrapper.find('[data-testid="allocation-capability-notice"]').exists()).toBe(false)
      wrapper.unmount()
    } finally {
      vi.unstubAllEnvs()
    }
  }, 20000)

  it('shows the legacy-only notice and incumbent bars for a legacy payload with the gate on', async () => {
    vi.stubEnv('VITE_ALLOCATION_ECHARTS_ENABLED', 'true')
    try {
      respondBreakdown = () => {
        const envelope = breakdownEnvelopeWithContext() as Record<string, unknown>
        delete envelope.chartV2
        return Promise.resolve({ data: envelope })
      }
      const wrapper = await mountDashboard()
      expect(wrapper.get('[data-testid="allocation-capability-notice"]').text()).toContain('legacy response')
      expect(pieState.captured).toHaveLength(0)
      expect(wrapper.findAll('.bar-stub')).toHaveLength(3)
      wrapper.unmount()
    } finally {
      vi.unstubAllEnvs()
    }
  }, 20000)

  it('surfaces a malformed breakdown document as an error with retry, never a downgrade', async () => {
    vi.stubEnv('VITE_ALLOCATION_ECHARTS_ENABLED', 'true')
    try {
      respondBreakdown = () => {
        const envelope = breakdownEnvelopeWithContext() as { chartV2: Record<string, unknown> }
        delete envelope.chartV2.assetClass
        return Promise.resolve({ data: envelope })
      }
      const wrapper = await mountDashboard()
      expect(wrapper.get('[data-testid="allocation-assetType-error"]').text()).toContain('Invalid chartV2 document')
      expect(wrapper.find('[data-testid="allocation-capability-notice"]').exists()).toBe(false)
      expect(transportCalls.filter((call) => call.url === '/dashboard/api/get-breakdown/')).toHaveLength(1)
      await wrapper.get('[data-testid="allocation-assetType-retry"]').trigger('click')
      await flushPromises()
      expect(transportCalls.filter((call) => call.url === '/dashboard/api/get-breakdown/')).toHaveLength(2)
      wrapper.unmount()
    } finally {
      vi.unstubAllEnvs()
    }
  }, 20000)
})


describe('SecurityDetailPage security-history wiring', () => {
  const securityVuetify = createVuetify({ components: vuetifyComponents, directives: vuetifyDirectives })

  beforeEach(() => {
    // The shared VChart mock state must not leak from the dashboard describe
    // (harmless while every gate was default-off, load-bearing under the C5a
    // default-on candidate).
    pieState.captured = []
    respondSecurity = null
  })

  async function mountSecurityPage() {
    const pinia = createPinia()
    await usePortfolioContextStore(pinia).reconcileContext()
    const wrapper = mount(SecurityDetailPage, {
      global: {
        plugins: [securityVuetify, pinia],
        provide: { showError: vi.fn(), clearErrors: vi.fn() },
        stubs: {
          SecurityActivity: true,
        },
      },
    })
    // The history renderer is an async component; settle its loader.
    for (let attempt = 0; attempt < 200; attempt += 1) {
      await flush()
      await new Promise((resolve) => setTimeout(resolve, 10))
      if (
        pieState.captured.length >= 2 ||
        wrapper.findAll('.bar-stub').length >= 2
      ) break
    }
    return wrapper
  }

  it('keeps the incumbent charts with the gate off, one negotiated request per history', async () => {
    // C5a: the rollback path is an explicit false, not an absent flag.
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'false')
    const before = pieState.captured.length
    const wrapper = await mountSecurityPage()
    const priceCalls = transportCalls.filter((call) => call.url.endsWith('/price-history/'))
    const positionCalls = transportCalls.filter((call) => call.url.endsWith('/position-history/'))
    expect(priceCalls).toHaveLength(1)
    expect(positionCalls).toHaveLength(1)
    expect(pieState.captured.length).toBe(before)
    expect(wrapper.findAll('.bar-stub').length).toBeGreaterThanOrEqual(2)
    expect(wrapper.find('[data-testid="security-data-table"]').exists()).toBe(false)
    wrapper.unmount()
    vi.unstubAllEnvs()
  }, 20000)

  it('renders both modern histories from the same negotiated results with the gate on', async () => {
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'true')
    try {
      const wrapper = await mountSecurityPage()
      const priceCalls = transportCalls.filter((call) => call.url.endsWith('/price-history/'))
      const positionCalls = transportCalls.filter((call) => call.url.endsWith('/position-history/'))
      expect(priceCalls).toHaveLength(1)
      expect(positionCalls).toHaveLength(1)
      expect(pieState.captured.length).toBe(2)
      const tables = wrapper.findAll('[data-testid="security-data-table"]')
      expect(tables).toHaveLength(2)
      expect(tables[0].text()).toContain('98.5% of nominal')
      expect(tables[1].text()).toContain('0.000116590')
      wrapper.unmount()
    } finally {
      vi.unstubAllEnvs()
    }
  }, 20000)

  it('retains and reconciles security zoom through the page interaction state', async () => {
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'true')
    try {
      const wrapper = await mountSecurityPage()
      const chartStub = wrapper.findAllComponents({ name: 'VChart' })[0]
      // The stock price axis: three observed points plus the carry-forward
      // endpoint (four plotted keys). 34%/67% map to row:2 and row:3.
      chartStub.vm.$emit('datazoom', { start: 34, end: 67 })
      await flush()
      await flush()
      const option = chartStub.props('option') as { dataZoom: Array<{ start: number; end: number }> }
      expect(option.dataZoom[0].start).toBeCloseTo(33.33, 1)
      expect(option.dataZoom[0].end).toBeCloseTo(66.67, 1)
      // A real data refresh re-reads every history; once the replacement
      // responses land, the zoom survives on the re-rendered chart.
      const priceBefore = transportCalls.filter((call) => call.url.endsWith('/price-history/')).length
      usePortfolioContextStore().triggerDataRefresh()
      await flush()
      await flush()
      await flush()
      expect(transportCalls.filter((call) => call.url.endsWith('/price-history/')).length).toBe(priceBefore + 1)
      const refreshed = wrapper.findAllComponents({ name: 'VChart' })[0]
      expect((refreshed.props('option') as { dataZoom: Array<{ start: number; end: number }> }).dataZoom[0].start).toBeCloseTo(33.33, 1)
      expect((refreshed.props('option') as { dataZoom: Array<{ start: number; end: number }> }).dataZoom[0].end).toBeCloseTo(66.67, 1)
      wrapper.unmount()
    } finally {
      vi.unstubAllEnvs()
    }
  }, 20000)

  it('resets the interaction when a context reset clears the chart document', async () => {
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'true')
    try {
      const wrapper = await mountSecurityPage()
      const chartStub = wrapper.findAllComponents({ name: 'VChart' })[0]
      chartStub.vm.$emit('datazoom', { start: 34, end: 67 })
      await flush()
      await flush()
      expect((chartStub.props('option') as { dataZoom: Array<{ start: number }> }).dataZoom[0].start).toBeCloseTo(33.33, 1)
      // A context event invalidates the documents (they briefly disappear);
      // the reset must not crash on the null document and must not carry
      // the zoom into the replacement documents.
      const context = usePortfolioContextStore()
      await context.changeContext({ effectiveCurrentDate: '2026-09-30' })
      await flush()
      await flush()
      await flush()
      const interaction = wrapper.findComponent({ name: 'EChartsSecurity' })?.props('interaction') as { viewport: unknown }
      expect(interaction.viewport).toBeNull()
      const refreshed = wrapper.findAllComponents({ name: 'VChart' })[0]
      expect((refreshed.props('option') as { dataZoom: Array<{ start: number }> }).dataZoom[0].start).toBe(0)
      wrapper.unmount()
    } finally {
      vi.unstubAllEnvs()
    }
  }, 20000)

  it('restores the loading skeleton while a period change is pending', async () => {
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'true')
    try {
      const wrapper = await mountSecurityPage()
      expect(wrapper.findAll('[data-testid="security-data-table"]')).toHaveLength(2)
      // Park the next history responses so the period change stays pending.
      const deferreds: Array<{ kind: 'price' | 'position'; resolve: () => void }> = []
      respondSecurity = (call) => {
        const kind: 'price' | 'position' = call.url.endsWith('/price-history/') ? 'price' : 'position'
        return new Promise((resolve) => {
          deferreds.push({ kind, resolve: () => resolve({ data: securityWire(kind) }) })
        })
      }
      const allButton = wrapper.findAll('button').find((button) => button.text() === 'All')
      expect(allButton).toBeTruthy()
      await allButton!.trigger('click')
      await flush()
      // While the histories are pending the section shows the incumbent
      // loading treatment and no stale chart or table.
      expect(wrapper.findAll('.v-skeleton-loader').length).toBeGreaterThan(0)
      expect(wrapper.findAll('[data-testid="security-data-table"]')).toHaveLength(0)
      for (const deferred of deferreds) deferred.resolve()
      await flush()
      await flush()
      expect(wrapper.findAll('[data-testid="security-data-table"]')).toHaveLength(2)
      expect(wrapper.findAll('.v-skeleton-loader').length).toBe(0)
      wrapper.unmount()
    } finally {
      vi.unstubAllEnvs()
    }
  }, 20000)
})
