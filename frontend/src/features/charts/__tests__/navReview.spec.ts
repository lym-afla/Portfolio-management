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
