// Synthetic chart-contract fixtures grounded in the merged C1 wire authority
// (`backend/tests/integration/api/test_chart_contract_v2.py` and
// `backend/tests/unit/services/test_chart_contract_values.py`): raw '100000',
// plot '100', both first-point IRRs '0.1234', period endpoint '2026-01-31',
// fixed decimal notation with meaningful trailing zeros. Every call returns
// fresh objects; no user portfolio data. Values are never recalculated here.
import type { ChartDocument, ChartPeriod, ChartSeries, ChartValue, LegacyNav } from '../contracts'

function point(value: string, plotValue: string, display: string): ChartValue {
  return { value, plotValue, display, status: 'ok', reason: 'observed' }
}

export function navFixture(): LegacyNav & { chartV2: ChartDocument } {
  const series: ChartSeries[] = [
    { id: 'metric:nav', label: 'NAV', metric: 'nav', role: 'bar', axis: 'money',
      unit: { kind: 'money', currency: 'USD', plotDivisor: '1000' },
      points: [point('100000', '100', 'USD 100,000.00')] },
    { id: 'metric:irr_inception', label: 'Since-inception IRR (annualized)',
      metric: 'irr_inception', role: 'line', axis: 'return',
      unit: { kind: 'ratio', plotDivisor: '1' }, points: [point('0.1234', '0.1234', '12.3%')] },
    { id: 'metric:irr_interval', label: 'Interval IRR (annualized)',
      metric: 'irr_interval', role: 'line', axis: 'return',
      unit: { kind: 'ratio', plotDivisor: '1' }, points: [point('0.1234', '0.1234', '12.3%')] },
  ]
  return {
    labels: ['Jan-26'], currency: 'USDk',
    datasets: [
      { label: 'NAV', type: 'bar', data: [100] },
      { label: 'IRR (RHS)', type: 'line', data: [0.1234] },
      { label: 'Rolling IRR (RHS)', type: 'line', data: [0.1234] },
    ],
    chartV2: {
      version: 2, kind: 'nav', outcome: 'ready', partition: 'complete',
      context: { accountSelection: { type: 'account', id: 7 }, accountIds: [7],
        effectiveDate: '2026-01-31', currency: 'USD', digits: 2 },
      periods: [{ key: 'nav:2026-01-31', endDate: '2026-01-31', displayLabel: 'Jan-26',
        interval: { startDate: null, endDate: '2026-01-31', kind: 'inception' }, partialPeriod: false }],
      series, totals: [point('100000', '100', 'USD 100,000.00')],
    },
  }
}

// Multi-period NAV fixture: the interval IRR carries a genuinely distinct
// value and horizon from the inception IRR, a category series exercises
// zero_exposure and absent_unclassified, and one endpoint is partial with a
// knownSubtotal. The 16-digit raw amount proves raw strings survive verbatim.
export function navSeriesFixture(): LegacyNav & { chartV2: ChartDocument } {
  const bigRaw = '9007199254740993.123456789'
  const unavailable = (status: 'unknown' | 'not_available', reason: ChartValue['reason'], display: string): ChartValue =>
    ({ value: null, plotValue: null, status, reason, display })
  const series: ChartSeries[] = [
    { id: 'metric:nav', label: 'NAV', metric: 'nav', role: 'bar', axis: 'money',
      unit: { kind: 'money', currency: 'USD', plotDivisor: '1000' },
      points: [
        point('100000', '100', '$100,000.00'),
        point(bigRaw, `${bigRaw}000`, 'USD 9,007,199,254,740,993.12'),
        { value: null, plotValue: null, knownSubtotal: '120000', status: 'partial',
          reason: 'missing_price', display: 'Partial NAV' },
      ] },
    { id: 'metric:irr_inception', label: 'IRR (RHS)', metric: 'irr_inception', role: 'line',
      axis: 'return', unit: { kind: 'ratio', plotDivisor: '1' },
      points: [point('0.1234', '0.1234', '12.3%'), point('0.2345', '0.2345', '23.5%'),
        point('0.3456', '0.3456', '34.6%')] },
    { id: 'metric:irr_interval', label: 'Rolling IRR (RHS)', metric: 'irr_interval', role: 'line',
      axis: 'return', unit: { kind: 'ratio', plotDivisor: '1' },
      points: [point('0.1234', '0.1234', '12.3%'), point('0.0567', '0.0567', '5.7%'),
        unavailable('not_available', 'solver_unavailable', 'N/A')] },
    { id: 'asset_type:Stock', label: 'Stock', metric: 'category_nav', role: 'bar',
      axis: 'money', unit: { kind: 'money', currency: 'USD', plotDivisor: '1000' },
      category: { kind: 'asset_type', code: 'Stock' },
      points: [point('40000', '40', '$40,000.00'),
        { value: '0', plotValue: '0', status: 'ok', reason: 'zero_exposure', display: '$0.00' },
        unavailable('unknown', 'absent_unclassified', '–')] },
  ]
  return {
    labels: ['Jan-26', 'Feb-26', '10-Mar-26'], currency: 'USDk',
    datasets: [
      { label: 'NAV', type: 'bar', yAxisID: 'y', data: [100, null, 120], backgroundColor: 'c1' },
      { label: 'IRR (RHS)', type: 'line', yAxisID: 'y1', data: [0.1234, 0.2345, 'N/A'], fill: false },
      { label: 'Rolling IRR (RHS)', type: 'line', yAxisID: 'y1', data: [0.1234, 0.0567, 'N/R'], fill: false },
      { label: 'Stock', type: 'bar', yAxisID: 'y', stack: 'combined', data: [40, 0, null],
        datalabels: { display: 'true' } },
    ],
    chartV2: {
      version: 2, kind: 'nav', outcome: 'partial', partition: 'complete',
      context: { accountSelection: { type: 'account', id: 7 }, accountIds: [7],
        effectiveDate: '2026-03-10', currency: 'USD', digits: 2 },
      periods: [
        { key: 'nav:2026-01-31', endDate: '2026-01-31', displayLabel: 'Jan-26',
          interval: { startDate: null, endDate: '2026-01-31', kind: 'inception' }, partialPeriod: false },
        { key: 'nav:2026-02-28', endDate: '2026-02-28', displayLabel: 'Feb-26',
          interval: { startDate: '2026-02-01', endDate: '2026-02-28', kind: 'sample_interval' }, partialPeriod: false },
        { key: 'nav:2026-03-10', endDate: '2026-03-10', displayLabel: '10-Mar-26',
          interval: { startDate: '2026-03-01', endDate: '2026-03-10', kind: 'sample_interval' }, partialPeriod: true },
      ],
      series,
      totals: [point('100000', '100', '$100,000.00'), point(bigRaw, `${bigRaw}000`, 'x'),
        { value: null, plotValue: null, knownSubtotal: '120000', status: 'partial',
          reason: 'missing_price', display: 'Partial NAV' }],
    },
  }
}

export function emptyNavFixture(): LegacyNav & { chartV2: ChartDocument } {
  return {
    labels: [], datasets: [], currency: 'USDk', empty: true,
    chartV2: {
      version: 2, kind: 'nav', outcome: 'empty', partition: 'complete',
      context: { accountSelection: { type: 'all', id: null }, accountIds: [],
        effectiveDate: '2026-01-31', currency: 'USD', digits: 2 },
      periods: [], series: [], totals: [],
    },
  }
}

// ---- Allocation documents (breakdown endpoint chartV2.<dimension>) --------
// Grounded in TestAllocationContractV2: amounts '25'/'75' against denominator
// '100', raw ratio shares '0.25'/'0.75', totalShare '1', money divisor '1'.
// The fixture never sums or recalculates; it pins the backend's certification.

export type AllocationFixtureDimension = 'asset_type' | 'asset_class' | 'currency'

const allocationCategories: Record<AllocationFixtureDimension, { code: string; amount: string; plot: string; share: string; amountDisplay: string; shareDisplay: string }[]> = {
  asset_type: [
    { code: 'Stock', amount: '25', plot: '25', share: '0.25', amountDisplay: 'USD 25.00', shareDisplay: '25.0%' },
    { code: 'Cash', amount: '75', plot: '75', share: '0.75', amountDisplay: 'USD 75.00', shareDisplay: '75.0%' },
  ],
  asset_class: [
    { code: 'Equity', amount: '25', plot: '25', share: '0.25', amountDisplay: 'USD 25.00', shareDisplay: '25.0%' },
    { code: 'Cash', amount: '75', plot: '75', share: '0.75', amountDisplay: 'USD 75.00', shareDisplay: '75.0%' },
  ],
  currency: [
    { code: 'USD', amount: '25', plot: '25', share: '0.25', amountDisplay: 'USD 25.00', shareDisplay: '25.0%' },
    { code: 'EUR', amount: '75', plot: '75', share: '0.75', amountDisplay: 'USD 75.00', shareDisplay: '75.0%' },
  ],
}

export interface AllocationFixtureOptions {
  dimension?: AllocationFixtureDimension
  pieEligibility?: 'eligible' | 'signed' | 'nonpositive_total' | 'incomplete' | 'nonpartitioning'
  partition?: 'complete' | 'legacy_non_partitioning' | 'unknown'
}

export function allocationFixture(options: AllocationFixtureOptions = {}): ChartDocument {
  const dimension = options.dimension ?? 'asset_type'
  const pieEligibility = options.pieEligibility ?? 'eligible'
  const partition = options.partition ?? 'complete'
  const rows = allocationCategories[dimension]
  const moneyUnit = { kind: 'money', currency: 'USD', plotDivisor: '1' } as const
  const ranked = [...rows].reverse() // Cash 75 first, Stock 25 second
  const amountFor = (row: (typeof rows)[number]): ChartValue => {
    if (pieEligibility === 'incomplete') {
      return row === rows[0]
        ? { value: null, plotValue: null, knownSubtotal: row.amount, status: 'partial', reason: 'missing_price', display: row.amountDisplay }
        : point(row.amount, row.plot, row.amountDisplay)
    }
    if (pieEligibility === 'signed' && row.code === 'Stock') {
      return { value: '-25', plotValue: '-25', status: 'ok', reason: 'observed', display: '(USD 25.00)' }
    }
    return point(row.amount, row.plot, row.amountDisplay)
  }
  const shareFor = (row: (typeof rows)[number]): ChartValue => {
    if (pieEligibility === 'incomplete') {
      return row === rows[0]
        ? { value: null, plotValue: null, status: 'unknown', reason: 'missing_price', display: '–' }
        : point('0.75', '0.75', '75.0%')
    }
    if (pieEligibility === 'signed' && row.code === 'Stock') {
      return point('-0.25', '-0.25', '-25.0%')
    }
    if (pieEligibility === 'nonpositive_total' || pieEligibility === 'nonpartitioning') {
      return { value: null, plotValue: null, status: 'not_available', reason: 'not_relevant', display: '–' }
    }
    return point(row.share, row.share, row.shareDisplay)
  }
  const denominator: ChartValue =
    pieEligibility === 'incomplete'
      ? { value: null, plotValue: null, knownSubtotal: '100', status: 'partial', reason: 'missing_price', display: 'USD 100.00' }
      : pieEligibility === 'nonpositive_total'
        ? point('0', '0', 'USD 0.00')
        : point('100', '100', 'USD 100.00')
  const totalShare: ChartValue =
    pieEligibility === 'eligible'
      ? point('1', '1', '100.0%')
      : pieEligibility === 'signed'
        ? point('1', '1', '100.0%')
        : { value: null, plotValue: null, status: 'not_available', reason: 'not_relevant', display: '–' }
  return {
    version: 2, kind: 'allocation',
    outcome: pieEligibility === 'incomplete' ? 'partial' : 'ready',
    partition,
    context: { accountSelection: { type: 'all', id: null }, accountIds: [7],
      effectiveDate: '2026-01-31', currency: 'USD', digits: 2 },
    periods: [{ key: `allocation:${dimension}:2026-01-31`, endDate: '2026-01-31',
      displayLabel: '31 Jan 2026',
      interval: { startDate: '2026-01-31', endDate: '2026-01-31', kind: 'sample_interval' },
      partialPeriod: false }],
    series: ranked.map((row) => ({
      id: `${dimension}:${row.code}`, label: row.code, metric: 'category_nav', role: 'bar',
      axis: 'money', unit: moneyUnit, points: [amountFor(row)],
      category: { kind: dimension, code: row.code },
    })),
    totals: [denominator],
    allocations: ranked.map((row, index) => ({
      seriesId: `${dimension}:${row.code}`, rank: index + 1,
      amount: amountFor(row), share: shareFor(row),
    })),
    allocationSummary: { dimension, unit: moneyUnit, denominator, totalShare, pieEligibility },
  }
}

// ---- Security documents (price/position histories) ------------------------
// Grounded in TestSecurityContractV2: bond price keeps the stored 6dp scale
// with percent_of_nominal; positions keep 9dp quantities and same-date events
// stay separate rows under distinct server keys.

export function securityFixture(
  kind: 'price' | 'position',
  unit: 'percent_of_nominal' | 'quantity' | 'money',
  value: string,
): ChartDocument {
  const base = navFixture().chartV2
  const security = { id: 9, instrumentType: unit === 'percent_of_nominal' ? 'Bond' : 'Stock' }
  const axis = kind === 'price' ? 'price' : 'quantity'
  const unitObject =
    unit === 'percent_of_nominal'
      ? { kind: 'percent_of_nominal', plotDivisor: '1' } as const
      : unit === 'quantity'
        ? { kind: 'quantity', plotDivisor: '1' } as const
        : { kind: 'money', currency: 'EUR', plotDivisor: '1' } as const
  const displayFor = () =>
    unit === 'percent_of_nominal' ? '98.5% of nominal' : unit === 'quantity' ? value : `€${value}`
  const periods: ChartPeriod[] =
    kind === 'price'
      ? [{ key: 'security:9:price:row:1', endDate: '2026-01-31', displayLabel: '31 Jan 2026',
          interval: { startDate: '2026-01-31', endDate: '2026-01-31', kind: 'sample_interval' }, partialPeriod: false }]
      : [ // Same-date position events stay separate ordered rows under distinct keys.
        { key: 'security:9:position:row:1', endDate: '2026-01-31', displayLabel: '31 Jan 2026',
          interval: { startDate: '2026-01-31', endDate: '2026-01-31', kind: 'sample_interval' }, partialPeriod: false },
        { key: 'security:9:position:row:2', endDate: '2026-01-31', displayLabel: '31 Jan 2026',
          interval: { startDate: '2026-01-31', endDate: '2026-01-31', kind: 'sample_interval' }, partialPeriod: false }]
  const points = [point(value, value, displayFor())]
  if (kind === 'position') {
    // An unavailable observation stays explicit; never a zero fill.
    points.push({ value: null, plotValue: null, status: 'not_available', reason: 'not_relevant', display: 'N/R' })
  }
  return {
    ...base, kind, totals: undefined, security,
    context: { ...base.context, currency: 'USD' },
    periods,
    series: [{
      id: `security:9:${kind}`, label: kind === 'price' ? 'Price' : 'Position',
      metric: kind, role: 'line', axis, unit: unitObject, points,
    }],
    partition: 'complete', outcome: 'ready',
  }
}

// Empty security histories keep their identified series with zero points
// (backend: build_security_price/position_document always emits the series).
export function emptySecurityFixture(kind: 'price' | 'position' = 'price'): ChartDocument {
  const base = navFixture().chartV2
  return {
    ...base, kind, outcome: 'empty', periods: [], totals: undefined,
    security: { id: 9, instrumentType: 'Bond' }, partition: 'complete',
    series: [{
      id: `security:9:${kind}`, label: kind === 'price' ? 'Price' : 'Position',
      metric: kind, role: 'line', axis: kind === 'price' ? 'price' : 'quantity',
      unit: kind === 'price'
        ? { kind: 'percent_of_nominal', plotDivisor: '1' }
        : { kind: 'quantity', plotDivisor: '1' },
      points: [],
    }],
  }
}
