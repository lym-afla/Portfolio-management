// C4 Task 3: security price/position history renderers. Price units come
// from series metadata — instrument currency or percent-of-nominal, never
// rescaled (bond 98.5 stays 98.5); quantities keep exact precision
// (0.000116590); same-date events stay distinct server-keyed points and
// table rows; nothing is interpolated, zero-filled or sampled. The
// effective-date carry-forward is presentation-only, clearly annotated and
// kept out of the validated document and the observed-point table.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h } from 'vue'

const chartState = vi.hoisted(() => ({
  captured: [] as Array<Record<string, unknown>>,
  events: [] as Array<{ name: string; payload: unknown }>,
}))

vi.mock('vue-echarts', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: ['option', 'updateOptions', 'autoresize', 'theme'],
      setup(_props: unknown, { expose }: { expose: (value: unknown) => void }) {
        chartState.captured.push(_props as Record<string, unknown>)
        expose({
          dispatchAction: (payload: unknown) => {
            chartState.events.push({ name: 'dispatchAction', payload })
          },
        })
        return () => h('div', { class: 'security-chart-stub' })
      },
    },
  }
})

import { emptySecurityFixture, securityFixture, type SecurityDocumentOverrides } from './securityFixtures'
import type { ChartDocument } from '../contracts'
import { buildSecurityOption } from '../buildSecurityOption'
import SecurityDataTable from '../SecurityDataTable.vue'
import SecurityHistoryChart from '../SecurityHistoryChart.vue'

function priceDocument(overrides: SecurityDocumentOverrides = {}): ChartDocument {
  return securityFixture({ kind: 'price', ...overrides })
}

function positionDocument(overrides: SecurityDocumentOverrides = {}): ChartDocument {
  return securityFixture({ kind: 'position', ...overrides })
}

interface LineSeries {
  id: string
  type: string
  step?: boolean | string
  connectNulls: boolean
  smooth: boolean
  data: Array<number | null>
}

function lineSeriesOf(option: ReturnType<typeof buildSecurityOption>): LineSeries {
  const series = (option as { series: LineSeries[] }).series
  return series[0]
}

beforeEach(() => {
  chartState.captured = []
  chartState.events = []
})

describe('buildSecurityOption', () => {
  it('plots an unsmoothed price line keyed by server period identity', () => {
    const doc = priceDocument({
      points: [
        { value: '101.250000', plotValue: '101.250000', status: 'ok', reason: 'observed', display: 'USD 101.25' },
        { value: null, plotValue: null, status: 'unknown', reason: 'missing_price', display: '–' },
        { value: '99.500000', plotValue: '99.500000', status: 'ok', reason: 'observed', display: 'USD 99.50' },
      ],
      periodKeys: ['security:9:price:row:1', 'security:9:price:row:2', 'security:9:price:row:3'],
    })
    const before = structuredClone(doc)
    const option = buildSecurityOption(doc)
    const series = lineSeriesOf(option)
    expect(series.type).toBe('line')
    expect(series.smooth).toBe(false)
    expect(series.connectNulls).toBe(false)
    expect(series.data).toEqual([101.25, null, 99.5])
    const xAxis = (option as { xAxis: { data: string[] } }).xAxis
    expect(xAxis.data).toEqual(['security:9:price:row:1', 'security:9:price:row:2', 'security:9:price:row:3'])
    expect(doc).toEqual(before)
  })

  it('keeps bond prices percent-of-nominal and labels the axis from metadata', () => {
    const doc = priceDocument({ unit: 'percent_of_nominal', value: '98.500000' })
    const option = buildSecurityOption(doc)
    expect(lineSeriesOf(option).data[0]).toBe(98.5)
    const yAxis = (option as { yAxis: { name: string } }).yAxis
    expect(yAxis.name).toBe('% of nominal')
  })

  it('names ordinary instrument price axes with the instrument currency', () => {
    const option = buildSecurityOption(priceDocument({ unit: 'money', value: '1.234500' }))
    expect((option as { yAxis: { name: string } }).yAxis.name).toBe('EUR')
  })

  it('keeps exact crypto quantity precision and steps the position line', () => {
    const option = buildSecurityOption(positionDocument({ value: '0.000116590' }))
    const series = lineSeriesOf(option)
    expect(series.data[0]).toBe(0.000116590)
    expect(series.step).toBe('end')
    const yAxis = (option as { yAxis: { name: string } }).yAxis
    expect(yAxis.name).toBe('quantity')
  })

  it('keeps same-date events as distinct axis categories', () => {
    const doc = positionDocument({ value: '0.000116590' })
    expect(doc.periods.map((period) => period.endDate)).toEqual(['2026-01-31', '2026-01-31'])
    const option = buildSecurityOption(doc)
    const xAxis = (option as { xAxis: { data: string[] } }).xAxis
    expect(xAxis.data).toEqual(['security:9:position:row:1', 'security:9:position:row:2'])
  })

  it('shows exact displays, statuses and reasons in the tooltip', () => {
    const doc = priceDocument({
      points: [
        { value: null, plotValue: null, knownSubtotal: '98.125', status: 'partial', reason: 'missing_price', display: 'Partial price' },
      ],
    })
    const option = buildSecurityOption(doc) as { tooltip: { formatter: (params: unknown) => string } }
    const html = option.tooltip.formatter({ dataIndex: 0 })
    expect(html).toContain('Partial price')
    expect(html).toContain('partial')
    expect(html).toContain('missing_price')
    expect(html).toContain('known subtotal 98.125')
    expect(html).not.toMatch(/percent/i)
  })

  it('escapes server strings in the tooltip', () => {
    const doc = priceDocument({ seriesLabel: 'Price<b>' })
    const option = buildSecurityOption(doc) as { tooltip: { formatter: (params: unknown) => string } }
    const html = option.tooltip.formatter({ dataIndex: 0 })
    expect(html).not.toContain('<b>')
    expect(html).toContain('&lt;b&gt;')
  })

  it('appends an annotated presentation-only carry-forward endpoint', () => {
    const doc = priceDocument({
      value: '98.500000',
      contextEffectiveDate: '2026-02-02',
    })
    const before = structuredClone(doc)
    const option = buildSecurityOption(doc)
    const xAxis = (option as { xAxis: { data: string[] } }).xAxis
    expect(xAxis.data).toHaveLength(2)
    expect(xAxis.data[1]).toBe('carry-forward:2026-02-02')
    expect(lineSeriesOf(option).data[1]).toBe(98.5)
    expect(doc).toEqual(before)
    const tooltip = (option as { tooltip: { formatter: (params: unknown) => string } }).tooltip
    const carried = tooltip.formatter({ dataIndex: 1, axisValue: 'carry-forward:2026-02-02' })
    expect(carried).toContain('carried forward')
    expect(carried).toContain('2026-01-31')
    const observed = tooltip.formatter({ dataIndex: 0, axisValue: 'security:9:price:row:1' })
    expect(observed).not.toContain('carried forward')
  })

  it.each([
    ['the last observation already sits on the effective date', { contextEffectiveDate: '2026-01-31' }],
    ['the last observation has no ok value', { contextEffectiveDate: '2026-02-02', points: [
      { value: null, plotValue: null, status: 'not_available' as const, reason: 'not_relevant' as const, display: 'N/R' },
    ] }],
    ['the document has no observations', { kind: 'price' as const, empty: true }],
  ])('appends no carry-forward when %s', (_name, overrides) => {
    const doc = priceDocument(overrides as SecurityDocumentOverrides)
    const option = buildSecurityOption(doc)
    const xAxis = (option as { xAxis: { data: string[] } }).xAxis
    expect(xAxis.data.every((key) => !key.startsWith('carry-forward:'))).toBe(true)
  })

  it('propagates unplotable values as a rendering failure, never a truncation', () => {
    const doc = priceDocument({ points: [
      { value: '1', plotValue: '9'.repeat(400), status: 'ok', reason: 'observed', display: 'big' },
    ] })
    expect(() => buildSecurityOption(doc)).toThrow(RangeError)
  })

  it('builds an honest empty option for an empty identified series', () => {
    const doc = emptySecurityFixture('price')
    const option = buildSecurityOption(doc)
    expect((option as { xAxis: { data: string[] } }).xAxis.data).toEqual([])
    expect(lineSeriesOf(option).data).toEqual([])
  })
})

describe('SecurityDataTable', () => {
  it('keeps every observation row under its server key, duplicates included', () => {
    const doc = positionDocument({ value: '0.000116590' })
    const wrapper = mount(SecurityDataTable, { props: { document: doc } })
    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].attributes('data-period-key')).toBe('security:9:position:row:1')
    expect(rows[1].attributes('data-period-key')).toBe('security:9:position:row:2')
    expect(wrapper.text()).toContain('31 Jan 2026')
    expect(wrapper.text()).toContain('0.000116590')
    wrapper.unmount()
  })

  it('states statuses, reasons and known subtotals verbatim', () => {
    const doc = priceDocument({
      points: [
        { value: null, plotValue: null, knownSubtotal: '98.125', status: 'partial', reason: 'missing_price', display: 'Partial price' },
      ],
    })
    const wrapper = mount(SecurityDataTable, { props: { document: doc } })
    const text = wrapper.text()
    expect(text).toContain('Partial price')
    expect(text).toContain('partial')
    expect(text).toContain('missing_price')
    expect(text).toContain('known subtotal 98.125')
    wrapper.unmount()
  })

  it('never lists a carry-forward row', () => {
    const doc = priceDocument({ contextEffectiveDate: '2026-02-02' })
    const wrapper = mount(SecurityDataTable, { props: { document: doc } })
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    wrapper.unmount()
  })
})

describe('SecurityHistoryChart', () => {
  async function mountChart(doc: ChartDocument, options: { requested?: boolean } = {}) {
    const wrapper = mount(SecurityHistoryChart, {
      props: {
        document: doc,
        requested: options.requested ?? true,
        'onUpdate:interaction': (next: unknown) => wrapper.setProps({ interaction: next as never }),
        'data-testid': 'security-history-chart',
      },
      slots: { fallback: () => h('div', { class: 'incumbent-fallback' }, 'incumbent line') },
    })
    for (let attempt = 0; attempt < 200; attempt += 1) {
      await flushPromises()
      await new Promise((resolve) => setTimeout(resolve, 10))
      if (
        chartState.captured.length > 0 ||
        wrapper.find('[data-testid="security-history-empty"]').exists() ||
        wrapper.find('[data-testid="security-render-error"]').exists()
      ) break
    }
    return wrapper
  }

  it('renders the renderer and the exact table for a populated document', async () => {
    const wrapper = await mountChart(priceDocument())
    expect(chartState.captured).toHaveLength(1)
    expect(wrapper.get('[data-testid="security-data-table"]').text()).toContain('98.5% of nominal')
    expect(wrapper.find('.incumbent-fallback').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows a no-data notice for an empty identified series', async () => {
    const wrapper = await mountChart(emptySecurityFixture('price'))
    expect(chartState.captured).toHaveLength(0)
    expect(wrapper.get('[data-testid="security-history-empty"]').text()).toContain('No price history')
    wrapper.unmount()
  })

  it('recovers a rendering failure with retry or the explicit legacy fallback', async () => {
    const wrapper = await mountChart(priceDocument())
    wrapper.findComponent({ name: 'EChartsSecurity' }).vm.$emit('render-error', new Error('canvas unavailable'))
    await flushPromises()
    expect(wrapper.get('[data-testid="security-render-error"]').text()).toContain('canvas unavailable')
    await wrapper.get('[data-testid="security-render-retry"]').trigger('click')
    expect(wrapper.find('[data-testid="security-render-error"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('offers the explicit user-chosen fallback on the same accepted payload', async () => {
    const wrapper = await mountChart(priceDocument())
    wrapper.findComponent({ name: 'EChartsSecurity' }).vm.$emit('render-error', new Error('canvas unavailable'))
    await flushPromises()
    await wrapper.get('[data-testid="security-render-fallback"]').trigger('click')
    expect(wrapper.find('.incumbent-fallback').exists()).toBe(true)
    expect(chartState.captured).toHaveLength(1)
    wrapper.unmount()
  })

  it('keeps zoom view-only through server period keys', async () => {
    const wrapper = await mountChart(priceDocument())
    // datazoom is bound on the inner chart wrapper, where ECharts emits it.
    wrapper.findComponent({ name: 'VChart' }).vm.$emit('datazoom', { start: 10, end: 80 })
    await flushPromises()
    expect(wrapper.emitted('update:interaction')?.length).toBeGreaterThan(0)
    const viewport = (wrapper.emitted('update:interaction')?.at(-1)?.[0] as { viewport: { firstPeriodKey: string; lastPeriodKey: string } }).viewport
    expect(viewport.firstPeriodKey).toBe('security:9:price:row:1')
    expect(viewport.lastPeriodKey).toBe('security:9:price:row:1')
    wrapper.unmount()
  })

  it('renders nothing modern when the gate did not request it', async () => {
    const wrapper = await mountChart(priceDocument(), { requested: false })
    expect(chartState.captured).toHaveLength(0)
    wrapper.unmount()
  }, 20000)
})
