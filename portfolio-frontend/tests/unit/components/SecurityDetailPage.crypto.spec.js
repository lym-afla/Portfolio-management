import { mount } from '@vue/test-utils'
import SecurityDetailPage from '@/views/database/SecurityDetailPage.vue'
import {
  getAccountChoices,
  getSecurityDetail,
  getSecurityPositionHistory,
  getSecurityPriceHistory,
  getSecurityTransactions,
} from '@/services/api'
import { getChartOptions } from '@/config/chartConfig'
import { generateVuetifyStubs } from '../test-utils'

jest.mock('chartjs-adapter-date-fns', () => ({}))

jest.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 1 } }),
}))

const mockDispatch = jest.fn()

jest.mock('vuex', () => ({
  useStore: () => ({
    state: { effectiveCurrentDate: '2026-01-02' },
    dispatch: mockDispatch,
  }),
}))

jest.mock('@/services/api', () => ({
  getAccountChoices: jest.fn(),
  getSecurityDetail: jest.fn(),
  getSecurityPositionHistory: jest.fn(),
  getSecurityPriceHistory: jest.fn(),
  getSecurityTransactions: jest.fn(),
}))

jest.mock('@/config/chartConfig', () => ({
  getChartOptions: jest.fn(),
}))

jest.mock('@/utils/logger', () => ({
  log: jest.fn(),
  error: jest.fn(),
}))

jest.mock('@/components/charts/LineChart.vue', () => ({
  name: 'LineChart',
  template: '<div class="line-chart" />',
}))

const flushPromises = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

describe('SecurityDetailPage crypto rewards', () => {
  beforeEach(() => {
    jest.clearAllMocks()
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
    mockDispatch.mockResolvedValue()
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
