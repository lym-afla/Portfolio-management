// D7 task 2 — behavioral contract of the extracted broker list/form
// components. RED first: the modules do not exist yet. The drafts below use
// synthetic credential literals that never leave these test inputs; the
// components under test must erase them on success/cancel/unmount and keep
// them (without echoing) on rejected saves.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import BrokerConnectionForm from '@/features/brokers/BrokerConnectionForm.vue'
import BrokerConnectionList from '@/features/brokers/BrokerConnectionList.vue'
import type { BrokerCredentialDraft } from '@/features/brokers/types'
import { generateVuetifyStubs } from '../../test-utils'

const flush = async () => {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await new Promise((resolve) => setTimeout(resolve, 0))
}

const renderedStubs = () => ({
  ...generateVuetifyStubs(),
  'v-list-item': { template: '<div class="v-list-item"><slot name="prepend" /><slot /><slot name="append" /></div>' },
  'v-tooltip': { template: '<div class="v-tooltip"><slot name="activator" /><slot /></div>' },
  'v-btn': { template: '<button type="button" class="v-btn"><slot /></button>' },
  'v-dialog': { template: '<div class="v-dialog"><slot /></div>' },
})

const brokerOptions = () => [
  { id: 1, name: 'Tinkoff Broker', country: 'US' },
  { id: 2, name: 'Interactive Brokers Main', country: 'US' },
  { id: 3, name: 'Custom Broker', country: 'US' },
  { id: 4, name: 'Bybit Unified', country: 'US' },
  { id: 5, name: 'OKX Trading', country: 'US' },
]

let wrapper: VueWrapper | null = null

interface FormProps {
  open?: boolean
  brokerOptions?: ReturnType<typeof brokerOptions>
  busy?: boolean
}

const mountForm = (props: FormProps = {}) => {
  const div = document.createElement('div')
  div.id = 'app'
  document.body.appendChild(div)
  wrapper = mount(BrokerConnectionForm, {
    attachTo: '#app',
    props: {
      open: true,
      brokerOptions: brokerOptions(),
      busy: false,
      ...props,
    },
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
  return wrapper
}

afterEach(() => {
  document.body.innerHTML = ''
  wrapper?.unmount()
})

describe('BrokerConnectionForm — provider drafts and submission intents', () => {
  it('maps broker names to providers and opens the type dialog for unknown names', async () => {
    const form = mountForm()
    await (form.vm as any).handleBrokerSelection(1)
    expect((form.vm as any).selectedProvider).toBe('tinkoff')
    await (form.vm as any).handleBrokerSelection(2)
    expect((form.vm as any).selectedProvider).toBe('ib')
    await (form.vm as any).handleBrokerSelection(4)
    expect((form.vm as any).selectedProvider).toBe('bybit')
    await (form.vm as any).handleBrokerSelection(5)
    expect((form.vm as any).selectedProvider).toBe('okx')
    await (form.vm as any).handleBrokerSelection(3)
    expect((form.vm as any).selectedProvider).toBeNull()
    expect(form.text()).toContain('Select Broker Type')
    expect(form.text()).toContain('Custom Broker')
    ;(form.vm as any).selectedBrokerType = 'okx'
    await (form.vm as any).confirmBrokerType()
    expect((form.vm as any).selectedProvider).toBe('okx')
  })

  it('emits the exact typed tinkoff draft on submit', async () => {
    const form = mountForm()
    const vm = form.vm as any
    await vm.handleBrokerSelection(1)
    vm.draft.token = 'synthetic-tk'
    await vm.saveToken()
    expect(form.emitted('submit')).toHaveLength(1)
    const draft = form.emitted('submit')![0][0] as BrokerCredentialDraft
    expect(draft).toEqual({
      provider: 'tinkoff', brokerId: 1, token: 'synthetic-tk',
      tokenType: 'read_only', sandboxMode: false,
    })
  })

  it('emits the exact typed ib draft including account fields', async () => {
    const form = mountForm()
    const vm = form.vm as any
    await vm.handleBrokerSelection(2)
    vm.draft.token = 'synthetic-ib'
    vm.draft.accountId = 'U123'
    vm.draft.paperTrading = true
    await vm.saveToken()
    expect(form.emitted('submit')![0][0]).toEqual({
      provider: 'ib', brokerId: 2, token: 'synthetic-ib',
      accountId: 'U123', paperTrading: true,
    })
  })

  it('emits the exact typed bybit draft including testnet', async () => {
    const form = mountForm()
    const vm = form.vm as any
    await vm.handleBrokerSelection(4)
    vm.draft.apiKey = 'k-synth'
    vm.draft.apiSecret = 's-synth'
    vm.draft.testnet = true
    await vm.saveToken()
    expect(form.emitted('submit')![0][0]).toEqual({
      provider: 'bybit', brokerId: 4, apiKey: 'k-synth',
      apiSecret: 's-synth', testnet: true,
    })
  })

  it('emits the exact typed okx draft including passphrase and simulated trading', async () => {
    const form = mountForm()
    const vm = form.vm as any
    await vm.handleBrokerSelection(5)
    vm.draft.apiKey = 'k-synth'
    vm.draft.apiSecret = 's-synth'
    vm.draft.passphrase = 'p-synth'
    vm.draft.simulatedTrading = true
    await vm.saveToken()
    expect(form.emitted('submit')![0][0]).toEqual({
      provider: 'okx', brokerId: 5, apiKey: 'k-synth', apiSecret: 's-synth',
      passphrase: 'p-synth', simulatedTrading: true,
    })
  })

  it('keeps provider fields mutually exclusive when the broker changes', async () => {
    const form = mountForm()
    const vm = form.vm as any
    await vm.handleBrokerSelection(4)
    vm.draft.apiKey = 'k-synth'
    await vm.handleBrokerSelection(1)
    expect(vm.draft.apiKey).toBe('')
    expect(vm.draft.apiSecret).toBe('')
    expect(vm.draft.passphrase).toBe('')
    expect(vm.draft.token).toBe('')
    expect(vm.draft.tokenType).toBe('read_only')
    expect(vm.draft.sandboxMode).toBe(false)
  })

  it('refuses submission without a validated form or a selected broker', async () => {
    const validation = { valid: false }
    const div = document.createElement('div')
    div.id = 'app'
    document.body.appendChild(div)
    const form = mount(BrokerConnectionForm, {
      attachTo: '#app',
      props: { open: true, brokerOptions: brokerOptions(), busy: false },
      global: {
        stubs: {
          ...renderedStubs(),
          'v-form': {
            template: '<form class="v-form"><slot /></form>',
            methods: { validate: () => validation.valid, reset: () => {} },
          },
        },
      },
    })
    const vm = form.vm as any
    await vm.handleBrokerSelection(1)
    vm.draft.token = 'synthetic-tk'
    await vm.saveToken()
    // Invalid form: the submit intent never fires.
    expect(form.emitted('submit')).toBeUndefined()
    validation.valid = true
    await vm.saveToken()
    expect(form.emitted('submit')).toHaveLength(1)
    form.unmount()
    document.body.innerHTML = ''

    // An unresolved provider (custom broker without a confirmed type) cannot
    // produce a draft: the typed union forbids it and the user gets the
    // incumbent error message.
    const secondDiv = document.createElement('div')
    secondDiv.id = 'app'
    document.body.appendChild(secondDiv)
    const second = mount(BrokerConnectionForm, {
      attachTo: '#app',
      props: { open: true, brokerOptions: brokerOptions(), busy: false },
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
    const secondVm = second.vm as any
    await secondVm.saveToken()
    expect(second.emitted('submit')).toBeUndefined()
    expect(second.emitted('error')).toEqual([['Please select a broker']])
    second.unmount()
    document.body.innerHTML = ''
  })

  it('ignores submits while a save is in flight (once-only per envelope)', async () => {
    const form = mountForm({ busy: true })
    const vm = form.vm as any
    await vm.handleBrokerSelection(1)
    vm.draft.token = 'synthetic-tk'
    await vm.saveToken()
    expect(form.emitted('submit')).toBeUndefined()
    form.unmount()
    document.body.innerHTML = ''
  })

  it('awaits async Vuetify validation and rechecks form ownership before submitting', async () => {
    // Vuetify 3's v-form validate() resolves { valid: boolean } — a sync
    // truthiness check treats the PROMISE as truthy and submits anyway.
    const validation = {
      result: { valid: false },
    }
    const div = document.createElement('div')
    div.id = 'app'
    document.body.appendChild(div)
    const form = mount(BrokerConnectionForm, {
      attachTo: '#app',
      props: { open: true, brokerOptions: brokerOptions(), busy: false },
      global: {
        stubs: {
          ...renderedStubs(),
          'v-form': {
            template: '<form class="v-form"><slot /></form>',
            methods: {
              validate: () => new Promise((resolve) => {
                setTimeout(() => resolve(validation.result), 10)
              }),
              reset: () => {},
            },
          },
        },
      },
    })
    const vm = form.vm as any
    await vm.handleBrokerSelection(1)
    vm.draft.token = ''
    await vm.saveToken()
    await new Promise((resolve) => setTimeout(resolve, 30))
    // { valid: false } must refuse the submit even though the promise
    // object itself is truthy.
    expect(form.emitted('submit')).toBeUndefined()

    validation.result = { valid: true }
    await vm.saveToken()
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(form.emitted('submit')).toHaveLength(1)
    form.unmount()
    document.body.innerHTML = ''

    // The await opens an ownership window: a dialog closed while
    // validation was in flight must not submit.
    const secondDiv = document.createElement('div')
    secondDiv.id = 'app'
    document.body.appendChild(secondDiv)
    const release = { go: false }
    const second = mount(BrokerConnectionForm, {
      attachTo: '#app',
      props: { open: true, brokerOptions: brokerOptions(), busy: false },
      global: {
        stubs: {
          ...renderedStubs(),
          'v-form': {
            template: '<form class="v-form"><slot /></form>',
            methods: {
              validate: () => new Promise((resolve) => {
                const check = () => {
                  if (release.go) resolve({ valid: true })
                  else setTimeout(check, 5)
                }
                check()
              }),
              reset: () => {},
            },
          },
        },
      },
    })
    const secondVm = second.vm as any
    await secondVm.handleBrokerSelection(1)
    secondVm.draft.token = 'synthetic-closed-mid-validation'
    const submitPromise = secondVm.saveToken()
    await second.setProps({ open: false })
    release.go = true
    await submitPromise
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(second.emitted('submit')).toBeUndefined()
    second.unmount()
    document.body.innerHTML = ''
  })

  it('invalidates in-flight validation on close, reopen and provider change', async () => {
    // Validation is async: a save started on one form generation must never
    // submit a DIFFERENT generation's draft when its validation lands late.
    const release = { go: false }
    const div = document.createElement('div')
    div.id = 'app'
    document.body.appendChild(div)
    const form = mount(BrokerConnectionForm, {
      attachTo: '#app',
      props: { open: true, brokerOptions: brokerOptions(), busy: false },
      global: {
        stubs: {
          ...renderedStubs(),
          'v-form': {
            template: '<form class="v-form"><slot /></form>',
            methods: {
              validate: () => new Promise((resolve) => {
                const check = () => {
                  if (release.go) resolve({ valid: true })
                  else setTimeout(check, 5)
                }
                check()
              }),
              reset: () => {},
            },
          },
        },
      },
    })
    const vm = form.vm as any
    await vm.handleBrokerSelection(4)
    vm.draft.apiKey = 'stale-key'
    vm.draft.apiSecret = 'stale-secret'
    const staleSubmit = vm.saveToken()
    // The old generation ends: close, reopen with ANOTHER provider and draft.
    await form.setProps({ open: false })
    await form.setProps({ open: true })
    await vm.handleBrokerSelection(1)
    vm.draft.token = 'synthetic-new-generation-draft'
    release.go = true
    await staleSubmit
    await new Promise((resolve) => setTimeout(resolve, 30))
    // The late validation succeeded, but it belongs to the stale generation:
    // the NEW draft must NOT be submitted without a fresh Save action.
    expect(form.emitted('submit')).toBeUndefined()
    form.unmount()
    document.body.innerHTML = ''

    // A provider change alone also invalidates in-flight validation.
    const secondDiv = document.createElement('div')
    secondDiv.id = 'app'
    document.body.appendChild(secondDiv)
    const release2 = { go: false }
    const second = mount(BrokerConnectionForm, {
      attachTo: '#app',
      props: { open: true, brokerOptions: brokerOptions(), busy: false },
      global: {
        stubs: {
          ...renderedStubs(),
          'v-form': {
            template: '<form class="v-form"><slot /></form>',
            methods: {
              validate: () => new Promise((resolve) => {
                const check = () => {
                  if (release2.go) resolve({ valid: true })
                  else setTimeout(check, 5)
                }
                check()
              }),
              reset: () => {},
            },
          },
        },
      },
    })
    const secondVm = second.vm as any
    await secondVm.handleBrokerSelection(4)
    secondVm.draft.apiKey = 'k'
    secondVm.draft.apiSecret = 's'
    const secondSubmit = secondVm.saveToken()
    await secondVm.handleBrokerSelection(1)
    secondVm.draft.token = 'synthetic-provider-changed'
    release2.go = true
    await secondSubmit
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(second.emitted('submit')).toBeUndefined()
    // A fresh, current-generation save still works.
    release2.go = false
    ;(second.vm as any).formRef.validate = () => new Promise((resolve) => {
      resolve({ valid: true })
    })
    await secondVm.saveToken()
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(second.emitted('submit')).toHaveLength(1)
    second.unmount()
    document.body.innerHTML = ''
  })

  it('erases the credential draft when the dialog closes and on unmount', async () => {
    const form = mountForm()
    const vm = form.vm as any
    await vm.handleBrokerSelection(5)
    vm.draft.apiKey = 'k-synth'
    vm.draft.apiSecret = 's-synth'
    vm.draft.passphrase = 'p-synth'
    await form.setProps({ open: false })
    await flush()
    expect(vm.draft.apiKey).toBe('')
    expect(vm.draft.apiSecret).toBe('')
    expect(vm.draft.passphrase).toBe('')
    expect(vm.selectedProvider).toBeNull()
    // Reopen: clean form.
    await form.setProps({ open: true })
    expect(vm.draft.apiKey).toBe('')

    const second = mountForm()
    const secondVm = second.vm as any
    await secondVm.handleBrokerSelection(5)
    secondVm.draft.passphrase = 'p-synth'
    second.unmount()
    await flush()
    // After unmount nothing of the draft remains reachable through the vm.
    expect(secondVm.draft.passphrase).toBe('')
  })
})

describe('BrokerConnectionList — display-only rendering and intents', () => {
  const rows = () => [
    {
      provider: 'tinkoff' as const, tokenId: 11, label: 'Read Only Token',
      statusIcon: 'mdi-check-circle' as const, statusLabel: 'Valid token',
      statusTone: 'success' as const, createdAtLabel: '01 Sept 2026, 13:30',
      chips: [], canTest: true, canRevoke: true, canDelete: false, busy: true,
    },
    {
      provider: 'bybit' as const, tokenId: 21, label: 'API key: bybit-synthetic-key',
      statusIcon: 'mdi-close-circle' as const, statusLabel: 'Inactive token',
      statusTone: 'error' as const, createdAtLabel: 'N/A',
      chips: [{ text: 'Inactive', tone: 'error' as const }],
      canTest: false, canRevoke: true, canDelete: true, busy: false,
    },
  ]

  const mountList = () =>
    mount(BrokerConnectionList, {
      props: {
        connections: rows(),
        loading: false,
        showInactive: true,
        rowErrors: {},
        'onUpdate:showInactive': (value: boolean) =>
          wrapper?.setProps({ showInactive: value }),
        onTest: vi.fn(),
        onRevoke: vi.fn(),
        'onDeleteRequest': vi.fn(),
      },
      global: { stubs: renderedStubs() },
    })

  it('renders text and icon status, labels, chips and per-row busy state', () => {
    const list = mountList()
    const text = list.text()
    expect(text).toContain('Tinkoff tokens (1)')
    expect(text).toContain('Interactive Brokers tokens (0)')
    expect(text).toContain('Read Only Token')
    expect(text).toContain('Valid token')
    expect(text).toContain('API key: bybit-synthetic-key')
    expect(text).toContain('Inactive')
    expect(text).toContain('No tokens found')
    const tinkoffPanel = list.findAll('.v-expansion-panel')[0]
    const testButton = tinkoffPanel.findAll('button.v-btn').find((b) => b.attributes('icon') === 'mdi-lock-check')
    expect(testButton?.attributes('loading')).toBe('true')
    expect(testButton?.attributes('aria-label')).toBe('Check token validity')
    const bybitPanel = list.findAll('.v-expansion-panel')[2]
    expect(bybitPanel.findAll('button.v-btn').some((b) => b.attributes('icon') === 'mdi-lock-check')).toBe(false)
    const revoke = bybitPanel.findAll('button.v-btn').find((b) => b.attributes('icon') === 'mdi-key-remove')
    expect(revoke?.attributes('aria-label')).toBe('Deactivate token')
    const remove = bybitPanel.findAll('button.v-btn').find((b) => b.attributes('icon') === 'mdi-delete')
    expect(remove?.attributes('aria-label')).toBe('Delete token permanently')
    expect(remove).toBeTruthy()
    list.unmount()
  })

  it('emits row intents keyed by provider and token', async () => {
    const onTest = vi.fn()
    const onRevoke = vi.fn()
    const onDeleteRequest = vi.fn()
    const div = document.createElement('div')
    div.id = 'app'
    document.body.appendChild(div)
    const list = mount(BrokerConnectionList, {
      attachTo: '#app',
      props: {
        connections: rows(), loading: false, showInactive: true, rowErrors: {},
        onTest, onRevoke, onDeleteRequest,
      },
      global: { stubs: renderedStubs() },
    })
    const tinkoffPanel = list.findAll('.v-expansion-panel')[0]
    await tinkoffPanel.findAll('button.v-btn').find((b) => b.attributes('icon') === 'mdi-lock-check')!.trigger('click')
    expect(onTest).toHaveBeenCalledWith({ provider: 'tinkoff', tokenId: 11 })
    const bybitPanel = list.findAll('.v-expansion-panel')[2]
    await bybitPanel.findAll('button.v-btn').find((b) => b.attributes('icon') === 'mdi-key-remove')!.trigger('click')
    expect(onRevoke).toHaveBeenCalledWith({ provider: 'bybit', tokenId: 21 })
    await bybitPanel.findAll('button.v-btn').find((b) => b.attributes('icon') === 'mdi-delete')!.trigger('click')
    expect(onDeleteRequest).toHaveBeenCalledWith({ provider: 'bybit', tokenId: 21 })
    list.unmount()
  })

  it('shows the row-scoped error inside the failing row only', () => {
    const div = document.createElement('div')
    div.id = 'app'
    document.body.appendChild(div)
    const list = mount(BrokerConnectionList, {
      attachTo: '#app',
      props: {
        connections: rows(), loading: false, showInactive: true,
        rowErrors: { 'tinkoff:11': 'Token is invalid or expired.' },
        onTest: vi.fn(), onRevoke: vi.fn(), onDeleteRequest: vi.fn(),
      },
      global: { stubs: renderedStubs() },
    })
    const tinkoffPanel = list.findAll('.v-expansion-panel')[0]
    expect(tinkoffPanel.text()).toContain('Token is invalid or expired.')
    const bybitPanel = list.findAll('.v-expansion-panel')[2]
    expect(bybitPanel.text()).not.toContain('Token is invalid or expired.')
    list.unmount()
  })
})
