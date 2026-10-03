// C3 PR #53 review round: partial-status inspection, exact-display tooltips
// with axis labelling, per-IRR horizons without "raw ratio", batched
// inside-zoom events, and panel initialization with an existing result.
// Written RED against e034bed4; fixtures use ordinary currency display
// strings exactly as the backend emits (partial-ness lives in status).
import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { parseNavEnvelope } from '../parseChartEnvelope'
import type { ChartDocument, NavResult } from '../contracts'
import type { ChartInteraction } from '../interaction'
import { buildNavOption } from '../buildNavOption'
import { clampTooltipPlacement } from '../tooltipPlacement'
import { defaultInteraction } from '../interaction'
import ChartInspection from '../ChartInspection.vue'
import NavChartPanel from '../NavChartPanel.vue'
import EChartsNav from '../EChartsNav.vue'
import { navWireFixture } from './navFixtures'

const chartState = vi.hoisted(() => ({ mounts: 0 }))
vi.mock('vue-echarts', async () => {
  const { h: hh } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: ['option', 'updateOptions', 'autoresize', 'theme'],
      setup() {
        chartState.mounts += 1
        return () => hh('div', { class: 'echarts-stub' })
      },
    },
  }
})

vi.mock('../rendererPolicy', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../rendererPolicy')>()
  return { ...actual, pilotRequested: () => true }
})

function parsedDocument(): ChartDocument {
  const parsed = parseNavEnvelope(navWireFixture('asset_type', 'M'))
  if (parsed.capability !== 'v2') throw new Error('fixture must parse as v2')
  return parsed.document
}

function v2Result(): NavResult {
  const document = parsedDocument()
  return { capability: 'v2', legacy: { labels: [], currency: 'USDk', datasets: [] }, document }
}

describe('finding 1: inspection preserves partial status, reason and knownSubtotal', () => {
  const mountInspection = (document: ChartDocument, inspectedKey: string) =>
    mount(ChartInspection, {
      props: { document, interaction: { ...defaultInteraction(document), inspectedPeriodKey: inspectedKey } },
    })

  it('shows status, reason and knownSubtotal for a partial series value with an ordinary currency display', () => {
    const document = parsedDocument()
    // Period 2 carries the partial point for the NAV/first money series.
    const text = mountInspection(document, document.periods[2].key).text()
    expect(text).toContain('USD 90,000.00')
    expect(text).toMatch(/partial/i)
    expect(text).toContain('missing_price')
    expect(text).toContain('known subtotal 90000')
  })

  it('shows status, reason and knownSubtotal for the partial full NAV from document.totals', () => {
    const document = parsedDocument()
    const text = mountInspection(document, document.periods[2].key).text()
    const navLine = text.slice(text.indexOf('Portfolio NAV (all categories)'))
    expect(navLine).toContain('USD 90,000.00')
    expect(navLine).toMatch(/partial/i)
    expect(navLine).toContain('known subtotal 90000')
  })
})

describe('finding 2: exact server displays in tooltips and labelled axes', () => {
  it('formats tooltips from server displays, statuses and units — never plotted numbers', () => {
    const document = parsedDocument()
    const option = buildNavOption(document, defaultInteraction(document)) as {
      tooltip?: { formatter?: (params: unknown) => string }
      yAxis?: Array<{ name?: string }>
    }
    expect(typeof option.tooltip?.formatter).toBe('function')
    const params = [{ axisValue: document.periods[2].key, seriesId: 'metric:nav' }]
    const tooltip = option.tooltip!.formatter(params)!
    expect(tooltip).toContain(document.periods[2].displayLabel)
    // The NAV series' partial point shows its exact display + status, not 0.
    expect(tooltip).toContain('USD 90,000.00')
    expect(tooltip).toMatch(/partial/i)
    expect(tooltip).toContain('known subtotal 90000')
  })

  it('escapes HTML-looking series labels in tooltip output', () => {
    const hostile = {
      ...parsedDocument(),
      series: parsedDocument().series.map((series, index) =>
        index === 0 ? { ...series, label: '<img src=x onerror=alert(1)>' } : series),
    }
    const option = buildNavOption(hostile, defaultInteraction(hostile)) as {
      tooltip?: { formatter?: (params: unknown) => string }
    }
    const formatter = option.tooltip?.formatter
    expect(formatter).toBeTypeOf('function')
    const tooltip = formatter!([{ axisValue: hostile.periods[0].key, seriesId: hostile.series[0].id }])!
    expect(tooltip).not.toContain('<img')
    expect(tooltip).toContain('&lt;img')
  })

  it('labels the money axis with currency scaling and the return axis as a percentage', () => {
    const document = parsedDocument()
    const option = buildNavOption(document, defaultInteraction(document)) as {
      yAxis?: Array<{ name?: string }>
    }
    expect(String(option.yAxis![0].name)).toMatch(/USD/i)
    expect(String(option.yAxis![0].name)).toMatch(/thousand/i)
    expect(String(option.yAxis![1].name)).toMatch(/%/)
  })
})

describe('finding 3: per-IRR horizons without "raw ratio"', () => {
  it('gives each IRR its own horizon: inception-to-endpoint vs the server interval', () => {
    const document = parsedDocument()
    // Period 2: interval kind sample_interval (server-provided bounds).
    const text = mount(ChartInspection, {
      props: { document, interaction: { ...defaultInteraction(document), inspectedPeriodKey: document.periods[2].key } },
    }).text()
    const period = document.periods[2]
    expect(text).toContain(`Since-inception IRR (annualized)`)
    expect(text).toContain(`Inception to ${period.endDate}`)
    expect(text).toContain(`Interval IRR (annualized)`)
    expect(text).toContain(`${period.interval.startDate} – ${period.interval.endDate}`)
    expect(text).not.toContain('raw ratio')
  })

  it('keeps the interval horizon inception at the first sample', () => {
    const document = parsedDocument()
    const text = mount(ChartInspection, {
      props: { document, interaction: { ...defaultInteraction(document), inspectedPeriodKey: document.periods[0].key } },
    }).text()
    const period = document.periods[0]
    void period
    // Both IRR lines show inception semantics at the first sample.
    expect(text.match(/Inception to [0-9-]+/g)?.length).toBeGreaterThanOrEqual(2)
  })
})

describe('finding 4: batched inside-zoom events', () => {
  it('maps batched dataZoom events (wheel/pinch) to the same viewport keys', async () => {
    const document = parsedDocument()
    const wrapper = mount(EChartsNav, { props: { document, interaction: defaultInteraction(document) } })
    await flushPromises()
    const chart = wrapper.findComponent({ name: 'VChart' })
    chart.vm.$emit('datazoom', { batch: [{ componentType: 'dataZoom', start: 25, end: 75 }] })
    const events = wrapper.emitted('update:interaction') as ChartInteraction[][] | undefined
    expect(events).toBeTruthy()
    const viewport = events![0][0].viewport
    expect(viewport).toEqual({ firstPeriodKey: document.periods[1].key, lastPeriodKey: document.periods[2].key })
    wrapper.unmount()
  })
})

describe('finding 5: panel initializes visible series with an existing result', () => {
  it('mounts with every series visible and the pilot chart populated', async () => {
    setActivePinia(createPinia())
    const result = v2Result()
    const wrapper = mount(NavChartPanel, {
      props: {
        result,
        loading: false,
        initialParams: {},
        effectiveCurrentDate: '2026-09-08',
      },
      slots: { chart: () => h('div', { class: 'slot-marker' }) },
      global: { stubs: { teleport: true } },
    })
    await flushPromises()
    // The incumbent slot is replaced by the pilot slot whose legend reflects
    // initialized visibility: every series pressed, both IRRs included.
    if (result.capability !== 'v2') throw new Error('unreachable')
    const pressed = wrapper.findAll('[data-series-id]').map((button) => button.attributes('aria-pressed'))
    expect(pressed.length).toBe(result.document.series.length)
    expect(new Set(pressed)).toEqual(new Set(['true']))
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
// Review round 2: percentage axis ticks, tooltip unit/horizon correctness,
// and verbatim comma-formatted monetary displays (rendering never reformats
// or Number-converts exact server strings).

describe('round 2: return-axis ticks format raw ratios as percentages', () => {
  it('formats 0.05 as 5% and keeps plotted values unchanged', () => {
    const document = parsedDocument()
    const before = structuredClone(document)
    const option = buildNavOption(document, defaultInteraction(document)) as {
      yAxis?: Array<{ name?: string; axisLabel?: { formatter?: (value: number) => string } }>
      series?: Array<{ id: string; data: Array<number | null> }>
    }
    const formatter = option.yAxis![1].axisLabel?.formatter
    expect(formatter).toBeTypeOf('function')
    expect(formatter!(0.05)).toBe('5%')
    expect(formatter!(0.1234)).toBe('12.34%')
    expect(formatter!(-0.02)).toBe('-2%')
    expect(formatter!(0)).toBe('0%')
    // Tick formatting is presentation only: plotted data and the validated
    // document are untouched.
    const money = option.series!.find((entry) => entry.id === 'asset_type:Stock')!
    expect(money.data[0]).toBe(100)
    expect(document).toEqual(before)
  })
})

describe('round 2: tooltip units and horizons', () => {
  const tooltipFor = (document: ChartDocument, periodIndex: number) => {
    const option = buildNavOption(document, defaultInteraction(document)) as {
      tooltip?: { formatter?: (params: unknown) => string }
    }
    const formatter = option.tooltip?.formatter
    expect(formatter).toBeTypeOf('function')
    return formatter!([{ axisValue: document.periods[periodIndex].key, seriesId: document.series[0].id }])!
  }

  it('never labels exact amounts with the plotting scale', () => {
    const document = parsedDocument()
    const tooltip = tooltipFor(document, 0)
    expect(tooltip).toContain('USD 100,000.00')
    expect(tooltip).not.toContain('USD 100,000.00 (USD thousands)')
    expect(tooltip).not.toContain('thousands)')
    // The scaled label stays on the money axis only.
    const option = buildNavOption(document, defaultInteraction(document)) as {
      yAxis?: Array<{ name?: string }>
    }
    expect(String(option.yAxis![0].name)).toMatch(/thousands/i)
  })

  it('uses the annualized IRR names with per-series horizons', () => {
    const document = parsedDocument()
    const option = buildNavOption(document, defaultInteraction(document)) as {
      tooltip?: { formatter?: (params: unknown) => string }
    }
    const formatter = option.tooltip!.formatter!
    const second = document.periods[1]
    const tooltip = formatter([{ axisValue: second.key, seriesId: 'metric:irr_inception' }, { axisValue: second.key, seriesId: 'metric:irr_interval' }])!
    expect(tooltip).toContain('Since-inception IRR (annualized)')
    expect(tooltip).toContain(`Inception to ${second.endDate}`)
    expect(tooltip).toContain('Interval IRR (annualized)')
    expect(tooltip).toContain(`${second.interval.startDate} – ${second.interval.endDate}`)
    const first = document.periods[0]
    const firstTooltip = formatter([{ axisValue: first.key, seriesId: 'metric:irr_inception' }])!
    expect(firstTooltip).toContain(`Inception to ${first.endDate}`)
  })
})

describe('round 2: monetary displays render verbatim with separators', () => {
  const FORMAT_WIRE = {
    labels: ['Jun-26', 'Jul-26'],
    datasets: [
      { label: 'NAV', type: 'bar' as const, yAxisID: 'y', data: [10000, -1234567.89] },
      { label: 'IRR (RHS)', type: 'line' as const, yAxisID: 'y1', data: [0.05, null] },
      { label: 'Rolling IRR (RHS)', type: 'line' as const, yAxisID: 'y1', data: [null, 0] },
    ],
    currency: 'USDk',
    chartV2: {
      version: 2,
      kind: 'nav' as const,
      outcome: 'partial' as const,
      partition: 'complete' as const,
      context: { accountSelection: { type: 'all', id: null }, accountIds: [], effectiveDate: '2026-07-31', currency: 'USD', digits: 2 },
      periods: [
        { key: 'nav:2026-06-30', endDate: '2026-06-30', displayLabel: 'Jun-26', interval: { startDate: null, endDate: '2026-06-30', kind: 'inception' as const }, partialPeriod: false },
        { key: 'nav:2026-07-31', endDate: '2026-07-31', displayLabel: 'Jul-26', interval: { startDate: '2026-07-01', endDate: '2026-07-31', kind: 'sample_interval' as const }, partialPeriod: false },
      ],
      series: [
        {
          id: 'metric:nav', label: 'NAV', metric: 'nav', role: 'bar' as const, axis: 'money' as const,
          unit: { kind: 'money' as const, currency: 'USD', plotDivisor: '1000' },
          points: [
            { value: '10000.0000', plotValue: '10.0000', status: 'ok' as const, reason: 'observed' as const, display: 'USD 10,000.00' },
            { value: '-1234567890.1234', plotValue: '-1234567.8901234', status: 'ok' as const, reason: 'observed' as const, display: '(USD 1,234,567,890.12)' },
          ],
        },
        {
          id: 'metric:irr_inception', label: 'IRR (RHS)', metric: 'irr_inception', role: 'line' as const, axis: 'return' as const,
          unit: { kind: 'ratio' as const, plotDivisor: '1' },
          points: [
            { value: '0.05', plotValue: '0.05', status: 'ok' as const, reason: 'observed' as const, display: '5.0%' },
            { value: '0.123456789012345678901234567890', plotValue: '0.123456789012345678901234567890', status: 'ok' as const, reason: 'observed' as const, display: '12.345678901234567890123456789012%' },
          ],
        },
        {
          id: 'metric:irr_interval', label: 'Rolling IRR (RHS)', metric: 'irr_interval', role: 'line' as const, axis: 'return' as const,
          unit: { kind: 'ratio' as const, plotDivisor: '1' },
          points: [
            { value: null, plotValue: null, status: 'not_available' as const, reason: 'solver_unavailable' as const, display: 'N/A' },
            { value: '0', plotValue: '0', status: 'ok' as const, reason: 'zero_exposure' as const, display: '0.0%' },
          ],
        },
      ],
      totals: [
        { value: '10000.0000', plotValue: '10.0000', status: 'ok' as const, reason: 'observed' as const, display: 'USD 10,000.00' },
        { value: null, plotValue: null, knownSubtotal: '9007199254740993.123456789', status: 'partial' as const, reason: 'missing_price' as const, display: 'USD 9,007,199,254,740,993.12' },
      ],
    },
  }

  function formatDocument(): ChartDocument {
    const parsed = parseNavEnvelope(FORMAT_WIRE)
    if (parsed.capability !== 'v2') throw new Error('expected v2')
    return parsed.document
  }

  it('keeps separators, negatives, precision and partial text exact in the table', async () => {
    const document = formatDocument()
    const table = await import('../ChartDataTable.vue')
    const wrapper = mount(table.default, {
      props: { document, interaction: defaultInteraction(document) },
    })
    const text = wrapper.find('table').text()
    expect(text).toContain('USD 10,000.00')
    expect(text).toContain('(USD 1,234,567,890.12)')
    expect(text).toContain('5.0%')
    // A 32-significant-digit display beyond Number's safe range stays verbatim.
    expect(text).toContain('12.345678901234567890123456789012%')
    expect(text).toContain('USD 9,007,199,254,740,993.12')
    expect(text).toContain('known subtotal 9007199254740993.123456789')
    wrapper.unmount()
  })

  it('keeps separators exact in inspection and tooltips without Number conversion', async () => {
    const document = formatDocument()
    const inspection = await import('../ChartInspection.vue')
    const inspectionText = mount(inspection.default, {
      props: { document, interaction: { ...defaultInteraction(document), inspectedPeriodKey: document.periods[1].key } },
    }).text()
    expect(inspectionText).toContain('(USD 1,234,567,890.12)')
    expect(inspectionText).toContain('USD 9,007,199,254,740,993.12')
    expect(inspectionText).toContain('known subtotal 9007199254740993.123456789')
    const option = buildNavOption(document, defaultInteraction(document)) as {
      tooltip?: { formatter?: (params: unknown) => string }
    }
    const tooltip = option.tooltip!.formatter!([{ axisValue: document.periods[0].key, seriesId: 'metric:nav' }])!
    expect(tooltip).toContain('USD 10,000.00')
    expect(tooltip).not.toContain('USD 10000')
  })
})

// ---------------------------------------------------------------------------
// Review round 3: the long axis tooltip must wrap and stay confined.

describe('round 3: mobile tooltip wrapping and confinement', () => {
  it('configures a wrap-friendly max width and a stable class, without container confine', () => {
    const document = parsedDocument()
    const option = buildNavOption(document, defaultInteraction(document)) as {
      tooltip?: { confine?: boolean; className?: string; extraCssText?: string }
    }
    // Round 4: `confine` re-clamps the placed tooltip against the chart
    // container after the position callback — exactly what pushed the box
    // back under the fixed header — so placement is owned by the round-4
    // body attachment + clamp instead.
    expect(option.tooltip?.confine).toBeUndefined()
    expect(option.tooltip?.className).toBe('nav-chart-tooltip')
    const css = String(option.tooltip?.extraCssText ?? '')
    expect(css).toMatch(/white-space:\s*normal/)
    expect(css).toMatch(/max-width/)
    expect(css).toMatch(/break-word/)
  })
})

// ---------------------------------------------------------------------------
// Review round 4: viewport containment is not visibility. The fixed workspace
// header overlays the top of the viewport and the chart container clips its
// own children, so the tooltip must escape the container (appendTo body) and
// the placement math must pin it inside the unobscured viewport band.

describe('round 4: tooltip clears the fixed header and container clipping', () => {
  it('renders the tooltip outside the chart container and positions it deliberately', () => {
    const document = parsedDocument()
    const option = buildNavOption(document, defaultInteraction(document)) as {
      tooltip?: { appendTo?: unknown; position?: unknown }
    }
    expect(typeof option.tooltip?.appendTo).toBe('function')
    expect(typeof option.tooltip?.position).toBe('function')
  })

  it('places the box below the cursor when the whole box fits the unobscured band', () => {
    // Container at viewport (33, 283), cursor mid-chart, header above 284.
    const placed = clampTooltipPlacement({
      pointX: 100,
      pointY: 180,
      contentWidth: 324,
      contentHeight: 211,
      containerLeft: 33,
      containerTop: 283,
      bounds: { left: 0, top: 284, right: 390, bottom: 844 },
    })
    expect(placed.y).toBe(180 + 18) // default below-cursor placement, container coords
    expect(283 + placed.y).toBeGreaterThanOrEqual(284) // below the header
    expect(placed.x).toBeGreaterThanOrEqual(2)
    expect(placed.x + 324).toBeLessThanOrEqual(390 - 33)
  })

  it('flips above the cursor when below would overflow the unobscured band', () => {
    // Cursor near the bottom of the band: below-cursor would overflow it.
    const placed = clampTooltipPlacement({
      pointX: 100,
      pointY: 480,
      contentWidth: 324,
      contentHeight: 211,
      containerLeft: 33,
      containerTop: 283,
      bounds: { left: 0, top: 284, right: 390, bottom: 844 },
    })
    expect(283 + placed.y).toBeGreaterThanOrEqual(284)
    expect(283 + placed.y + 211).toBeLessThanOrEqual(844)
  })

  it('pushes the box below the header when the default spot is obscured', () => {
    // Chart container scrolled mostly under the header: container top 120,
    // header bottom 284, cursor at container y=20 (viewport 140 — obscured).
    const placed = clampTooltipPlacement({
      pointX: 100,
      pointY: 20,
      contentWidth: 324,
      contentHeight: 211,
      containerLeft: 33,
      containerTop: 120,
      bounds: { left: 0, top: 284, right: 390, bottom: 844 },
    })
    expect(120 + placed.y).toBeGreaterThanOrEqual(284) // never behind the header
    expect(120 + placed.y + 211).toBeLessThanOrEqual(844) // inside the viewport
  })

  it('pins at the top of an unobscured band too short for the box (degenerate)', () => {
    const placed = clampTooltipPlacement({
      pointX: 100,
      pointY: 30,
      contentWidth: 324,
      contentHeight: 211,
      containerLeft: 33,
      containerTop: 120,
      bounds: { left: 0, top: 284, right: 390, bottom: 400 },
    })
    expect(120 + placed.y).toBe(286) // band top + 2px margin, nothing better exists
  })

  it('clamps horizontally inside the unobscured band', () => {
    const placed = clampTooltipPlacement({
      pointX: 350,
      pointY: 180,
      contentWidth: 324,
      contentHeight: 211,
      containerLeft: 33,
      containerTop: 283,
      bounds: { left: 0, top: 284, right: 390, bottom: 844 },
    })
    expect(placed.x).toBeLessThanOrEqual(390 - 33 - 324 - 2)
  })
})
