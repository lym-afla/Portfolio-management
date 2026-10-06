// D7 task 0 — characterization of the incumbent broker connection surface,
// driven through the rendered controls and the same handlers the template
// binds (BrokerTokenManager.vue stays the compatibility entrypoint after
// extraction, so these pins must keep passing unchanged). Wire shapes mirror
// backend/users/serializers.py including the IB rows-are-{id} reality — see
// docs/design/frontend-brokers-security.md §1. Synthetic credential literals
// live only in these test inputs.
import { mount } from '@vue/test-utils'
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'
import BrokerTokenManager from '@/components/BrokerTokenManager.vue'
import {
  deleteToken,
  getAvailableBrokers,
  getBrokerTokens,
  revokeToken,
  saveBybitToken,
  saveIBToken,
  saveOKXToken,
  saveTinkoffToken,
  testIBConnection,
  testTinkoffConnection,
} from '@/services/api'
import { generateVuetifyStubs } from '../../test-utils'
import { deferred } from '../../helpers/deferred'

vi.mock('@/services/api', () => ({
  deleteToken: vi.fn(),
  getAvailableBrokers: vi.fn(),
  getBrokerTokens: vi.fn(),
  revokeToken: vi.fn(),
  saveBybitToken: vi.fn(),
  saveIBToken: vi.fn(),
  saveOKXToken: vi.fn(),
  saveTinkoffToken: vi.fn(),
  testIBConnection: vi.fn(),
  testTinkoffConnection: vi.fn(),
}))

vi.mock('@/utils/logger', () => ({
  default: { log: vi.fn(), error: vi.fn() },
}))

const originalConsole = { warn: console.warn, error: console.error, log: console.log }

beforeAll(() => {
  console.warn = vi.fn()
  console.error = vi.fn()
  console.log = vi.fn()
})

afterAll(() => {
  console.warn = originalConsole.warn
  console.error = originalConsole.error
  console.log = originalConsole.log
})

// The row action buttons sit inside v-tooltip activator slots, so the
// generic default-slot-only stub would hide them; this stub renders both
// slots and keeps attribute fallthrough (icon/loading) on the button. The
// v-dialog stub renders its slot unconditionally, so dialog assertions use
// the component's dialog-model state, not bare text presence.
const renderedStubs = () => ({
  ...generateVuetifyStubs(),
  'v-list-item': { template: '<div class="v-list-item"><slot name="prepend" /><slot /><slot name="append" /></div>' },
  'v-tooltip': { template: '<div class="v-tooltip"><slot name="activator" /><slot /></div>' },
  'v-btn': { template: '<button type="button" class="v-btn"><slot /></button>' },
  'v-dialog': { template: '<div class="v-dialog"><slot /></div>' },
})

const wireTokens = () => ({
  tinkoff_tokens: [
    { id: 11, token_type: 'read_only', sandbox_mode: false, is_active: true, created_at: '2026-09-01T10:30:00Z' },
    { id: 12, token_type: 'full_access', sandbox_mode: false, is_active: false, created_at: '2026-08-01T09:00:00Z' },
  ],
  ib_tokens: [{ id: 1 }],
  bybit_tokens: [
    { id: 21, api_key: 'bybit-synthetic-key', testnet: true, is_active: true, created_at: '2026-07-15T08:00:00Z' },
  ],
  okx_tokens: [
    { id: 31, api_key: 'okx-synthetic-key', simulated_trading: true, is_active: false, created_at: '2026-06-02T12:00:00Z' },
  ],
})

const flush = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

let wrapper

const mountManager = async () => {
  const div = document.createElement('div')
  div.id = 'app'
  document.body.appendChild(div)
  wrapper = mount(BrokerTokenManager, {
    attachTo: '#app',
    global: {
      stubs: {
        ...renderedStubs(),
        'v-form': {
          template: '<form class="v-form"><slot /></form>',
          methods: { validate: () => true, reset: () => {} },
        },
      },
    },
  })
  await flush()
  // Open the Add Token dialog the way a user does before every save flow.
  const add = wrapper.findAll('button.v-btn').find((b) => b.text().trim() === 'Add Token')
  await add.trigger('click')
  await flush()
  return wrapper
}

const rowButtons = (root, icon) =>
  root.findAll('button.v-btn').filter((button) => button.attributes('icon') === icon)

const dialogWithButton = (label) =>
  wrapper.findAll('.v-dialog').find((dialog) =>
    dialog.findAll('button.v-btn').some((button) => button.text() === label))

const formComponent = () => {
  const form = wrapper.findComponent({ name: 'BrokerConnectionForm' })
  expect(form.exists(), 'BrokerConnectionForm child').toBe(true)
  return form
}

const clickDialogButton = async (label) => {
  const dialog = dialogWithButton(label)
  expect(dialog, `dialog with button ${label}`).toBeTruthy()
  await dialog.findAll('button.v-btn').find((button) => button.text() === label).trigger('click')
  await flush()
}

beforeEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
  getAvailableBrokers.mockResolvedValue([
    { id: 1, name: 'Tinkoff Broker' },
    { id: 2, name: 'Interactive Brokers Main' },
    { id: 4, name: 'Bybit Unified' },
    { id: 5, name: 'OKX Trading' },
  ])
  getBrokerTokens.mockResolvedValue(wireTokens())
  revokeToken.mockResolvedValue({ message: 'Token revoked successfully' })
  deleteToken.mockResolvedValue(undefined)
})

afterEach(() => {
  document.body.innerHTML = ''
  wrapper?.unmount()
})

describe('broker connection characterization (incumbent surface)', () => {
  it('renders populated provider rows with the incumbent status text, titles and chips', async () => {
    await mountManager()
    const text = wrapper.text()
    expect(text).toContain('Tinkoff tokens (1)')
    expect(text).toContain('Read Only Token')
    // Time-of-day renders in the machine timezone; pin the en-GB shape.
    expect(text).toMatch(/Created on 01 Sept 2026, \d{2}:\d{2}/)
    expect(text).toContain('Interactive Brokers tokens (0)')
    expect(text).toContain('Bybit tokens (1)')
    expect(text).toContain('API key: bybit-synthetic-key')
    expect(text).toContain('Testnet')
    expect(text).toContain('OKX tokens (0)')
    // Inactive rows stay hidden until the toggle is set (v-model state).
    expect(text).not.toContain('Full Access Token')
    expect(text).not.toContain('Inactive')
    wrapper.vm.showInactiveTokens = true
    await flush()
    const shown = wrapper.text()
    expect(shown).toContain('Full Access Token')
    expect(shown).toContain('Inactive')
    expect(shown).toContain('OKX tokens (1)')
    expect(shown).toContain('Simulated Trading')
  })

  it('preserves the IB wire reality: id-only rows hidden by default, test/revoke/delete when revealed', async () => {
    await mountManager()
    expect(wrapper.text()).toContain('Interactive Brokers tokens (0)')
    wrapper.vm.showInactiveTokens = true
    await flush()
    expect(wrapper.text()).toContain('Interactive Brokers tokens (1)')
    expect(wrapper.text()).toContain('Account:')
    // The wire carries no is_active for IB, so the incumbent renders the
    // error status and the permanent delete affordance for the revealed row.
    const panel = wrapper.findAll('.v-expansion-panel')[1]
    expect(rowButtons(panel, 'mdi-lock-check')).toHaveLength(1)
    expect(rowButtons(panel, 'mdi-key-remove')).toHaveLength(1)
    expect(rowButtons(panel, 'mdi-delete')).toHaveLength(1)
  })

  it('offers no test button for crypto providers and reports unsupported testing', async () => {
    await mountManager()
    wrapper.vm.showInactiveTokens = true
    await flush()
    const bybitPanel = wrapper.findAll('.v-expansion-panel')[2]
    const okxPanel = wrapper.findAll('.v-expansion-panel')[3]
    expect(rowButtons(bybitPanel, 'mdi-lock-check')).toHaveLength(0)
    expect(rowButtons(okxPanel, 'mdi-lock-check')).toHaveLength(0)
    await wrapper.vm.testConnection('bybit', 21)
    expect(wrapper.emitted('info')).toEqual([['Connection testing is not implemented for this broker yet']])
    expect(testTinkoffConnection).not.toHaveBeenCalled()
    expect(testIBConnection).not.toHaveBeenCalled()
  })

  it('keys test busy state per provider and token: equal numeric ids never share state', async () => {
    const tinkoffPending = deferred()
    const ibPending = deferred()
    testTinkoffConnection.mockReturnValueOnce(tinkoffPending.promise)
    testIBConnection.mockReturnValueOnce(ibPending.promise)
    getBrokerTokens.mockResolvedValue({
      ...wireTokens(),
      tinkoff_tokens: [{ id: 1, token_type: 'read_only', is_active: true, created_at: '2026-09-01T10:30:00Z' }],
    })
    await mountManager()
    wrapper.vm.showInactiveTokens = true
    await flush()
    const tinkoffTest = () => rowButtons(wrapper, 'mdi-lock-check')[0]
    const ibTest = () => rowButtons(wrapper, 'mdi-lock-check').at(-1)

    await tinkoffTest().trigger('click')
    await flush()
    expect(testTinkoffConnection).toHaveBeenCalledWith(1)
    expect(tinkoffTest().attributes('loading')).toBe('true')
    // The extracted list binds row.busy, so idle rows render an explicit false.
    expect(ibTest().attributes('loading')).toBe('false')

    await ibTest().trigger('click')
    await flush()
    expect(testIBConnection).toHaveBeenCalledWith(1)
    expect(ibTest().attributes('loading')).toBe('true')
    expect(tinkoffTest().attributes('loading')).toBe('true')

    // Only the owning request releases its own busy flag.
    ibPending.resolve({})
    await flush()
    // A released flag is explicitly false; a never-started one is absent.
    expect(ibTest().attributes('loading')).toBe('false')
    expect(tinkoffTest().attributes('loading')).toBe('true')

    tinkoffPending.resolve({ data: { token: { id: 1, is_active: false } } })
    await flush()
    expect(tinkoffTest().attributes('loading')).toBe('false')
    expect(wrapper.emitted('success').flat()).toContain('Connection test successful')
    // The incumbent refreshes the list after a test regardless of the (dead)
    // response-body branch — that refresh is what updates the row status.
    expect(getBrokerTokens).toHaveBeenCalledTimes(2)
  })

  it('revokes through the exact (provider, tokenId) identity and refreshes', async () => {
    await mountManager()
    const revokeButton = rowButtons(wrapper, 'mdi-key-remove')[0]
    await revokeButton.trigger('click')
    await flush()
    expect(revokeToken).toHaveBeenCalledTimes(1)
    expect(revokeToken).toHaveBeenCalledWith('tinkoff', 11)
    expect(getBrokerTokens).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('success')).toEqual([['Token revoked successfully']])
  })

  it('deletes exactly the snapshotted inactive token after naming it in the confirmation', async () => {
    await mountManager()
    wrapper.vm.showInactiveTokens = true
    await flush()
    const inactiveTinkoffRow = wrapper.findAll('.v-expansion-panel')[0].findAll('.v-list-item')[1]
    await rowButtons(inactiveTinkoffRow, 'mdi-delete')[0].trigger('click')
    await flush()
    expect(wrapper.vm.showDeleteDialog).toBe(true)
    // The confirmation names the broker/connection and never implies
    // portfolio transactions are affected (D7 design requirement).
    expect(wrapper.text()).toContain('Delete connection')
    expect(wrapper.text()).toContain('Tinkoff · Full Access Token (#12)')
    expect(wrapper.text()).toContain('portfolio transactions are not affected')
    expect(wrapper.text()).toContain('This action cannot be undone.')
    // Nothing else changed the snapshot between open and confirm.
    await clickDialogButton('Delete')
    expect(deleteToken).toHaveBeenCalledTimes(1)
    expect(deleteToken).toHaveBeenCalledWith('tinkoff', 12)
    expect(getBrokerTokens).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('success')).toEqual([['Token deleted successfully']])
    expect(wrapper.vm.showDeleteDialog).toBe(false)
  })

  it('surfaces the server-side active-token delete rejection', async () => {
    deleteToken.mockRejectedValueOnce({
      response: { status: 400, data: { error: 'Cannot delete active token. Deactivate it first.' } },
    })
    await mountManager()
    await wrapper.vm.confirmDeleteToken('tinkoff', 11)
    await wrapper.vm.deleteToken()
    await flush()
    expect(wrapper.emitted('error')).toEqual([['Cannot delete active token. Deactivate it first.']])
  })

  it('saves each provider with the exact incumbent payload', async () => {
    saveTinkoffToken.mockResolvedValue({ message: 'Token saved successfully', id: 77 })
    testTinkoffConnection.mockResolvedValue({ valid: true, token: { id: 77, is_active: true } })
    await mountManager()
    let form = formComponent()
    await form.vm.handleBrokerSelection(1)
    form.vm.draft.token = 'synthetic-tk'
    await form.vm.saveToken()
    await flush()
    expect(saveTinkoffToken).toHaveBeenCalledWith({ broker: 1, token: 'synthetic-tk', token_type: 'read_only', sandbox_mode: false })
    // Post-save testing: the fresh token is tested once; the incumbent
    // refreshes once inside the test and once after the save branch (3 total
    // with the mount fetch) — characterized and preserved by the extraction.
    expect(testTinkoffConnection).toHaveBeenCalledWith(77)
    expect(getBrokerTokens).toHaveBeenCalledTimes(3)
    // The save message and the post-save test each emit success.
    expect(wrapper.emitted('success').slice(0, 2)).toEqual([
      ['Token saved successfully'], ['Connection test successful'],
    ])

    saveIBToken.mockResolvedValue({ message: 'Token saved successfully', id: 1 })
    form = formComponent()
    await form.vm.handleBrokerSelection(2)
    form.vm.draft.token = 'synthetic-ib'
    form.vm.draft.accountId = 'U123'
    await form.vm.saveToken()
    await flush()
    expect(saveIBToken).toHaveBeenCalledWith({ broker: 2, token: 'synthetic-ib', account_id: 'U123', paper_trading: false })
    expect(wrapper.emitted('success').at(-1)).toEqual(['Token saved successfully'])

    saveBybitToken.mockResolvedValue({})
    form = formComponent()
    await form.vm.handleBrokerSelection(4)
    form.vm.draft.apiKey = 'k-synth'
    form.vm.draft.apiSecret = 's-synth'
    form.vm.draft.testnet = true
    await form.vm.saveToken()
    await flush()
    expect(saveBybitToken).toHaveBeenCalledWith({ broker: 4, api_key: 'k-synth', api_secret: 's-synth', testnet: true })
    expect(wrapper.emitted('success').at(-1)).toEqual(['Bybit token saved successfully'])

    saveOKXToken.mockResolvedValue({})
    form = formComponent()
    await form.vm.handleBrokerSelection(5)
    form.vm.draft.apiKey = 'k-synth'
    form.vm.draft.apiSecret = 's-synth'
    form.vm.draft.passphrase = 'p-synth'
    form.vm.draft.simulatedTrading = true
    await form.vm.saveToken()
    expect(saveOKXToken).toHaveBeenCalledWith({
      broker: 5, api_key: 'k-synth', api_secret: 's-synth', passphrase: 'p-synth', simulated_trading: true,
    })
    expect(wrapper.emitted('success').at(-1)).toEqual(['OKX token saved successfully'])
  })

  it('routes the already-active rejection into the Token Already Exists dialog and erases the draft', async () => {
    saveTinkoffToken.mockRejectedValueOnce({
      response: { status: 400, data: { message: 'This exact token is already active' } },
    })
    await mountManager()
    const form = formComponent()
    await form.vm.handleBrokerSelection(1)
    form.vm.draft.token = 'synthetic-dup'
    await form.vm.saveToken()
    await flush()
    expect(wrapper.text()).toContain('Token Already Exists')
    expect(wrapper.text()).toContain('This exact token is already active')
    // The dialog closed as accepted feedback — the credential draft's open
    // lifetime ended with it, so the secret must be gone (review focus 3).
    expect(form.props('open')).toBe(false)
    expect(form.vm.draft.token).toBe('')
  })

  it('routes the reactivation success into the Token Reactivated dialog, refreshes and erases the draft', async () => {
    saveTinkoffToken.mockResolvedValueOnce({ message: 'Existing token has been reactivated', id: 12 })
    await mountManager()
    const form = formComponent()
    await form.vm.handleBrokerSelection(1)
    form.vm.draft.token = 'synthetic-react'
    await form.vm.saveToken()
    await flush()
    expect(wrapper.text()).toContain('Token Reactivated')
    expect(wrapper.text()).toContain('Existing token has been reactivated')
    expect(getBrokerTokens).toHaveBeenCalledTimes(2)
    // The incumbent leaked the token value on this path; the extracted form
    // must erase the draft when the dialog closes (review focus 3).
    expect(form.props('open')).toBe(false)
    expect(form.vm.draft.token).toBe('')
  })
})
