// C4 Task 1: allocation/security transports and envelope parsing. One
// chart_contract=2 request per existing fetch — the breakdown endpoint keeps
// its single request for all three dimensions, the security owner keeps one
// request per history. A missing v2 field is explicit legacy_only; a present
// but malformed field is an error, never a silent downgrade. Decimal/display
// strings survive byte-for-byte; security contexts follow the security
// endpoints' own semantics (committed effective date, global selection;
// instrument currencies never compared against the reporting currency).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { configureApiTransport } from '@/services/http/client'
import type { AxiosInstance } from 'axios'
import type { ChartDocument, SecurityHistoryQuery } from '../contracts'
import { allocationFixture, securityFixture } from './fixtures'

vi.mock('@/services/api', () => { throw new Error('chartApi imported the broad legacy api facade') })
vi.mock('@/config/axiosConfig', () => { throw new Error('chartApi imported the legacy Axios config') })

import {
  ChartApiError,
  ChartContextMismatchError,
  fetchBreakdownChart,
  fetchSecurityHistory,
} from '../chartApi'
import { parseAllocationEnvelope, parseSecurityEnvelope } from '../parseChartEnvelope'
import {
  allocationEchartsRequested,
  securityEchartsRequested,
} from '../rendererPolicy'

const clone = <T>(value: T): T => structuredClone(value)

const breakdownContext = {
  revision: 6,
  accountSelection: { type: 'all', id: null },
  effectiveCurrentDate: '2026-01-31',
  currency: 'USD',
  digits: 2,
} as const

/** Backend-faithful breakdown envelope (legacy fields + three v2 documents). */
function allocationEnvelope(): Record<string, unknown> {
  return {
    assetType: { data: { Stocks: '$62.00', Bonds: '$18.00' }, percentage: { Stocks: '62%', Bonds: '18%' } },
    assetClass: { data: { Equity: '$70.00' }, percentage: { Equity: '70%' } },
    currency: { data: { USD: '$68.00', EUR: '$22.00' }, percentage: { USD: '68%', EUR: '22%' } },
    totalNAV: '$100.00',
    chartV2: {
      assetType: allocationFixture({ dimension: 'asset_type' }),
      assetClass: allocationFixture({ dimension: 'asset_class' }),
      currency: allocationFixture({ dimension: 'currency' }),
    },
  }
}

/** Price/position envelopes grounded in the security fixtures (security 9). */
function securityEnvelope(kind: 'price' | 'position'): Record<string, unknown> {
  if (kind === 'price') {
    return {
      legacy: [{ date: '2026-01-31', price: 98.5 }, { date: '2026-02-02', price: 99.125 }],
      chartV2: securityFixture('price', 'percent_of_nominal', '98.500000'),
    }
  }
  return {
    legacy: [{ date: '2026-01-31', position: '0.000116590' }],
    chartV2: securityFixture('position', 'quantity', '0.000116590'),
  }
}

function withContext(document: ChartDocument): ChartDocument {
  return {
    ...document,
    context: {
      accountSelection: breakdownContext.accountSelection,
      accountIds: [7],
      effectiveDate: breakdownContext.effectiveCurrentDate,
      currency: 'USD',
      digits: 2,
    },
  }
}

function allocationEnvelopeWithContext(): Record<string, unknown> {
  const envelope = clone(allocationEnvelope())
  const chartV2 = envelope.chartV2 as Record<string, ChartDocument>
  chartV2.assetType = withContext(chartV2.assetType)
  chartV2.assetClass = withContext(chartV2.assetClass)
  chartV2.currency = withContext(chartV2.currency)
  return envelope
}

function securityEnvelopeWithContext(
  kind: 'price' | 'position',
  accountIds: readonly number[] = [],
): Record<string, unknown> {
  const envelope = clone(securityEnvelope(kind))
  const document = envelope.chartV2 as ChartDocument
  envelope.chartV2 = {
    ...document,
    context: {
      accountSelection: { type: 'account', id: 7 },
      accountIds: [...accountIds],
      effectiveDate: '2026-02-02',
      currency: 'USD',
      digits: 2,
    },
  }
  return envelope
}

const transport = vi.fn()
beforeEach(() => {
  transport.mockReset()
  configureApiTransport({ get: transport } as unknown as AxiosInstance)
})

describe('parseAllocationEnvelope', () => {
  it('validates all three documents beside the untouched legacy payload', () => {
    const envelope = clone(allocationEnvelope())
    const before = clone(envelope)
    const result = parseAllocationEnvelope(envelope)
    expect(result.capability).toBe('v2')
    if (result.capability !== 'v2') return
    expect(result.documents.assetType.allocationSummary?.dimension).toBe('asset_type')
    expect(result.documents.assetClass.allocationSummary?.dimension).toBe('asset_class')
    expect(result.documents.currency.allocationSummary?.dimension).toBe('currency')
    expect(result.legacy.assetType.data).toEqual({ Stocks: '$62.00', Bonds: '$18.00' })
    expect(result.legacy.totalNAV).toBe('$100.00')
    expect(envelope).toEqual(before)
  })

  it('returns explicit legacy_only when chartV2 is absent', () => {
    const envelope = clone(allocationEnvelope())
    delete envelope.chartV2
    const result = parseAllocationEnvelope(envelope)
    expect(result).toMatchObject({ capability: 'legacy_only', legacy: { totalNAV: '$100.00' } })
  })

  it.each([
    ['null chartV2', (envelope: Record<string, unknown>) => { envelope.chartV2 = null }],
    ['malformed document metadata', (envelope: Record<string, unknown>) => {
      ;((envelope.chartV2 as Record<string, Record<string, unknown>>).assetType as { version: unknown }).version = 3
    }],
    ['wrong document kind', (envelope: Record<string, unknown>) => {
      ;((envelope.chartV2 as Record<string, Record<string, unknown>>).currency as { kind: unknown }).kind = 'nav'
    }],
    ['wrong dimension under its key', (envelope: Record<string, unknown>) => {
      ;(((envelope.chartV2 as Record<string, Record<string, unknown>>).assetType as { allocationSummary: { dimension: unknown } }).allocationSummary as { dimension: unknown }).dimension = 'currency'
    }],
    ['missing dimension key', (envelope: Record<string, unknown>) => {
      delete (envelope.chartV2 as Record<string, unknown>).assetClass
    }],
    ['unexpected extra dimension', (envelope: Record<string, unknown>) => {
      ;(envelope.chartV2 as Record<string, unknown>).broker = allocationFixture({ dimension: 'asset_type' })
    }],
    ['legacy data with non-string values', (envelope: Record<string, unknown>) => {
      ;((envelope.assetType as Record<string, unknown>).data as Record<string, unknown>).Stocks = 62
    }],
  ])('rejects %s instead of a silent downgrade', (_name, corrupt) => {
    const envelope = clone(allocationEnvelope())
    corrupt(envelope)
    expect(() => parseAllocationEnvelope(envelope)).toThrow(/chartV2|dimension|legacy/i)
  })
})

describe('parseSecurityEnvelope', () => {
  it('validates a price document beside its byte-identical legacy rows', () => {
    const envelope = clone(securityEnvelope('price'))
    const result = parseSecurityEnvelope(envelope, 'price')
    expect(result.capability).toBe('v2')
    if (result.capability !== 'v2') return
    expect(result.document.kind).toBe('price')
    expect(result.document.series[0].points[0]?.value).toBe('98.500000')
    expect(result.legacy).toEqual([{ date: '2026-01-31', price: 98.5 }, { date: '2026-02-02', price: 99.125 }])
  })

  it('validates a position document with exact quantity strings', () => {
    const envelope = clone(securityEnvelope('position'))
    const result = parseSecurityEnvelope(envelope, 'position')
    expect(result.capability).toBe('v2')
    if (result.capability !== 'v2') return
    expect(result.document.kind).toBe('position')
    expect(result.document.series[0].points[0]?.value).toBe('0.000116590')
    expect(result.legacy).toEqual([{ date: '2026-01-31', position: '0.000116590' }])
  })

  it('treats a bare legacy array as explicit legacy_only (pre-v2 wire)', () => {
    const bare = [{ date: '2025-06-01', price: 100 }]
    const result = parseSecurityEnvelope(clone(bare), 'price')
    expect(result).toEqual({ capability: 'legacy_only', legacy: bare })
  })

  it.each<[string, (envelope: Record<string, unknown>) => void, 'price' | 'position']>([
    ['null chartV2', (envelope: Record<string, unknown>) => { envelope.chartV2 = null }, 'price'],
    ['malformed document', (envelope: Record<string, unknown>) => {
      ;(envelope.chartV2 as { version: unknown }).version = 3
    }, 'price'],
    ['kind mismatch on the price endpoint', (envelope: Record<string, unknown>) => {
      envelope.chartV2 = securityFixture('position', 'quantity', '1')
    }, 'price'],
    ['object payload without chartV2', (envelope: Record<string, unknown>) => { delete envelope.chartV2 }, 'price'],
    ['price legacy row with a non-numeric price', (envelope: Record<string, unknown>) => {
      ;(envelope.legacy as Record<string, unknown>[])[0].price = '98.5'
    }, 'price'],
    ['position legacy row with a numeric position', (envelope: Record<string, unknown>) => {
      ;(envelope.legacy as Record<string, unknown>[])[0].position = 1.5
    }, 'position'],
  ])('rejects %s', (_name, corrupt, kind) => {
    const envelope = clone(securityEnvelope(kind))
    corrupt(envelope)
    expect(() => parseSecurityEnvelope(envelope, kind)).toThrow(/chartV2|legacy|kind|price|position/i)
  })
})

describe('fetchBreakdownChart', () => {
  const query = { context: breakdownContext }

  it('issues exactly one GET with chart_contract=2 and no per-dimension requests', async () => {
    transport.mockResolvedValue({ data: allocationEnvelopeWithContext() })
    const controller = new AbortController()
    const result = await fetchBreakdownChart(query, { signal: controller.signal })
    expect(transport).toHaveBeenCalledTimes(1)
    const [url, config] = transport.mock.calls[0]
    expect(url).toBe('/dashboard/api/get-breakdown/')
    expect(config).toMatchObject({ signal: controller.signal })
    expect(config.params).toEqual({ chart_contract: 2 })
    expect(result.capability).toBe('v2')
  })

  it('preserves large raw values and comma displays byte-for-byte', async () => {
    const envelope = allocationEnvelopeWithContext()
    const assetType = (envelope.chartV2 as Record<string, ChartDocument>).assetType
    const big: ChartDocument['series'][number]['points'][number] = {
      value: '9007199254740993.123456789',
      plotValue: '9007199254740993.123456789',
      status: 'ok',
      reason: 'observed',
      display: 'USD 9,007,199,254,740,993.123456789',
    }
    // Mutate the ranked allocation row in place so document consistency holds.
    const firstAllocation = assetType.allocations![0]
    assetType.series = assetType.series.map((series) =>
      series.id === firstAllocation.seriesId ? { ...series, points: [big] } : series,
    )
    assetType.allocations = assetType.allocations!.map((allocation) =>
      allocation.seriesId === firstAllocation.seriesId ? { ...allocation, amount: big } : allocation,
    )
    transport.mockResolvedValue({ data: envelope })
    const result = await fetchBreakdownChart(query, { signal: new AbortController().signal })
    if (result.capability !== 'v2') throw new Error('expected v2')
    const document = result.documents.assetType
    const row = document.allocations!.find((entry) => entry.seriesId === firstAllocation.seriesId)
    expect(row?.amount.value).toBe('9007199254740993.123456789')
    expect(row?.amount.display).toBe('USD 9,007,199,254,740,993.123456789')
    expect(result.legacy.assetType.data.Stocks).toBe('$62.00')
  })

  it('returns explicit legacy_only without a second request', async () => {
    const envelope = clone(allocationEnvelope())
    delete envelope.chartV2
    transport.mockResolvedValue({ data: envelope })
    const result = await fetchBreakdownChart(query, { signal: new AbortController().signal })
    expect(result.capability).toBe('legacy_only')
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('fails a malformed v2 payload without a legacy retry', async () => {
    const envelope = clone(allocationEnvelope())
    ;((envelope.chartV2 as Record<string, Record<string, unknown>>).currency as { kind: unknown }).kind = 'nav'
    transport.mockResolvedValue({ data: envelope })
    await expect(fetchBreakdownChart(query, { signal: new AbortController().signal })).rejects.toThrow(/kind|chartV2/i)
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['effective date answering a stale date', (envelope: Record<string, unknown>) => {
      for (const document of Object.values(envelope.chartV2 as Record<string, ChartDocument>)) {
        document.context.effectiveDate = '2025-12-31'
      }
    }],
    ['wrong reporting currency', (envelope: Record<string, unknown>) => {
      // Context and units must stay internally consistent for the document to
      // parse; the mismatch then fires against the committed USD context.
      for (const document of Object.values(envelope.chartV2 as Record<string, ChartDocument>)) {
        document.context = { ...document.context, currency: 'EUR' }
        document.series = document.series.map((series) => ({ ...series, unit: { kind: 'money', currency: 'EUR', plotDivisor: '1' } }))
        if (document.allocationSummary) {
          document.allocationSummary = {
            ...document.allocationSummary,
            unit: { kind: 'money', currency: 'EUR', plotDivisor: '1' },
          }
        }
      }
    }],
    ['wrong account selection', (envelope: Record<string, unknown>) => {
      for (const document of Object.values(envelope.chartV2 as Record<string, ChartDocument>)) {
        document.context = { ...document.context, accountSelection: { type: 'account', id: 3 } }
      }
    }],
  ])('rejects a %s as a context mismatch', async (_name, corrupt) => {
    const envelope = allocationEnvelopeWithContext()
    corrupt(envelope)
    transport.mockResolvedValue({ data: envelope })
    const failure = await fetchBreakdownChart(query, { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartContextMismatchError)
    expect(failure).not.toBeInstanceOf(ChartApiError)
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('maps the C1 error envelope to a typed retryable error, once', async () => {
    transport.mockRejectedValue({
      response: {
        status: 500,
        data: { error: { code: 'CHART_CALCULATION_FAILED', message: 'Breakdown could not be calculated. Please try again.', retryable: true } },
      },
    })
    const failure = await fetchBreakdownChart(query, { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartApiError)
    expect(failure).toMatchObject({ code: 'CHART_CALCULATION_FAILED', status: 500, retryable: true })
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('propagates transport aborts untouched', async () => {
    const abort = Object.assign(new Error('canceled'), { name: 'CanceledError', code: 'ERR_CANCELED' })
    transport.mockRejectedValue(abort)
    await expect(fetchBreakdownChart(query, { signal: new AbortController().signal })).rejects.toBe(abort)
  })
})

describe('fetchSecurityHistory', () => {
  const baseQuery: SecurityHistoryQuery = {
    context: {
      revision: 2,
      accountSelection: { type: 'account', id: 7 },
      effectiveCurrentDate: '2026-02-02',
      currency: 'USD',
      digits: 2,
    },
    securityId: 9,
    accountId: null,
    period: '1Y',
  }

  it('requests the price history with period only — never an account_id', async () => {
    transport.mockResolvedValue({ data: securityEnvelopeWithContext('price') })
    const controller = new AbortController()
    await fetchSecurityHistory({ ...baseQuery, accountId: 5 }, 'price', { signal: controller.signal })
    expect(transport).toHaveBeenCalledTimes(1)
    const [url, config] = transport.mock.calls[0]
    expect(url).toBe('/database/api/securities/9/price-history/')
    expect(config).toMatchObject({ signal: controller.signal })
    expect(config.params).toEqual({ chart_contract: 2, period: '1Y' })
  })

  it('requests the position history with the local account filter when selected', async () => {
    transport.mockResolvedValue({ data: securityEnvelopeWithContext('position', [5]) })
    await fetchSecurityHistory({ ...baseQuery, accountId: 5 }, 'position', { signal: new AbortController().signal })
    const [url, config] = transport.mock.calls[0]
    expect(url).toBe('/database/api/securities/9/position-history/')
    expect(config.params).toEqual({ chart_contract: 2, period: '1Y', account_id: 5 })
  })

  it('omits account_id for an all-accounts position query', async () => {
    transport.mockResolvedValue({ data: securityEnvelopeWithContext('position') })
    await fetchSecurityHistory(baseQuery, 'position', { signal: new AbortController().signal })
    expect(transport.mock.calls[0][1].params).toEqual({ chart_contract: 2, period: '1Y' })
  })

  it('keeps instrument money currency distinct from the reporting currency', async () => {
    const envelope = securityEnvelopeWithContext('price')
    const document = envelope.chartV2 as ChartDocument
    document.series = [{
      ...document.series[0],
      unit: { kind: 'money', currency: 'EUR', plotDivisor: '1' },
    }]
    transport.mockResolvedValue({ data: envelope })
    const result = await fetchSecurityHistory(baseQuery, 'price', { signal: new AbortController().signal })
    expect(result.capability).toBe('v2')
  })

  it.each([
    ['a position request for account 5 answering with account 7', 'position', 5, [7]],
    ['an all-accounts position request answering with a scoped document', 'position', null, [7]],
    ['a price request answering with any account scope', 'price', null, [7]],
  ] as const)('rejects %s as a context mismatch', async (_name, kind, accountId, accountIds) => {
    transport.mockResolvedValue({ data: securityEnvelopeWithContext(kind, accountIds) })
    const failure = await fetchSecurityHistory({ ...baseQuery, accountId }, kind, { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartContextMismatchError)
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('accepts a position document answering the exact local filter', async () => {
    transport.mockResolvedValue({ data: securityEnvelopeWithContext('position', [5]) })
    const result = await fetchSecurityHistory({ ...baseQuery, accountId: 5 }, 'position', { signal: new AbortController().signal })
    expect(result.capability).toBe('v2')
  })

  it('rejects a document answering for a different security identity', async () => {
    const envelope = securityEnvelopeWithContext('price')
    const document = envelope.chartV2 as ChartDocument
    document.security = { id: 12, instrumentType: 'Stock' }
    document.series = [{ ...document.series[0], id: 'security:12:price' }]
    document.periods = document.periods.map((period) => ({ ...period, key: period.key.replace('security:9:', 'security:12:') }))
    transport.mockResolvedValue({ data: envelope })
    const failure = await fetchSecurityHistory(baseQuery, 'price', { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartContextMismatchError)
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['stale effective date', (envelope: Record<string, unknown>) => {
      const document = envelope.chartV2 as ChartDocument
      document.context = { ...document.context, effectiveDate: '2026-01-01' }
    }],
    ['wrong global selection', (envelope: Record<string, unknown>) => {
      const document = envelope.chartV2 as ChartDocument
      document.context = { ...document.context, accountSelection: { type: 'all', id: null } }
    }],
  ])('rejects a %s as a context mismatch', async (_name, corrupt) => {
    const envelope = securityEnvelopeWithContext('price')
    corrupt(envelope)
    transport.mockResolvedValue({ data: envelope })
    const failure = await fetchSecurityHistory(baseQuery, 'price', { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartContextMismatchError)
  })

  it('returns explicit legacy_only for a bare-array legacy payload', async () => {
    transport.mockResolvedValue({ data: [{ date: '2025-06-01', price: 100 }] })
    const result = await fetchSecurityHistory(baseQuery, 'price', { signal: new AbortController().signal })
    expect(result).toMatchObject({ capability: 'legacy_only', legacy: [{ date: '2025-06-01', price: 100 }] })
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('maps the C1 error envelope and preserves its retryable metadata', async () => {
    transport.mockRejectedValue({
      response: {
        status: 500,
        data: { error: { code: 'CHART_CALCULATION_FAILED', message: 'Security price history could not be calculated.', retryable: true } },
      },
    })
    const failure = await fetchSecurityHistory(baseQuery, 'price', { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartApiError)
    expect(failure).toMatchObject({ code: 'CHART_CALCULATION_FAILED', retryable: true })
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('propagates transport aborts untouched', async () => {
    const abort = Object.assign(new Error('canceled'), { name: 'AbortError' })
    transport.mockRejectedValue(abort)
    await expect(fetchSecurityHistory(baseQuery, 'position', { signal: new AbortController().signal })).rejects.toBe(abort)
  })
})

describe('C4 renderer gates', () => {
  it('default both allocation and security gates off', () => {
    expect(allocationEchartsRequested()).toBe(false)
    expect(securityEchartsRequested()).toBe(false)
  })

  it('enables each gate only for the exact string true', () => {
    vi.stubEnv('VITE_ALLOCATION_ECHARTS_ENABLED', 'true')
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'true')
    expect(allocationEchartsRequested()).toBe(true)
    expect(securityEchartsRequested()).toBe(true)
    vi.stubEnv('VITE_ALLOCATION_ECHARTS_ENABLED', '1')
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'TRUE')
    expect(allocationEchartsRequested()).toBe(false)
    expect(securityEchartsRequested()).toBe(false)
    vi.unstubAllEnvs()
  })

  it('keeps the NAV pilot gate independent of the new flags', () => {
    vi.stubEnv('VITE_NAV_ECHARTS_ENABLED', 'true')
    vi.stubEnv('VITE_ALLOCATION_ECHARTS_ENABLED', 'true')
    vi.stubEnv('VITE_SECURITY_ECHARTS_ENABLED', 'true')
    expect(allocationEchartsRequested()).toBe(true)
    expect(securityEchartsRequested()).toBe(true)
    vi.unstubAllEnvs()
  })
})
