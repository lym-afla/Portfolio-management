import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/services/http/errors'
import { configureApiTransport } from '@/services/http/client'
import { getDashboardSummaryV2 } from '@/services/api/dashboard'
import { statementFixture } from './statement-fixture'

// Typed-boundary tests for the negotiated summary document: these exercise
// the REAL decoders through a stubbed axios transport. A present-but-invalid
// summaryV2 must throw (never a silent downgrade); a legacy-only payload
// (older backend ignoring the parameter) degrades explicitly.

function transportReturning(payload: unknown) {
  return {
    get: vi.fn(async () => ({ data: payload })),
    post: vi.fn(),
  }
}

afterEach(() => {
  configureApiTransport(null)
})

describe('getDashboardSummaryV2 boundary', () => {
  it('sends the contract negotiation parameter and returns a decoded v2 document', async () => {
    const statement = statementFixture()
    const legacy = {
      'Current NAV': '$112,500.00',
      Invested: '$100,000.00',
      'Cash-out': '($5,000.00)',
      total_return: '17.5%',
      irr: '8.4%',
    }
    const transport = transportReturning({ ...legacy, summaryV2: statement })
    configureApiTransport(transport as never)
    const result = await getDashboardSummaryV2()
    expect(transport.get).toHaveBeenCalledWith('/dashboard/api/get-summary/?summary_contract=2')
    expect(result.capability).toBe('v2')
    if (result.capability === 'v2') {
      expect(result.statement.netResult.nav.display).toBe('$112,500.00')
      expect(result.statement.context.digits).toBe(2)
    }
  })

  it('degrades explicitly to legacy-only when the server ignores the parameter', async () => {
    const legacy = {
      'Current NAV': '$1.00',
      Invested: '$1.00',
      'Cash-out': '$0.00',
      total_return: '0.0%',
      irr: 'N/R',
    }
    configureApiTransport(transportReturning(legacy) as never)
    const result = await getDashboardSummaryV2()
    expect(result.capability).toBe('legacy_only')
  })

  it('errors on a present-but-invalid v2 document instead of downgrading', async () => {
    const statement = statementFixture() as unknown as Record<string, unknown>
    const components = (statement.netResult as Record<string, unknown>).components as Record<
      string,
      unknown
    >
    components.income = { raw: '3500', display: '$3,500.00', status: 'somehow_broken' }
    const legacy = {
      'Current NAV': '$1.00',
      Invested: '$1.00',
      'Cash-out': '$0.00',
      total_return: '0.0%',
      irr: 'N/R',
    }
    configureApiTransport(transportReturning({ ...legacy, summaryV2: statement }) as never)
    await expect(getDashboardSummaryV2()).rejects.toBeInstanceOf(ApiError)
  })

  it('errors on a malformed legacy payload', async () => {
    configureApiTransport(transportReturning({ 'Current NAV': 12 }) as never)
    await expect(getDashboardSummaryV2()).rejects.toBeInstanceOf(ApiError)
  })

  it('validates the statement context and reconciliation enums', async () => {
    const statement = statementFixture() as unknown as Record<string, unknown>
    ;(statement.context as Record<string, unknown>).digits = '2'
    const legacy = {
      'Current NAV': '$1.00',
      Invested: '$1.00',
      'Cash-out': '$0.00',
      total_return: '0.0%',
      irr: 'N/R',
    }
    configureApiTransport(transportReturning({ ...legacy, summaryV2: statement }) as never)
    await expect(getDashboardSummaryV2()).rejects.toThrow(/context/)
  })
})
