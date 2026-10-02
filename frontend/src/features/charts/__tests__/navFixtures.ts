// Explicit synthetic NAV fixtures for the C3 pilot. Builders return RAW
// wire-shaped objects (typed unknown at the boundary) that must pass
// parseNavEnvelope — the same path real responses take. Values pin C1 rules:
// money value/plotValue ÷1000, raw-ratio IRRs, gaps never zero-filled,
// partial values carry knownSubtotal, period keys are server-issued even
// when display labels repeat. No user portfolio data; nothing is summed here.
import type { ChartDocument, ChartValue } from '../contracts'

export type FixtureMode =
  | 'none'
  | 'account'
  | 'asset_type'
  | 'asset_class'
  | 'currency'
  | 'value_contributions'
  | 'value_contributions_cumulative'
export type FixtureFrequency = 'D' | 'W' | 'M' | 'Q' | 'Y'

export const ALL_MODES: readonly FixtureMode[] = [
  'none', 'account', 'asset_type', 'asset_class', 'currency',
  'value_contributions', 'value_contributions_cumulative',
]
export const ALL_FREQUENCIES: readonly FixtureFrequency[] = ['D', 'W', 'M', 'Q', 'Y']

const ok = (value: string, plotValue: string, display: string): ChartValue =>
  ({ value, plotValue, status: 'ok', reason: 'observed', display })
const partial = (subtotal: string, display: string): ChartValue =>
  ({ value: null, plotValue: null, knownSubtotal: subtotal, status: 'partial', reason: 'missing_price', display })
const absent = (): ChartValue =>
  ({ value: null, plotValue: null, status: 'unknown', reason: 'absent_unclassified', display: '–' })
const na = (): ChartValue =>
  ({ value: null, plotValue: null, status: 'not_available', reason: 'solver_unavailable', display: 'N/A' })

const iso = (date: Date) => date.toISOString().slice(0, 10)
const plusDays = (isoDate: string, days: number) => {
  const date = new Date(`${isoDate}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return iso(date)
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const dayLabel = (isoDate: string) => {
  const date = new Date(`${isoDate}T00:00:00Z`)
  const dd = String(date.getUTCDate()).padStart(2, '0')
  const mon = MONTHS[date.getUTCMonth()].slice(0, 3)
  const yy = String(date.getUTCFullYear()).slice(2)
  return `${dd}-${mon}-${yy}`
}

interface FixturePeriod {
  key: string
  endDate: string
  displayLabel: string
  intervalStart: string | null
  partialPeriod: boolean
}

/** Frequency-plausible endpoints with one trailing calendar-partial bucket. */
function fixturePeriods(frequency: FixtureFrequency, count = 3): FixturePeriod[] {
  const endDates: string[] = []
  const partials: boolean[] = []
  if (frequency === 'D') {
    for (let index = 0; index < count; index += 1) {
      endDates.push(plusDays('2026-09-22', index))
      partials.push(false)
    }
  } else if (frequency === 'W') {
    for (let index = 0; index < count; index += 1) endDates.push(plusDays('2026-09-05', index * 7)), partials.push(false)
    endDates.push('2026-09-29'), partials.push(true) // mid-week endpoint
  } else if (frequency === 'M') {
    endDates.push('2026-06-30', '2026-07-31', '2026-08-31'), partials.push(false, false, false)
    endDates.push('2026-09-10'), partials.push(true) // mid-month endpoint
  } else if (frequency === 'Q') {
    endDates.push('2026-03-31', '2026-06-30'), partials.push(false, false)
    endDates.push('2026-09-10'), partials.push(true)
  } else {
    endDates.push('2024-12-31', '2025-12-31'), partials.push(false, false)
    endDates.push('2026-06-30'), partials.push(true)
  }
  return endDates.map((endDate, index) => ({
    key: `nav:${endDate}${index}`,
    endDate,
    displayLabel:
      frequency === 'M' ? `${MONTHS[new Date(`${endDate}T00:00:00Z`).getUTCMonth()]}-${String(new Date(`${endDate}T00:00:00Z`).getUTCFullYear()).slice(2)}`
        : frequency === 'Q' ? `Q${Math.floor(new Date(`${endDate}T00:00:00Z`).getUTCMonth() / 3) + 1} ${String(new Date(`${endDate}T00:00:00Z`).getUTCFullYear()).slice(2)}`
          : frequency === 'Y' ? String(new Date(`${endDate}T00:00:00Z`).getUTCFullYear())
            : dayLabel(endDate),
    intervalStart: index === 0 ? null : plusDays(endDates[index - 1], 1),
    partialPeriod: partials[index],
  }))
}

interface FixtureSeriesSpec {
  id: string
  label: string
  metric: string
  role: 'bar' | 'line'
  axis: 'money' | 'return'
  category?: { kind: string; code?: string; memberAccountIds?: number[] }
}

function modeSeries(mode: FixtureMode): FixtureSeriesSpec[] {
  const irrs: FixtureSeriesSpec[] = [
    { id: 'metric:irr_inception', label: 'IRR (RHS)', metric: 'irr_inception', role: 'line', axis: 'return' },
    { id: 'metric:irr_interval', label: 'Rolling IRR (RHS)', metric: 'irr_interval', role: 'line', axis: 'return' },
  ]
  switch (mode) {
    case 'none':
      return [{ id: 'metric:nav', label: 'NAV', metric: 'nav', role: 'bar', axis: 'money' }, ...irrs]
    case 'account':
      return [
        { id: 'account-group:3,7', label: 'Alpha Prime', metric: 'category_nav', role: 'bar', axis: 'money', category: { kind: 'account_group', memberAccountIds: [3, 7] } },
        { id: 'account-group:9', label: 'Alpha Prime', metric: 'category_nav', role: 'bar', axis: 'money', category: { kind: 'account_group', memberAccountIds: [9] } },
        ...irrs,
      ]
    case 'asset_type':
      return [
        { id: 'asset_type:Stock', label: 'Stock', metric: 'category_nav', role: 'bar', axis: 'money', category: { kind: 'asset_type', code: 'Stock' } },
        { id: 'asset_type:Cash', label: 'Cash', metric: 'category_nav', role: 'bar', axis: 'money', category: { kind: 'asset_type', code: 'Cash' } },
        ...irrs,
      ]
    case 'asset_class':
      return [
        { id: 'asset_class:Equity', label: 'Equity', metric: 'category_nav', role: 'bar', axis: 'money', category: { kind: 'asset_class', code: 'Equity' } },
        { id: 'asset_class:Cash', label: 'Cash', metric: 'category_nav', role: 'bar', axis: 'money', category: { kind: 'asset_class', code: 'Cash' } },
        ...irrs,
      ]
    case 'currency':
      return [
        { id: 'currency:USD', label: 'USD', metric: 'category_nav', role: 'bar', axis: 'money', category: { kind: 'currency', code: 'USD' } },
        { id: 'currency:EUR', label: 'EUR', metric: 'category_nav', role: 'bar', axis: 'money', category: { kind: 'currency', code: 'EUR' } },
        ...irrs,
      ]
    case 'value_contributions':
      return [
        { id: 'metric:opening_nav', label: 'Previous NAV', metric: 'opening_nav', role: 'bar', axis: 'money' },
        { id: 'metric:contributions', label: 'Contributions', metric: 'contributions', role: 'bar', axis: 'money' },
        { id: 'metric:return', label: 'Return', metric: 'return', role: 'bar', axis: 'money' },
        ...irrs,
      ]
    default:
      return [
        { id: 'metric:net_investments', label: 'Net Investments', metric: 'net_investments', role: 'bar', axis: 'money' },
        { id: 'metric:return', label: 'Return', metric: 'return', role: 'bar', axis: 'money' },
        ...irrs,
      ]
  }
}

const BIG_RAW = '9007199254740993.123456789'

function moneyPoints(count: number, variant: number): ChartValue[] {
  const pattern: ChartValue[][] = [
    [ok('100000', '100', 'USD 100,000.00'), ok('110000', '110', 'USD 110,000.00'), partial('90000', 'Partial USD 90,000.00'), ok('120000', '120', 'USD 120,000.00')],
    [ok('60000', '60', 'USD 60,000.00'), ok(BIG_RAW, `${BIG_RAW}000`, 'USD 9,007,199,254,740,993.12'), ok('-25000', '-25', '(USD 25,000.00)'), ok('0', '0', 'USD 0.00')],
    [absent(), ok('40000', '40', 'USD 40,000.00'), ok('35000', '35', 'USD 35,000.00'), ok('5000', '5', 'USD 5,000.00')],
    [ok('-12000', '-12', '(USD 12,000.00)'), absent(), ok('8000', '8', 'USD 8,000.00'), ok('9000', '9', 'USD 9,000.00')],
    [ok('2000', '2', 'USD 2,000.00'), ok('-500', '-0.5', '(USD 500.00)'), ok('1000', '1', 'USD 1,000.00'), na()],
  ]
  return pattern[variant % pattern.length].slice(0, count)
}

function irrPoints(count: number, variant: number): ChartValue[] {
  const inception = [ok('0.1234', '0.1234', '12.3%'), ok('0.2345', '0.2345', '23.5%'), partial('0.3456', '34.6%'), ok('-0.0500', '-0.0500', '-5.0%')]
  const interval = [ok('0.1234', '0.1234', '12.3%'), ok('0.0567', '0.0567', '5.7%'), na(), ok('-0.0200', '-0.0200', '-2.0%')]
  return (variant === 0 ? inception : interval).slice(0, count)
}

function totalPoints(count: number): ChartValue[] {
  return [ok('100000', '100', 'USD 100,000.00'), ok('110000', '110', 'USD 110,000.00'), partial('90000', 'Partial USD 90,000.00'), ok('120000', '120', 'USD 120,000.00')].slice(0, count)
}

/** Raw wire envelope (legacy payload + chartV2 document) for one mapping. */
export function navWireFixture(mode: FixtureMode = 'none', frequency: FixtureFrequency = 'M') {
  const periods = fixturePeriods(frequency)
  const specs = modeSeries(mode)
  const series = specs.map((spec, index) => ({
    id: spec.id,
    label: spec.label,
    metric: spec.metric,
    role: spec.role,
    axis: spec.axis,
    unit: spec.axis === 'money'
      ? { kind: 'money', currency: 'USD', plotDivisor: '1000' }
      : { kind: 'ratio', plotDivisor: '1' },
    points: spec.axis === 'return' ? irrPoints(periods.length, spec.metric === 'irr_inception' ? 0 : 1) : moneyPoints(periods.length, index),
    ...(spec.category ? { category: spec.category } : {}),
  }))
  const labels = periods.map((period) => period.displayLabel)
  const datasets = series.map((seriesEntry) => ({
    label: seriesEntry.label,
    type: seriesEntry.role,
    yAxisID: seriesEntry.axis === 'return' ? 'y1' : 'y',
    data: seriesEntry.points.map((point) => (point.status === 'ok' ? Number(point.plotValue) : null)),
    backgroundColor: '#0F4C81',
    datalabels: { display: 'true' },
  }))
  return {
    labels,
    datasets,
    currency: 'USDk',
    chartV2: {
      version: 2,
      kind: 'nav' as const,
      outcome: 'partial' as const,
      partition: 'complete' as const,
      context: {
        accountSelection: { type: 'all', id: null },
        accountIds: [3, 7, 9],
        effectiveDate: periods[periods.length - 1].endDate,
        currency: 'USD',
        digits: 2,
      },
      periods: periods.map((period) => ({
        key: period.key,
        endDate: period.endDate,
        displayLabel: period.displayLabel,
        interval: { startDate: period.intervalStart, endDate: period.endDate, kind: period.intervalStart === null ? 'inception' : 'sample_interval' },
        partialPeriod: period.partialPeriod,
      })),
      series,
      totals: totalPoints(periods.length),
    },
  }
}

/** Parsed document for direct option/style tests (validated like the wire). */
export function navDocumentFixture(mode: FixtureMode = 'none', frequency: FixtureFrequency = 'M'): ChartDocument {
  // Avoid importing parseChartEnvelope here so fixtures stay importable in
  // isolation; the specs parse the wire fixture themselves.
  return navWireFixture(mode, frequency).chartV2 as ChartDocument
}

export function navEmptyWireFixture() {
  return {
    labels: [],
    datasets: [],
    currency: 'USDk',
    empty: true,
    chartV2: {
      version: 2,
      kind: 'nav' as const,
      outcome: 'empty' as const,
      partition: 'complete' as const,
      context: {
        accountSelection: { type: 'all', id: null },
        accountIds: [],
        effectiveDate: '2026-09-30',
        currency: 'USD',
        digits: 2,
      },
      periods: [],
      series: [],
      totals: [],
    },
  }
}
