// C4 security-document fixtures grounded in the merged C1 wire authority
// (backend/services/charts.py build_security_price_document /
// build_security_position_document): server-issued row-key periods, exact
// decimal strings, instrument-specific units, and same-date position events
// kept under distinct server keys. Every call returns fresh objects.
import type { ChartDocument, ChartValue } from '../contracts'

export interface SecurityDocumentOverrides {
  kind?: 'price' | 'position'
  unit?: 'money' | 'percent_of_nominal' | 'quantity'
  value?: string
  points?: ChartValue[]
  periodKeys?: string[]
  contextEffectiveDate?: string
  seriesLabel?: string
  empty?: boolean
}

function point(value: string, display: string): ChartValue {
  return { value, plotValue: value, status: 'ok', reason: 'observed', display }
}

export function securityFixture(options: SecurityDocumentOverrides = {}): ChartDocument {
  const kind = options.kind ?? 'price'
  const unit = options.unit ?? (kind === 'position' ? 'quantity' : 'percent_of_nominal')
  const value = options.value ?? (kind === 'position' ? '0.000116590' : '98.500000')
  const effectiveDate = options.contextEffectiveDate ?? '2026-01-31'
  const instrumentType = unit === 'percent_of_nominal' ? 'Bond' : 'Stock'
  const unitObject =
    unit === 'money'
      ? ({ kind: 'money', currency: 'EUR', plotDivisor: '1' } as const)
      : unit === 'quantity'
        ? ({ kind: 'quantity', plotDivisor: '1' } as const)
        : ({ kind: 'percent_of_nominal', plotDivisor: '1' } as const)
  const display =
    unit === 'percent_of_nominal'
      ? `${value.replace(/0+$/, '').replace(/\.$/, '')}% of nominal`
      : unit === 'money'
        ? `€${value}`
        : value
  // Positions default to TWO same-date events under distinct server keys
  // (the backend keeps same-date transactions as separate ordered rows).
  const defaultPoints: ChartValue[] =
    kind === 'position' ? [point(value, display), point(value, display)] : [point(value, display)]
  const points = options.points ?? defaultPoints
  const periodKeys =
    options.periodKeys ??
    points.map((_entry, index) => `security:9:${kind}:row:${index + 1}`)
  const endDate = '2026-01-31'
  return {
    version: 2,
    kind,
    outcome: options.empty ? 'empty' : 'ready',
    context: {
      accountSelection: { type: 'all', id: null },
      accountIds: [],
      effectiveDate,
      currency: 'USD',
      digits: 2,
    },
    security: { id: 9, instrumentType },
    periods: options.empty
      ? []
      : periodKeys.map((key) => ({
          key,
          endDate,
          displayLabel: '31 Jan 2026',
          interval: { startDate: endDate, endDate, kind: 'sample_interval' },
          partialPeriod: false,
        })),
    series: [
      {
        id: `security:9:${kind}`,
        label: options.seriesLabel ?? (kind === 'price' ? 'Price' : 'Position'),
        metric: kind,
        role: 'line',
        axis: kind === 'price' ? 'price' : 'quantity',
        unit: unitObject,
        points: options.empty ? [] : points,
      },
    ],
    partition: 'complete',
  }
}

export function emptySecurityFixture(kind: 'price' | 'position' = 'price'): ChartDocument {
  return securityFixture({ kind, empty: true })
}
