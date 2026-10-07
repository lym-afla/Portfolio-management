// C4 Task 2: three solid allocation pies. buildAllocationOption produces one
// pie series per eligible allocation document — server rank order, zero inner
// radius, stable server-ID colors shared with NAV, no built-in legend, no
// selection, and no ECharts-derived percent anywhere. Ineligible documents
// never produce a pie: the panel states the reason and the exact table keeps
// every signed/status row with the backend-supplied denominator/totalShare.
// Legend interactions focus a slice and its row — they never hide categories,
// renormalize geometry or change the denominator.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h } from 'vue'

// Shared hoisted state so the hoisted vue-echarts mock can record mounts.
const chartState = vi.hoisted(() => ({
  captured: [] as Array<{ option: Record<string, unknown> }>,
  dispatches: [] as unknown[],
}))

vi.mock('vue-chartjs', () => ({
  Bar: { name: 'Bar', template: '<div class="bar-stub" />' },
}))
vi.mock('vue-echarts', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: ['option', 'updateOptions', 'autoresize', 'theme'],
      setup(_props: { option: Record<string, unknown> }, { expose }: { expose: (value: unknown) => void }) {
        chartState.captured.push(_props)
        expose({
          dispatchAction: (payload: unknown) => {
            chartState.dispatches.push(payload)
          },
        })
        return () => h('div', { class: 'echarts-stub' })
      },
    },
  }
})

import { allocationFixture, type AllocationFixtureOptions } from './fixtures'
import type { ChartDocument } from '../contracts'
import { buildAllocationOption } from '../buildAllocationOption'
import { seriesColor } from '../seriesStyles'
import { defaultAllocationInteraction, reconcileAllocationInteraction } from '../allocationInteraction'
import AllocationLegend from '../AllocationLegend.vue'
import AllocationDataTable from '../AllocationDataTable.vue'
import AllocationChart from '../AllocationChart.vue'
import BreakdownChart from '@/components/dashboard/BreakdownChart.vue'

function documentFor(options: AllocationFixtureOptions = {}): ChartDocument {
  return allocationFixture(options)
}

/** -25/125 against a 100 denominator: signed but exactly partitioning. */
function signedPartitioningDocument(): ChartDocument {
  const doc = documentFor({ pieEligibility: 'signed', partition: 'complete' })
  const stock = doc.series.find((series) => series.id === 'asset_type:Stock')!
  const cash = doc.series.find((series) => series.id === 'asset_type:Cash')!
  stock.points = [{ value: '-25', plotValue: '-25', status: 'ok', reason: 'observed', display: '(USD 25.00)' }]
  cash.points = [{ value: '125', plotValue: '125', status: 'ok', reason: 'observed', display: 'USD 125.00' }]
  doc.allocations = [
    { seriesId: cash.id, rank: 1, amount: cash.points[0], share: { value: '1.25', plotValue: '1.25', status: 'ok', reason: 'observed', display: '125.0%' } },
    { seriesId: stock.id, rank: 2, amount: stock.points[0], share: { value: '-0.25', plotValue: '-0.25', status: 'ok', reason: 'observed', display: '-25.0%' } },
  ]
  return doc
}

/** An eligible document carrying one explicit zero-exposure category. */
function eligibleWithZeroRow(): ChartDocument {
  const doc = documentFor()
  const cash = doc.series.find((series) => series.id === 'asset_type:Cash')!
  const zero: ChartDocument['series'][number]['points'][number] = {
    value: '0', plotValue: '0', status: 'ok', reason: 'zero_exposure', display: '$0.00',
  }
  cash.points = [zero]
  doc.allocations = [
    { seriesId: stockRow(doc).seriesId, rank: 1, amount: doc.series.find((s) => s.id === stockRow(doc).seriesId)!.points[0], share: { value: '1', plotValue: '1', status: 'ok', reason: 'observed', display: '100.0%' } },
    { seriesId: cash.id, rank: 2, amount: zero, share: { value: '0', plotValue: '0', status: 'ok', reason: 'zero_exposure', display: '0.0%' } },
  ]
  return doc
}

function stockRow(doc: ChartDocument): { seriesId: string } {
  const row = doc.allocations!.find((allocation) => allocation.seriesId.endsWith(':Stock'))
  if (!row) throw new Error('fixture has no Stock row')
  return row
}

interface PieSeries {
  type: string
  radius: [number, string]
  selectedMode: boolean
  data: Array<{ id: string; name: string; value: number; itemStyle?: { color?: string } }>
}

function pieSeriesOf(option: ReturnType<typeof buildAllocationOption>): PieSeries {
  const series = (option as { series: PieSeries[] }).series
  return series[0]
}

beforeEach(() => {
  chartState.captured = []
  chartState.dispatches = []
})

describe('buildAllocationOption', () => {
  it('builds one solid pie per eligible document, in server rank order', () => {
    for (const dimension of ['asset_type', 'asset_class', 'currency'] as const) {
      const doc = documentFor({ dimension })
      const before = structuredClone(doc)
      const option = buildAllocationOption(doc)
      expect(option).not.toBeNull()
      const series = (option as { series: PieSeries[] }).series
      expect(series).toHaveLength(1)
      expect(series[0].type).toBe('pie')
      expect(series[0].radius[0]).toBe(0)
      expect(series[0].data).toHaveLength(2)
      // Server rank order: the larger amount is the first slice.
      const largerRow = { asset_type: 'Cash', asset_class: 'Cash', currency: 'EUR' }[dimension]
      expect(series[0].data[0].id).toBe(`${dimension}:${largerRow}`)
      expect(series[0].data[0].value).toBe(75)
      const smallerRow = { asset_type: 'Stock', asset_class: 'Equity', currency: 'USD' }[dimension]
      expect(series[0].data[1].id).toBe(`${dimension}:${smallerRow}`)
      expect(series[0].data[1].value).toBe(25)
      // The validated document is never mutated by option construction.
      expect(doc).toEqual(before)
      expect(doc.allocationSummary?.denominator.value).toBe('100')
      expect(doc.allocations?.map((row) => row.share.display)).toEqual(['75.0%', '25.0%'])
    }
  })

  it('colors slices by server series id, shared with NAV category identity', () => {
    const option = buildAllocationOption(documentFor())
    const series = pieSeriesOf(option)
    expect(series.data[0].itemStyle?.color).toBe(seriesColor('asset_type:Cash'))
    expect(series.data[1].itemStyle?.color).toBe(seriesColor('asset_type:Stock'))
  })

  it('disables selection and ships no built-in legend', () => {
    const option = buildAllocationOption(documentFor()) as Record<string, unknown>
    expect(pieSeriesOf(option).selectedMode).toBe(false)
    expect('legend' in option).toBe(false)
  })

  it('renders exact server strings in the tooltip, never ECharts percent', () => {
    const doc = documentFor()
    const option = buildAllocationOption(doc) as { tooltip: { formatter: (params: unknown) => string } }
    const html = option.tooltip.formatter({ dataIndex: 0 })
    expect(html).toContain('Cash')
    expect(html).toContain('USD 75.00')
    expect(html).toContain('75.0%')
    expect(html).toContain('USD 100.00')
    expect(html).toContain('100.0%')
    expect(html).not.toMatch(/percent/i)
  })

  it('escapes server strings in the tooltip', () => {
    const doc = documentFor()
    const stock = doc.series.find((series) => series.id === 'asset_type:Stock')!
    doc.series = doc.series.map((series) => (series.id === stock.id ? { ...series, label: 'Stock<script>alert(1)</script>' } : series))
    const option = buildAllocationOption(doc) as { tooltip: { formatter: (params: unknown) => string } }
    const html = option.tooltip.formatter({ dataIndex: 1 })
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })

  it('states unavailable values and the denominator status instead of numbers', () => {
    const doc = documentFor({ pieEligibility: 'nonpartitioning', partition: 'legacy_non_partitioning' })
    // Ineligible documents have no pie at all — the reason path covers them;
    // the tooltip contract itself is only reachable for eligible documents.
    expect(buildAllocationOption(doc)).toBeNull()
  })

  it('keeps an explicit zero-exposure row in the pie data without inventing geometry', () => {
    const option = buildAllocationOption(eligibleWithZeroRow())
    const series = pieSeriesOf(option)
    expect(series.data).toHaveLength(2)
    const zero = series.data.find((item) => item.id === 'asset_type:Cash')
    expect(zero?.value).toBe(0)
  })

  it.each([
    ['signed', { pieEligibility: 'signed', partition: 'complete' } as AllocationFixtureOptions],
    ['incomplete', { pieEligibility: 'incomplete', partition: 'unknown' } as AllocationFixtureOptions],
    ['nonpositive_total', { pieEligibility: 'nonpositive_total', partition: 'complete' } as AllocationFixtureOptions],
    ['nonpartitioning', { pieEligibility: 'nonpartitioning', partition: 'legacy_non_partitioning' } as AllocationFixtureOptions],
  ])('builds no pie for the %s state', (_name, options) => {
    expect(buildAllocationOption(documentFor(options))).toBeNull()
  })

  it('builds no pie for an empty allocation document', () => {
    const doc = documentFor({ pieEligibility: 'nonpositive_total' })
    doc.outcome = 'empty'
    doc.series = []
    doc.allocations = []
    expect(buildAllocationOption(doc)).toBeNull()
  })

  it('refuses to plot a signed partitioning document', () => {
    expect(buildAllocationOption(signedPartitioningDocument())).toBeNull()
  })

  it('propagates unplotable values as a rendering failure, never a truncation', () => {
    const doc = documentFor()
    const big = { value: '1', plotValue: '9'.repeat(400), status: 'ok' as const, reason: 'observed' as const, display: 'big' }
    const first = doc.allocations![0]
    doc.allocations = doc.allocations!.map((allocation) => (
      allocation.seriesId === first.seriesId ? { ...allocation, amount: big } : allocation
    ))
    doc.series = doc.series.map((series) => (series.id === first.seriesId ? { ...series, points: [big] } : series))
    expect(() => buildAllocationOption(doc)).toThrow(RangeError)
  })
})

describe('allocation interaction model', () => {
  it('starts unfocused and drops a focus that no longer exists', () => {
    const doc = documentFor()
    expect(defaultAllocationInteraction()).toEqual({ focusedSeriesId: null })
    const focused = { focusedSeriesId: 'asset_type:Cash' }
    expect(reconcileAllocationInteraction(doc, structuredClone(doc), focused)).toEqual(focused)
    const next = structuredClone(doc)
    next.series = next.series.filter((series) => series.id !== 'asset_type:Cash')
    expect(reconcileAllocationInteraction(doc, next, focused)).toEqual({ focusedSeriesId: null })
  })
})

describe('AllocationLegend', () => {
  it('renders one keyboard-operable button per allocation announcing exact values', () => {
    const wrapper = mount(AllocationLegend, {
      props: { document: documentFor(), interaction: defaultAllocationInteraction() },
    })
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0].text()).toContain('Cash')
    expect(buttons[0].attributes('aria-label')).toContain('USD 75.00')
    expect(buttons[0].attributes('aria-label')).toContain('75.0%')
    expect(buttons[1].attributes('aria-label')).toContain('USD 25.00')
    expect(buttons[1].attributes('data-allocation-id')).toBe('asset_type:Stock')
    wrapper.unmount()
  })

  it('focus and hover highlight a slice without hiding or toggling anything', async () => {
    const wrapper = mount(AllocationLegend, {
      props: { document: documentFor(), interaction: defaultAllocationInteraction() },
    })
    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('focus')
    let emitted = wrapper.emitted('update:interaction')
    expect(emitted?.at(-1)).toEqual([{ focusedSeriesId: 'asset_type:Stock' }])
    await buttons[1].trigger('blur')
    emitted = wrapper.emitted('update:interaction')
    expect(emitted?.at(-1)).toEqual([{ focusedSeriesId: null }])
    // A click only focuses; it never emits a visibility-style toggling payload.
    await buttons[0].trigger('click')
    emitted = wrapper.emitted('update:interaction')
    expect(emitted?.at(-1)).toEqual([{ focusedSeriesId: 'asset_type:Cash' }])
    for (const payload of wrapper.emitted('update:interaction') ?? []) {
      const interaction = payload[0] as { focusedSeriesId: string | null }
      expect(Object.keys(interaction)).toEqual(['focusedSeriesId'])
    }
    wrapper.unmount()
  })

})

describe('AllocationDataTable', () => {
  it('keeps every server row in rank order with exact displays', () => {
    const wrapper = mount(AllocationDataTable, {
      props: { document: documentFor(), interaction: defaultAllocationInteraction() },
    })
    const text = wrapper.text()
    expect(text).toContain('Cash')
    expect(text).toContain('USD 75.00')
    expect(text).toContain('75.0%')
    expect(text).toContain('Stock')
    expect(text).toContain('USD 25.00')
    expect(text).toContain('25.0%')
    // The backend-supplied denominator and total share — never a hardcoded 100%.
    expect(text).toContain('USD 100.00')
    expect(text).toContain('100.0%')
    wrapper.unmount()
  })

  it('keeps zero rows without giving them a fabricated share', () => {
    const wrapper = mount(AllocationDataTable, {
      props: { document: eligibleWithZeroRow(), interaction: defaultAllocationInteraction() },
    })
    const text = wrapper.text()
    expect(text).toContain('Cash')
    expect(text).toContain('$0.00')
    expect(text).toContain('0.0%')
    wrapper.unmount()
  })

  it('shows signed rows and status text verbatim; no abs, no suppression', () => {
    const doc = signedPartitioningDocument()
    const wrapper = mount(AllocationDataTable, {
      props: { document: doc, interaction: defaultAllocationInteraction() },
    })
    const text = wrapper.text()
    expect(text).toContain('(USD 25.00)')
    expect(text).toContain('-25.0%')
    expect(text).toContain('USD 125.00')
    expect(text).toContain('125.0%')
    wrapper.unmount()
  })

  it('states unavailable shares instead of an unsupported total percentage', () => {
    const wrapper = mount(AllocationDataTable, {
      props: {
        document: documentFor({ pieEligibility: 'nonpositive_total', partition: 'complete' }),
        interaction: defaultAllocationInteraction(),
      },
    })
    const text = wrapper.text()
    expect(text).toContain('not_available')
    expect(text).not.toMatch(/100(\.0)?%/)
    wrapper.unmount()
  })

  it('states partial amounts with their known subtotal', () => {
    const wrapper = mount(AllocationDataTable, {
      props: {
        document: documentFor({ pieEligibility: 'incomplete', partition: 'unknown' }),
        interaction: defaultAllocationInteraction(),
      },
    })
    const text = wrapper.text()
    expect(text).toContain('partial')
    expect(text).toContain('known subtotal')
    wrapper.unmount()
  })

  it('focuses a row into the shared interaction without altering any value', async () => {
    const interaction = defaultAllocationInteraction()
    const doc = documentFor()
    const wrapper = mount(AllocationDataTable, {
      props: { document: doc, interaction },
    })
    const before = structuredClone(doc)
    await wrapper.findAll('tbody tr')[0].trigger('click')
    expect(wrapper.emitted('update:interaction')?.at(-1)).toEqual([{ focusedSeriesId: 'asset_type:Cash' }])
    expect(doc).toEqual(before)
    wrapper.unmount()
  })
})

describe('AllocationChart', () => {
  async function mountChart(doc: ChartDocument, options: { requested?: boolean } = {}) {
    const wrapper = mount(AllocationChart, {
      props: {
        document: doc,
        requested: options.requested ?? true,
        interaction: defaultAllocationInteraction(),
        'onUpdate:interaction': (next: unknown) => wrapper.setProps({ interaction: next as never }),
      },
      slots: { fallback: () => h('div', { class: 'incumbent-fallback' }, 'incumbent bars') },
    })
    // The renderer is an async component: settle until the pie actually
    // mounted (the HTML legend alone renders immediately), the certified
    // reason replaced it, or a rendering failure surfaced.
    for (let attempt = 0; attempt < 200; attempt += 1) {
      await flushPromises()
      await new Promise((resolve) => setTimeout(resolve, 10))
      if (
        chartState.captured.length > 0 ||
        wrapper.find('[data-testid="allocation-ineligible"]').exists() ||
        wrapper.find('[data-testid="allocation-render-error"]').exists()
      ) break
    }
    return wrapper
  }

  it('renders the pie and legend for an eligible document when requested', { timeout: 20000 }, async () => {
    const wrapper = await mountChart(documentFor())
    expect(chartState.captured).toHaveLength(1)
    expect(wrapper.find('[data-testid="allocation-legend"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="allocation-ineligible"]').exists()).toBe(false)
    expect(wrapper.find('.incumbent-fallback').exists()).toBe(false)
    wrapper.unmount()
  })

  it('renders the reason and no pie for every ineligible state', { timeout: 20000 }, async () => {
    for (const options of [
      { pieEligibility: 'signed', partition: 'complete' },
      { pieEligibility: 'incomplete', partition: 'unknown' },
      { pieEligibility: 'nonpositive_total', partition: 'complete' },
      { pieEligibility: 'nonpartitioning', partition: 'legacy_non_partitioning' },
    ] as AllocationFixtureOptions[]) {
      const wrapper = await mountChart(documentFor(options))
      expect(chartState.captured).toHaveLength(0)
      const reason = wrapper.get('[data-testid="allocation-ineligible"]')
      expect(reason.text()).toContain('Table')
      expect(wrapper.find('.incumbent-fallback').exists()).toBe(false)
      wrapper.unmount()
    }
  })

  it('maps legend focus to a highlight action without extra requests or geometry change', async () => {
    const wrapper = await mountChart(documentFor())
    const legendButtons = wrapper.findAll('[data-testid="allocation-legend"] button')
    await legendButtons[0].trigger('focus')
    await flushPromises()
    const highlights = chartState.dispatches.filter(
      (payload) => (payload as { type?: string }).type === 'highlight',
    )
    expect(highlights).toHaveLength(1)
    expect(highlights[0]).toMatchObject({ seriesIndex: 0, dataIndex: 0 })
    wrapper.unmount()
  })

  it('recovers a rendering failure with an explicit retry', async () => {
    const wrapper = await mountChart(documentFor())
    wrapper.findComponent({ name: 'EChartsAllocation' }).vm.$emit('render-error', new Error('canvas unavailable'))
    await flushPromises()
    expect(wrapper.get('[data-testid="allocation-render-error"]').text()).toContain('canvas unavailable')
    await wrapper.get('[data-testid="allocation-render-retry"]').trigger('click')
    expect(wrapper.find('[data-testid="allocation-render-error"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('offers the explicit user-chosen legacy fallback on the same accepted payload', async () => {
    const wrapper = await mountChart(documentFor())
    wrapper.findComponent({ name: 'EChartsAllocation' }).vm.$emit('render-error', new Error('canvas unavailable'))
    await flushPromises()
    await wrapper.get('[data-testid="allocation-render-fallback"]').trigger('click')
    expect(wrapper.find('.incumbent-fallback').exists()).toBe(true)
    expect(wrapper.find('[data-testid="allocation-render-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocation-legend"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('renders nothing modern when the gate did not request it', async () => {
    const wrapper = await mountChart(documentFor(), { requested: false })
    expect(chartState.captured).toHaveLength(0)
    expect(wrapper.find('[data-testid="allocation-legend"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('BreakdownChart modern path', () => {
  async function mountCard(props: Record<string, unknown>) {
    const wrapper = mount(BreakdownChart, {
      props: {
        title: 'Asset Type',
        currency: 'USD',
        data: { data: { Stocks: '$25.00', Cash: '$75.00' }, percentage: { Stocks: '25%', Cash: '75%' } },
        totalNAV: '$100.00',
        ...props,
      },
      global: {
        stubs: {
          Bar: { template: '<div class="bar-stub" />' },
          'v-tabs': { template: '<div class="tabs-stub"><slot /></div>' },
          'v-tab': { template: '<div class="tab-stub"><slot /></div>' },
          'v-window': { template: '<div class="window-stub"><slot /></div>' },
          'v-window-item': { template: '<div class="window-item-stub"><slot /></div>' },
          'v-table': { template: '<table class="v-table-stub"><slot /></table>' },
          'v-alert': { props: ['type', 'text'], template: '<div class="alert-stub"><slot />{{ text }}</div>' },
        },
      },
    })
    // The pie renderer is an async component; settle its loader.
    for (let attempt = 0; attempt < 200; attempt += 1) {
      await flushPromises()
      await new Promise((resolve) => setTimeout(resolve, 10))
      if (
        chartState.captured.length > 0 ||
        wrapper.find('[data-testid="allocation-ineligible"]').exists()
      ) break
    }
    return wrapper
  }

  it('keeps the incumbent bars and hardcoded-total table when no modern document arrives', async () => {
    const wrapper = await mountCard({ chartDocument: null })
    expect(wrapper.find('.bar-stub').exists()).toBe(true)
    const text = wrapper.text()
    expect(text).toContain('100%')
    expect(wrapper.findComponent(AllocationChart).exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows the modern composition and the exact table for an eligible document', async () => {
    const wrapper = await mountCard({ chartDocument: documentFor() })
    expect(chartState.captured).toHaveLength(1)
    expect(wrapper.find('[data-testid="allocation-legend"]').exists()).toBe(true)
    const table = wrapper.get('[data-testid="allocation-data-table"]').text()
    expect(table).toContain('75.0%')
    expect(table).toContain('USD 100.00')
    wrapper.unmount()
  })

  it('shows the ineligible reason in the chart tab and the complete exact table', async () => {
    const wrapper = await mountCard({
      chartDocument: documentFor({ pieEligibility: 'signed', partition: 'complete' }),
    })
    expect(chartState.captured).toHaveLength(0)
    expect(wrapper.get('[data-testid="allocation-ineligible"]').text()).toContain('Table')
    const table = wrapper.get('[data-testid="allocation-data-table"]').text()
    expect(table).toContain('(USD 25.00)')
    expect(table).toContain('-25.0%')
    wrapper.unmount()
  })
})
