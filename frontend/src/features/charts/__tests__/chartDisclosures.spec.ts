// Phase C Task 6: exact tables default to collapsed disclosures and security
// observations paginate client-side over the accepted document. RED-first:
// these were written against the always-visible tables and failed before the
// disclosure/pagination implementation landed.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { ChartDocument } from '../contracts'
import ChartDataTable from '../ChartDataTable.vue'
import SecurityDataTable from '../SecurityDataTable.vue'
import { defaultInteraction } from '../interaction'
import { parseNavEnvelope } from '../parseChartEnvelope'
import { navWireFixture } from './navFixtures'
import { securityFixture, type SecurityDocumentOverrides } from './securityFixtures'

function navDocument(): ChartDocument {
  const parsed = parseNavEnvelope(navWireFixture('asset_type', 'M'))
  if (parsed.capability !== 'v2') throw new Error('fixture must parse as v2')
  return parsed.document
}

function securityDocument(overrides: SecurityDocumentOverrides = {}): ChartDocument {
  return securityFixture(overrides)
}

/** A long observation document: `count` same-date position events under
    distinct server keys — the duplicate-date identity must survive paging. */
function longSecurityDocument(count: number): ChartDocument {
  const points = Array.from({ length: count }, () => ({
    value: '0.000116590', plotValue: '0.000116590', status: 'ok' as const, reason: 'observed' as const, display: '0.000116590',
  }))
  const keys = points.map((_entry, index) => `security:9:position:row:${index + 1}`)
  return securityDocument({ kind: 'position', points, periodKeys: keys })
}

function expandTable(wrapper: ReturnType<typeof mount>, testId = 'chart-table-toggle') {
  return wrapper.find(`[data-testid="${testId}"]`).trigger('click')
}

describe('NAV exact table disclosure (phase C)', () => {
  it('collapses the table behind a labelled button by default', () => {
    const wrapper = mount(ChartDataTable, { props: { document: navDocument(), interaction: defaultInteraction(navDocument()) } })
    const toggle = wrapper.get('[data-testid="chart-table-toggle"]')
    expect(toggle.text()).toContain('Show exact values by period')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('table').exists()).toBe(false)
    wrapper.unmount()
  })

  it('expands on click, shows the exact table with the full-NAV totals, and relabels', async () => {
    const doc = navDocument()
    const wrapper = mount(ChartDataTable, { props: { document: doc, interaction: defaultInteraction(doc) } })
    await expandTable(wrapper)
    const toggle = wrapper.get('[data-testid="chart-table-toggle"]')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(toggle.text()).toContain('Hide exact values by period')
    expect(wrapper.find('caption').text()).toBe('Exact values by period')
    const text = wrapper.find('table').text()
    expect(text).toContain('Portfolio NAV (all categories)')
    expect(text).toContain(doc.totals![0].display)
    await toggle.trigger('click')
    expect(wrapper.find('table').exists()).toBe(false)
    wrapper.unmount()
  })

  it('uses a native button: keyboard Enter/Space activation is the platform contract', () => {
    const wrapper = mount(ChartDataTable, { props: { document: navDocument(), interaction: defaultInteraction(navDocument()) } })
    const toggle = wrapper.get('[data-testid="chart-table-toggle"]')
    expect(toggle.element.tagName).toBe('BUTTON')
    expect(toggle.attributes('type')).toBe('button')
    wrapper.unmount()
  })
})

describe('security observation table disclosure (phase C)', () => {
  it('collapses behind "Show exact values by observation" by default', () => {
    const wrapper = mount(SecurityDataTable, { props: { document: securityDocument() } })
    const toggle = wrapper.get('[data-testid="security-table-toggle"]')
    expect(toggle.text()).toContain('Show exact values by observation')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('table').exists()).toBe(false)
    wrapper.unmount()
  })

  it('paginates client-side over the accepted document: 25 rows initially', async () => {
    const doc = longSecurityDocument(60)
    const wrapper = mount(SecurityDataTable, { props: { document: doc } })
    await expandTable(wrapper, 'security-table-toggle')
    let rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(25)
    expect(rows[0].attributes('data-period-key')).toBe('security:9:position:row:1')
    expect(rows[24].attributes('data-period-key')).toBe('security:9:position:row:25')
    expect(wrapper.get('[data-testid="security-table-range"]').text()).toContain('1–25 of 60')
    await wrapper.get('[data-testid="security-table-next"]').trigger('click')
    rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(25)
    expect(rows[0].attributes('data-period-key')).toBe('security:9:position:row:26')
    await wrapper.get('[data-testid="security-table-next"]').trigger('click')
    rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(10)
    expect(rows[9].attributes('data-period-key')).toBe('security:9:position:row:60')
    expect(wrapper.get('[data-testid="security-table-next"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="security-table-prev"]').trigger('click')
    expect(wrapper.findAll('tbody tr')[0].attributes('data-period-key')).toBe('security:9:position:row:26')
    wrapper.unmount()
  })

  it('keeps same-date observations distinct across pages (server keys, never dates)', async () => {
    const doc = longSecurityDocument(30)
    const wrapper = mount(SecurityDataTable, { props: { document: doc } })
    await expandTable(wrapper, 'security-table-toggle')
    const keys = wrapper.findAll('tbody tr').map((row) => row.attributes('data-period-key'))
    expect(new Set(keys).size).toBe(25)
    expect(new Set(doc.periods.map((period) => period.endDate)).size).toBe(1)
    wrapper.unmount()
  })

  it('offers 25/50/100 page sizes and re-slices without refetching', async () => {
    const doc = longSecurityDocument(60)
    const wrapper = mount(SecurityDataTable, { props: { document: doc } })
    await expandTable(wrapper, 'security-table-toggle')
    const options = wrapper.findAll('[data-testid="security-table-page-size"] option').map((option) => option.text())
    expect(options).toEqual(['25', '50', '100'])
    await wrapper.get('[data-testid="security-table-page-size"]').setValue('50')
    expect(wrapper.findAll('tbody tr')).toHaveLength(50)
    expect(wrapper.get('[data-testid="security-table-range"]').text()).toContain('1–50 of 60')
    await wrapper.get('[data-testid="security-table-page-size"]').setValue('100')
    expect(wrapper.findAll('tbody tr')).toHaveLength(60)
    expect(wrapper.get('[data-testid="security-table-next"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('resets the page when an incompatible document arrives (different identity)', async () => {
    const doc = longSecurityDocument(60)
    const wrapper = mount(SecurityDataTable, { props: { document: doc } })
    await expandTable(wrapper, 'security-table-toggle')
    await wrapper.get('[data-testid="security-table-next"]').trigger('click')
    expect(wrapper.findAll('tbody tr')[0].attributes('data-period-key')).toBe('security:9:position:row:26')
    // A price document for the same page is an incompatible observation set.
    await wrapper.setProps({ document: securityDocument({ kind: 'price' }) })
    expect(wrapper.findAll('tbody tr')[0].attributes('data-period-key')).toBe('security:9:price:row:1')
    wrapper.unmount()
  })

  it('clamps the page when the accepted document shrinks', async () => {
    const doc = longSecurityDocument(60)
    const wrapper = mount(SecurityDataTable, { props: { document: doc } })
    await expandTable(wrapper, 'security-table-toggle')
    await wrapper.get('[data-testid="security-table-next"]').trigger('click')
    await wrapper.get('[data-testid="security-table-next"]').trigger('click')
    expect(wrapper.findAll('tbody tr')).toHaveLength(10)
    // A compatible-identity document with fewer observations clamps the page.
    const shrunk = longSecurityDocument(30)
    await wrapper.setProps({ document: shrunk })
    expect(wrapper.findAll('tbody tr')).toHaveLength(5)
    expect(wrapper.get('[data-testid="security-table-range"]').text()).toContain('26–30 of 30')
    wrapper.unmount()
  })
})
