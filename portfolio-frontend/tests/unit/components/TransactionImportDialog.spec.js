import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import TransactionImportDialog from '@/components/dialogs/TransactionImportDialog.vue'
import { getBrokersWithTokens } from '@/services/api'
import { generateVuetifyStubs } from '../test-utils'
import { useWebSocket } from '@/composables/useWebSocket'

// Mock API calls
jest.mock('@/services/api', () => ({
  getBrokersWithTokens: jest.fn()
}))

// Mock WebSocket composable
jest.mock('@/composables/useWebSocket', () => ({
  useWebSocket: jest.fn()
}))

// Store original console methods
const originalConsoleWarn = console.warn
const originalConsoleError = console.error

beforeAll(() => {
  // Disable console warnings and errors during tests
  console.warn = jest.fn()
  console.error = jest.fn()
})

afterAll(() => {
  // Restore original console methods
  console.warn = originalConsoleWarn
  console.error = originalConsoleError
})

describe('TransactionImportDialog', () => {
  let wrapper
  
  beforeEach(() => {
    // Reset API mocks
    jest.clearAllMocks()
    
    // Mock API responses
    getBrokersWithTokens.mockResolvedValue([
      { id: 1, name: 'Tinkoff Broker' },
      { id: 2, name: 'Interactive Brokers' }
    ])

    // Mock WebSocket composable
    const isConnected = ref(true)
    const lastMessage = ref(null)
    useWebSocket.mockReturnValue({
      isConnected,
      lastMessage,
      sendMessage: jest.fn(),
      connect: jest.fn(),
      disconnect: jest.fn(),
      reset: jest.fn()
    })

    // Create a div to mount the component
    const div = document.createElement('div')
    div.id = 'app'
    document.body.appendChild(div)

    // Mount component with generated stubs
    wrapper = mount(TransactionImportDialog, {
      attachTo: '#app',
      props: {
        modelValue: true
      },
      global: {
        stubs: {
          ...generateVuetifyStubs(),
          // Override v-tooltip stub to properly render its content
          'v-tooltip': {
            template: '<div class="v-tooltip"><slot name="activator" :props="{}"/></div>'
          }
        }
      }
    })
  })

  afterEach(() => {
    // Clean up
    document.body.innerHTML = ''
    if (wrapper) {
      wrapper.unmount()
    }
  })

  it('loads connected brokers on mount', async () => {
    // Wait for mounted hook to complete
    await wrapper.vm.$nextTick()
    
    // Verify that getBrokersWithTokens was called
    expect(getBrokersWithTokens).toHaveBeenCalled()
    
    // Verify that brokers were loaded into the component
    expect(wrapper.vm.connectedBrokerAccounts).toHaveLength(2)
    expect(wrapper.vm.hasConnectedBrokers).toBe(true)
  })

  it('handles import method selection correctly', async () => {
    await wrapper.vm.$nextTick()

    // Initially no method should be selected
    expect(wrapper.vm.importMethod).toBe(null)
    expect(wrapper.vm.importMethodSelected).toBe(false)

    // Test File Import selection
    await wrapper.vm.selectMethod('file')
    expect(wrapper.vm.importMethod).toBe('file')
    
    await wrapper.vm.confirmMethod()
    expect(wrapper.vm.importMethodSelected).toBe(true)

    // Test back to selection
    await wrapper.vm.backToSelection()
    expect(wrapper.vm.importMethod).toBe(null)
    expect(wrapper.vm.importMethodSelected).toBe(false)
    // Test API Import selection
    wrapper.vm.connectedBrokerAccounts = [
      { id: 1, name: 'Test Broker' }
    ]
    await wrapper.vm.$nextTick()

    await wrapper.vm.selectMethod('api')
    expect(wrapper.vm.importMethod).toBe('api')
    await wrapper.vm.confirmMethod()
    expect(wrapper.vm.importMethodSelected).toBe(true)

    // Verify form elements visibility after API selection
    const formElements = wrapper.findAll('.v-select, .v-text-field')
    expect(formElements.length).toBeGreaterThan(0)
  })

  it('disables API import when no brokers are connected', async () => {
    // Set no connected brokers
    wrapper.vm.connectedBrokerAccounts = []
    await wrapper.vm.$nextTick()

    // Try to select API import method
    await wrapper.vm.selectMethod('api')
    
    // Verify no selection was made
    expect(wrapper.vm.importMethod).toBe(null)
    expect(wrapper.vm.importMethodSelected).toBe(false)

    // Verify the disabled state through component data
    expect(wrapper.vm.hasConnectedBrokers).toBe(false)

    // Verify tooltip exists
    const tooltip = wrapper.find('.v-tooltip')
    expect(tooltip.exists()).toBe(true)
  })

  // Add a new test for UI elements
  it('renders import method cards correctly', async () => {
    await wrapper.vm.$nextTick()
    
    const cards = wrapper.findAll('.import-method-card')
    expect(cards.length).toBe(2)
    
    // Check API card (first card)
    const apiCard = cards[0]
    expect(apiCard.find('.v-card-title').text()).toBe('Direct Import')
    
    // Check File card (second card)
    const fileCard = cards[1]
    expect(fileCard.find('.v-card-title').text()).toBe('File Import')
  })

  it('validates API import form fields', async () => {
    await wrapper.vm.$nextTick()
    
    // Select API import method
    await wrapper.vm.selectMethod('api')
    await wrapper.vm.confirmMethod()
    await wrapper.vm.$nextTick()
    
    // Initially form should be invalid because no fields are filled
    expect(wrapper.vm.isApiImportValid).toBeFalsy()
    
    // Fill in form fields
    wrapper.vm.selectedBrokerAccount = { id: 1, name: 'Test Broker' }
    wrapper.vm.dateRange = {
      from: '2024-01-01',
      to: '2024-01-31'
    }
    await wrapper.vm.$nextTick()
    
    // Check if form fields are filled correctly
    expect(wrapper.vm.selectedBrokerAccount).toBeTruthy()
    expect(wrapper.vm.dateRange.from).toBe('2024-01-01')
    expect(wrapper.vm.dateRange.to).toBe('2024-01-31')
  })

  it('handles back to selection properly', async () => {
    await wrapper.vm.$nextTick()
    
    // Select API import and fill some data
    await wrapper.vm.selectMethod('api')
    await wrapper.vm.confirmMethod()
    wrapper.vm.selectedBrokerAccount = { id: 1, name: 'Test Broker' }
    wrapper.vm.dateRange = {
      from: '2024-01-01',
      to: '2024-01-31'
    }
    
    // Go back to selection
    await wrapper.vm.backToSelection()
    
    // Verify all form data is reset
    expect(wrapper.vm.importMethod).toBe(null)
    expect(wrapper.vm.importMethodSelected).toBe(false)
    expect(wrapper.vm.selectedBrokerAccount).toBe(null)
    expect(wrapper.vm.dateRange.from).toBe(null)
    expect(wrapper.vm.dateRange.to).toBe(null)
  })

  it('shows correct form based on selected import method', async () => {
    await wrapper.vm.$nextTick()
    
    // Select API import
    await wrapper.vm.selectMethod('api')
    await wrapper.vm.confirmMethod()
    
    // Should show API form elements
    expect(wrapper.find('.v-select').exists()).toBe(true)
    expect(wrapper.findAll('.v-text-field').length).toBe(2) // Date range fields
    expect(wrapper.find('.v-file-input').exists()).toBe(false)
    
    // Switch to File import
    await wrapper.vm.backToSelection()
    await wrapper.vm.selectMethod('file')
    await wrapper.vm.confirmMethod()
    
    // Should show File form elements
    expect(wrapper.find('.v-select').exists()).toBe(false)
    expect(wrapper.findAll('.v-text-field').length).toBe(0)
    expect(wrapper.find('.v-file-input').exists()).toBe(true)
  })

  it('handles dialog close properly', async () => {
    // Verify initial state
    expect(wrapper.vm.dialog).toBe(true)
    
    // Close dialog
    await wrapper.vm.closeDialog()
    
    // Verify dialog is closed and form is reset
    expect(wrapper.vm.dialog).toBe(false)
    expect(wrapper.vm.importMethod).toBe(null)
    expect(wrapper.vm.importMethodSelected).toBe(false)
    expect(wrapper.vm.file).toBe(null)
    expect(wrapper.vm.selectedBrokerAccount).toBe(null)
    expect(wrapper.vm.dateRange.from).toBe(null)
    expect(wrapper.vm.dateRange.to).toBe(null)
  })

  it('disables continue button when no method is selected', async () => {
    await wrapper.vm.$nextTick()
    
    // Initially button should be disabled
    const initialButton = wrapper.find('.v-btn[color="primary"]')
    expect(initialButton.attributes('disabled')).toBe('true')
    
    // Select a method
    await wrapper.vm.selectMethod('file')
    await wrapper.vm.$nextTick()
    
    // Find button again after state change
    const updatedButton = wrapper.find('.v-btn[color="primary"]')
    expect(updatedButton.attributes('disabled')).toBe('false')
  })
}) 