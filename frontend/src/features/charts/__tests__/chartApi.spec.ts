// C2 Task 3: opt-in NAV transport. One GET with explicit v2 negotiation, a
// captured-context check (historical ranges stay valid: document
// effectiveDate equals query.toDate, not the committed effective date), and
// typed C1 error envelopes — exactly one network request in every case, no
// silent legacy fallback or retry.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { configureApiTransport } from '@/services/http/client'
import type { AxiosInstance } from 'axios'
import type { NavQuery } from '../contracts'
import { navFixture } from './fixtures'

vi.mock('@/services/api', () => { throw new Error('chartApi imported the broad legacy api facade') })
vi.mock('@/config/axiosConfig', () => { throw new Error('chartApi imported the legacy Axios config') })

import {
  ChartApiError,
  ChartContextMismatchError,
  fetchNavChart,
} from '../chartApi'

const clone = <T>(value: T): T => structuredClone(value)

const baseQuery: NavQuery = {
  context: {
    revision: 4,
    accountSelection: { type: 'account', id: 7 },
    effectiveCurrentDate: '2026-09-30',
    currency: 'USD',
    digits: 2,
  },
  mode: 'none',
  frequency: 'M',
  fromDate: '2026-01-01',
  toDate: '2026-01-31',
}

/** Fixture envelope whose v2 context matches baseQuery (incl. historical toDate). */
function v2Envelope(): ReturnType<typeof navFixture> {
  const envelope = clone(navFixture())
  envelope.chartV2.context = {
    accountSelection: { type: 'account', id: 7 },
    accountIds: [7, 9],
    effectiveDate: baseQuery.toDate,
    currency: 'USD',
    digits: 2,
  }
  return envelope
}

const transport = vi.fn()
beforeEach(() => {
  transport.mockReset()
  configureApiTransport({ get: transport } as unknown as AxiosInstance)
})

describe('fetchNavChart request shape', () => {
  it('issues exactly one GET with explicit v2 negotiation and the AbortSignal', async () => {
    transport.mockResolvedValue({ data: v2Envelope() })
    const controller = new AbortController()
    const result = await fetchNavChart(baseQuery, { signal: controller.signal })
    expect(transport).toHaveBeenCalledTimes(1)
    const [url, config] = transport.mock.calls[0]
    expect(url).toBe('/dashboard/api/get-nav-chart-data/')
    expect(config).toMatchObject({ signal: controller.signal })
    expect(config.params).toEqual({
      chart_contract: 2,
      breakdown: 'none',
      frequency: 'M',
      dateFrom: '2026-01-01',
      dateTo: '2026-01-31',
    })
    expect(result.capability).toBe('v2')
  })

  it.each(['none', 'account', 'asset_type', 'asset_class', 'currency', 'value_contributions', 'value_contributions_cumulative'] as const)(
    'negotiates mode %s verbatim',
    async (mode) => {
      transport.mockResolvedValue({ data: v2Envelope() })
      await fetchNavChart({ ...baseQuery, mode }, { signal: new AbortController().signal })
      expect(transport.mock.calls[0][1].params.breakdown).toBe(mode)
    },
  )

  it.each(['D', 'W', 'M', 'Q', 'Y'] as const)('negotiates frequency %s verbatim', async (frequency) => {
    transport.mockResolvedValue({ data: v2Envelope() })
    await fetchNavChart({ ...baseQuery, frequency }, { signal: new AbortController().signal })
    expect(transport.mock.calls[0][1].params.frequency).toBe(frequency)
  })

  it('preserves a nullable dateFrom for earliest-date semantics', async () => {
    transport.mockResolvedValue({ data: v2Envelope() })
    await fetchNavChart({ ...baseQuery, fromDate: null }, { signal: new AbortController().signal })
    expect(transport.mock.calls[0][1].params.dateFrom).toBeNull()
  })
})

describe('fetchNavChart responses', () => {
  it('returns legacy_only for an HTTP 200 envelope without chartV2', async () => {
    const legacyOnly = { labels: ['Jan-26'], datasets: [{ label: 'NAV', type: 'bar', data: [100] }], currency: 'USDk' }
    transport.mockResolvedValue({ data: clone(legacyOnly) })
    const result = await fetchNavChart(baseQuery, { signal: new AbortController().signal })
    expect(result).toEqual({ capability: 'legacy_only', legacy: legacyOnly })
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('returns the validated document beside the untouched legacy payload', async () => {
    const envelope = v2Envelope()
    transport.mockResolvedValue({ data: envelope })
    const result = await fetchNavChart(baseQuery, { signal: new AbortController().signal })
    if (result.capability !== 'v2') throw new Error('expected v2')
    expect(result.document.series[0].points[0].value).toBe('100000')
    expect(result.legacy.labels).toEqual(['Jan-26'])
    expect('chartV2' in result.legacy).toBe(false)
  })

  it('fails a malformed v2 envelope locally without a legacy retry', async () => {
    const broken = v2Envelope()
    ;(broken.chartV2 as { version: unknown }).version = 3
    transport.mockResolvedValue({ data: broken })
    await expect(fetchNavChart(baseQuery, { signal: new AbortController().signal })).rejects.toThrow(/chartV2|version/i)
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('maps the C1 400 INVALID_CHART_QUERY envelope to a typed non-retryable error', async () => {
    transport.mockRejectedValue({
      response: {
        status: 400,
        data: { error: { code: 'INVALID_CHART_QUERY', message: 'Unsupported chart frequency.', retryable: false } },
      },
    })
    const failure = await fetchNavChart(baseQuery, { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartApiError)
    expect(failure).toMatchObject({ code: 'INVALID_CHART_QUERY', status: 400, retryable: false })
    expect(failure.message).toBe('Unsupported chart frequency.')
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('maps the C1 500 CHART_CALCULATION_FAILED envelope to a typed retryable error', async () => {
    transport.mockRejectedValue({
      response: {
        status: 500,
        data: { error: { code: 'CHART_CALCULATION_FAILED', message: 'Chart data could not be calculated. Please try again.', retryable: true } },
      },
    })
    const failure = await fetchNavChart(baseQuery, { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartApiError)
    expect(failure).toMatchObject({ code: 'CHART_CALCULATION_FAILED', status: 500, retryable: true })
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('sanitizes credential-bearing nested C1 messages while preserving code/status/retryable', async () => {
    const leaked = 'request rejected: bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig'
    transport.mockRejectedValue({
      response: {
        status: 500,
        data: { error: { code: 'CHART_CALCULATION_FAILED', message: leaked, retryable: true } },
      },
    })
    const failure = await fetchNavChart(baseQuery, { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartApiError)
    expect(failure.message).not.toContain('eyJhbGciOiJIUzI1NiJ9')
    expect(failure.message).not.toContain('bearer')
    expect(failure).toMatchObject({ code: 'CHART_CALCULATION_FAILED', status: 500, retryable: true })
    expect(transport).toHaveBeenCalledTimes(1)
    const headerLeak = 'failed while refreshing: Authorization: Bearer abcdef123456'
    transport.mockRejectedValue({
      response: {
        status: 400,
        data: { error: { code: 'INVALID_CHART_QUERY', message: headerLeak, retryable: false } },
      },
    })
    const redacted = await fetchNavChart(baseQuery, { signal: new AbortController().signal }).catch((error) => error)
    expect(redacted).toBeInstanceOf(ChartApiError)
    expect(redacted.message).not.toContain('Bearer abcdef123456')
    expect(redacted).toMatchObject({ code: 'INVALID_CHART_QUERY', status: 400, retryable: false })
  })

  it('fails a malformed error body as a local non-retryable error, once', async () => {
    transport.mockRejectedValue({ response: { status: 500, data: { detail: 'Synthetic widget unavailable' } } })
    const failure = await fetchNavChart(baseQuery, { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartApiError)
    expect(failure.code).toBeUndefined()
    expect(failure.retryable).toBe(false)
    expect(transport).toHaveBeenCalledTimes(1)
  })

  it('propagates transport aborts untouched for the runner to discard', async () => {
    const abort = Object.assign(new Error('canceled'), { name: 'CanceledError', code: 'ERR_CANCELED' })
    transport.mockRejectedValue(abort)
    const controller = new AbortController()
    const pending = fetchNavChart(baseQuery, { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toBe(abort)
    expect(transport).toHaveBeenCalledTimes(1)
  })
})

describe('fetchNavChart captured-context check', () => {
  it('accepts a valid historical range whose effectiveDate equals toDate', async () => {
    transport.mockResolvedValue({ data: v2Envelope() })
    const result = await fetchNavChart(baseQuery, { signal: new AbortController().signal })
    expect(result.capability).toBe('v2')
    if (result.capability === 'v2') {
      expect(result.document.context.effectiveDate).toBe('2026-01-31')
      expect(baseQuery.context.effectiveCurrentDate).toBe('2026-09-30')
    }
  })

  it('accepts any authorized accountIds shape without reconstructing membership', async () => {
    const envelope = v2Envelope()
    envelope.chartV2.context.accountIds = [3, 12, 77]
    transport.mockResolvedValue({ data: envelope })
    const result = await fetchNavChart(baseQuery, { signal: new AbortController().signal })
    expect(result.capability).toBe('v2')
  })

  it.each([
    ['effectiveDate answering the committed date instead of toDate', (envelope: ReturnType<typeof v2Envelope>) => {
      envelope.chartV2.context.effectiveDate = '2026-09-30'
    }],
    ['wrong reporting currency', (envelope: ReturnType<typeof v2Envelope>) => {
      envelope.chartV2.context.currency = 'EUR'
      for (const series of envelope.chartV2.series) {
        if (series.unit.kind === 'money') (series.unit as { currency: string }).currency = 'EUR'
      }
    }],
    ['wrong digits', (envelope: ReturnType<typeof v2Envelope>) => {
      envelope.chartV2.context.digits = 4
    }],
    ['wrong account selection', (envelope: ReturnType<typeof v2Envelope>) => {
      envelope.chartV2.context.accountSelection = { type: 'all', id: null }
    }],
  ])('rejects a %s as a local context mismatch', async (_name, corrupt) => {
    const envelope = v2Envelope()
    corrupt(envelope)
    transport.mockResolvedValue({ data: envelope })
    const failure = await fetchNavChart(baseQuery, { signal: new AbortController().signal }).catch((error) => error)
    expect(failure).toBeInstanceOf(ChartContextMismatchError)
    expect(failure).not.toBeInstanceOf(ChartApiError)
    expect(transport).toHaveBeenCalledTimes(1)
  })
})
