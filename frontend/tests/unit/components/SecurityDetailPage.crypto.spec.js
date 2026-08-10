import { mount } from '@vue/test-utils'
import { vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import SecurityDetailPage from '@/views/database/SecurityDetailPage.vue'
import {
  getAccountChoices,
  getSecurityDetail,
  getSecurityPositionHistory,
  getSecurityPriceHistory,
  getSecurityTransactions,
} from '@/services/api'
import { useAppStore } from '@/stores/app'
import { getChartOptions } from '@/config/chartConfig'
import { generateVuetifyStubs } from '../test-utils'

vi.mock('chartjs-adapter-date-fns', () => ({}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 1 } }),
  useRouter: () => ({ push: vi.fn() }),
  createRouter: () => ({
    beforeEach: () => {},
    afterEach: () => {},
  }),
  createWebHistory: () => ({}),
}))

vi.mock('@/services/api', () => ({
  getAccountChoices: vi.fn(),
  getSecurityDetail: vi.fn(),
  getSecurityPositionHistory: vi.fn(),
  getSecurityPriceHistory: vi.fn(),
  getSecurityTransactions: vi.fn(),
}))

vi.mock('@/config/chartConfig', () => ({
  getChartOptions: vi.fn(),
}))

vi.mock('@/utils/logger', () => ({
  default: {
    log: vi.fn(),
    error: vi.fn(),
  },
  log: vi.fn(),
  error: vi.fn(),
}))

vi.mock('@/components/charts/LineChart.vue', () => ({
  default: {
    name: 'LineChart',
    template: '<div class="line-chart" />',
  },
}))

const flushPromises = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

describe('SecurityDetailPage crypto rewards', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    const appStore = useAppStore()
    // Seed the effective date so the page does not call the (mocked) API for it.
    appStore.setEffectiveCurrentDate('2026-01-02')
    // Guard: spy on fetchEffectiveCurrentDate in case the page falls back to it.
    vi.spyOn(appStore, 'fetchEffectiveCurrentDate').mockResolvedValue()

    getAccountChoices.mockResolvedValue({ options: [] })
    getSecurityDetail.mockResolvedValue({
      id: 1,
      instrument_type: 'Crypto',
      ISIN: 'CRYPTO:BTC',
      name: 'Bitcoin',
      currency: 'USD',
      first_investment: '01-Jan-26',
      open_position: '0.010000000',
      current_value: '$500.00',
      realized: '–',
      unrealized: '–',
      capital_distribution: '$500.00',
      irr: 'NA',
      crypto_reward_native_quantity: '0.010000000',
      crypto_reward_fiat_value: '500.00',
    })
    getSecurityPriceHistory.mockResolvedValue([])
    getSecurityPositionHistory.mockResolvedValue([])
    getSecurityTransactions.mockResolvedValue({
      transactions: [],
      total_items: 0,
    })
    getChartOptions.mockResolvedValue({
      colorPalette: ['#000000', '#111111'],
      navChartOptions: {},
    })
  })

  it('renders native and fiat reward totals for crypto securities', async () => {
    const wrapper = mount(SecurityDetailPage, {
      global: {
        stubs: {
          ...generateVuetifyStubs(),
          'v-skeleton-loader': true,
          'v-table': {
            template: '<table><slot /></table>',
          },
          'v-data-table': {
            template: '<div><slot name="bottom" /></div>',
          },
          'v-pagination': true,
          'v-divider': true,
          'v-list-subheader': {
            template: '<div><slot /></div>',
          },
          TimelineSelector: true,
          TransactionRow: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Crypto Rewards')
    expect(wrapper.text()).toContain('Native rewards')
    expect(wrapper.text()).toContain('0.010000000')
    expect(wrapper.text()).toContain('Fiat reward value')
    expect(wrapper.text()).toContain('500.00')
  })
})
