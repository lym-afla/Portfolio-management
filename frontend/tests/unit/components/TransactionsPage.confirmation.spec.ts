// D4 Task 5 — exact-identity deletion lifecycle on the Transactions page:
// regular/FX with the same numeric id stay distinct, the selection cannot be
// retargeted, late replies are dropped, failures retain subject/error, and
// success deletes once through the correct endpoint.
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import TransactionsPage from '@/views/TransactionsPage.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
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

const mocks = vi.hoisted(() => ({
  getTransactions: vi.fn(),
  getTransactionDetails: vi.fn(),
  getFXTransactionDetails: vi.fn(),
  deleteTransaction: vi.fn(),
  deleteFXTransaction: vi.fn(),
  getYearOptions: vi.fn(),
}))
vi.mock('@/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/api')>()),
  getTransactions: mocks.getTransactions,
  getTransactionDetails: mocks.getTransactionDetails,
  getFXTransactionDetails: mocks.getFXTransactionDetails,
  deleteTransaction: mocks.deleteTransaction,
  deleteFXTransaction: mocks.deleteFXTransaction,
  getYearOptions: mocks.getYearOptions,
}))

const vuetify = createVuetify({ components, directives })

const regularRow = {
  id: 'regular_5', transaction_type: 'regular', date: '2026-09-08', type: 'Buy',
  security: { id: 1, name: 'ACME Corp' }, account: { broker_name: 'Fixture Broker', name: 'Main' },
  quantity: '10', price: '120.50', cur: 'USD', cash_flow: '($1,215.00)', balances: {},
}
const fxRow = {
  id: 'fx_5', transaction_type: 'fx', date: '2026-09-01', type: 'FX',
  from_cur: 'EUR', to_cur: 'USD', from_amount: '(1,000.00)', to_amount: '1,080.00',
  balances: {},
}

const listResponse = {
  transactions: [regularRow, fxRow],
  total_items: 2, current_page: 1, total_pages: 1, currencies: ['USD', 'EUR'],
}

async function mountPage() {
  const pinia = createPinia()
  configureContextFixture('2026-09-08')
  await usePortfolioContextStore(pinia).reconcileContext()
  const wrapper = mount(TransactionsPage, {
    attachTo: document.body,
    global: { plugins: [vuetify, pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  await flushPromises()
  return { wrapper, pinia }
}

// Vuetify overlays linger hidden (v-show) after close in jsdom; the open
// dialog is the overlay still flagged active.
const dialogElement = () =>
  document.querySelector('.v-overlay--active[role="dialog"]') as HTMLElement

const confirmButton = () =>
  dialogElement().querySelector('[data-testid="confirm-confirm"]') as HTMLElement

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ''
  mocks.getTransactions.mockResolvedValue(structuredClone(listResponse))
  mocks.getYearOptions.mockResolvedValue([2026])
})

describe('TransactionsPage delete confirmation', () => {
  it('regular_5 and fx_5 stay distinct and delete through their own endpoints', async () => {
    mocks.deleteTransaction.mockResolvedValue(undefined)
    mocks.deleteFXTransaction.mockResolvedValue(undefined)
    const { wrapper } = await mountPage()

    const deleteButtons = [...document.querySelectorAll('button[aria-label^="Delete"]')]
    expect(deleteButtons.length).toBe(2)
    // regular_5 first row: its label carries the regular row's identity.
    expect(deleteButtons[0].getAttribute('aria-label')).toContain('ACME Corp')
    ;(deleteButtons[0] as HTMLElement).click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    // The list row already carries amount fields: no detail request needed.
    expect(mocks.getTransactionDetails).not.toHaveBeenCalled()
    expect(dialogElement().textContent).toContain('ACME Corp')
    confirmButton().click()
    await flushPromises()
    expect(mocks.deleteTransaction).toHaveBeenCalledTimes(1)
    expect(mocks.deleteTransaction).toHaveBeenCalledWith('5')
    expect(mocks.deleteFXTransaction).not.toHaveBeenCalled()

    // Now the FX row with the SAME numeric id.
    await new Promise((resolve) => setTimeout(resolve, 50))
    const fxDelete = [...document.querySelectorAll('button[aria-label^="Delete"]')]
      .find((btn) => btn.getAttribute('aria-label')!.includes('FX transaction on 2026-09-01')) as HTMLElement
    fxDelete.click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    confirmButton().click()
    await flushPromises()
    expect(mocks.deleteFXTransaction).toHaveBeenCalledTimes(1)
    expect(mocks.deleteFXTransaction).toHaveBeenCalledWith('5')
    expect(mocks.deleteTransaction).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps the fixed selection when the list changes underneath', async () => {
    const { wrapper, pinia } = await mountPage()
    ;([...document.querySelectorAll('button[aria-label^="Delete"]')]
      .find((btn) => btn.getAttribute('aria-label')!.includes('ACME Corp')) as HTMLElement).click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))

    // Filters retarget the underlying list while the dialog is open.
    mocks.getTransactions.mockResolvedValue({
      transactions: [{ ...fxRow }], total_items: 1, current_page: 1, total_pages: 1, currencies: ['USD'],
    })
    useAppStore(pinia).updateTableSettings({ search: 'something else', page: 1 })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 600))

    const dialog = dialogElement()
    expect(dialog.textContent).toContain('ACME Corp')
    expect(dialog.textContent).toContain('2026-09-08')
    // The visible list changed; the confirmation subject did not.
    expect(document.querySelectorAll('button[aria-label^="Delete"]').length).toBe(1)
    wrapper.unmount()
  })

  it('drops a late detail reply that outlives its subject', async () => {
    // List row WITHOUT amount fields forces a detail load before confirm.
    const bare = {
      ...regularRow, cash_flow: undefined, quantity: undefined, price: undefined,
    }
    mocks.getTransactions.mockResolvedValue({
      transactions: [bare, fxRow], total_items: 2, current_page: 1, total_pages: 1, currencies: ['USD'],
    })
    const slowDetail = deferred()
    mocks.getTransactionDetails.mockReturnValue(slowDetail.promise)
    const { wrapper } = await mountPage()

    ;([...document.querySelectorAll('button[aria-label^="Delete"]')]
      .find((btn) => btn.getAttribute('aria-label')!.includes('ACME Corp')) as HTMLElement).click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(mocks.getTransactionDetails).toHaveBeenCalledWith('5')

    // Close, then open the FX row (new subject, new generation).
    const cancel = dialogElement().querySelector('[data-testid="confirm-cancel"]') as HTMLElement
    cancel.click()
    await flushPromises()
    const fxDelete = [...document.querySelectorAll('button[aria-label^="Delete"]')]
      .find((btn) => btn.getAttribute('aria-label')!.includes('FX transaction on 2026-09-01')) as HTMLElement
    fxDelete.click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(dialogElement().textContent).toContain('2026-09-01')

    // The stale regular-detail reply finally lands: must not replace fx_5.
    slowDetail.resolve({ id: 5, currency: 'USD', date: '2026-09-08', cash_flow: '($1,215.00)', quantity: '10' })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(dialogElement().textContent).not.toContain('ACME Corp')
    expect(dialogElement().textContent).toContain('2026-09-01')
    wrapper.unmount()
  })

  it('disables deletion when the detail request fails', async () => {
    const bare = { ...regularRow, cash_flow: undefined, quantity: undefined, price: undefined }
    mocks.getTransactions.mockResolvedValue({
      transactions: [bare], total_items: 1, current_page: 1, total_pages: 1, currencies: ['USD'],
    })
    mocks.getTransactionDetails.mockRejectedValue({ detail: 'not found' })
    const { wrapper } = await mountPage()

    ;(document.querySelector('button[aria-label^="Delete"]') as HTMLElement).click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    const dialog = dialogElement()
    expect(dialog.textContent).toMatch(/could not load/i)
    expect(confirmButton().getAttribute('disabled')).not.toBeNull()
    expect(mocks.deleteTransaction).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('retains the subject and error after a rejected deletion', async () => {
    mocks.deleteTransaction.mockRejectedValue({ detail: 'Denied' })
    const { wrapper } = await mountPage()
    ;([...document.querySelectorAll('button[aria-label^="Delete"]')]
      .find((btn) => btn.getAttribute('aria-label')!.includes('ACME Corp')) as HTMLElement).click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    confirmButton().click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))

    const dialog = dialogElement()
    expect(dialog).toBeTruthy()
    expect(dialog.textContent).toContain('ACME Corp')
    expect(dialog.textContent).toMatch(/could not be deleted|failed|try again/i)
    expect(mocks.deleteTransaction).toHaveBeenCalledTimes(1)
    // Retry stays possible and stays on the same subject.
    confirmButton().click()
    await flushPromises()
    expect(mocks.deleteTransaction).toHaveBeenCalledTimes(2)
    expect(mocks.deleteTransaction).toHaveBeenLastCalledWith('5')
    wrapper.unmount()
  })

  it('deletes once on success, refreshes the query and closes', async () => {
    mocks.deleteTransaction.mockResolvedValue(undefined)
    const { wrapper } = await mountPage()
    const fetchCountBefore = mocks.getTransactions.mock.calls.length
    ;([...document.querySelectorAll('button[aria-label^="Delete"]')]
      .find((btn) => btn.getAttribute('aria-label')!.includes('ACME Corp')) as HTMLElement).click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    confirmButton().click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(mocks.deleteTransaction).toHaveBeenCalledTimes(1)
    expect(mocks.getTransactions.mock.calls.length).toBeGreaterThan(fetchCountBefore)
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeNull()
    wrapper.unmount()
  })

  it('closes and invalidates the pending subject when the auth session changes', async () => {
    mocks.getTransactionDetails.mockReturnValue(new Promise(() => {}))
    const bare = { ...regularRow, cash_flow: undefined, quantity: undefined, price: undefined }
    mocks.getTransactions.mockResolvedValue({
      transactions: [bare], total_items: 1, current_page: 1, total_pages: 1, currencies: ['USD'],
    })
    const { wrapper, pinia } = await mountPage()
    ;(document.querySelector('button[aria-label^="Delete"]') as HTMLElement).click()
    await flushPromises()
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeTruthy()

    useAuthStore(pinia).clearTokens()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeNull()
    wrapper.unmount()
  })
})
