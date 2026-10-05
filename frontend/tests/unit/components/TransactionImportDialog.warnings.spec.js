import { mount } from '@vue/test-utils'
import { vi } from 'vitest'
import { ref } from 'vue'
import TransactionImportDialog from '@/components/dialogs/TransactionImportDialog.vue'
import { getBrokersWithTokens } from '@/services/api'
import { generateVuetifyStubs } from '../test-utils'
import { useWebSocket } from '@/composables/useWebSocket'

// Mock API calls
vi.mock('@/services/api', () => ({
  getBrokersWithTokens: vi.fn(),
  analyzeFile: vi.fn(),
  getAccounts: vi.fn(),
}))

// Mock WebSocket composable
vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(),
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
  let lastMessage
  let connect

  beforeEach(async () => {
    vi.clearAllMocks()

    getBrokersWithTokens.mockResolvedValue([
      { id: 1, name: 'Tinkoff Broker' },
      { id: 2, name: 'Interactive Brokers' }
    ])

    const isConnected = ref(true)
    lastMessage = ref(null)
    connect = vi.fn(async () => true)
    useWebSocket.mockReturnValue({
      isConnected,
      lastMessage,
      sendMessage: vi.fn(() => true),
      connect,
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
    await wrapper.vm.$nextTick()
  })

  afterEach(() => {
    document.body.innerHTML = ''
    if (wrapper) {
      wrapper.unmount()
    }
  })

  // The import workflow only accepts completions inside an active session,
  // so the driver starts a synthetic API run before feeding the event.
  const startSyntheticRun = async () => {
    wrapper.vm.selectedBroker = { id: 11, name: 'Tinkoff Broker' }
    await wrapper.vm.startApiImport()
    lastMessage.value = {
      type: 'import_update',
      data: { status: 'progress', current: 1, message: 'Importing...', progress: 10 }
    }
    await wrapper.vm.$nextTick()
  }

  const completeWith = async (payload) => {
    lastMessage.value = {
      type: 'import_complete',
      data: payload,
      message: 'Import process completed'
    }
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
  }

  it('renders warnings when import_complete payload includes a warnings field', async () => {
    await startSyntheticRun()

    // Simulate the backend sending import_complete with partial_failures
    // threaded through as a warnings array (one entry per failed endpoint).
    await completeWith({
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

    // The success dialog must be open and the warning alert must render with
    // both endpoint names and error messages.
    const completions = wrapper.emitted('import-completed')
    expect(completions).toHaveLength(1)
    expect(completions[0][0].warnings).toHaveLength(2)

    const html = wrapper.html()
    expect(html).toContain('Some data sources could not be fetched')
    expect(html).toContain('spot_fills')
    expect(html).toContain('OKX HTTP 500: simulated 500')
    expect(html).toContain('option_settlements')
    expect(html).toContain('bills archive cap')
  })

  it('does not render the warnings alert when warnings is empty or absent', async () => {
    await startSyntheticRun()

    // No warnings field at all (e.g. a clean import or a Tinkoff import).
    await completeWith({
      totalTransactions: 3,
      importedTransactions: 3,
      skippedTransactions: 0,
      duplicateTransactions: 0,
      importErrors: 0
    })

    const completions = wrapper.emitted('import-completed')
    expect(completions).toHaveLength(1)
    expect(completions[0][0]).not.toHaveProperty('warnings')
    expect(wrapper.vm.importStats.warnings).toEqual([])
    expect(wrapper.html()).not.toContain('Some data sources could not be fetched')
  })
})
