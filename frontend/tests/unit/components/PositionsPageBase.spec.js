import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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
})
