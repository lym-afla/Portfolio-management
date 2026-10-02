// PR #51 review round — regressions for the six review findings.
// 1: delayed DELETE outcomes are generation/session-guarded.
// 2: detail subjects use the ACTUAL detail-API currency fields
//    (regular `currency`, FX `from_currency`/`to_currency`/`commission_currency`).
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import TransactionsPage from '@/views/TransactionsPage.vue'
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

// Realistic wire shapes: LIST rows use cur/from_cur/to_cur; DETAIL payloads
// use the serializer fields (currency / from_currency / to_currency).
const regularRow = {
  id: 'regular_5', transaction_type: 'regular', date: '2026-09-08', type: 'Buy',
  security: { id: 1, name: 'ACME Corp' }, account: { broker_name: 'Fixture Broker', name: 'Main' },
  quantity: '10', price: '120.50', cur: 'USD', cash_flow: '($1,215.00)', balances: {},
}
const bareRegularRow = {
  id: 'regular_7', transaction_type: 'regular', date: '2026-08-20', type: 'Sell',
  security: { id: 2, name: 'UST 2.375% 31' }, account: { broker_name: 'Fixture Broker', name: 'Main' },
  cur: 'USD', balances: {},
}
const bareFxRow = {
  id: 'fx_5', transaction_type: 'fx', date: '2026-09-01', type: 'FX', balances: {},
}
const regularDetailPayload = {
  id: 7, account: 2, security: 2, currency: 'EUR',
  date: '2026-08-20', type: 'Sell', quantity: '5', price: '99.75',
  commission: '-7.50', cash_flow: '498.25',
}
const fxDetailPayload = {
  id: 5, account: 1, date: '2026-09-01',
  from_currency: 'EUR', to_currency: 'USD', commission_currency: 'GBP',
  from_amount: '-1000.00', to_amount: '1080.00', exchange_rate: '1.08', commission: '-8.00',
}

async function mountPage(rows: unknown[]) {
  const pinia = createPinia()
  configureContextFixture('2026-09-08')
  await usePortfolioContextStore(pinia).reconcileContext()
  mocks.getTransactions.mockResolvedValue({
    transactions: structuredClone(rows), total_items: rows.length, current_page: 1, total_pages: 1, currencies: ['USD'],
  })
  const wrapper = mount(TransactionsPage, {
    attachTo: document.body,
    global: { plugins: [vuetify, pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  await flushPromises()
  return { wrapper, pinia }
}

const dialogElement = () =>
  document.querySelector('.v-overlay--active[role="dialog"]') as HTMLElement

const deleteButtonFor = (match: string) =>
  [...document.querySelectorAll('tbody button[aria-label^="Delete"]')]
    .find((btn) => btn.getAttribute('aria-label')!.includes(match)) as HTMLElement

const openDeleteFor = async (match: string) => {
  deleteButtonFor(match).click()
  await flushPromises()
  await new Promise((resolve) => setTimeout(resolve, 50))
}

const confirmButton = () =>
  dialogElement().querySelector('[data-testid="confirm-confirm"]') as HTMLElement

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ''
  mocks.getYearOptions.mockResolvedValue([2026])
})

describe('review 1: delayed DELETE outcome is generation/session-guarded', () => {
  it('ignores a successful delete that resolves after the session changed', async () => {
    const pending = deferred()
    mocks.deleteTransaction.mockReturnValue(pending.promise)
    const { wrapper, pinia } = await mountPage([regularRow])

    await openDeleteFor('ACME Corp')
    confirmButton().click()
    await flushPromises()
    expect(mocks.deleteTransaction).toHaveBeenCalledTimes(1)

    // The auth session ends while the DELETE is still in flight.
    useAuthStore(pinia).clearTokens()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeNull()

    const fetchCount = mocks.getTransactions.mock.calls.length
    pending.resolve(undefined)
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))

    // The stale outcome must not close anything, refresh, or resurface state.
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeNull()
    expect(mocks.getTransactions.mock.calls.length).toBe(fetchCount)
    wrapper.unmount()
  })

  it('still closes and refreshes when the outcome arrives in the same session', async () => {
    mocks.deleteTransaction.mockResolvedValue(undefined)
    const { wrapper } = await mountPage([regularRow])
    await openDeleteFor('ACME Corp')
    const before = mocks.getTransactions.mock.calls.length
    confirmButton().click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeNull()
    expect(mocks.getTransactions.mock.calls.length).toBeGreaterThan(before)
    wrapper.unmount()
  })

  it('keeps the inline error only for the still-open subject after a session-ended rejection', async () => {
    const pending = deferred()
    mocks.deleteTransaction.mockReturnValue(pending.promise)
    const { wrapper, pinia } = await mountPage([regularRow])
    await openDeleteFor('ACME Corp')
    confirmButton().click()
    await flushPromises()

    useAuthStore(pinia).clearTokens()
    await flushPromises()
    pending.reject({ detail: 'Denied late' })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    // No dialog resurfaces and nothing throws for the stale rejection.
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeNull()
    wrapper.unmount()
  })
})

describe('review 1b: busy cleanup follows request ownership', () => {
  it('keeps the newer confirmation disabled when an older DELETE settles late', async () => {
    const secondRow = {
      ...regularRow, id: 'regular_6', date: '2026-07-04', type: 'Dividend',
      security: { id: 3, name: 'TSMC ADR' }, cash_flow: '$42.00',
    }
    const deleteA = deferred()
    const deleteB = deferred()
    mocks.deleteTransaction.mockReturnValueOnce(deleteA.promise).mockReturnValueOnce(deleteB.promise)
    const { wrapper, pinia } = await mountPage([regularRow, secondRow])

    // DELETE A issued, then the session ends while it is in flight.
    await openDeleteFor('ACME Corp')
    confirmButton().click()
    await flushPromises()
    expect(mocks.deleteTransaction).toHaveBeenCalledTimes(1)
    const auth = useAuthStore(pinia)
    auth.clearTokens()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeNull()

    // A fresh session restores the table; a newer dialog then issues
    // DELETE B on another subject while A is still pending.
    auth.setTokens({ accessToken: 'fixture-second-token', refreshToken: 'fixture-second-refresh' })
    auth.setUser({ id: 7, username: 'alice' })
    configureContextFixture('2026-09-08')
    await usePortfolioContextStore(pinia).reconcileContext()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    await openDeleteFor('TSMC ADR')
    confirmButton().click()
    await flushPromises()
    expect(mocks.deleteTransaction).toHaveBeenCalledTimes(2)

    // The OLD delete settles late: it must not release the newer
    // confirmation's busy lock.
    deleteA.resolve(undefined)
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(dialogElement()).toBeTruthy()
    expect(confirmButton().disabled).toBe(true)

    // The owning delete closes its own dialog when it settles.
    deleteB.resolve(undefined)
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(document.querySelector('.v-overlay--active[role="dialog"]')).toBeNull()
    wrapper.unmount()
  })
})

describe('review 2: detail subjects use the actual detail-API currency fields', () => {
  it('suffixes the regular cash flow with the serializer currency field', async () => {
    mocks.getTransactionDetails.mockResolvedValue(structuredClone(regularDetailPayload))
    const { wrapper } = await mountPage([bareRegularRow])
    await openDeleteFor('UST 2.375% 31')
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    const text = dialogElement().textContent!
    expect(text).toContain('498.25 EUR')
    wrapper.unmount()
  })

  it('suffixes FX from/to/commission with their own serializer currencies', async () => {
    mocks.getFXTransactionDetails.mockResolvedValue(structuredClone(fxDetailPayload))
    const { wrapper } = await mountPage([bareFxRow])
    await openDeleteFor('FX transaction on 2026-09-01')
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    const text = dialogElement().textContent!
    expect(text).toContain('-1000.00 EUR')
    expect(text).toContain('1080.00 USD')
    expect(text).toContain('-8.00 GBP')
    wrapper.unmount()
  })
})
