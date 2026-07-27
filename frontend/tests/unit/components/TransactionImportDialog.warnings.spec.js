import { mount } from '@vue/test-utils'
import { vi } from 'vitest'
import { ref } from 'vue'
import TransactionImportDialog from '@/components/dialogs/TransactionImportDialog.vue'
import { getBrokersWithTokens } from '@/services/api'
import { generateVuetifyStubs } from '../test-utils'
import { useWebSocket } from '@/composables/useWebSocket'

// Mock API calls
vi.mock('@/services/api', () => ({
  getBrokersWithTokens: vi.fn()
}))

// Mock WebSocket composable
vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn()
}))

// Silence noisy console output during the test
const originalConsoleWarn = console.warn
const originalConsoleError = console.error

beforeAll(() => {
  console.warn = vi.fn()
  console.error = vi.fn()
})

afterAll(() => {
  console.warn = originalConsoleWarn
  console.error = originalConsoleError
})

describe('TransactionImportDialog — partial_failures warnings', () => {
  let wrapper

  beforeEach(() => {
    vi.clearAllMocks()

    getBrokersWithTokens.mockResolvedValue([
      { id: 1, name: 'Tinkoff Broker' },
      { id: 2, name: 'Interactive Brokers' }
    ])

    const isConnected = ref(true)
    const lastMessage = ref(null)
    useWebSocket.mockReturnValue({
      isConnected,
      lastMessage,
      sendMessage: vi.fn(),
      connect: vi.fn(),
      disconnect: vi.fn(),
      reset: vi.fn()
    })

    const div = document.createElement('div')
    div.id = 'app'
    document.body.appendChild(div)

    wrapper = mount(TransactionImportDialog, {
      attachTo: '#app',
      props: {
        modelValue: true
      },
      global: {
        stubs: {
          ...generateVuetifyStubs(),
          'v-tooltip': {
            template: '<div class="v-tooltip"><slot name="activator" :props="{}"/></div>'
          }
        }
      }
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
    if (wrapper) {
      wrapper.unmount()
    }
  })

  it('renders warnings when import_complete payload includes a warnings field', async () => {
    await wrapper.vm.$nextTick()

    // Simulate the backend sending import_complete with partial_failures
    // threaded through as a warnings array (one entry per failed endpoint).
    wrapper.vm.handleImportSuccess({
      totalTransactions: 5,
      importedTransactions: 5,
      skippedTransactions: 0,
      duplicateTransactions: 0,
      importErrors: 0,
      warnings: [
        { endpoint: 'spot_fills', error: 'OKX HTTP 500: simulated 500' },
        { endpoint: 'option_settlements', error: 'OKX API error: bills archive cap' }
      ]
    })
    await wrapper.vm.$nextTick()

    // The success dialog must be open and the warning alert must render with
    // both endpoint names and error messages.
    expect(wrapper.vm.showSuccessDialog).toBe(true)
    expect(wrapper.vm.importStats.warnings).toHaveLength(2)

    const html = wrapper.html()
    expect(html).toContain('Some data sources could not be fetched')
    expect(html).toContain('spot_fills')
    expect(html).toContain('OKX HTTP 500: simulated 500')
    expect(html).toContain('option_settlements')
    expect(html).toContain('bills archive cap')
  })

  it('does not render the warnings alert when warnings is empty or absent', async () => {
    await wrapper.vm.$nextTick()

    // No warnings field at all (e.g. a clean import or a Tinkoff import).
    wrapper.vm.handleImportSuccess({
      totalTransactions: 3,
      importedTransactions: 3,
      skippedTransactions: 0,
      duplicateTransactions: 0,
      importErrors: 0
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.showSuccessDialog).toBe(true)
    expect(wrapper.vm.importStats.warnings).toEqual([])
    expect(wrapper.html()).not.toContain('Some data sources could not be fetched')
  })
})
