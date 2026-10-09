import { configureContextFixture } from '../context-fixture'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { createPinia } from 'pinia'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'

vi.mock('@/services/api', () => ({
  getEffectiveCurrentDate: vi.fn().mockResolvedValue({
    date: '2026-08-18',
    effective_current_date: '2026-08-18',
  }),
  // The typed wire the adapter returns (Task 2): numeric years as text/value,
  // the divider, and the backend's All-time/YTD ranges.
  getYearOptions: vi.fn().mockResolvedValue([
    { text: '2026', value: '2026' },
    { text: '2025', value: '2025' },
    { divider: true },
    { text: 'All-time', value: 'all_time' },
    { text: '2026YTD', value: 'ytd' },
  ]),
}))

// Tests disable vite-plugin-vuetify's auto-import transform, so Vuetify
// components must be registered explicitly for v-data-table internals to
// resolve and actually render.
const vuetify = createVuetify({ components, directives })

const makeWrapper = (props = {}) => {
  const fetchPositions = vi.fn().mockResolvedValue({
    positions: [{ type: 'Stock', name: 'ACME', entry_value: 10 }],
    totals: {},
    total_items: 1,
  })
  const wrapper = mount(PositionsPageBase, {
    attachTo: document.body,
    global: { plugins: [vuetify, createPinia()] },
    props: { fetchPositions, tableId: 'open-positions', pageTitle: 'Test', ...props },
  })
  return { wrapper, fetchPositions }
}

beforeEach(() => {
  vi.clearAllMocks()
  configureContextFixture()
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('PositionsPageBase', () => {
  it('adapts the real backend year wire without surfacing a year-options failure', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    expect(wrapper.text()).not.toContain('Unable to load positions or year options')
    const yearSelect = wrapper.find('.positions-year-select')
    expect(yearSelect.exists()).toBe(true)
    // The offered values stay inside the timespan vocabulary the query
    // builder understands: the backend's own specials plus calendar years.
    const options = wrapper.vm.yearOptions
    expect(options.some((option) => option.value === 'ytd' && option.text === 'YTD')).toBe(true)
    expect(options.some((option) => option.value === 'all_time' && option.text === 'All time')).toBe(true)
    expect(options.some((option) => option.value === 2026 && option.text === '2026')).toBe(true)
  })

  it('renders the error-alert Retry action with the readable text-variant classes', async () => {
    const fetchPositions = vi.fn().mockRejectedValue(new Error('fixture positions failure'))
    const { wrapper } = makeWrapper({ fetchPositions })
    await flushPromises()
    const retry = wrapper.find('[data-testid="positions-retry"]')
    expect(retry.exists()).toBe(true)
    expect(retry.text()).toBe('Retry')
    expect(retry.classes()).toContain('v-btn--variant-text')
    expect(retry.classes()).not.toContain('v-btn--variant-elevated')
  })
  it('rebases a saved relative range before the first query on route entry', async () => {
    const pinia = createPinia()
    configureContextFixture('2025-12-31')
    const context = usePortfolioContextStore(pinia)
    const appStore = useAppStore(pinia)
    await context.reconcileContext()
    appStore.updateTableSettings({ timespan: 'ytd', dateFrom: '2026-01-01', dateTo: '2026-08-18', page: 3 })
    const fetchPositions = vi.fn().mockResolvedValue({ positions: [], totals: {}, total_items: 0 })
    const wrapper = mount(PositionsPageBase, {
      global: { plugins: [vuetify, pinia] },
      props: { fetchPositions, tableId: 'open-positions', pageTitle: 'Test' },
    })
    await flushPromises()
    expect(fetchPositions).toHaveBeenCalledTimes(1)
    expect(fetchPositions).toHaveBeenCalledWith(expect.objectContaining({ dateFrom: '2025-01-01', dateTo: '2025-12-31', page: 1 }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    wrapper.unmount()
  })
  it('accepts null all-time start and issues one initial mounted request', async () => {
    const pinia = createPinia()
    const context = usePortfolioContextStore(pinia)
    const appStore = useAppStore(pinia)
    await context.reconcileContext()
    appStore.updateTableSettings({ timespan: 'all_time', dateFrom: null, dateTo: '2026-08-18' })
    const fetchPositions = vi.fn().mockResolvedValue({ positions: [], totals: {}, total_items: 0 })
    const wrapper = mount(PositionsPageBase, {
      global: { plugins: [vuetify, pinia] },
      props: { fetchPositions, tableId: 'open-positions', pageTitle: 'Test' },
    })
    await flushPromises()
    expect(fetchPositions).toHaveBeenCalledTimes(1)
    expect(fetchPositions).toHaveBeenCalledWith(expect.objectContaining({ dateFrom: null, dateTo: '2026-08-18' }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    wrapper.unmount()
  })
  it('fetches once with the new YTD range while mounted after a context date commit', async () => {
    const pinia = createPinia()
    const context = usePortfolioContextStore(pinia)
    const appStore = useAppStore(pinia)
    await context.reconcileContext()
    appStore.updateTableSettings({ timespan: 'ytd', dateFrom: '2026-01-01', dateTo: '2026-08-18', page: 3 })
    const fetchPositions = vi.fn().mockResolvedValue({ positions: [], totals: {}, total_items: 0 })
    const wrapper = mount(PositionsPageBase, {
      global: { plugins: [vuetify, pinia] },
      props: { fetchPositions, tableId: 'open-positions', pageTitle: 'Test' },
    })
    await flushPromises()
    fetchPositions.mockClear()
    configureContextFixture('2025-12-31')
    await context.reconcileContext()
    await flushPromises()
    expect(appStore.tableSettings).toMatchObject({ timespan: 'ytd', dateFrom: '2025-01-01', dateTo: '2025-12-31', page: 1 })
    expect(fetchPositions).toHaveBeenCalledTimes(1)
    expect(fetchPositions).toHaveBeenCalledWith(expect.objectContaining({ dateFrom: '2025-01-01', dateTo: '2025-12-31', page: 1 }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    wrapper.unmount()
  })
  it('adapts the real year wire into selector items (server order, divider, specials)', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    // The backend list is authoritative: numeric years keep numeric values
    // for the query builder; the specials map onto the timespan values the
    // query builder understands; the divider passes through for rendering.
    expect(wrapper.vm.yearOptions).toEqual([
      { text: '2026', value: 2026 },
      { text: '2025', value: 2025 },
      { divider: true, text: '', value: '' },
      { text: 'All time', value: 'all_time' },
      { text: 'YTD', value: 'ytd' },
    ])
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
    wrapper.unmount()
  })

  it('renders the Overview preset leaves for an unconfigured table', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    expect(wrapper.text()).toContain('Security')
    expect(wrapper.text()).toContain('Entry value')
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
    // Flat Overview still draws boundaries between visible groups.
    const marked = wrapper.findAll('th.group-start')
    expect(marked.length).toBeGreaterThanOrEqual(1)
  })

  it('right-aligns footer totals via text-<align> classes', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()
    const foot = wrapper.find('tfoot')
    expect(foot.exists()).toBe(true)
    expect(foot.find('td.text-end').exists()).toBe(true)
    expect(foot.find('td.end').exists()).toBe(false)
  })

  it('renders a glossary tooltip on a described header column and keeps the sort icon', async () => {
    const { wrapper } = makeWrapper()
    await flushPromises()

    // IRR is a described leaf on the open table's Overview preset.
    const tooltips = wrapper.findAllComponents({ name: 'VTooltip' })
    expect(tooltips.length).toBeGreaterThanOrEqual(1)
    const irrTooltip = tooltips.find((t) => t.props('text')?.includes('Money-weighted'))
    expect(irrTooltip).toBeTruthy()
    // Sort affordance preserved: the described th is still sortable and its
    // content row still carries the sort icon class.
    const th = wrapper.element.querySelector('th[data-leaf-key="irr"]')
    expect(th.className).toContain('v-data-table__th--sortable')
    expect(th.querySelector('.v-data-table-header__sort-icon')).not.toBeNull()
    expect(th.textContent).toContain('IRR')
  })

  it('shows the import empty state when there are no items and no search', async () => {
    const fetchPositions = vi.fn().mockResolvedValue({
      positions: [],
      totals: {},
      total_items: 0,
    })
    const wrapper = mount(PositionsPageBase, {
      global: {
        plugins: [vuetify, createPinia()],
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
      props: { fetchPositions, tableId: 'open-positions', pageTitle: 'Test' },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('No positions yet')
    expect(wrapper.text()).toContain('import transactions')
    expect(wrapper.text()).not.toContain('No positions match your search')
  })

  it('shows the filtered-out empty state when search yields no items', async () => {
    const fetchPositions = vi
      .fn()
      .mockResolvedValue({ positions: [], totals: {}, total_items: 0 })
    // `search` lives in the app store (debounced setter), so seed the store
    // instead of driving the input.
    const pinia = createPinia()
    const appStore = useAppStore(pinia)
    appStore.tableSettings.search = 'nomatch'
    const wrapper = mount(PositionsPageBase, {
      global: { plugins: [vuetify, pinia] },
      props: { fetchPositions, tableId: 'open-positions', pageTitle: 'Test' },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('No positions match your search')
    expect(wrapper.text()).not.toContain('No positions yet')
  })
})

describe('PositionsPageBase sticky-column and divider CSS (source assertions)', () => {
  // The compiled component does not carry its scoped style block, so the
  // sticky/divider CSS is asserted against the SFC source directly.
  const src = readFileSync('src/components/PositionsPageBase.vue', 'utf-8')

  it('styles the error-alert Retry action as the readable text variant', () => {
    // The elevated default inside an error-toned alert rendered white text on
    // a white background (computed contrast 1.0). The retry action must use
    // the text variant with an explicit white color on the alert.
    const retryButton = src.match(/<v-btn[^>]*data-testid="positions-retry"[^>]*>/)
    expect(retryButton).toBeTruthy()
    expect(retryButton[0]).toContain('variant="text"')
    expect(retryButton[0]).toContain('color="white"')
  })

  it('sticks key-pinned identity columns with opaque backgrounds and a measured offset', () => {
    expect(src).toContain('position: sticky')
    expect(src).toContain('left: 0')
    expect(src).toContain('--positions-pin-offset')
    expect(src).toContain('rgb(var(--v-theme-surface))')
    // Offsets are measured from the rendered first pinned column.
    expect(src).toContain('ResizeObserver')
  })

  it('pins by column key classes, never nth-child positions', () => {
    expect(src).toContain('col-pin-1')
    expect(src).toContain('col-pin-2')
    expect(src).not.toContain('nth-child')
  })

  it('separates groups with a vertical rule via .group-start', () => {
    expect(src).toContain('group-start')
    expect(src).toMatch(/group-start[^}]*border-left/)
  })

  it('keeps the table from re-sorting or re-filtering the received page', () => {
    // The neutral customKeySort repair plus no :search binding.
    expect(src).toContain('neutralSorters')
    expect(src).not.toMatch(/:search="search"/)
    expect(src).toContain(':items-length="totalItems"')
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
