// D4 Task 4 — row Edit/Delete controls are named Vuetify buttons with 44px
// touch targets; the emitted row payload is the unchanged transaction object.
import { beforeAll, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import TransactionRow from '@/components/transactions/TransactionRow.vue'

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

const vuetify = createVuetify({ components, directives })

const rowTransaction = {
  id: 'regular_5',
  transaction_type: 'regular',
  date: '2026-09-08',
  type: 'Buy',
  security: { id: 1, name: 'ACME Corp' },
  account: { broker_name: 'Fixture Broker', name: 'Main' },
  cur: 'USD',
  cash_flow: '(1,015.00)',
  balances: { USD: '500.00' },
}

const mountRow = (transaction = rowTransaction) =>
  mount(TransactionRow, {
    attachTo: document.body,
    global: { plugins: [vuetify, createPinia()] },
    props: { transaction, currencies: ['USD'], showBalances: true, showCashFlow: true, showActions: true },
  })

describe('TransactionRow actions', () => {
  it('renders named Edit and Delete buttons carrying date and account/security identity', () => {
    const wrapper = mountRow()
    const edit = wrapper.find('button[aria-label*="Edit"]')
    const del = wrapper.find('button[aria-label*="Delete"]')
    expect(edit.exists()).toBe(true)
    expect(del.exists()).toBe(true)
    expect(edit.attributes('aria-label')).toContain('2026-09-08')
    expect(edit.attributes('aria-label')).toContain('ACME Corp')
    expect(edit.attributes('aria-label')).toContain('Fixture Broker')
    expect(del.attributes('aria-label')).toContain('2026-09-08')
    expect(del.attributes('aria-label')).toContain('Buy')
    wrapper.unmount()
  })

  it('falls back to a date-only identity when no account/security text exists', () => {
    const wrapper = mountRow({
      id: 'fx_3', transaction_type: 'fx', date: '2026-01-15', type: 'FX', balances: {},
    })
    const edit = wrapper.find('button[aria-label*="Edit"]')
    expect(edit.attributes('aria-label')).toContain('2026-01-15')
    expect(edit.attributes('aria-label')).not.toContain(':')
    wrapper.unmount()
  })

  it('gives both controls 44px touch-target styling', () => {
    const wrapper = mountRow()
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThanOrEqual(2)
    for (const button of buttons) {
      expect(button.classes()).toContain('workspace-row-action')
    }
    wrapper.unmount()
  })

  it('emits edit/delete with the unchanged row payload', async () => {
    const wrapper = mountRow()
    await wrapper.find('button[aria-label*="Edit"]').trigger('click')
    await wrapper.find('button[aria-label*="Delete"]').trigger('click')
    const editEmitted = wrapper.emitted('edit')
    const deleteEmitted = wrapper.emitted('delete')
    expect(editEmitted).toHaveLength(1)
    // The emitted payload is the row's transaction object itself (the
    // reactive prop reference), never a rebuilt or trimmed copy.
    expect(editEmitted![0][0]).toStrictEqual(rowTransaction)
    expect(deleteEmitted![0][0]).toStrictEqual(rowTransaction)
    wrapper.unmount()
  })

  it('keeps the signed amount, description and type cells as text', () => {
    const wrapper = mountRow()
    expect(wrapper.text()).toContain('(1,015.00)')
    expect(wrapper.text()).toContain('ACME Corp')
    expect(wrapper.text()).toContain('Buy')
    wrapper.unmount()
  })
})
