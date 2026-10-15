// Review finding 2: the security account selector must be safe under REAL
// Vuetify — the stubbed specs cannot see the underlying input value. Visible
// text AND input value are asserted for: empty choices, delayed choices,
// missing specific accounts, clear, and normal selections. No '[object
// Object]' and no JSON braces may ever reach the input.
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

const vuetify = createVuetify({ components, directives })

async function mountPage({ choices } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  configureContextFixture('2026-01-02')
  await usePortfolioContextStore().reconcileContext()
  vi.spyOn(useAppStore(), 'fetchEffectiveCurrentDate').mockResolvedValue()
  if (choices !== undefined) api.getAccountChoices.mockResolvedValue({ options: choices })
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

// Real Vuetify renders the select: the field's visible text and the actual
// input element are both under test.
const fieldState = (wrapper) => {
  const label = wrapper.find('.security-account-label')
  const input = wrapper.find('input')
  return {
    visible: label.exists() ? label.text() : null,
    inputValue: input.exists() ? input.element.value : null,
  }
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
  })
  api.getSecurityTransactions.mockResolvedValue({ transactions: [], total_items: 0 })
  chartApi.fetchSecurityHistory.mockResolvedValue({ capability: 'legacy_only', legacy: [] })
})

describe('SecurityDetailPage account selector under real Vuetify (review finding 2)', () => {
  it('shows All accounts with a safe input value while unfiltered', async () => {
    const wrapper = await mountPage()
    const state = fieldState(wrapper)
    expect(state.visible).toBe('All accounts')
    expect(state.inputValue ?? '').not.toContain('[object Object]')
    expect(state.inputValue ?? '').not.toMatch(/[{}]/)
    wrapper.unmount()
  })

  it('shows All accounts with safe input when the choices list is EMPTY', async () => {
    const wrapper = await mountPage({ choices: [] })
    const state = fieldState(wrapper)
    expect(state.visible).toBe('All accounts')
    expect(state.inputValue ?? '').not.toContain('[object Object]')
    expect(state.inputValue ?? '').not.toMatch(/[{}]/)
    wrapper.unmount()
  })

  it('stays All accounts while the choices have not arrived yet (delayed)', async () => {
    let release
    api.getAccountChoices.mockReturnValue(new Promise((resolve) => { release = resolve }))
    const pinia = createPinia()
    setActivePinia(pinia)
    configureContextFixture('2026-01-02')
    await usePortfolioContextStore().reconcileContext()
    vi.spyOn(useAppStore(), 'fetchEffectiveCurrentDate').mockResolvedValue()
    const wrapper = mount(SecurityPage, {
      global: { plugins: [vuetify, pinia], stubs: { 'v-skeleton-loader': true, TimelineSelector: true, TransactionRow: true } },
    })
    await flushPromises()
    const state = fieldState(wrapper)
    expect(state.visible).toBe('All accounts')
    expect(state.inputValue ?? '').not.toContain('[object Object]')
    release({ options: WIRE_CHOICES })
    await flushPromises()
    expect(fieldState(wrapper).visible).toBe('All accounts')
    wrapper.unmount()
  })

  it('never renders object or JSON text for a MISSING specific account', async () => {
    const wrapper = await mountPage()
    const vs = wrapper.findComponent({ name: 'VSelect' })
    await vs.vm.$emit('update:modelValue', { type: 'account', id: 999 })
    await flushPromises()
    const state = fieldState(wrapper)
    expect(state.visible).toBe('Unavailable')
    expect(String(state.inputValue ?? '')).not.toContain('[object Object]')
    expect(String(state.inputValue ?? '')).not.toMatch(/\{.*type.*account/)
    wrapper.unmount()
  })

  it('renders the matched display name for a normal selection with a safe input', async () => {
    const wrapper = await mountPage()
    const vs = wrapper.findComponent({ name: 'VSelect' })
    await vs.vm.$emit('update:modelValue', { type: 'account', id: 11 })
    await flushPromises()
    const state = fieldState(wrapper)
    expect(state.visible).toBe('IBKR Main')
    expect(String(state.inputValue ?? '')).not.toContain('[object Object]')
    wrapper.unmount()
  })

  it('returns to All accounts on clear with a safe input', async () => {
    const wrapper = await mountPage()
    const vs = wrapper.findComponent({ name: 'VSelect' })
    await vs.vm.$emit('update:modelValue', { type: 'account', id: 11 })
    await flushPromises()
    // clearable emits null.
    await vs.vm.$emit('update:modelValue', null)
    await flushPromises()
    const state = fieldState(wrapper)
    expect(state.visible).toBe('All accounts')
    expect(String(state.inputValue ?? '')).not.toContain('[object Object]')
    wrapper.unmount()
  })
})
