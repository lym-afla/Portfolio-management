import { mount } from '@vue/test-utils'
import { vi } from 'vitest'
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
vi.mock('@/services/api', () => ({
  saveTinkoffToken: vi.fn(),
  saveIBToken: vi.fn(),
  saveBybitToken: vi.fn(),
  saveOKXToken: vi.fn(),
  getAvailableBrokers: vi.fn(),
  getBrokerTokens: vi.fn()
}))

// D7: list/form/request ownership moved into features/brokers; this retained
// suite drives the same capabilities through the compatibility entrypoint and
// its BrokerConnectionForm child (the component that owns the draft now).
const formComponent = (wrapper) => {
  const form = wrapper.findComponent({ name: 'BrokerConnectionForm' })
  expect(form.exists(), 'BrokerConnectionForm child').toBe(true)
  return form
}

describe('BrokerTokenManager', () => {
  const originalConsoleWarn = console.warn
  const originalConsoleError = console.error
  const originalConsoleLog = console.log

  beforeAll(() => {
    console.warn = vi.fn()
    console.error = vi.fn()
    console.log = vi.fn()
  })

  afterAll(() => {
    console.warn = originalConsoleWarn
    console.error = originalConsoleError
    console.log = originalConsoleLog
  })

  let wrapper

  beforeEach(() => {
    // Reset API mocks
    vi.clearAllMocks()

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
    await formComponent(wrapper).vm.handleBrokerSelection(1)
    expect(formComponent(wrapper).vm.selectedProvider).toBe('tinkoff')
    expect(formComponent(wrapper).vm.brokerTypeDialogOpen).toBe(false)
  })

  it('automatically detects IB broker type', async () => {
    await formComponent(wrapper).vm.handleBrokerSelection(2)
    expect(formComponent(wrapper).vm.selectedProvider).toBe('ib')
    expect(formComponent(wrapper).vm.brokerTypeDialogOpen).toBe(false)
  })

  it('automatically detects Bybit broker type', async () => {
    await formComponent(wrapper).vm.handleBrokerSelection(4)
    expect(formComponent(wrapper).vm.selectedProvider).toBe('bybit')
    expect(formComponent(wrapper).vm.brokerTypeDialogOpen).toBe(false)
  })

  it('automatically detects OKX broker type', async () => {
    await formComponent(wrapper).vm.handleBrokerSelection(5)
    expect(formComponent(wrapper).vm.selectedProvider).toBe('okx')
    expect(formComponent(wrapper).vm.brokerTypeDialogOpen).toBe(false)
  })

  it('shows broker type dialog for custom broker', async () => {
    await formComponent(wrapper).vm.handleBrokerSelection(3)
    expect(formComponent(wrapper).vm.brokerTypeDialogOpen).toBe(true)
    expect(formComponent(wrapper).vm.unknownBrokerName).toBe('Custom Broker')
  })

  it('handles broker type selection confirmation', async () => {
    // Setup
    const form = formComponent(wrapper)
    await form.vm.handleBrokerSelection(3)
    form.vm.selectedBrokerType = 'tinkoff'

    // Confirm selection
    await form.vm.confirmBrokerType()

    // Verify results
    expect(form.vm.selectedBrokerId).toBe(3)
    expect(form.vm.draft.tokenType).toBe('read_only')
    expect(form.vm.brokerTypeDialogOpen).toBe(false)
  })

  const openAddDialog = async () => {
    const add = wrapper.findAll('.v-btn').find((b) => b.text() === 'Add Token')
    await add.trigger('click')
    await wrapper.vm.$nextTick()
  }

  it('saves Tinkoff token correctly', async () => {
    await openAddDialog()
    const form = formComponent(wrapper)
    expect(form.props('open')).toBe(true)
    await form.vm.handleBrokerSelection(1)
    form.vm.draft.token = 'test-token'

    // Trigger save
    await form.vm.saveToken()

    // Verify API call
    expect(saveTinkoffToken).toHaveBeenCalledWith({
      broker: 1,
      token: 'test-token',
      token_type: 'read_only',
      sandbox_mode: false
    })
  })

  it('saves IB token correctly', async () => {
    await openAddDialog()
    const form = formComponent(wrapper)
    await form.vm.handleBrokerSelection(2)
    form.vm.draft.token = 'test-token'
    form.vm.draft.accountId = 'U123456'

    // Mock successful API response
    saveIBToken.mockResolvedValue({
      message: 'Token saved successfully',
      id: 1
    })

    // Trigger save
    await form.vm.saveToken()

    // Verify API call
    expect(saveIBToken).toHaveBeenCalledWith({
      broker: 2,
      token: 'test-token',
      account_id: 'U123456',
      paper_trading: false
    })
  })

  it('saves Bybit token correctly', async () => {
    await openAddDialog()
    const form = formComponent(wrapper)
    await form.vm.handleBrokerSelection(4)
    form.vm.draft.apiKey = 'bybit-key'
    form.vm.draft.apiSecret = 'bybit-secret'
    form.vm.draft.testnet = true

    await form.vm.saveToken()

    expect(saveBybitToken).toHaveBeenCalledWith({
      broker: 4,
      api_key: 'bybit-key',
      api_secret: 'bybit-secret',
      testnet: true
    })
  })

  it('saves OKX token correctly', async () => {
    await openAddDialog()
    const form = formComponent(wrapper)
    await form.vm.handleBrokerSelection(5)
    form.vm.draft.apiKey = 'okx-key'
    form.vm.draft.apiSecret = 'okx-secret'
    form.vm.draft.passphrase = 'okx-passphrase'
    form.vm.draft.simulatedTrading = true

    await form.vm.saveToken()

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

    await openAddDialog()
    const form = formComponent(wrapper)
    await form.vm.handleBrokerSelection(1)
    form.vm.draft.token = 'test-token'

    // Trigger save
    await form.vm.saveToken()
    await form.vm.$nextTick()

    // Verify error handling: the manager emits an 'error' event and the
    // rejected save leaves the dialog open with the entry for retry.
    expect(wrapper.emitted('error')).toBeTruthy()
    expect(wrapper.vm.isSaving).toBe(false)
    expect(form.props('open')).toBe(true)
    expect(form.vm.draft.token).toBe('test-token')
  })
})
