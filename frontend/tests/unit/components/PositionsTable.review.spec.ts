// PR #51 review round — regressions for review findings 3 and 4.
// 3: accessibility attributes and pin offsets initialize when the table
//    FIRST renders after delayed data, not only after a view change.
// 4: the page-rendered Cash/TOTAL footer rows carry the same key-based pin
//    classes and header associations as the base totals row.
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { createPinia } from 'pinia'
import PositionsPageBase from '@/components/PositionsPageBase.vue'
import OpenPositionsPage from '@/views/OpenPositionsPage.vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { configureContextFixture } from '../context-fixture'
import { deferred } from '../helpers/deferred'

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

vi.mock('@/services/api', () => ({
  getEffectiveCurrentDate: vi.fn().mockResolvedValue({ date: '2026-08-18', effective_current_date: '2026-08-18' }),
  getYearOptions: vi.fn().mockResolvedValue([2026]),
  getOpenPositions: vi.fn().mockResolvedValue({
    portfolio_open: [{
      id: 1, type: 'Stock', name: 'ACME', currency: 'USD', current_position: '10.000000000',
      investment_date: '14-Mar-23', entry_price: '$120.50', entry_value: '$1,205.00',
      current_price: '$145.25', current_value: '$1,452.50', share_of_portfolio: '31.5%',
      price_change_percentage: '20.54%', realized_gl: '$0.00', unrealized_gl: '$247.50',
      capital_distribution: '$12.00', capital_distribution_percentage: '1.00%',
      commission: '($15.00)', commission_percentage: '0.12%',
      total_return_amount: '$244.50', total_return_percentage: '20.29%', irr: '12.30%',
    }],
    portfolio_open_totals: {
      type: 'Total for assets', entry_value: '$1,205.00', current_value: '$1,452.50',
      share_of_portfolio: '100%', total_return_amount: '$244.50',
      total_return_percentage: '20.29%', irr: '12.30%',
      cash: '$100.00', cash_share_of_portfolio: '6.4%', total_nav: '$1,552.50',
    },
    total_items: 1, current_page: 1, total_pages: 1,
    cash_balances: { USD: '$100.00' },
  }),
}))

const vuetify = createVuetify({ components, directives })

const openRow = (name: string) => ({
  id: 1, type: 'Stock', name, currency: 'USD', current_position: '10.000000000',
  investment_date: '14-Mar-23', entry_price: '$120.50', entry_value: '$1,205.00',
  current_price: '$145.25', current_value: '$1,452.50', share_of_portfolio: '31.5%',
  price_change_percentage: '20.54%', realized_gl: '$0.00', unrealized_gl: '$247.50',
  capital_distribution: '$12.00', capital_distribution_percentage: '1.00%',
  commission: '($15.00)', commission_percentage: '0.12%',
  total_return_amount: '$244.50', total_return_percentage: '20.29%', irr: '12.30%',
})

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('review 3: accessibility/pinning initialize on first render', () => {
  it('names and makes the scroll region focusable as soon as the delayed table renders', async () => {
    const pending = deferred()
    const pinia = createPinia()
    configureContextFixture('2026-08-18')
    await usePortfolioContextStore(pinia).reconcileContext()
    const wrapper = mount(PositionsPageBase, {
      attachTo: document.body,
      global: { plugins: [vuetify, pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
      props: {
        // Stays pending until the test releases it: the table renders late.
        fetchPositions: () => pending.promise,
        tableId: 'open-positions',
        pageTitle: 'Open Positions',
      },
    })
    await flushPromises()
    // Still loading: no table yet.
    expect(document.querySelector('.positions-table')).toBeNull()

    pending.resolve({
      positions: [openRow('ACME')],
      totals: { type: 'Total for assets', entry_value: '$1,205.00', current_value: '$1,452.50' },
      total_items: 1,
    })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 120))

    // WITHOUT any view/sort interaction, the first render already carries
    // the caption, the named focusable scroll region and the pin offsets.
    const table = document.querySelector('.positions-table') as HTMLElement
    expect(table).toBeTruthy()
    expect(table.querySelector('table caption')?.textContent).toContain('Open Positions')
    const wrapperEl = table.querySelector('.v-table__wrapper') as HTMLElement
    expect(wrapperEl.getAttribute('tabindex')).toBe('0')
    expect(wrapperEl.getAttribute('role')).toBe('region')
    expect(wrapperEl.getAttribute('aria-label')).toBe('Open Positions table, scrollable')
    expect(table.style.getPropertyValue('--positions-pin-offset')).not.toBe('')
    expect(table.querySelector('thead th[data-leaf-key="name"]')?.className).toContain('col-pin-1')
    wrapper.unmount()
  })
})

describe('review 4: Cash/TOTAL footer rows share pinning and header associations', () => {
  it('labels and pinned cells in the extra rows match the base totals row', async () => {
    const pinia = createPinia()
    configureContextFixture('2026-08-18')
    await usePortfolioContextStore(pinia).reconcileContext()
    const wrapper = mount(OpenPositionsPage, {
      attachTo: document.body,
      global: { plugins: [vuetify, pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 120))

    const table = document.querySelector('.positions-table') as HTMLElement
    const rows = table.querySelectorAll('tfoot tr')
    expect(rows.length).toBe(3) // totals + Cash + TOTAL
    const totalsCells = [...rows[0].querySelectorAll('td')]
    for (const extra of [rows[1], rows[2]]) {
      const cells = [...extra.querySelectorAll('td')]
      expect(cells.length).toBe(totalsCells.length)
      cells.forEach((cell, index) => {
        const totalsCell = totalsCells[index]
        // Same header association and leaf identity as the totals cell above.
        expect(cell.getAttribute('headers')).toBe(totalsCell.getAttribute('headers'))
        expect(cell.getAttribute('data-leaf-key')).toBe(totalsCell.getAttribute('data-leaf-key'))
        // Same key-based pin treatment (both pinned, or neither).
        const pinClass = (cls: string) => (cls.match(/col-pin-\d+/) ?? [''])[0]
        expect(pinClass(String(cell.className))).toBe(pinClass(String(totalsCell.className)))
      })
    }
    // The row labels stay in the Security column of every footer row.
    expect(rows[0].querySelector('td')?.textContent).toContain('Total for assets')
    expect(rows[1].querySelector('td')?.textContent).toContain('Cash')
    expect(rows[2].querySelector('td')?.textContent).toContain('TOTAL')
    wrapper.unmount()
  })
})
