import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/services/http/errors'
import { configureApiTransport } from '@/services/http/client'
import {
  getDashboardSummaryV2,
  SummaryContextMismatchError,
} from '@/services/api/dashboard'
import { statementFixture } from './statement-fixture'
import type { ReconciledStatement } from '@/services/api/dashboard'

// Typed-boundary tests for the negotiated summary document: these exercise
// the REAL decoders through a stubbed axios transport. A present-but-invalid
// summaryV2 must throw (never a silent downgrade); a legacy-only payload
// (older backend ignoring the parameter) degrades explicitly; the document
// context must match the captured request context or the response is a
// mismatch, never rendered.

const legacyFive = {
  'Current NAV': '$112,500.00',
  Invested: '$100,000.00',
  'Cash-out': '($5,000.00)',
  total_return: '17.5%',
  irr: '8.4%',
}

const capturedContext = {
  accountSelection: { type: 'all', id: null },
  effectiveCurrentDate: '2026-10-15',
  currency: 'USD',
  digits: 2,
} as const

function transportReturning(payload: unknown) {
  return {
    get: vi.fn(async () => ({ data: payload })),
    post: vi.fn(),
  }
}

function brokenStatement(mutate: (statement: ReconciledStatement) => void): unknown {
  const statement = statementFixture()
  mutate(statement)
  return { ...legacyFive, summaryV2: statement }
}

async function expectRejected(payload: unknown, message?: RegExp) {
  configureApiTransport(transportReturning(payload) as never)
  const promise = getDashboardSummaryV2(capturedContext)
  await expect(promise).rejects.toBeInstanceOf(ApiError)
  if (message) await expect(promise).rejects.toThrow(message)
}

afterEach(() => {
  configureApiTransport(null)
})

describe('getDashboardSummaryV2 boundary', () => {
  it('sends the contract negotiation parameter and returns a decoded v2 document', async () => {
    const transport = transportReturning({
      ...legacyFive,
      summaryV2: statementFixture(),
    })
    configureApiTransport(transport as never)
    const result = await getDashboardSummaryV2(capturedContext)
    expect(transport.get).toHaveBeenCalledWith('/dashboard/api/get-summary/?summary_contract=2')
    expect(result.capability).toBe('v2')
    if (result.capability === 'v2') {
      expect(result.statement.netResult.nav.display).toBe('$112,500.00')
      expect(result.statement.context.digits).toBe(2)
    }
  })

  it('preserves valid high-precision raw strings verbatim', async () => {
    const statement = statementFixture()
    statement.netResult.components.income = {
      raw: '0.123456789012345',
      display: '$0.12',
      status: 'ok',
    }
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    const result = await getDashboardSummaryV2(capturedContext)
    if (result.capability === 'v2') {
      expect(result.statement.netResult.components.income.raw).toBe('0.123456789012345')
    } else {
      expect.unreachable('expected a v2 result')
    }
  })

  it('degrades explicitly to legacy-only when the server ignores the parameter', async () => {
    configureApiTransport(transportReturning(legacyFive) as never)
    const result = await getDashboardSummaryV2(capturedContext)
    expect(result.capability).toBe('legacy_only')
  })

  it('errors on a malformed legacy payload', async () => {
    await expectRejected({ 'Current NAV': 12 })
  })

  it.each([
    ['scientific notation raw', (s: ReconciledStatement) => {
      s.netResult.components.income = { raw: '1e5', display: '$100,000.00', status: 'ok' }
    }],
    ['NaN raw', (s: ReconciledStatement) => {
      s.netResult.components.fees = { raw: 'NaN', display: '($1.00)', status: 'ok' }
    }],
    ['Infinity raw', (s: ReconciledStatement) => {
      s.netResult.attributedSum = { raw: 'Infinity', display: '$1.00', status: 'ok' }
    }],
    ['non-numeric raw', (s: ReconciledStatement) => {
      s.netResult.components.income = { raw: 'abc', display: '$3,500.00', status: 'ok' }
    }],
    ['ok status with null raw', (s: ReconciledStatement) => {
      s.netResult.components.income = { raw: null, display: '$3,500.00', status: 'ok' }
    }],
    ['knownSubtotal on an ok amount', (s: ReconciledStatement) => {
      s.netResult.nav = { raw: '112500', display: '$112,500.00', status: 'ok', knownSubtotal: '1' }
    }],
    ['non-string reason', (s: ReconciledStatement) => {
      s.netResult.nav = { raw: '112500', display: '$112,500.00', status: 'partial', reason: 7 }
    }],
  ] as const)('rejects %s', async (_name, mutate) => {
    await expectRejected(brokenStatement(mutate))
  })

  it('permits partial amounts to carry a decimal knownSubtotal', async () => {
    const statement = statementFixture()
    statement.status = 'partial'
    statement.reasons = ['missing_fx']
    statement.netResult.nav = {
      raw: '110000',
      display: '$110,000.00',
      status: 'partial',
      reason: 'missing_fx',
      knownSubtotal: '110000',
    }
    statement.netResult.reconciliation = 'incomplete'
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    const result = await getDashboardSummaryV2(capturedContext)
    expect(result.capability).toBe('v2')
  })

  it.each([
    ['impossible calendar date', (s: ReconciledStatement) => {
      ;(s.context as unknown as Record<string, unknown>).effectiveDate = '2026-13-45'
    }],
    ['non-date effective date', (s: ReconciledStatement) => {
      ;(s.context as unknown as Record<string, unknown>).effectiveDate = 'not-a-date'
    }],
    ['fractional digits', (s: ReconciledStatement) => {
      ;(s.context as unknown as Record<string, unknown>).digits = 2.5
    }],
    ['negative digits', (s: ReconciledStatement) => {
      ;(s.context as unknown as Record<string, unknown>).digits = -1
    }],
    ['string digits', (s: ReconciledStatement) => {
      ;(s.context as unknown as Record<string, unknown>).digits = '2'
    }],
    ['unsupported selection type', (s: ReconciledStatement) => {
      ;(s.context as unknown as Record<string, unknown>).accountSelection = { type: 'bogus', id: 1 }
    }],
    ['fractional account id', (s: ReconciledStatement) => {
      ;(s.context as unknown as Record<string, unknown>).accountIds = [1.5]
    }],
    ['negative account id', (s: ReconciledStatement) => {
      ;(s.context as unknown as Record<string, unknown>).accountIds = [-3]
    }],
    ['non-numeric tolerance', (s: ReconciledStatement) => {
      ;(s.netResult as unknown as Record<string, unknown>).toleranceRaw = 'NaN'
    }],
    ['complete status with unreconciled outcome', (s: ReconciledStatement) => {
      ;(s as unknown as Record<string, unknown>).status = 'complete'
      ;(s.netResult as unknown as Record<string, unknown>).reconciliation = 'unreconciled'
    }],
    ['reconciled outcome with partial status', (s: ReconciledStatement) => {
      ;(s as unknown as Record<string, unknown>).status = 'partial'
      ;(s.netResult as unknown as Record<string, unknown>).reconciliation = 'reconciled'
    }],
    ['fractional in-kind count', (s: ReconciledStatement) => {
      ;(s.diagnostics as unknown as Record<string, unknown>).unclassifiedInKindFlows =
        { present: true, count: 1.5 }
    }],
  ] as const)('rejects %s', async (_name, mutate) => {
    await expectRejected(brokenStatement(mutate))
  })

  it('rejects malformed contract notes instead of silently filtering them', async () => {
    await expectRejected(brokenStatement((s) => {
      ;(s.diagnostics as unknown as Record<string, unknown>).notes = ['fine', 42]
    }))
  })

  it.each([
    ['ok return with a null value', (s: ReconciledStatement) => {
      s.returns.totalReturn = { value: null, display: '17.5%', status: 'ok', reason: 'observed' }
    }],
    ['terminal return with a value', (s: ReconciledStatement) => {
      s.returns.irr = { value: '0.084', display: 'N/A', status: 'not_available', reason: 'solver_unavailable' }
    }],
  ] as const)('rejects %s', async (_name, mutate) => {
    await expectRejected(brokenStatement(mutate))
  })

  // ---- context validation against the captured request (finding 3) ----

  it('rejects a mismatched effective date as a context mismatch', async () => {
    const statement = statementFixture()
    statement.context.effectiveDate = '2025-01-01'
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    await expect(getDashboardSummaryV2(capturedContext)).rejects.toBeInstanceOf(
      SummaryContextMismatchError,
    )
  })

  it('rejects a mismatched currency, selection and digits', async () => {
    for (const mutate of [
      (s: ReconciledStatement) => {
        s.context.currency = 'EUR'
      },
      (s: ReconciledStatement) => {
        s.context.accountSelection = { type: 'account', id: 42 }
      },
      (s: ReconciledStatement) => {
        s.context.digits = 3
      },
    ]) {
      const statement = statementFixture()
      mutate(statement)
      configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
      await expect(getDashboardSummaryV2(capturedContext)).rejects.toBeInstanceOf(
        SummaryContextMismatchError,
      )
      configureApiTransport(null)
    }
  })

  // ---- account-scope validation (round 3, finding 3) ----

  const accountCaptured = {
    accountSelection: { type: 'account', id: 11 },
    effectiveCurrentDate: '2026-10-15',
    currency: 'USD',
    digits: 2,
  } as const

  function withAccountScope(statement: ReconciledStatement): ReconciledStatement {
    statement.context.accountSelection = { type: 'account', id: 11 }
    statement.context.accountIds = [11]
    return statement
  }

  it('accepts an account selection whose resolved set is exactly the selection', async () => {
    const statement = withAccountScope(statementFixture())
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    const result = await getDashboardSummaryV2(accountCaptured)
    expect(result.capability).toBe('v2')
  })

  it('rejects account scope with a different resolved account', async () => {
    const statement = withAccountScope(statementFixture())
    statement.context.accountIds = [12]
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    await expect(getDashboardSummaryV2(accountCaptured)).rejects.toBeInstanceOf(
      SummaryContextMismatchError,
    )
  })

  it('rejects account scope with unexpected extra accounts', async () => {
    const statement = withAccountScope(statementFixture())
    statement.context.accountIds = [11, 12]
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    await expect(getDashboardSummaryV2(accountCaptured)).rejects.toBeInstanceOf(
      SummaryContextMismatchError,
    )
  })

  it('rejects account scope with duplicated account ids', async () => {
    // Duplicates are structurally invalid on any selection shape.
    const statement = withAccountScope(statementFixture())
    statement.context.accountIds = [11, 11]
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    await expect(getDashboardSummaryV2(accountCaptured)).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects duplicated account ids on any selection shape', async () => {
    const statement = statementFixture()
    statement.context.accountIds = [1, 1]
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    await expect(getDashboardSummaryV2(capturedContext)).rejects.toBeInstanceOf(ApiError)
  })

  // ---- cross-document status validation (round 3, finding 4) ----

  it.each([
    ['a partial NAV', (s: ReconciledStatement) => {
      s.netResult.nav = { raw: '1', display: '$1.00', status: 'partial', reason: 'missing_fx' }
    }],
    ['a partial component', (s: ReconciledStatement) => {
      s.netResult.components.fx = { raw: null, display: 'N/A', status: 'partial', reason: 'missing_fx' }
    }],
    ['omitted valuations', (s: ReconciledStatement) => {
      s.diagnostics.omittedValuations = [{ reason: 'missing_price', account_id: 1 }]
    }],
    ['declared unclassified in-kind dependencies', (s: ReconciledStatement) => {
      s.diagnostics.unclassifiedInKindFlows = { present: true, count: 2 }
    }],
    ['remaining reasons', (s: ReconciledStatement) => {
      s.reasons = ['missing_price']
    }],
    ['a negative tolerance', (s: ReconciledStatement) => {
      s.netResult.toleranceRaw = '-0.01'
    }],
    ['a partial amount without a reason', (s: ReconciledStatement) => {
      s.netResult.components.fees = { raw: '-1', display: '($1.00)', status: 'partial' }
    }],
  ] as const)('rejects complete/reconciled documents with %s', async (_name, mutate) => {
    await expectRejected(brokenStatement(mutate))
  })

  it('accepts legitimate unavailable returns on a certified statement', async () => {
    const statement = statementFixture()
    statement.returns.irr = {
      value: null, display: 'N/A', status: 'not_available', reason: 'solver_unavailable',
    }
    configureApiTransport(transportReturning({ ...legacyFive, summaryV2: statement }) as never)
    const result = await getDashboardSummaryV2(capturedContext)
    expect(result.capability).toBe('v2')
  })

  it('errors when the required captured context is missing', async () => {
    configureApiTransport(transportReturning({
      ...legacyFive,
      summaryV2: statementFixture(),
    }) as never)
    await expect(
      getDashboardSummaryV2(undefined as never),
    ).rejects.toBeInstanceOf(ApiError)
  })
})
