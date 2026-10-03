// C3 Task 2: accessible legend, exact-value table and shared inspection.
// Assertions check the resulting controlled state and its actual option
// mapping — not only emitted events. Server displays are exact; the two IRRs
// are independently operable under fixed names; the table shows every series
// and the full NAV from doc.totals regardless of hidden categories.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { parseNavEnvelope } from '../parseChartEnvelope'
import type { ChartDocument } from '../contracts'
import type { ChartInteraction } from '../interaction'
import { buildNavOption } from '../buildNavOption'
import { defaultInteraction, reconcileInteraction } from '../interaction'
import ChartLegend from '../ChartLegend.vue'
import ChartDataTable from '../ChartDataTable.vue'
import ChartInspection from '../ChartInspection.vue'
import { navWireFixture } from './navFixtures'

function emittedInteraction(wrapper: { emitted: (event: string) => unknown[][] | undefined }, index = 0): ChartInteraction {
  const events = wrapper.emitted('update:interaction') as ChartInteraction[][] | undefined
  if (!events || !events[index]) throw new Error('missing update:interaction event')
  return events[index][0]
}

function parsedDocument(): ChartDocument {
  const result = parseNavEnvelope(navWireFixture('asset_type', 'M'))
  if (result.capability !== 'v2') throw new Error('fixture must parse as v2')
  return result.document
}

describe('ChartLegend', () => {
  it('renders both IRR controls under their exact fixed names', () => {
    const doc = parsedDocument()
    const wrapper = mount(ChartLegend, {
      props: { document: doc, interaction: defaultInteraction(doc) },
    })
    const buttons = wrapper.findAll('button')
    const texts = buttons.map((button) => button.text())
    expect(texts).toContain('Since-inception IRR (annualized)')
    expect(texts).toContain('Interval IRR (annualized)')
    expect(buttons.map((button) => button.attributes('aria-pressed'))).toEqual(
      doc.series.map(() => 'true'),
    )
  })

  it('toggles each series independently and maps to excluded option series', async () => {
    const doc = parsedDocument()
    const interaction = defaultInteraction(doc)
    const wrapper = mount(ChartLegend, { props: { document: doc, interaction } })
    const intervalButton = wrapper.findAll('button').find((button) => button.text() === 'Interval IRR (annualized)')!
    await intervalButton.trigger('click')
    const update = emittedInteraction(wrapper, 0)
    expect(update.visibleSeriesIds).not.toContain('metric:irr_interval')
    expect(update.visibleSeriesIds).toContain('metric:irr_inception')
    expect(update.visibleSeriesIds).toContain('asset_type:Stock')
    const option = buildNavOption(doc, update)
    const ids = (option.series as Array<{ id: string }>).map((series) => series.id)
    expect(ids).not.toContain('metric:irr_interval')
    expect(ids).toContain('metric:irr_inception')
    // Toggling back restores visibility independently.
    await wrapper.setProps({ interaction: update })
    await intervalButton.trigger('click')
    const restored = emittedInteraction(wrapper, 1)
    expect(restored.visibleSeriesIds).toContain('metric:irr_interval')
  })

  it('keeps keyboard focus on the same control across a same-identity refresh', async () => {
    const doc = parsedDocument()
    const wrapper = mount(ChartLegend, {
      props: { document: doc, interaction: defaultInteraction(doc) },
      attachTo: globalThis.document.body,
    })
    const intervalButton = wrapper.findAll('button').find((button) => button.text() === 'Interval IRR (annualized)')!
    const before = intervalButton.element
    before.focus()
    await wrapper.setProps({ document: parsedDocument() })
    // Same-identity refresh keeps the same focused node (stable id keys).
    expect(wrapper.findAll('button').find((button) => button.text() === 'Interval IRR (annualized)')!.element)
      .toBe(before)
    wrapper.unmount()
  })
})

describe('ChartDataTable', () => {
  const mountTable = (doc: ChartDocument, interaction = defaultInteraction(doc)) =>
    mount(ChartDataTable, { props: { document: doc, interaction } })

  it('exposes a caption, scoped headers, every series and the full-NAV column', () => {
    const doc = parsedDocument()
    const wrapper = mountTable(doc)
    expect(wrapper.find('caption').text()).toBe('Exact values by period')
    const columnHeaders = wrapper.findAll('thead th[scope="col"]')
    expect(columnHeaders.map((header) => header.text())).toEqual([
      'Period', 'Interval', 'Stock', 'Cash', 'IRR (RHS)', 'Rolling IRR (RHS)',
      'Portfolio NAV (all categories)',
    ])
    expect(wrapper.findAll('tbody th[scope="row"]').length).toBe(doc.periods.length)
  })

  it('renders exact server displays and marks unavailable points with status and reason', () => {
    // value_contributions carries an absent point (return, pattern 2).
    const contributions = parseNavEnvelope(navWireFixture('value_contributions', 'M'))
    if (contributions.capability !== 'v2') throw new Error('expected v2')
    const wrapper = mountTable(contributions.document)
    const rows = wrapper.findAll('tbody tr')
    const returnColumn = 2 // after Period/Interval: opening_nav 0, contributions 1, return 2
    const returnCells = rows.map((row) => row.findAll('td.chart-table__value')[returnColumn].text())
    expect(returnCells[0]).toContain('unknown')
    expect(returnCells[0]).toContain('absent_unclassified')
    expect(returnCells[0]).not.toMatch(/^0/)
    // Totals column shows the exact full-NAV displays from doc.totals.
    const totalCells = rows.map((row) => row.findAll('td.chart-table__value').at(-1)!.text())
    expect(totalCells[0]).toBe(contributions.document.totals![0].display)
    expect(totalCells[2]).toMatch(/partial/i)
    expect(totalCells[2]).toContain('known subtotal 90000')
    // Partial calendar periods are labelled, distinct from valuation status.
    expect(rows[3].find('th .chart-table__partial').text()).toBe('partial calendar period')
  })

  it('shows the full NAV regardless of hidden categories', () => {
    const doc = parsedDocument()
    const hidden = { ...defaultInteraction(doc), visibleSeriesIds: ['metric:irr_inception'] }
    const wrapper = mountTable(doc, hidden)
    const header = wrapper.findAll('thead th[scope="col"]').at(-1)!.text()
    expect(header).toBe('Portfolio NAV (all categories)')
    expect(wrapper.findAll('tbody tr')[0].findAll('td.chart-table__value').at(-1)!.text())
      .toBe(doc.totals![0].display)
  })

  it('selects the inspected period by click and by keyboard', async () => {
    const doc = parsedDocument()
    const interaction = defaultInteraction(doc)
    const wrapper = mountTable(doc, interaction)
    const row = wrapper.findAll('tbody tr')[1]
    await row.trigger('click')
    let update = emittedInteraction(wrapper)
    expect(update.inspectedPeriodKey).toBe(doc.periods[1].key)
    expect(update.visibleSeriesIds).toEqual(interaction.visibleSeriesIds)
    await wrapper.setProps({ interaction: update })
    await wrapper.findAll('tbody tr')[2].trigger('keydown', { key: 'Enter' })
    update = emittedInteraction(wrapper, 1)
    expect(update.inspectedPeriodKey).toBe(doc.periods[2].key)
  })

  it('keeps HTML-looking series names inert text', () => {
    const doc = parsedDocument()
    const hostile = {
      ...doc,
      series: doc.series.map((series, index) =>
        index === 1 ? { ...series, label: '<img src=x onerror=window.__c3xss=1>Stock' } : series),
    }
    const wrapper = mountTable(hostile)
    expect(wrapper.find('thead img').exists()).toBe(false)
    expect(wrapper.findAll('thead th[scope="col"]')[3].text()).toContain('<img src=x')
  })
})

describe('ChartInspection', () => {
  const mountInspection = (doc: ChartDocument, interaction = defaultInteraction(doc)) =>
    mount(ChartInspection, { props: { document: doc, interaction } })

  it('shows exact displays, units and both horizon semantics', () => {
    const doc = parsedDocument()
    const interaction = { ...defaultInteraction(doc), inspectedPeriodKey: doc.periods[1].key }
    const wrapper = mountInspection(doc, interaction)
    const text = wrapper.text()
    expect(text).toContain(doc.periods[1].displayLabel)
    expect(text).toContain(`${doc.periods[1].interval.startDate} – ${doc.periods[1].interval.endDate}`)
    expect(text).toContain('reporting currency USD')
    expect(text).toContain('annualized percentage')
    expect(text).toContain('Portfolio NAV (all categories)')
    expect(text).toContain(doc.totals![1].display)
    const inceptionInteraction = { ...interaction, inspectedPeriodKey: doc.periods[0].key }
    const first = mountInspection(doc, inceptionInteraction)
    expect(first.text()).toContain(`Inception to ${doc.periods[0].interval.endDate}`)
  })

  it('emits an ordered viewport from the native selects and swaps reversed picks', async () => {
    const doc = parsedDocument()
    const interaction = defaultInteraction(doc)
    const wrapper = mountInspection(doc, interaction)
    const selects = wrapper.findAll('select')
    await selects[0].setValue(doc.periods[2].key)
    const first = emittedInteraction(wrapper, 0)
    expect(first.viewport).toEqual({ firstPeriodKey: doc.periods[2].key, lastPeriodKey: doc.periods[3].key })
    // Changing viewport never touches inspection or visibility.
    expect(first.inspectedPeriodKey).toBe(interaction.inspectedPeriodKey)
    expect(first.visibleSeriesIds).toEqual(interaction.visibleSeriesIds)
    await wrapper.setProps({ interaction: first })
    await selects[1].setValue(doc.periods[0].key)
    const swapped = emittedInteraction(wrapper, 1)
    expect(swapped.viewport).toEqual({ firstPeriodKey: doc.periods[0].key, lastPeriodKey: doc.periods[2].key })
  })

  it('reset zoom clears only the viewport', async () => {
    const doc = parsedDocument()
    const interaction = {
      ...defaultInteraction(doc),
      inspectedPeriodKey: doc.periods[0].key,
      viewport: { firstPeriodKey: doc.periods[0].key, lastPeriodKey: doc.periods[1].key },
    }
    const wrapper = mountInspection(doc, interaction)
    await wrapper.find('.chart-inspection__reset').trigger('click')
    const update = emittedInteraction(wrapper, 0)
    expect(update.viewport).toBeNull()
    expect(update.inspectedPeriodKey).toBe(doc.periods[0].key)
  })
})

describe('reconcileInteraction across same-context refresh', () => {
  it('retains surviving hidden ids and shows newly introduced ids', () => {
    const previous = parsedDocument()
    const state = defaultInteraction(previous)
    const hidden = {
      ...state,
      visibleSeriesIds: state.visibleSeriesIds.filter((id) => id !== 'asset_type:Cash'),
    }
    const nextRaw = navWireFixture('asset_type', 'M')
    // A newly introduced category must appear visible; the previously hidden
    // Cash must stay hidden — the two cases must remain distinguishable.
    nextRaw.chartV2.series = [
      ...nextRaw.chartV2.series,
      {
        id: 'asset_type:Bond', label: 'Bond', metric: 'category_nav', role: 'bar', axis: 'money',
        unit: { kind: 'money', currency: 'USD', plotDivisor: '1000' },
        points: nextRaw.chartV2.series[1].points,
        category: { kind: 'asset_type', code: 'Bond' },
      },
    ]
    const nextResult = parseNavEnvelope(nextRaw)
    if (nextResult.capability !== 'v2') throw new Error('expected v2')
    const next = nextResult.document
    const reconciled = reconcileInteraction(previous, next, hidden)
    expect(reconciled.visibleSeriesIds).not.toContain('asset_type:Cash')
    expect(reconciled.visibleSeriesIds).toContain('asset_type:Bond')
    expect(reconciled.visibleSeriesIds).toContain('metric:irr_interval')
  })

  it('retains mapped viewport and inspected keys, clearing invalid ones', () => {
    const previous = parsedDocument()
    const state: ChartInteraction = {
      visibleSeriesIds: previous.series.map((series) => series.id),
      viewport: { firstPeriodKey: previous.periods[0].key, lastPeriodKey: previous.periods[2].key },
      inspectedPeriodKey: previous.periods[1].key,
    }
    const sameKeys = parsedDocument()
    const kept = reconcileInteraction(previous, sameKeys, state)
    expect(kept.viewport).toEqual(state.viewport)
    expect(kept.inspectedPeriodKey).toBe(state.inspectedPeriodKey)
    const otherFrequency = parseNavEnvelope(navWireFixture('asset_type', 'Q'))
    if (otherFrequency.capability !== 'v2') throw new Error('expected v2')
    const cleared = reconcileInteraction(previous, otherFrequency.document, state)
    expect(cleared.viewport).toBeNull()
    expect(cleared.inspectedPeriodKey).toBeNull()
  })
})
