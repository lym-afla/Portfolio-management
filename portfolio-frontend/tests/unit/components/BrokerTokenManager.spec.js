import { mount } from '@vue/test-utils'
import BrokerTokenManager from '@/components/BrokerTokenManager.vue'
import {
  saveTinkoffToken,
  saveIBToken,
  saveBybitToken,
  saveOKXToken,
  getAvailableBrokers,
  getBrokerTokens
} from '@/services/api'
import { generateVuetifyStubs } from '../test-utils'

// Mock API calls
jest.mock('@/services/api', () => ({
  saveTinkoffToken: jest.fn(),
  saveIBToken: jest.fn(),
  saveBybitToken: jest.fn(),
  saveOKXToken: jest.fn(),
  getAvailableBrokers: jest.fn(),
  getBrokerTokens: jest.fn()
}))

describe('BrokerTokenManager', () => {
  const originalConsoleWarn = console.warn
  const originalConsoleError = console.error
  const originalConsoleLog = console.log

  beforeAll(() => {
    console.warn = jest.fn()
    console.error = jest.fn()
    console.log = jest.fn()
  })

  afterAll(() => {
    console.warn = originalConsoleWarn
    console.error = originalConsoleError
    console.log = originalConsoleLog
  })

  let wrapper

  beforeEach(() => {
    // Reset API mocks
    jest.clearAllMocks()

    // Mock API responses
    getAvailableBrokers.mockResolvedValue([
      { id: 1, name: 'Tinkoff Broker' },
      { id: 2, name: 'Interactive Brokers Main' },
      { id: 3, name: 'Custom Broker' },
      { id: 4, name: 'Bybit Unified' },
      { id: 5, name: 'OKX Trading' }
    ])

    getBrokerTokens.mockResolvedValue({
      tinkoff_tokens: [],
      ib_tokens: [],
      bybit_tokens: [],
      okx_tokens: []
    })

    // Create a div to mount the component
    const div = document.createElement('div')
    div.id = 'app'
    document.body.appendChild(div)

    // Mount component with generated stubs and form validation
    wrapper = mount(BrokerTokenManager, {
      attachTo: '#app',
      global: {
        stubs: {
          ...generateVuetifyStubs(),
          'v-form': {
            template: '<form class="v-form"><slot /></form>',
            methods: {
              validate: () => true
            }
          }
        }
      }
    })
  })

  afterEach(() => {
    // Clean up
    document.body.innerHTML = ''
    wrapper.unmount()
  })

  it('loads brokers on mount', async () => {
    // Wait for mounted hook to complete
    await wrapper.vm.$nextTick()

    // Verify that getAvailableBrokers was called
    expect(getAvailableBrokers).toHaveBeenCalled()
    expect(getBrokerTokens).toHaveBeenCalled()
  })

  it('automatically detects Tinkoff broker type', async () => {
    await wrapper.vm.handleBrokerSelection(1)
    expect(wrapper.vm.selectedBrokerType).toBe('tinkoff')
    expect(wrapper.vm.showBrokerTypeDialog).toBe(false)
  })

  it('automatically detects IB broker type', async () => {
    await wrapper.vm.handleBrokerSelection(2)
    expect(wrapper.vm.selectedBrokerType).toBe('ib')
    expect(wrapper.vm.showBrokerTypeDialog).toBe(false)
  })

  it('automatically detects Bybit broker type', async () => {
    await wrapper.vm.handleBrokerSelection(4)
    expect(wrapper.vm.selectedBrokerType).toBe('bybit')
    expect(wrapper.vm.showBrokerTypeDialog).toBe(false)
  })

  it('automatically detects OKX broker type', async () => {
    await wrapper.vm.handleBrokerSelection(5)
    expect(wrapper.vm.selectedBrokerType).toBe('okx')
    expect(wrapper.vm.showBrokerTypeDialog).toBe(false)
  })

  it('shows broker type dialog for custom broker', async () => {
    await wrapper.vm.handleBrokerSelection(3)
    expect(wrapper.vm.showBrokerTypeDialog).toBe(true)
    expect(wrapper.vm.selectedBrokerName).toBe('Custom Broker')
  })

  it('handles broker type selection confirmation', async () => {
    // Setup
    await wrapper.vm.handleBrokerSelection(3)
    wrapper.vm.selectedBrokerType = 'tinkoff'

    // Confirm selection
    await wrapper.vm.confirmBrokerType()

    // Verify results
    expect(wrapper.vm.newToken.broker).toBe(3)
    expect(wrapper.vm.newToken.token_type).toBe('read_only')
    expect(wrapper.vm.showBrokerTypeDialog).toBe(false)
  })

  it('saves Tinkoff token correctly', async () => {
    // Setup token data
    wrapper.vm.newToken = {
      broker: 1,
      token: 'test-token',
      token_type: 'read_only',
      sandbox_mode: false
    }
    wrapper.vm.selectedBrokerType = 'tinkoff'

    // No need to set $refs.form here as it's handled by the stub

    // Trigger save
    await wrapper.vm.saveToken()

    // Verify API call
    expect(saveTinkoffToken).toHaveBeenCalledWith({
      broker: 1,
      token: 'test-token',
      token_type: 'read_only',
      sandbox_mode: false
    })
  })

  it('saves IB token correctly', async () => {
    // Setup token data
    wrapper.vm.newToken = {
      broker: 2,
      token: 'test-token',
      account_id: 'U123456',
      paper_trading: false
    }
    wrapper.vm.selectedBrokerType = 'ib'

    // Mock successful API response
    saveIBToken.mockResolvedValue({
      message: 'Token saved successfully',
      id: 1
    })

    // Trigger save
    await wrapper.vm.saveToken()

    // Verify API call
    expect(saveIBToken).toHaveBeenCalledWith({
      broker: 2,
      token: 'test-token',
      account_id: 'U123456',
      paper_trading: false
    })
  })

  it('saves Bybit token correctly', async () => {
    wrapper.vm.newToken = {
      broker: 4,
      api_key: 'bybit-key',
      api_secret: 'bybit-secret',
      testnet: true
    }
    wrapper.vm.selectedBrokerType = 'bybit'

    await wrapper.vm.saveToken()

    expect(saveBybitToken).toHaveBeenCalledWith({
      broker: 4,
      api_key: 'bybit-key',
      api_secret: 'bybit-secret',
      testnet: true
    })
  })

  it('saves OKX token correctly', async () => {
    wrapper.vm.newToken = {
      broker: 5,
      api_key: 'okx-key',
      api_secret: 'okx-secret',
      passphrase: 'okx-passphrase',
      simulated_trading: true
    }
    wrapper.vm.selectedBrokerType = 'okx'

    await wrapper.vm.saveToken()

    expect(saveOKXToken).toHaveBeenCalledWith({
      broker: 5,
      api_key: 'okx-key',
      api_secret: 'okx-secret',
      passphrase: 'okx-passphrase',
      simulated_trading: true
    })
  })

  it('handles API errors gracefully', async () => {
    // Setup error scenario
    saveTinkoffToken.mockRejectedValue(new Error('API Error'))
    const errorSpy = jest.spyOn(wrapper.vm, 'handleError')

    // Setup token data
    wrapper.vm.newToken = {
      broker: 1,
      token: 'test-token',
      token_type: 'read_only',
      sandbox_mode: false
    }
    wrapper.vm.selectedBrokerType = 'tinkoff'

    // Trigger save
    await wrapper.vm.saveToken()

    // Verify error handling
    expect(errorSpy).toHaveBeenCalled()
    expect(wrapper.vm.isSaving).toBe(false)
  })
})
