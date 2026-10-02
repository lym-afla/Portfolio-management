// Synthetic chart-contract fixtures grounded in the merged C1 wire authority
// (`backend/tests/integration/api/test_chart_contract_v2.py` and
// `backend/tests/unit/services/test_chart_contract_values.py`): raw '100000',
// plot '100', both first-point IRRs '0.1234', period endpoint '2026-01-31',
// fixed decimal notation with meaningful trailing zeros. Every call returns
// fresh objects; no user portfolio data. Values are never recalculated here.
import type { ChartDocument, ChartSeries, ChartValue, LegacyNav } from '../contracts'

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
