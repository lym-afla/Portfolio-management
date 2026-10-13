// Phase C Task 7: compact "Currently held with" / "Previously held with"
// broker-account groups on the security page, defined as of the committed
// valuation date from the backend's canonical holdings read model. Clicking
// an account is an explicit filter action (the selector reflects it).
// RED-first against the page without the holdings section.
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
  configureContextFixture('2026-03-01')
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
    first_investment: 'None', open_position: '10.000000', current_value: '$100.00',
    realized: '–', unrealized: '–', capital_distribution: '–', irr: 'NA',
    holdings: [
      { account_id: 11, account_name: 'Main', broker_name: 'IBKR', display_name: 'IBKR – Main', quantity: '10.000000', status: 'open' },
      { account_id: 12, account_name: 'IIS', broker_name: 'Tinkoff', display_name: 'Tinkoff – IIS', quantity: '0.000000', status: 'closed' },
    ],
  })
  api.getSecurityTransactions.mockResolvedValue({ transactions: [], total_items: 0 })
  chartApi.fetchSecurityHistory.mockResolvedValue({ capability: 'legacy_only', legacy: [] })
})

describe('SecurityDetailPage holdings context (phase C)', () => {
  it('shows the currently-held accounts under "Currently held with"', async () => {
    const wrapper = await mountPage()
    const section = wrapper.get('[data-testid="security-holdings"]')
    const current = section.find('.holdings-group--current')
    expect(current.text()).toContain('Currently held with')
    expect(current.text()).toContain('IBKR – Main')
    expect(current.text()).toContain('10.000000')
    expect(current.text()).not.toContain('Tinkoff – IIS')
    wrapper.unmount()
  })

  it('shows sold-out accounts under "Previously held with"', async () => {
    const wrapper = await mountPage()
    const section = wrapper.get('[data-testid="security-holdings"]')
    const previous = section.find('.holdings-group--previous')
    expect(previous.text()).toContain('Previously held with')
    expect(previous.text()).toContain('Tinkoff – IIS')
    expect(previous.text()).toContain('0.000000')
    wrapper.unmount()
  })

  it('hides the section when the backend reports no holdings rows', async () => {
    api.getSecurityDetail.mockResolvedValue({
      id: 1, instrument_type: 'Stock', ISIN: 'X', name: 'Testco', currency: 'USD',
      first_investment: 'None', open_position: '0.000000', current_value: '$0.00',
      realized: '–', unrealized: '–', capital_distribution: '–', irr: 'NA',
      holdings: [],
    })
    const wrapper = await mountPage()
    expect(wrapper.find('[data-testid="security-holdings"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('clicking an account is an explicit filter: the selector reflects it', async () => {
    const wrapper = await mountPage()
    const section = wrapper.get('[data-testid="security-holdings"]')
    await section.findAll('.holdings-group__filter').at(0).trigger('click')
    await flushPromises()
    expect(wrapper.get('.v-select-stub__field').text()).toBe('IBKR Main')
    wrapper.unmount()
  })
})
