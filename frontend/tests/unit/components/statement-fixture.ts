import type { ReconciledStatement, StatementAmount } from '@/services/api/dashboard'

// Shared statement fixture for Phase D statement specs. The numbers mirror
// the approved mock's synthetic arithmetic (100,000 - 5,000 net capital;
// 8,000 + 7,000 + 3,500 - 1,000 - 500 + 500 = 17,500; 95,000 + 17,500 =
// 112,500 NAV).

export function amount(
  display: string,
  overrides: Partial<StatementAmount> = {},
): StatementAmount {
  return { raw: '0', display, status: 'ok', ...overrides }
}

export function statementFixture(
  overrides: Partial<Record<string, unknown>> = {},
): ReconciledStatement {
  return {
    version: 2,
    kind: 'statement',
    context: {
      accountSelection: { type: 'all', id: null },
      accountIds: [1],
      effectiveDate: '2026-10-15',
      currency: 'USD',
      digits: 2,
    },
    status: 'complete',
    reasons: [],
    capital: {
      invested: amount('$100,000.00', { raw: '100000' }),
      cashOut: amount('($5,000.00)', { raw: '-5000' }),
      netInvestedCapital: amount('$95,000.00', { raw: '95000' }),
    },
    netResult: {
      nav: amount('$112,500.00', { raw: '112500' }),
      controlTotal: amount('$17,500.00', { raw: '17500' }),
      components: {
        realizedPrice: amount('$8,000.00', { raw: '8000' }),
        unrealizedPrice: amount('$7,000.00', { raw: '7000' }),
        income: amount('$3,500.00', { raw: '3500' }),
        fees: amount('($1,000.00)', { raw: '-1000' }),
        taxes: amount('($500.00)', { raw: '-500' }),
        fx: amount('$500.00', { raw: '500' }),
        otherFlows: amount('–', { raw: '0' }),
      },
      fxDetail: {
        security: amount('$500.00', { raw: '500' }),
        cashFlows: amount('–', { raw: '0' }),
      },
      attributedSum: amount('$17,500.00', { raw: '17500' }),
      unexplainedDifference: amount('–', { raw: '0' }),
      toleranceRaw: '0.04',
      toleranceBasis: 'half-ULP budget',
      reconciliation: 'reconciled',
    },
    returns: {
      totalReturn: { value: '0.175', display: '17.5%', status: 'ok', reason: 'observed' },
      irr: { value: '0.084', display: '8.4%', status: 'ok', reason: 'observed' },
    },
    diagnostics: {
      omittedValuations: [],
      unclassifiedInKindFlows: { present: false, count: 0 },
      notes: [],
    },
    ...overrides,
  } as ReconciledStatement
}
