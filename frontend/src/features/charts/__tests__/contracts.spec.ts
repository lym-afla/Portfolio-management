// C2 Task 1: exact NAV document/legacy validation at the typed boundary.
// Decimal strings stay strings; identity and dates are server-issued only;
// malformed v2 is a contract error, never a silent legacy downgrade.
import { describe, expect, it } from 'vitest'
import { parseChartDocument, parseNavEnvelope } from '../parseChartEnvelope'
import { adaptLegacyNav } from '../adaptLegacyNav'
import type { ChartSeries } from '../contracts'
import { emptyNavFixture, navFixture, navSeriesFixture, allocationFixture, securityFixture, emptySecurityFixture } from './fixtures'

const clone = <T>(value: T): T => structuredClone(value)

describe('parseNavEnvelope: v2 documents', () => {
  it('preserves decimal strings and does not invent modern identity', () => {
    const result = parseNavEnvelope(navFixture())
    expect(result.capability).toBe('v2')
    if (result.capability !== 'v2') return
    expect(result.document.series[0].points[0].value).toBe('100000')
    expect(result.document.series[0].points[0].plotValue).toBe('100')
    expect(typeof result.document.series[0].points[0].plotValue).toBe('string')
    expect(result.document.series[0].points[0].display).toBe('USD 100,000.00')
    const legacy = { labels: ['Jan-26'], datasets: [], currency: 'USDk' }
    expect(parseNavEnvelope(legacy)).toEqual({ capability: 'legacy_only', legacy })
  })

  it('accepts a legacy_only envelope marked empty without inventing points', () => {
    const envelope = { labels: [], datasets: [], currency: 'USDk', empty: true }
    const result = parseNavEnvelope(envelope)
    expect(result.capability).toBe('legacy_only')
    if (result.capability === 'legacy_only') {
      expect(result.legacy.labels).toEqual([])
      expect(result.legacy.datasets).toEqual([])
    }
  })

  it('keeps 16-significant-digit raw strings verbatim through validation', () => {
    const document = parseChartDocument(navSeriesFixture().chartV2)
    const bigRaw = '9007199254740993.123456789'
    expect(document.series[0].points[1].value).toBe(bigRaw)
    expect(document.series[0].points[1].plotValue).toBe(`${bigRaw}000`)
    expect(document.totals?.[1].value).toBe(bigRaw)
  })

  it('allows repeated display labels under distinct server period keys', () => {
    const source = clone(navFixture().chartV2)
    source.periods = [
      { ...source.periods[0], key: 'nav:2026-01-31', displayLabel: 'Jan-26' },
      { ...source.periods[0], key: 'nav:2026-02-28', endDate: '2026-02-28',
        interval: { startDate: '2026-02-01', endDate: '2026-02-28', kind: 'sample_interval' } },
    ]
    source.series.forEach((series) => {
      series.points = [...series.points, series.points[0]]
    })
    source.totals = [...(source.totals ?? []), source.totals![0]]
    const document = parseChartDocument(source)
    expect(document.periods.map((period) => period.displayLabel)).toEqual(['Jan-26', 'Jan-26'])
    expect(document.periods.map((period) => period.key)).toEqual(['nav:2026-01-31', 'nav:2026-02-28'])
  })

  it('accepts valid zero observed, zero_exposure, absent and partial points with their statuses', () => {
    const document = parseChartDocument(navSeriesFixture().chartV2)
    const stock = document.series.find((series) => series.id === 'asset_type:Stock')!
    expect(stock.points[0]).toMatchObject({ value: '40000', status: 'ok', reason: 'observed' })
    expect(stock.points[1]).toMatchObject({ value: '0', plotValue: '0', status: 'ok', reason: 'zero_exposure' })
    expect(stock.points[2]).toMatchObject({ value: null, plotValue: null, status: 'unknown', reason: 'absent_unclassified' })
    expect(document.series[0].points[2]).toMatchObject({ value: null, plotValue: null, status: 'partial', reason: 'missing_price' })
    expect(document.series[0].points[2].knownSubtotal).toBe('120000')
    expect(document.outcome).toBe('partial')
  })

  it('keeps both IRR horizons distinct: inception null start, interval bounded', () => {
    const document = parseChartDocument(navSeriesFixture().chartV2)
    const inception = document.series.find((series) => series.metric === 'irr_inception')!
    const interval = document.series.find((series) => series.metric === 'irr_interval')!
    expect(inception.points.map((point) => point.value)).toEqual(['0.1234', '0.2345', '0.3456'])
    expect(interval.points.map((point) => point.value)).toEqual(['0.1234', '0.0567', null])
    expect(interval.points[2]).toMatchObject({ status: 'not_available', reason: 'solver_unavailable', display: 'N/A' })
    expect(document.periods[0].interval).toMatchObject({ startDate: null, kind: 'inception' })
    expect(document.periods[1].interval).toMatchObject({ startDate: '2026-02-01', kind: 'sample_interval' })
  })

  it('accepts an empty v2 document with neither series nor periods', () => {
    const document = parseChartDocument(emptyNavFixture().chartV2)
    expect(document.outcome).toBe('empty')
    expect(document.series).toEqual([])
    expect(document.periods).toEqual([])
    expect(document.totals).toEqual([])
  })

  it('does not require period dates to be unique when server keys differ', () => {
    const source = clone(navFixture().chartV2)
    source.periods = [
      source.periods[0],
      { ...source.periods[0], key: 'nav:2026-01-31b' },
    ]
    source.series.forEach((series) => { series.points = [...series.points, series.points[0]] })
    source.totals = [...(source.totals ?? []), source.totals![0]]
    expect(() => parseChartDocument(source)).not.toThrow()
  })
})

describe('parseNavEnvelope: v2 rejection cases', () => {
  const rejectsWith = (mutate: (document: ReturnType<typeof navFixture>['chartV2']) => void, pattern: RegExp) => {
    const source = clone(navFixture().chartV2)
    mutate(source)
    expect(() => parseChartDocument(source)).toThrow(pattern)
  }

  it('rejects absent, empty and duplicated series identity', () => {
    rejectsWith((document) => { delete (document.series[0] as Partial<ChartSeries>).id }, /identity/i)
    rejectsWith((document) => { document.series[1].id = '' }, /identity/i)
    rejectsWith((document) => { document.series[1].id = document.series[0].id }, /identity/i)
  })

  it('rejects absent and duplicated period keys', () => {
    rejectsWith((document) => { delete (document.periods[0] as { key?: string }).key }, /identity|period/i)
    rejectsWith((document) => {
      document.periods = [document.periods[0], { ...document.periods[0] }]
      document.series.forEach((series) => { series.points = [...series.points, series.points[0]] })
      document.totals = [...(document.totals ?? []), document.totals![0]]
    }, /identity|period/i)
  })

  it('rejects impossible and malformed dates', () => {
    rejectsWith((document) => { document.periods[0].endDate = '2026-02-30' }, /date/i)
    rejectsWith((document) => { document.periods[0].endDate = '31-01-2026' }, /date/i)
    rejectsWith((document) => { document.context.effectiveDate = '2026-13-01' }, /date/i)
    const multi = clone(navSeriesFixture().chartV2)
    multi.periods[1].interval.startDate = '2026-02-31'
    expect(() => parseChartDocument(multi)).toThrow(/date/i)
  })

  it('rejects interval boundaries that disagree with their period', () => {
    rejectsWith((document) => {
      document.periods[0].interval.endDate = '2026-01-30'
    }, /interval/i)
    rejectsWith((document) => {
      document.periods[0].interval.startDate = '2026-02-01'
    }, /interval|inception/i)
    rejectsWith((document) => {
      const later = clone(document.periods[0])
      later.key = 'nav:2026-02-28'
      later.endDate = '2026-02-28'
      later.interval = { startDate: '2026-03-01', endDate: '2026-02-28', kind: 'sample_interval' }
      document.periods = [document.periods[0], later]
      document.series.forEach((series) => { series.points = [...series.points, series.points[0]] })
      document.totals = [...(document.totals ?? []), document.totals![0]]
    }, /interval/i)
  })

  it('rejects malformed decimal strings for v2 values', () => {
    for (const bad of ['NaN', 'Infinity', '-Infinity', '1e3', '1E+3', '0.1.2', '', ' 1', '1 ', '+1', '.5', '1.']) {
      rejectsWith((document) => { document.series[0].points[0].value = bad }, /decimal/i)
    }
  })

  it('rejects numeric v2 monetary values', () => {
    rejectsWith((document) => {
      (document.series[0].points[0] as { value: unknown }).value = 100000
    }, /decimal|string/i)
    rejectsWith((document) => {
      (document.totals![0] as { plotValue: unknown }).plotValue = 100
    }, /decimal|string/i)
  })

  it('rejects mismatched point and totals lengths', () => {
    rejectsWith((document) => { document.series[0].points = [] }, /length|points/i)
    rejectsWith((document) => { document.totals = [] }, /length|totals/i)
  })

  it('rejects invalid enums, context shapes and unit kinds', () => {
    rejectsWith((document) => { (document.series[0].points[0] as { status: unknown }).status = 'fine' }, /status/i)
    rejectsWith((document) => { (document.series[0].points[0] as { reason: unknown }).reason = 'guessed' }, /reason/i)
    rejectsWith((document) => { (document as { kind: unknown }).kind = 'velocity' }, /kind/i)
    rejectsWith((document) => { (document as { outcome: unknown }).outcome = 'unknown_outcome' }, /outcome/i)
    rejectsWith((document) => { (document as { partition: unknown }).partition = 'half' }, /partition/i)
    rejectsWith((document) => { (document as { version: unknown }).version = 3 }, /version/i)
    rejectsWith((document) => { (document.context.accountSelection as { type: unknown }).type = 'universe' }, /context|selection/i)
    rejectsWith((document) => { (document.context as { digits: unknown }).digits = 2.5 }, /context|digits/i)
    rejectsWith((document) => { (document.context.accountIds as unknown as number[]).push(7) }, /context|accounts/i)
    rejectsWith((document) => { (document.series[1].unit as { kind: string }).kind = 'money' }, /unit/i)
    rejectsWith((document) => { (document.series[0].unit as { plotDivisor: string }).plotDivisor = '100' }, /unit|divisor/i)
  })

  it('rejects non-ok points that carry values or plot values', () => {
    rejectsWith((document) => {
      (document.series[0].points as { [index: number]: unknown })[0] = { value: '1', plotValue: null, status: 'unknown', reason: 'missing_price', display: 'x' }
    }, /status|value/i)
    rejectsWith((document) => {
      (document.series[0].points as { [index: number]: unknown })[0] = { value: null, plotValue: '1', status: 'not_available', reason: 'solver_unavailable', display: 'N/A' }
    }, /status|plot/i)
    rejectsWith((document) => {
      (document.series[0].points as { [index: number]: unknown })[0] = { value: '1', plotValue: '1', knownSubtotal: '1', status: 'ok', reason: 'observed', display: 'x' }
    }, /subtotal/i)
  })

  it('rejects a present chartV2 that is null or an unsupported version, never downgrading', () => {
    const nullV2 = clone(navFixture())
    nullV2.chartV2 = null as unknown as ReturnType<typeof navFixture>['chartV2']
    expect(() => parseNavEnvelope(nullV2)).toThrow(/chartV2|contract/i)
    const wrongVersion = clone(navFixture());
    (wrongVersion.chartV2 as { version: unknown }).version = 3
    expect(() => parseNavEnvelope(wrongVersion)).toThrow(/version/i)
  })
})

describe('adaptLegacyNav: honest legacy passthrough', () => {
  it('preserves styling, extra dataset fields and unavailable markers', () => {
    const envelope = clone(navSeriesFixture())
    const legacy = adaptLegacyNav(envelope)
    expect(legacy.labels).toEqual(['Jan-26', 'Feb-26', '10-Mar-26'])
    expect(legacy.currency).toBe('USDk')
    expect(legacy.datasets).toHaveLength(4)
    expect(legacy.datasets[3]).toMatchObject({ label: 'Stock', stack: 'combined', datalabels: { display: 'true' } })
    expect(legacy.datasets[1].data).toEqual([0.1234, 0.2345, 'N/A'])
    expect(legacy.datasets[2].data).toEqual([0.1234, 0.0567, 'N/R'])
    expect(legacy.datasets[0].data).toEqual([100, null, 120])
  })

  it('keeps non-dataset envelope fields such as empty without dropping or coercing them', () => {
    const legacy = adaptLegacyNav(emptyNavFixture())
    expect(legacy).toMatchObject({ empty: true, labels: [], datasets: [] })
  })

  it('never injects modern identity or dates into legacy datasets', () => {
    const legacy = adaptLegacyNav(navFixture())
    for (const dataset of legacy.datasets) {
      expect('id' in dataset).toBe(false)
      expect('endDate' in dataset).toBe(false)
      expect('key' in dataset).toBe(false)
    }
  })

  it('rejects malformed legacy shapes', () => {
    expect(() => adaptLegacyNav({ labels: 'Jan-26', datasets: [], currency: 'USDk' })).toThrow(/label/i)
    expect(() => adaptLegacyNav({ labels: [1], datasets: [], currency: 'USDk' })).toThrow(/label/i)
    expect(() => adaptLegacyNav({ labels: [], datasets: [{ data: [1] }], currency: 'USDk' })).toThrow(/dataset/i)
    expect(() => adaptLegacyNav({ labels: [], datasets: [{ label: 'X', data: 'not-array' }], currency: 'USDk' })).toThrow(/dataset|data/i)
    expect(() => adaptLegacyNav({ labels: [], datasets: [{ label: 'X', type: 'pie', data: [] }], currency: 'USDk' })).toThrow(/dataset|type/i)
    expect(() => adaptLegacyNav({ labels: [], datasets: [{ label: 'X', data: [true] }], currency: 'USDk' })).toThrow(/dataset|data/i)
    expect(() => adaptLegacyNav({ labels: ['Jan-26'], datasets: [{ label: 'X', data: [1, 2] }], currency: 'USDk' })).toThrow(/length/i)
    expect(() => adaptLegacyNav(null)).toThrow()
    expect(() => adaptLegacyNav({ labels: [], datasets: [] })).toThrow(/currency/i)
  })
})

// ---------------------------------------------------------------------------
// Task 2: allocation and security documents (validation only; no rollout).

describe('parseChartDocument: allocation documents', () => {
  it('accepts eligible partitions for all three dimensions without recalculating', () => {
    for (const dimension of ['asset_type', 'asset_class', 'currency'] as const) {
      const source = allocationFixture({ dimension })
      const before = clone(source)
      const document = parseChartDocument(source)
      expect(document).toEqual(before)
      expect(document.allocationSummary!.denominator.value).toBe('100')
      expect(document.allocationSummary!.totalShare.value).toBe('1')
      expect(document.allocations!.map((allocation) => allocation.amount.value)).toEqual(['75', '25'])
      expect(document.allocations!.map((allocation) => allocation.share.value)).toEqual(['0.75', '0.25'])
      expect(document.allocations!.map((allocation) => allocation.rank)).toEqual([1, 2])
    }
  })

  it.each([
    ['signed', { pieEligibility: 'signed' as const }],
    ['nonpositive_total', { pieEligibility: 'nonpositive_total' as const }],
    ['incomplete', { pieEligibility: 'incomplete' as const }],
    ['nonpartitioning', { pieEligibility: 'nonpartitioning' as const, partition: 'legacy_non_partitioning' as const }],
  ])('accepts explanatory %s documents without transforming values', (_name, options) => {
    const source = allocationFixture(options)
    const before = clone(source)
    expect(parseChartDocument(source)).toEqual(before)
  })

  it('keeps signed amounts and shares verbatim for explanatory presentation', () => {
    const document = parseChartDocument(allocationFixture({ pieEligibility: 'signed' }))
    const stock = document.allocations!.find((allocation) => allocation.seriesId === 'asset_type:Stock')!
    expect(stock.amount.value).toBe('-25')
    expect(stock.share.value).toBe('-0.25')
    expect(document.allocationSummary!.totalShare.value).toBe('1')
  })

  it('keeps partial denominators with knownSubtotal instead of a full value', () => {
    const document = parseChartDocument(allocationFixture({ pieEligibility: 'incomplete', partition: 'unknown' }))
    const denominator = document.allocationSummary!.denominator
    expect(denominator.status).toBe('partial')
    expect(denominator.value).toBeNull()
    expect(denominator.knownSubtotal).toBe('100')
    expect(document.outcome).toBe('partial')
  })

  it('rejects missing allocations or allocationSummary and their presence on other kinds', () => {
    const noSummary = clone(allocationFixture())
    delete (noSummary as { allocationSummary?: unknown }).allocationSummary
    expect(() => parseChartDocument(noSummary)).toThrow(/allocation/i)
    const noAllocations = clone(allocationFixture())
    delete (noAllocations as { allocations?: unknown }).allocations
    expect(() => parseChartDocument(noAllocations)).toThrow(/allocation/i)
    const navWithAllocations = clone(navFixture().chartV2) as unknown as { allocations?: unknown }
    navWithAllocations.allocations = []
    expect(() => parseChartDocument(navWithAllocations)).toThrow(/allocation/i)
  })

  it('rejects unknown, duplicate and incomplete series references', () => {
    const unknown = clone(allocationFixture());
    (unknown.allocations![0] as { seriesId: string }).seriesId = 'asset_type:Ghost'
    expect(() => parseChartDocument(unknown)).toThrow(/series|reference/i)
    const duplicate = clone(allocationFixture());
    (duplicate.allocations![1] as { seriesId: string }).seriesId = duplicate.allocations![0].seriesId
    expect(() => parseChartDocument(duplicate)).toThrow(/twice|duplicate|reference/i)
    const unreferenced = clone(allocationFixture())
    unreferenced.allocations = unreferenced.allocations!.slice(0, 1)
    expect(() => parseChartDocument(unreferenced)).toThrow(/reference|series/i)
  })

  it('rejects invalid ranks', () => {
    for (const rank of [0, -1, 1.5, '2'] as unknown[]) {
      const source = clone(allocationFixture());
      (source.allocations![1] as { rank: unknown }).rank = rank
      expect(() => parseChartDocument(source)).toThrow(/rank/i)
    }
    const descending = clone(allocationFixture())
    descending.allocations = [descending.allocations![1], descending.allocations![0]]
    expect(() => parseChartDocument(descending)).toThrow(/rank|order/i)
  })

  it('rejects incompatible summary currency and unit', () => {
    const currency = clone(allocationFixture());
    (currency.allocationSummary!.unit as { currency: string }).currency = 'EUR'
    expect(() => parseChartDocument(currency)).toThrow(/currency/i)
    const ratio = clone(allocationFixture());
    (ratio.allocationSummary!.unit as { kind: string }).kind = 'ratio'
    expect(() => parseChartDocument(ratio)).toThrow(/unit/i)
    const divisor = clone(allocationFixture());
    (divisor.allocationSummary!.unit as { plotDivisor: string }).plotDivisor = '1000'
    expect(() => parseChartDocument(divisor)).toThrow(/unit|divisor/i)
    const seriesCurrency = clone(allocationFixture());
    (seriesCurrency.series[0].unit as { currency: string }).currency = 'EUR'
    expect(() => parseChartDocument(seriesCurrency)).toThrow(/currency/i)
  })

  it('rejects eligible claims contradicted by partial values or incomplete partitions', () => {
    const partialAmount = clone(allocationFixture({ pieEligibility: 'incomplete' }))
    ;(partialAmount.allocationSummary as { pieEligibility: string }).pieEligibility = 'eligible'
    expect(() => parseChartDocument(partialAmount)).toThrow(/eligible/i)
    const wrongPartition = clone(allocationFixture({ pieEligibility: 'nonpartitioning', partition: 'legacy_non_partitioning' }))
    expect(() => parseChartDocument(wrongPartition)).not.toThrow()
    const eligibleBadPartition = clone(allocationFixture())
    ;(eligibleBadPartition as { partition: string }).partition = 'legacy_non_partitioning'
    expect(() => parseChartDocument(eligibleBadPartition)).toThrow(/eligible/i)
    const unavailableTotalShare = clone(allocationFixture({ pieEligibility: 'nonpositive_total' }))
    ;(unavailableTotalShare.allocationSummary as { pieEligibility: string }).pieEligibility = 'eligible'
    expect(() => parseChartDocument(unavailableTotalShare)).toThrow(/eligible/i)
  })

  it('requires allocation series to be category_nav of the summary dimension', () => {
    const wrongMetric = clone(allocationFixture())
    ;(wrongMetric.series[0] as { metric: string }).metric = 'nav'
    expect(() => parseChartDocument(wrongMetric)).toThrow(/category|dimension|metric/i)
    const wrongKind = clone(allocationFixture())
    ;(wrongKind.series[0].category as { kind: string }).kind = 'currency'
    expect(() => parseChartDocument(wrongKind)).toThrow(/dimension|category/i)
  })

  it('accepts an empty allocation document carrying its single sampling period', () => {
    const source = allocationFixture()
    const empty = {
      ...source, outcome: 'empty' as const, series: [], allocations: [],
      totals: [source.allocationSummary!.denominator],
    }
    expect(() => parseChartDocument(empty)).not.toThrow()
  })
})

describe('parseChartDocument: security documents', () => {
  it('keeps bond price percent-of-nominal at stored scale', () => {
    const document = parseChartDocument(securityFixture('price', 'percent_of_nominal', '98.500000'))
    expect(document.series[0].points[0].value).toBe('98.500000')
    expect(document.series[0].points[0].plotValue).toBe('98.500000')
    expect(document.series[0].points[0].display).toBe('98.5% of nominal')
    expect(document.series[0].unit).toEqual({ kind: 'percent_of_nominal', plotDivisor: '1' })
    expect(document.series[0]).toMatchObject({ metric: 'price', axis: 'price', role: 'line' })
    expect(document.security).toEqual({ id: 9, instrumentType: 'Bond' })
  })

  it('keeps instrument money currency distinct from reporting currency', () => {
    const document = parseChartDocument(securityFixture('price', 'money', '50.250000'))
    expect(document.series[0].unit).toEqual({ kind: 'money', currency: 'EUR', plotDivisor: '1' })
    expect(document.context.currency).toBe('USD')
    expect(document.series[0].points[0].value).toBe('50.250000')
  })

  it('keeps quantity precision and same-date events as separate keyed rows', () => {
    const document = parseChartDocument(securityFixture('position', 'quantity', '0.000116590'))
    expect(document.series[0].points[0].value).toBe('0.000116590')
    expect(document.series[0].unit).toEqual({ kind: 'quantity', plotDivisor: '1' })
    expect(document.series[0]).toMatchObject({ metric: 'position', axis: 'quantity' })
    expect(document.periods.map((period) => period.endDate)).toEqual(['2026-01-31', '2026-01-31'])
    expect(new Set(document.periods.map((period) => period.key)).size).toBe(2)
    expect(document.series[0].points[1]).toMatchObject({ value: null, status: 'not_available' })
  })

  it('accepts empty histories while preserving their identified empty series', () => {
    for (const kind of ['price', 'position'] as const) {
      const document = parseChartDocument(emptySecurityFixture(kind))
      expect(document.outcome).toBe('empty')
      expect(document.periods).toEqual([])
      expect(document.series).toHaveLength(1)
      expect(document.series[0]).toMatchObject({
        id: `security:9:${kind}`, metric: kind,
        axis: kind === 'price' ? 'price' : 'quantity',
      })
      expect(document.series[0].points).toEqual([])
    }
  })

  it('still rejects an empty nav document that carries series', () => {
    const source = clone(emptyNavFixture().chartV2) as unknown as { series?: unknown[] }
    source.series = [{ id: 'metric:nav', label: 'NAV', metric: 'nav', role: 'bar', axis: 'money', unit: { kind: 'money', currency: 'USD', plotDivisor: '1000' }, points: [] }]
    expect(() => parseChartDocument(source)).toThrow(/empty|series/i)
  })

  it('rejects missing or malformed security identity', () => {
    const missing = clone(securityFixture('price', 'percent_of_nominal', '98.500000'))
    delete (missing as { security?: unknown }).security
    expect(() => parseChartDocument(missing)).toThrow(/security/i)
    const badId = clone(securityFixture('price', 'percent_of_nominal', '98.500000'))
    ;(badId.security as { id: unknown }).id = 0
    expect(() => parseChartDocument(badId)).toThrow(/security/i)
    const badType = clone(securityFixture('position', 'quantity', '1'))
    ;(badType.security as { instrumentType: unknown }).instrumentType = ''
    expect(() => parseChartDocument(badType)).toThrow(/security/i)
  })

  it('rejects kind/metric/axis/unit combinations C1 never emits', () => {
    const wrongMetric = clone(securityFixture('price', 'percent_of_nominal', '98.500000'))
    ;(wrongMetric.series[0] as { metric: string }).metric = 'position'
    expect(() => parseChartDocument(wrongMetric)).toThrow(/price|metric/i)
    const wrongAxis = clone(securityFixture('position', 'quantity', '1'))
    ;(wrongAxis.series[0] as { axis: string }).axis = 'money'
    expect(() => parseChartDocument(wrongAxis)).toThrow(/unit|axis/i)
    const wrongDivisor = clone(securityFixture('price', 'money', '50.250000'))
    ;(wrongDivisor.series[0].unit as { plotDivisor: string }).plotDivisor = '1000'
    expect(() => parseChartDocument(wrongDivisor)).toThrow(/unit|divisor/i)
  })
})
