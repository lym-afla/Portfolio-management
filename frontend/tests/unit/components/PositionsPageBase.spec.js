import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { createPinia } from 'pinia'
import PositionsPageBase from '@/components/PositionsPageBase.vue'

vi.mock('@/services/api', () => ({
  getEffectiveCurrentDate: vi.fn().mockResolvedValue({
    date: '2026-08-18',
    effective_current_date: '2026-08-18',
  }),
  getYearOptions: vi.fn().mockResolvedValue(['2026', '2025']),
}))

// Tests disable vite-plugin-vuetify's auto-import transform, so Vuetify
// components must be registered explicitly for v-data-table internals to
// resolve and actually render.
const vuetify = createVuetify({ components, directives })

const headers = [
  { title: 'Type', key: 'type', align: 'start', sortable: true },
  {
    title: 'Entry', key: 'entry', align: 'end', sortable: false,
    children: [
      { title: 'Investment date', key: 'investment_date', align: 'end', sortable: true },
      { title: 'Value', key: 'entry_value', align: 'end', sortable: true },
    ],
  },
]

const makeWrapper = (props = {}) => {
  const fetchPositions = vi.fn().mockResolvedValue({
    positions: [{ type: 'Stock', name: 'ACME', entry_value: 10 }],
    totals: {},
    total_items: 1,
  })
  const wrapper = mount(PositionsPageBase, {
    global: { plugins: [vuetify, createPinia()] },
    props: { fetchPositions, headers, pageTitle: 'Test', ...props },
  })
  return { wrapper, fetchPositions }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PositionsPageBase', () => {
  it('declares the defaultVisibleKeys prop (default null)', () => {
    const { wrapper } = makeWrapper()
    expect(wrapper.props('defaultVisibleKeys')).toBeUndefined()
  })

  it('sort change reaches the fetch with the sorted key (server sort wired)', async () => {
    const { wrapper, fetchPositions } = makeWrapper()
    await flushPromises()
    fetchPositions.mockClear()
    await wrapper.vm.handleSortChange([{ key: 'entry_value', order: 'desc' }])
    await flushPromises()
    expect(fetchPositions).toHaveBeenCalled()
    const lastCall = fetchPositions.mock.calls.at(-1)[0]
    expect(lastCall.sortBy).toEqual({ key: 'entry_value', order: 'desc' })
  })

  it('renders grouped header leaves when no defaultVisibleKeys given', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    expect(wrapper.text()).toContain('Investment date')
    expect(wrapper.text()).toContain('Type')
  })

  it('hides leaves not in defaultVisibleKeys', async () => {
    const { wrapper } = makeWrapper({
      defaultVisibleKeys: ['type', 'name', 'entry_value'],
    })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Investment date')
    expect(wrapper.text()).toContain('Value')
    expect(wrapper.text()).toContain('Type')
  })

  it('toggleColumn hides and shows a leaf column', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    expect(wrapper.text()).toContain('Investment date')
    wrapper.vm.toggleColumn('investment_date')
    await flushPromises()
    expect(wrapper.text()).not.toContain('Investment date')
    wrapper.vm.toggleColumn('investment_date')
    await flushPromises()
    expect(wrapper.text()).toContain('Investment date')
  })

  it('has a column visibility menu button in the toolbar', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    const btn = wrapper.find('button[aria-label="Show or hide columns"]')
    expect(btn.exists()).toBe(true)
  })

  it('marks group header boundaries with a group-start class', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    // The Entry group header and its first leaf should both carry the class.
    const marked = wrapper.findAll('th.group-start')
    expect(marked.length).toBeGreaterThanOrEqual(2)
  })

  it('right-aligns footer totals via text-<align> classes', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    const foot = wrapper.find('tfoot')
    expect(foot.exists()).toBe(true)
    expect(foot.find('td.text-end').exists()).toBe(true)
    expect(foot.find('td.end').exists()).toBe(false)
  })
})

describe('PositionsPageBase sticky-column and divider CSS (source assertions)', () => {
  // The compiled component does not carry its scoped style block, so the
  // sticky/divider CSS is asserted against the SFC source directly.
  const src = readFileSync('src/components/PositionsPageBase.vue', 'utf-8')

  it('sticks the first two identity columns with opaque backgrounds', () => {
    expect(src).toContain('position: sticky')
    expect(src).toContain('left: 0')
    expect(src).toContain('left: 90px')
    expect(src).toContain('rgb(var(--v-theme-surface))')
  })

  it('scopes sticky cells to body/footer cells and the first header row', () => {
    // Row 2 of a grouped header must not become sticky.
    expect(src).toContain('tbody td:nth-child(1)')
    expect(src).toContain('tfoot td:nth-child(1)')
    expect(src).toContain('thead tr:first-child th:nth-child(1)')
  })

  it('separates groups with a vertical rule via th.group-start', () => {
    expect(src).toContain('th.group-start')
    expect(src).toMatch(/th\.group-start[^}]*border-left/)
  })

  it('no longer relies on the non-existent Vuetify divider class', () => {
    expect(src).not.toContain('v-data-table-column--divider')
  })
})

describe('App.vue global td white-space cleanup (source assertion)', () => {
  const src = readFileSync('src/App.vue', 'utf-8')

  it('does not force wrapping/hyphenation on table cells globally', () => {
    expect(src).not.toContain('hyphens: auto')
    expect(src).not.toMatch(/\.v-data-table td\s*\{/)
  })
})
