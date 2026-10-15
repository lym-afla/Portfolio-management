// Review round 2: the account SCOPE must never silently broaden. The
// canonical identity lives in request-owning state; the Vuetify select model
// and label are derived display surfaces. These tests wire the REAL Vuetify
// select to the actual request owner and assert, per scenario, the visible
// text, the underlying input value, the identity's effect on requests
// (account_id present/absent) and the absence of unfiltered fallbacks.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const api = vi.hoisted(() => ({
  getAccountChoices: vi.fn(),
  getSecurityDetail: vi.fn(),
  getSecurityTransactions: vi.fn(),
}))
vi.mock('@/services/api', () => api)

const chartApi = vi.hoisted(() => ({
  fetchSecurityHistory: vi.fn(),
}))
vi.mock('@/features/charts/chartApi', () => chartApi)

vi.mock('@/config/chartConfig', () => ({
  getChartOptions: vi.fn(async () => ({ navChartOptions: {} })),
  colorPalette: ['#0F4C81'],
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 1 } }),
  useRouter: () => ({ push: vi.fn() }),
  createRouter: () => ({
    beforeEach: () => {},
    afterEach: () => {},
    onError: () => {},
  }),
  createWebHistory: () => ({}),
}))


const WIRE_CHOICES = [
  ['General', [['All accounts', { type: 'all', id: null }]]],
  '__SEPARATOR__',
  ['Your Accounts', [
    ['IBKR Main', { type: 'account', id: 11, display_name: 'IBKR Main' }],
    ['Tinkoff IIS', { type: 'account', id: 12, display_name: 'Tinkoff IIS' }],
  ]],
]

const CHOICES_WITHOUT_11 = [
  ['General', [['All accounts', { type: 'all', id: null }]]],
  '__SEPARATOR__',
  ['Your Accounts', [
    ['Tinkoff IIS', { type: 'account', id: 12, display_name: 'Tinkoff IIS' }],
  ]],
]

const vuetify = createVuetify({ components, directives })

async function mountPage() {
  const pinia = createPinia()
  setActivePinia(pinia)
  configureContextFixture('2026-01-02')
  await usePortfolioContextStore().reconcileContext()
  vi.spyOn(useAppStore(), 'fetchEffectiveCurrentDate').mockResolvedValue()
  const wrapper = mount(SecurityPage, {
    global: {
      plugins: [vuetify, pinia],
      stubs: {
        'v-skeleton-loader': true,
        TimelineSelector: true,
        TransactionRow: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}

const fieldState = (wrapper) => {
  const label = wrapper.find('.security-account-label')
  const input = wrapper.find('input')
  return {
    visible: label.exists() ? label.text() : null,
    inputValue: input.exists() ? input.element.value : null,
  }
}

const expectSafe = (state) => {
  expect(String(state.inputValue ?? '')).not.toContain('[object Object]')
  expect(String(state.inputValue ?? '')).not.toMatch(/\{/)
}

/** The latest position-history request's account_id (absent = unfiltered). */
const lastPositionAccountFilter = () => {
  const call = chartApi.fetchSecurityHistory.mock.calls.filter((call) => call[1] === 'position').at(-1)
  return call ? call[0].accountId ?? null : undefined
}



const clickHoldingsFilter = async (wrapper) => {
  await wrapper.find('[data-testid="security-holdings"] .holdings-group__filter').trigger('click')
  await flushPromises()
}

// Imported after mocks so the page module resolves against them.
import SecurityPage from '@/views/database/SecurityDetailPage.vue'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'

beforeEach(() => {
  vi.clearAllMocks()
  api.getAccountChoices.mockResolvedValue({ options: WIRE_CHOICES })
  api.getSecurityDetail.mockResolvedValue({
    id: 1, instrument_type: 'Stock', ISIN: 'X', name: 'Testco', currency: 'USD',
    first_investment: 'None', open_position: '1', current_value: '$1.00',
    realized: '–', unrealized: '–', capital_distribution: '–', irr: 'NA',
    holdings: [
      { account_id: 11, account_name: 'Main', broker_name: 'IBKR', display_name: 'IBKR – Main', quantity: '1.000000000', quantity_display: '1.000000000', status: 'open' },
    ],
  })
  api.getSecurityTransactions.mockResolvedValue({ transactions: [], total_items: 0 })
  chartApi.fetchSecurityHistory.mockResolvedValue({ capability: 'legacy_only', legacy: [] })
})

describe('account scope survives display fallbacks (review round 2)', () => {
  it('keeps identity A and its account filter when the A option later disappears', async () => {
    const wrapper = await mountPage()
    const vs = wrapper.findComponent({ name: 'VSelect' })
    await vs.vm.$emit('update:modelValue', { type: 'account', id: 11 })
    await flushPromises()
    expect(fieldState(wrapper).visible).toBe('IBKR Main')

    // The choices refresh without account 11 (e.g. it vanished server-side).
    api.getAccountChoices.mockResolvedValue({ options: CHOICES_WITHOUT_11 })
    usePortfolioContextStore().triggerDataRefresh()
    await flushPromises()

    // Display falls back safely; identity and request scope DO NOT.
    const state = fieldState(wrapper)
    expect(state.visible).toBe('Unavailable')
    expectSafe(state)
    // The next scoped refresh still requests account 11 — never unfiltered.
    usePortfolioContextStore().triggerDataRefresh()
    await flushPromises()
    expect(lastPositionAccountFilter()).toBe(11)
    wrapper.unmount()
  })

  it('a holdings click with delayed choices preserves and requests that account', async () => {
    let release
    api.getAccountChoices.mockReturnValue(new Promise((resolve) => { release = resolve }))
    const wrapper = await mountPage()
    // Choices are still pending: the select shows the safe fallback.
    expect(fieldState(wrapper).visible).toBe('All accounts')

    await clickHoldingsFilter(wrapper)
    // The qualified display name from the holdings row is the honest label.
    expect(fieldState(wrapper).visible).toBe('IBKR – Main')
    expectSafe(fieldState(wrapper))
    // The click requested THAT account, never all accounts.
    expect(lastPositionAccountFilter()).toBe(11)

    // Choices arrive late: the matched label restores automatically and the
    // scope does not change (no unfiltered re-request).
    const scopedBefore = chartApi.fetchSecurityHistory.mock.calls.length
    release({ options: WIRE_CHOICES })
    await flushPromises()
    expect(fieldState(wrapper).visible).toBe('IBKR Main')
    expectSafe(fieldState(wrapper))
    const callsSince = chartApi.fetchSecurityHistory.mock.calls.slice(scopedBefore)
    for (const call of callsSince) {
      expect(call[0].accountId).toBe(11)
    }
    wrapper.unmount()
  })

  it('restoring choices returns the matched label without a scope change', async () => {
    // Identity A while choices lack it.
    api.getAccountChoices.mockResolvedValue({ options: CHOICES_WITHOUT_11 })
    const wrapper = await mountPage()
    const vs = wrapper.findComponent({ name: 'VSelect' })
    await vs.vm.$emit('update:modelValue', { type: 'account', id: 11 })
    await flushPromises()
    expect(fieldState(wrapper).visible).toBe('Unavailable')
    expect(lastPositionAccountFilter()).toBe(11)

    // Choices return WITH account 11: the label restores automatically.
    api.getAccountChoices.mockResolvedValue({ options: WIRE_CHOICES })
    const before = chartApi.fetchSecurityHistory.mock.calls.length
    usePortfolioContextStore().triggerDataRefresh()
    await flushPromises()
    expect(fieldState(wrapper).visible).toBe('IBKR Main')
    expectSafe(fieldState(wrapper))
    // The identity did not change: the refreshed scoped requests still carry 11
    // and no unfiltered request appeared.
    const since = chartApi.fetchSecurityHistory.mock.calls.slice(before)
    assert(since.length > 0, 'the refresh re-issued the scoped requests')
    // Position requests carry the account; price requests have no account
    // parameter by contract (neither ever falls back to unfiltered).
    for (const call of since) {
      const expectedAccountId = call[1] === 'position' ? 11 : null
      expect(call[0].accountId).toBe(expectedAccountId)
    }
    wrapper.unmount()
  })

  it('explicit Clear requests the unfiltered scope on purpose', async () => {
    const wrapper = await mountPage()
    const vs = wrapper.findComponent({ name: 'VSelect' })
    await vs.vm.$emit('update:modelValue', { type: 'account', id: 11 })
    await flushPromises()
    expect(lastPositionAccountFilter()).toBe(11)
    await vs.vm.$emit('update:modelValue', null)
    await flushPromises()
    expect(fieldState(wrapper).visible).toBe('All accounts')
    expectSafe(fieldState(wrapper))
    expect(lastPositionAccountFilter()).toBeNull()
    wrapper.unmount()
  })
})

import { strict as assert } from 'node:assert'
