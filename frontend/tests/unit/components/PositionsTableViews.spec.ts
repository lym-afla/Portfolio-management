// D4 Task 3 — rendered view/semantics/pinning/footer behavior of both
// position tables across every preset, driven through the real Vuetify
// v-data-table (attachTo document.body so menus and teleported overlays
// actually render).
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { createPinia } from 'pinia'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import { useAppStore } from '@/stores/app'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { configureContextFixture } from '../context-fixture'

// jsdom has no visualViewport; Vuetify's overlay location strategy needs it
// to open menus in component tests.
beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

vi.mock('@/services/api', () => ({
  getEffectiveCurrentDate: vi.fn().mockResolvedValue({ date: '2026-08-18', effective_current_date: '2026-08-18' }),
  getYearOptions: vi.fn().mockResolvedValue([2026, 2025]),
}))

const vuetify = createVuetify({ components, directives })

const openRow = (name: string, extra: Record<string, unknown> = {}) => ({
  id: 1, type: 'Stock', name, currency: 'USD', current_position: '10.000000000',
  investment_date: '14-Mar-23', entry_price: '$120.50', entry_value: '$1,205.00',
  current_price: '$145.25', current_value: '$1,452.50', share_of_portfolio: '31.5%',
  price_change_percentage: '20.54%', realized_gl: '$0.00', unrealized_gl: '$247.50',
  capital_distribution: '$12.00', capital_distribution_percentage: '1.00%',
  commission: '($15.00)', commission_percentage: '0.12%',
  total_return_amount: '$244.50', total_return_percentage: '20.29%', irr: '12.30%',
  ...extra,
})

const closedRow = (name: string, extra: Record<string, unknown> = {}) => ({
  id: 1, type: 'Bond', name, currency: 'EUR',
  investment_date: '21-Nov-23', entry_value: '€1,000.00',
  exit_date: '15-Aug-26', exit_value: '€1,100.00',
  realized_gl: '€100.00', price_change_percentage: '10.00%',
  capital_distribution: '€20.00', capital_distribution_percentage: '2.00%',
  commission: '(€5.00)', commission_percentage: '0.50%',
  total_return_amount: '€115.00', total_return_percentage: '11.50%', irr: '5.40%',
  ...extra,
})

const openTotals = {
  type: 'Total for assets', entry_value: '$1,205.00', current_value: '$1,452.50',
  share_of_portfolio: '100%', total_return_amount: '$244.50',
  total_return_percentage: '20.29%', irr: '12.30%',
  cash: '$100.00', cash_share_of_portfolio: '6.4%', total_nav: '$1,552.50',
}
const closedTotals = {
  type: 'TOTAL', entry_value: '€1,000.00', exit_value: '€1,100.00',
  total_return_amount: '€115.00', total_return_percentage: '11.50%', irr: '5.40%',
}

async function mountTable(
  tableId: 'open-positions' | 'closed-positions',
  rows: Record<string, unknown>[],
  tableTotals: Record<string, unknown>,
  options: { search?: string; sortBy?: { key: string; order: string }[] } = {},
) {
  const fetchPositions = vi.fn().mockResolvedValue({
    positions: rows, totals: tableTotals, total_items: rows.length,
    cash_balances: { USD: '$100.00' },
  })
  const pinia = createPinia()
  configureContextFixture('2026-08-18')
  const context = usePortfolioContextStore(pinia)
  await context.reconcileContext()
  const appStore = useAppStore(pinia)
  if (options.search) appStore.updateTableSettings({ search: options.search })
  if (options.sortBy) appStore.updateTableSettings({ sortBy: options.sortBy })
  const wrapper = mount(PositionsPageBase, {
    attachTo: document.body,
    global: { plugins: [vuetify, pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    props: { fetchPositions, tableId, pageTitle: tableId === 'open-positions' ? 'Open Positions' : 'Closed Positions' },
    slots: tableId === 'open-positions'
      ? {
          'tfoot-label': 'Total for assets',
          'tfoot-extra': `
            <template #tfoot-extra="{ flattenedHeaders, labelKey }">
              <tr><td v-for="h in flattenedHeaders" :key="'cash-' + h.key" class="text-end">
                <span v-if="h.key === labelKey" class="text-start">Cash</span>
                <template v-else-if="h.key === 'current_value'">CASH_VALUE</template>
              </td></tr>
              <tr><td v-for="h in flattenedHeaders" :key="'total-' + h.key" class="text-end">
                <span v-if="h.key === labelKey" class="text-start">TOTAL</span>
              </td></tr>
            </template>`,
        }
      : { 'tfoot-label': 'TOTAL' },
  })
  await flushPromises()
  return { wrapper, fetchPositions }
}

const bodyRowHeaderCells = (wrapper: VueWrapper) =>
  [...wrapper.element.querySelectorAll('tbody tr th[scope="row"]')]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('both tables render every preset with server-owned order', () => {
  it.each([
    ['open-positions', [openRow('ACME')], openTotals],
    ['closed-positions', [closedRow('UST 2.375% 31')], closedTotals],
  ] as const)('%s renders the Overview preset flat with qualified labels', async (tableId, rows, totals) => {
    const { wrapper } = await mountTable(tableId, rows, totals)
    const leafHeaders = wrapper.element.querySelectorAll('thead th[data-leaf-key]')
    expect(leafHeaders.length).toBe(tableId === 'open-positions' ? 8 : 7)
    expect(wrapper.text()).toContain('Security')
    expect(wrapper.text()).toContain(tableId === 'open-positions' ? 'Current value' : 'Exit value')
    // One flat structural row: no group bands in Overview.
    expect(wrapper.element.querySelectorAll('thead tr')).toHaveLength(1)
    expect(wrapper.element.querySelectorAll('thead th.positions-group-band')).toHaveLength(0)
    wrapper.unmount()
  })

  it('keeps the displayed order exactly as the server returned it', async () => {
    // Server page intentionally NOT in local sort order.
    const rows = [
      openRow('Zebra Holdings', { id: 2 }),
      openRow('Alpha Industries', { id: 1 }),
    ]
    const { wrapper, fetchPositions } = await mountTable('open-positions', rows, openTotals, {
      sortBy: [{ key: 'name', order: 'asc' }],
    })
    expect(bodyRowHeaderCells(wrapper).map((cell) => cell.textContent?.trim())).toEqual([
      'Zebra Holdings', 'Alpha Industries',
    ])
    // The sort intent stays server-owned in the outbound request.
    const lastCall = fetchPositions.mock.calls.at(-1)![0]
    expect(lastCall.sortBy).toEqual({ key: 'name', order: 'asc' })
    wrapper.unmount()
  })

  it('renders grouped Full ledger with quiet bands and colgroup', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    const viewSelect = wrapper.find('[data-testid="positions-view-select"]')
    await viewSelect.find('.v-field').trigger('mousedown')
    await viewSelect.find('.v-field').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 50))
    const items = [...document.querySelectorAll('.v-overlay--active .v-list-item')]
    const fullLedger = items.find((item) => item.textContent?.includes('Full ledger'))
    ;(fullLedger as HTMLElement).click()
    await flushPromises()
    expect(wrapper.element.querySelectorAll('thead tr')).toHaveLength(2)
    const bands = wrapper.element.querySelectorAll('thead th.positions-group-band')
    expect([...bands].map((band) => band.textContent?.trim())).toEqual(
      ['Identity', 'Entry', 'Current', 'Performance'],
    )
    for (const band of bands) expect(band.getAttribute('scope')).toBe('colgroup')
    const cols = wrapper.element.querySelectorAll('colgroup col[data-group]')
    expect([...cols].map((col) => col.getAttribute('data-group'))).toEqual(
      ['identity', 'entry', 'current', 'performance'],
    )
    // All 20 original leaves reachable.
    expect(wrapper.element.querySelectorAll('thead th[data-leaf-key]').length).toBe(20)
    wrapper.unmount()
  })

  it('renders the closed Full ledger without invented price columns', async () => {
    const { wrapper } = await mountTable('closed-positions', [closedRow('UST')], closedTotals)
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('mousedown')
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 50))
    const fullLedger = [...document.querySelectorAll('.v-overlay--active .v-list-item')]
      .find((item) => item.textContent?.includes('Full ledger')) as HTMLElement
    fullLedger.click()
    await flushPromises()
    const leafKeys = [...wrapper.element.querySelectorAll('thead th[data-leaf-key]')]
      .map((th) => th.getAttribute('data-leaf-key'))
    expect(leafKeys).toHaveLength(16)
    expect(leafKeys).not.toContain('entry_price')
    expect(leafKeys).not.toContain('exit_price')
    wrapper.unmount()
  })

  it('keeps amount and percentage leaves separately sortable', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('mousedown')
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 50))
    ;([...document.querySelectorAll('.v-overlay--active .v-list-item')]
      .find((item) => item.textContent?.includes('Full ledger')) as HTMLElement).click()
    await flushPromises()
    const thFor = (key: string) =>
      wrapper.element.querySelector(`thead th[data-leaf-key="${key}"]`)!
    expect(thFor('total_return_amount').className).toContain('v-data-table__th--sortable')
    expect(thFor('total_return_percentage').className).toContain('v-data-table__th--sortable')
    wrapper.unmount()
  })
})

describe('key-based pinning', () => {
  it('pins only the identity leaves by key, never Currency', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    const thFor = (key: string) =>
      wrapper.element.querySelector(`thead th[data-leaf-key="${key}"]`)
    // Overview hides Type: Security is the only pinned leaf, at offset 0.
    expect(thFor('name')!.className).toContain('col-pin-1')
    expect(thFor('name')!.className).not.toContain('col-pin-2')
    expect(wrapper.element.querySelector('tbody th[data-leaf-key="name"]')!.className).toContain('col-pin-1')
    const currency = wrapper.element.querySelector('tbody td[data-leaf-key="currency"]')
    expect(currency!.className).not.toContain('col-pin')
    wrapper.unmount()
  })

  it('assigns pin-1 to Type and pin-2 to Security in the Full ledger', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('mousedown')
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 50))
    ;([...document.querySelectorAll('.v-overlay--active .v-list-item')]
      .find((item) => item.textContent?.includes('Full ledger')) as HTMLElement).click()
    await flushPromises()
    const thFor = (key: string) =>
      wrapper.element.querySelector(`thead th[data-leaf-key="${key}"]`)!
    expect(thFor('type')!.className).toContain('col-pin-1')
    expect(thFor('name')!.className).toContain('col-pin-2')
    wrapper.unmount()
  })
})

describe('footer alignment and row labels', () => {
  it('renders every footer cell under its visible leaf with header associations', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    const leafIds = [...wrapper.element.querySelectorAll('thead th[data-leaf-key]')]
      .map((th) => th.id)
    const totalsRow = wrapper.element.querySelectorAll('tfoot tr')[0]
    const cells = [...totalsRow.querySelectorAll('td')]
    expect(cells.map((cell) => cell.getAttribute('headers'))).toEqual(leafIds)
    // The totals value lands under its own leaf, not by fixed position.
    const entryValueCell = cells[leafIds.indexOf('open-positions-entry_value')]
    expect(entryValueCell.textContent).toContain('$1,205.00')
    wrapper.unmount()
  })

  it('keeps Assets/Cash/TOTAL labels in the Security column when Type is hidden', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    // Overview already hides Type: label column is Security.
    const firstFooterRow = wrapper.element.querySelectorAll('tfoot tr')[0]
    const firstCell = firstFooterRow.querySelector('td')
    expect(firstCell!.getAttribute('data-leaf-key')).toBe('name')
    expect(firstCell!.textContent).toContain('Total for assets')
    const cashRow = wrapper.element.querySelectorAll('tfoot tr')[1]
    expect(cashRow.querySelector('td')!.textContent).toContain('Cash')
    const totalRow = wrapper.element.querySelectorAll('tfoot tr')[2]
    expect(totalRow.querySelector('td')!.textContent).toContain('TOTAL')
    wrapper.unmount()
  })
})

describe('table semantics', () => {
  it('provides a caption, row headers and cell header associations', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    const caption = wrapper.element.querySelector('table caption')
    expect(caption?.textContent).toContain('Open Positions')
    expect(caption?.textContent).toContain('Overview')
    const rowHeader = wrapper.element.querySelector('tbody th[scope="row"]')
    expect(rowHeader?.getAttribute('data-leaf-key')).toBe('name')
    expect(rowHeader?.getAttribute('headers')).toBe('open-positions-name')
    const cell = wrapper.element.querySelector('tbody td[data-leaf-key="entry_value"]')
    expect(cell?.getAttribute('headers')).toBe('open-positions-entry_value')
    wrapper.unmount()
  })

  it('sets aria-sort on the actually sorted leaf header', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    const th = wrapper.element.querySelector('thead th[data-leaf-key="entry_value"]') as HTMLElement
    th.click()
    await flushPromises()
    const sorted = wrapper.element.querySelector('thead th[aria-sort]')
    expect(sorted?.getAttribute('data-leaf-key')).toBe('entry_value')
    expect(sorted?.getAttribute('aria-sort')).toBe('ascending')
    th.click()
    await flushPromises()
    expect(wrapper.element.querySelector('thead th[aria-sort]')?.getAttribute('aria-sort')).toBe('descending')
    wrapper.unmount()
  })

  it('exposes focusable glossary triggers with qualified labels', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    const glossary = wrapper.element.querySelector('th[data-leaf-key="current_value"] button.positions-glossary') as HTMLButtonElement
    expect(glossary).toBeTruthy()
    expect(glossary.getAttribute('aria-label')).toMatch(/^Current value:/)
    // Instrument prices keep their security-currency semantics.
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('mousedown')
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 50))
    ;([...document.querySelectorAll('.v-overlay--active .v-list-item')]
      .find((item) => item.textContent?.includes('Entry & valuation')) as HTMLElement).click()
    await flushPromises()
    const priceGlossary = wrapper.element.querySelector('th[data-leaf-key="entry_price"] button.positions-glossary') as HTMLButtonElement
    expect(priceGlossary.getAttribute('aria-label')).toMatch(/security's trading currency/i)
    wrapper.unmount()
  })
})

describe('hidden active sort', () => {
  it('names the hidden sort with full title and offers Clear sort without mutating it first', async () => {
    const { wrapper, fetchPositions } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    // Sort by Entry price while it is visible (Comparison preset exposes it).
    const summaryBefore = wrapper.find('[data-testid="hidden-sort-summary"]')
    expect(summaryBefore.exists()).toBe(false)
    // Switch to Entry & valuation so entry_price is visible; sort by it.
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('mousedown')
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 50))
    ;([...document.querySelectorAll('.v-overlay--active .v-list-item')]
      .find((item) => item.textContent?.includes('Entry & valuation')) as HTMLElement).click()
    await flushPromises()
    const priceTh = wrapper.element.querySelector('thead th[data-leaf-key="entry_price"]') as HTMLElement
    priceTh.click()
    await flushPromises()
    expect(wrapper.element.querySelector('th[data-leaf-key="entry_price"]').getAttribute('aria-sort')).toBe('ascending')
    // Switch back to Overview: the sorted leaf becomes hidden.
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('mousedown')
    await wrapper.find('[data-testid="positions-view-select"]').find('.v-field').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 50))
    ;([...document.querySelectorAll('.v-overlay--active .v-list-item')]
      .find((item) => item.textContent?.trim() === 'Overview') as HTMLElement).click()
    await flushPromises()
    const summary = wrapper.find('[data-testid="hidden-sort-summary"]')
    expect(summary.exists()).toBe(true)
    expect(summary.text()).toContain('Sorted by Entry price — ascending')
    // Hiding the column did NOT clear the server sort.
    const callsWithSort = fetchPositions.mock.calls.filter((call) => call[0].sortBy?.key === 'entry_price')
    expect(callsWithSort.length).toBeGreaterThan(0)
    // Clear sort removes it.
    await wrapper.find('[data-testid="clear-sort"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="hidden-sort-summary"]').exists()).toBe(false)
    const lastCall = fetchPositions.mock.calls.at(-1)![0]
    expect(lastCall.sortBy).toEqual({})
    wrapper.unmount()
  })
})

describe('grouped Columns chooser', () => {
  it('lists fully qualified names grouped by lifecycle group with a locked Security', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    ;(wrapper.element.querySelector('button[aria-label="Show or hide columns"]') as HTMLElement).click()
    await new Promise((resolve) => setTimeout(resolve, 50))
    const menu = document.querySelector('.v-overlay--active .positions-columns-menu')!
    expect(menu).toBeTruthy()
    const subheaders = [...menu.querySelectorAll('.v-list-subheader')].map((el) => el.textContent?.trim())
    expect(subheaders).toEqual(['Identity', 'Entry', 'Current', 'Performance'])
    // Fully qualified names distinguish repeated labels.
    expect(menu.textContent).toContain('Entry price')
    expect(menu.textContent).toContain('Current price')
    expect(menu.textContent).toContain('Realized G/L amount')
    // Security is present, checked and locked.
    const nameCheckbox = menu.querySelector('[data-testid="column-name"] input') as HTMLInputElement
    expect(nameCheckbox.disabled).toBe(true)
    expect(nameCheckbox.checked).toBe(true)
    wrapper.unmount()
  })

  it('stays open for repeated selections and closes on Done', async () => {
    const { wrapper } = await mountTable('open-positions', [openRow('ACME')], openTotals)
    ;(wrapper.element.querySelector('button[aria-label="Show or hide columns"]') as HTMLElement).click()
    await new Promise((resolve) => setTimeout(resolve, 50))
    const menuActive = () => !!document.querySelector('.v-overlay--active .positions-columns-menu')
    expect(menuActive()).toBe(true)
    const toggle = (key: string) => {
      const box = document.querySelector(`.v-overlay--active [data-testid="column-${key}"] input`) as HTMLInputElement
      box.click()
    }
    // Overview starts with 8 leaves; hide Currency, then add Entry price —
    // both while the menu stays open (Overview keys minus currency plus
    // entry_price is still 8 leaves).
    toggle('currency')
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(menuActive()).toBe(true)
    toggle('entry_price')
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(menuActive()).toBe(true)
    expect(wrapper.element.querySelectorAll('thead th[data-leaf-key]').length).toBe(8)
    const leafKeys = [...wrapper.element.querySelectorAll('thead th[data-leaf-key]')]
      .map((th) => th.getAttribute('data-leaf-key'))
    expect(leafKeys).not.toContain('currency')
    expect(leafKeys).toContain('entry_price')
    ;(document.querySelector('.v-overlay--active [data-testid="columns-done"]') as HTMLElement).click()
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(menuActive()).toBe(false)
    wrapper.unmount()
  })
})

describe('distinct empty states', () => {
  it('separates truly empty from filtered-empty', async () => {
    const emptyFetch = vi.fn().mockResolvedValue({ positions: [], totals: {}, total_items: 0 })
    const pinia = createPinia()
    configureContextFixture('2026-08-18')
    await usePortfolioContextStore(pinia).reconcileContext()
    useAppStore(pinia).updateTableSettings({ search: 'nomatch' })
    const wrapper = mount(PositionsPageBase, {
      attachTo: document.body,
      global: { plugins: [vuetify, pinia] },
      props: { fetchPositions: emptyFetch, tableId: 'open-positions', pageTitle: 'Open Positions' },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('No positions match your search')
    expect(wrapper.text()).not.toContain('No positions yet')
    wrapper.unmount()
  })
})
