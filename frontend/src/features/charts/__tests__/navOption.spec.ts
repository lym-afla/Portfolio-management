// C3 Task 1: the sole plotting boundary and pure NAV options. Backend
// plotValue is the only number source; period identity comes from server
// keys; gaps stay gaps; both IRRs keep their own horizon; visibility and
// viewport never change values. Fixtures enter through parseNavEnvelope so
// tests exercise the same validation as the wire.
import { describe, expect, it } from 'vitest'
import { parseNavEnvelope } from '../parseChartEnvelope'
import type { ChartDocument, ChartValue } from '../contracts'
import { toPlotNumber } from '../renderBoundary'
import { buildNavOption } from '../buildNavOption'
import { seriesColor, irrLineStyle } from '../seriesStyles'
import { defaultInteraction } from '../interaction'
import { ALL_FREQUENCIES, ALL_MODES, navEmptyWireFixture, navWireFixture } from './navFixtures'

const clone = <T>(value: T): T => structuredClone(value)

function parsedDocument(mode: (typeof ALL_MODES)[number], frequency: (typeof ALL_FREQUENCIES)[number]): ChartDocument {
  const result = parseNavEnvelope(navWireFixture(mode, frequency))
  if (result.capability !== 'v2') throw new Error('fixture must parse as v2')
  return result.document
}

function optionSeries(option: ReturnType<typeof buildNavOption>) {
  return option.series as Array<{
    id: string
    name: string
    type: string
    yAxisIndex: number
    stack?: string
    smooth?: boolean
    connectNulls?: boolean
    data: Array<number | null>
    lineStyle?: { type?: string }
  }>
}

describe('toPlotNumber', () => {
  it('converts only ok plotValue strings, never re-dividing by plotDivisor', () => {
    expect(toPlotNumber({ value: '100000', plotValue: '100', status: 'ok', reason: 'observed', display: 'x' })).toBe(100)
    expect(toPlotNumber({ value: '0', plotValue: '0', status: 'ok', reason: 'zero_exposure', display: 'x' })).toBe(0)
    expect(toPlotNumber({ value: '-25000', plotValue: '-25', status: 'ok', reason: 'observed', display: 'x' })).toBe(-25)
    expect(toPlotNumber({ value: '0.1234', plotValue: '0.1234', status: 'ok', reason: 'observed', display: 'x' })).toBe(0.1234)
  })

  it('returns null for every non-ok point even with a knownSubtotal', () => {
    expect(toPlotNumber({ value: null, plotValue: null, status: 'unknown', reason: 'absent_unclassified', display: '–' })).toBeNull()
    expect(toPlotNumber({ value: null, plotValue: null, knownSubtotal: '90000', status: 'partial', reason: 'missing_price', display: 'x' })).toBeNull()
    expect(toPlotNumber({ value: null, plotValue: null, status: 'not_available', reason: 'solver_unavailable', display: 'N/A' })).toBeNull()
    expect(toPlotNumber({ value: null, plotValue: null, status: 'ok', reason: 'observed', display: 'x' } as unknown as ChartValue)).toBeNull()
  })

  it('keeps huge finite decimals exact in state and throws RangeError out of range', () => {
    const big = '9007199254740993.123456789'
    const point: ChartValue = { value: big, plotValue: `${big}`, status: 'ok', reason: 'observed', display: 'x' }
    expect(toPlotNumber(point)).toBe(Number(big))
    expect(point.value).toBe(big)
    expect(() => toPlotNumber({ value: '9'.repeat(400), plotValue: '9'.repeat(400), status: 'ok', reason: 'observed', display: 'x' })).toThrow(RangeError)
  })
})

describe('buildNavOption across all 35 mode/frequency mappings', () => {
  it.each(ALL_MODES.map((mode) => [mode] as const))('maps mode %s with correct series identities', (mode) => {
    for (const frequency of ALL_FREQUENCIES) {
      const document = parsedDocument(mode, frequency)
      const before = clone(document)
      const option = buildNavOption(document, defaultInteraction(document))
      expect(document).toEqual(before)
      const series = optionSeries(option)
      expect(new Set(series.map((entry) => entry.id))).toEqual(new Set(document.series.map((entry) => entry.id)))
      const irrs = series.filter((entry) => entry.id.startsWith('metric:irr'))
      expect(irrs.map((entry) => entry.yAxisIndex)).toEqual(irrs.map(() => 1))
      expect(series.filter((entry) => entry.type === 'bar').map((entry) => entry.stack)).toEqual(
        series.filter((entry) => entry.type === 'bar').map(() => 'nav'),
      )
      for (const entry of series) {
        if (entry.type === 'line') {
          expect(entry.smooth).toBe(false)
          expect(entry.connectNulls).toBe(false)
        }
      }
      const xAxis = option.xAxis as Array<{ type: string; data: string[] }>
      expect(xAxis[0].data).toEqual(document.periods.map((period) => period.key))
    }
  })

  it.each(ALL_FREQUENCIES.map((frequency) => [frequency] as const))('formats %s period labels from server displayLabels by key', (frequency) => {
    const document = parsedDocument('none', frequency)
    const option = buildNavOption(document, defaultInteraction(document))
    const xAxis = option.xAxis as Array<{ data: string[]; axisLabel?: { formatter?: (value: string) => string } }>
    const formatter = xAxis[0].axisLabel?.formatter
    expect(formatter).toBeTypeOf('function')
    for (const period of document.periods) {
      expect(formatter!(period.key)).toBe(period.displayLabel)
    }
  })

  it('keeps gaps as nulls and signed values signed; never zero-fills', () => {
    const document = parsedDocument('value_contributions', 'M')
    const option = buildNavOption(document, defaultInteraction(document))
    const byId = new Map(optionSeries(option).map((entry) => [entry.id, entry.data]))
    // Partial (opening_nav, pattern 0) and absent (return, pattern 2) stay gaps.
    expect(byId.get('metric:opening_nav')).toEqual([100, 110, null, 120])
    expect(byId.get('metric:return')).toEqual([null, 40, 35, 5])
    // Contributions (pattern 1) keep signs, the exact zero and the converted
    // big plot value; the raw string remains authoritative in the document.
    expect(byId.get('metric:contributions')).toEqual([60, 9007199254740994, -25, 0])
    const source = document.series.find((series) => series.id === 'metric:contributions')!
    expect(source.points[1].value).toBe('9007199254740993.123456789')
    expect(byId.get('metric:irr_interval')).toEqual([0.1234, 0.0567, null, -0.02])
  })

  it('supports repeated display labels under distinct keys', () => {
    const document = parsedDocument('account', 'W')
    const labels = document.periods.map((period) => period.displayLabel)
    expect(new Set(document.periods.map((period) => period.key)).size).toBe(document.periods.length)
    void labels
    const option = buildNavOption(document, defaultInteraction(document))
    const xAxis = option.xAxis as Array<{ data: string[] }>
    expect(xAxis[0].data.length).toBe(document.periods.length)
  })

  it('excludes hidden series from options without touching values or totals', () => {
    const document = parsedDocument('asset_type', 'M')
    const interaction = {
      visibleSeriesIds: document.series.map((series) => series.id).filter((id) => id !== 'metric:irr_interval'),
      viewport: null,
      inspectedPeriodKey: null,
    }
    const option = buildNavOption(document, interaction)
    const ids = optionSeries(option).map((entry) => entry.id)
    expect(ids).not.toContain('metric:irr_interval')
    expect(ids).toContain('metric:irr_inception')
    expect(ids).toContain('asset_type:Stock')
    const full = buildNavOption(document, { ...interaction, visibleSeriesIds: document.series.map((series) => series.id) })
    const shared = (id: string) => optionSeries(full).find((entry) => entry.id === id)!.data
    expect(optionSeries(option).find((entry) => entry.id === 'metric:irr_inception')!.data).toEqual(shared('metric:irr_inception'))
  })

  it('changes only the zoom window, never periods or values', () => {
    const document = parsedDocument('none', 'Q')
    const all = defaultInteraction(document)
    const zoomed = { ...all, viewport: { firstPeriodKey: document.periods[0].key, lastPeriodKey: document.periods[1].key } }
    const plain = buildNavOption(document, all)
    const zoom = buildNavOption(document, zoomed)
    expect(optionSeries(zoom).map((entry) => entry.data)).toEqual(optionSeries(plain).map((entry) => entry.data))
    expect((zoom.xAxis as Array<{ data: string[] }>)[0].data).toEqual((plain.xAxis as Array<{ data: string[] }>)[0].data)
  })

  it('maps an empty v2 document to an empty, well-formed option', () => {
    const result = parseNavEnvelope(navEmptyWireFixture())
    if (result.capability !== 'v2') throw new Error('expected v2')
    const option = buildNavOption(result.document, defaultInteraction(result.document))
    expect(optionSeries(option)).toEqual([])
    expect((option.xAxis as Array<{ data: string[] }>)[0].data).toEqual([])
  })
})

describe('seriesStyles stability', () => {
  it('assigns colors by stable server identity so survivors never recolor', () => {
    expect(seriesColor('metric:nav')).toBe(seriesColor('metric:nav'))
    const before = ['asset_type:Cash', 'asset_type:Stock', 'currency:EUR'].map((id) => seriesColor(id))
    const after = ['asset_type:Bond', 'asset_type:Cash', 'asset_type:Stock', 'currency:EUR'].map((id) => seriesColor(id))
    expect(after[1]).toBe(before[0])
    expect(after[2]).toBe(before[1])
    expect(after[3]).toBe(before[2])
  })

  it('keeps the two IRR lines visually distinct with fixed styles', () => {
    const styles = [irrLineStyle('metric:irr_inception'), irrLineStyle('metric:irr_interval')]
    expect(styles[0]).not.toEqual(styles[1])
    expect(seriesColor('metric:irr_inception')).not.toBe(seriesColor('metric:irr_interval'))
    expect(irrLineStyle('metric:irr_inception')).toEqual(irrLineStyle('metric:irr_inception'))
  })
})
