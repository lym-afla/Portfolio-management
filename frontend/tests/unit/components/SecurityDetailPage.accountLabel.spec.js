// Phase C Task 7: the local Broker Account selector visibly says
// "All accounts" while the request is unfiltered, preserves explicit
// selections and the safe 'Unavailable' label. RED-first: the field was
// blank when no account was chosen.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

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

// The selection slot is the surface under test: render it explicitly; the
// tests drive update:modelValue directly (the same event v-model listens to).
const VSelectStub = {
  name: 'VSelect',
  props: ['modelValue', 'items', 'itemTitle', 'itemValue', 'label', 'clearable'],
  emits: ['update:modelValue'],
  template: `<div class="v-select-stub"><span class="v-select-stub__field"><slot name="selection" /></span></div>`,
}

const flushPromises = async () => {
  for (let i = 0; i < 4; i += 1) await new Promise((resolve) => setTimeout(resolve, 0))
}

async function mountPage() {
  const pinia = createPinia()
  setActivePinia(pinia)
  configureContextFixture('2026-01-02')
  await usePortfolioContextStore().reconcileContext()
  vi.spyOn(useAppStore(), 'fetchEffectiveCurrentDate').mockResolvedValue()
  const wrapper = mount(SecurityPage, {
    global: {
      plugins: [pinia],
      stubs: {
        ...generateVuetifyStubs(),
        'v-select': VSelectStub,
        TimelineSelector: true,
        TransactionRow: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}

const selectAccount = async (wrapper, value) => {
  await wrapper.findComponent(VSelectStub).vm.$emit('update:modelValue', value)
  await flushPromises()
}

// Imported after mocks so the page module resolves against them.
import SecurityPage from '@/views/database/SecurityDetailPage.vue'
import { generateVuetifyStubs } from '../test-utils'
import { configureContextFixture } from '../context-fixture'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { useAppStore } from '@/stores/app'

beforeEach(() => {
  vi.clearAllMocks()
  api.getAccountChoices.mockResolvedValue({ options: [
    ['General', [['All accounts', { type: 'all', id: null }]]],
    '__SEPARATOR__',
    ['Your Accounts', [
      ['IBKR Main', { type: 'account', id: 11, display_name: 'IBKR Main' }],
      ['Tinkoff IIS', { type: 'account', id: 12, display_name: 'Tinkoff IIS' }],
    ]],
  ] })
  api.getSecurityDetail.mockResolvedValue({
    id: 1, instrument_type: 'Stock', ISIN: 'X', name: 'Testco', currency: 'USD',
    first_investment: 'None', open_position: '1', current_value: '$1.00',
    realized: '–', unrealized: '–', capital_distribution: '–', irr: 'NA',
  })
  api.getSecurityTransactions.mockResolvedValue({ transactions: [], total_items: 0 })
  chartApi.fetchSecurityHistory.mockResolvedValue({
    capability: 'legacy_only',
    legacy: [],
  })
})

describe('SecurityDetailPage account selector label (phase C)', () => {
  it('visibly says "All accounts" while the request is unfiltered', async () => {
    const wrapper = await mountPage()
    expect(wrapper.get('.v-select-stub__field').text()).toBe('All accounts')
    wrapper.unmount()
  })

  it('shows the explicit selection display name', async () => {
    const wrapper = await mountPage()
    await selectAccount(wrapper, { type: 'account', id: 11 })
    expect(wrapper.get('.v-select-stub__field').text()).toBe('IBKR Main')
    wrapper.unmount()
  })

  it('keeps the safe Unavailable label for a selection missing from the options', async () => {
    const wrapper = await mountPage()
    await selectAccount(wrapper, { type: 'account', id: 999 })
    expect(wrapper.get('.v-select-stub__field').text()).toBe('Unavailable')
    wrapper.unmount()
  })
})
