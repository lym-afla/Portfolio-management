// D5 Task 3 — Prices/FX route contracts and operational-dialog form shell:
// named actions, focus entry/return, section labels, readable errors and
// rejected-form preservation. Validation rules, payloads and completion
// events are asserted unchanged; only presentation moves.
import { beforeEach, beforeAll, afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { configureContextFixture } from '../context-fixture'
import AccountFormDialog from '@/components/dialogs/AccountFormDialog.vue'
import BrokerFormDialog from '@/components/dialogs/BrokerFormDialog.vue'
import SecurityFormDialog from '@/components/dialogs/SecurityFormDialog.vue'
import PriceFormDialog from '@/components/dialogs/PriceFormDialog.vue'
import FXDialog from '@/components/dialogs/FXDialog.vue'
import PriceImportDialog from '@/components/dialogs/PriceImportDialog.vue'
import FXImportDialog from '@/components/dialogs/FXImportDialog.vue'
import AssetTransferDialog from '@/components/dialogs/AssetTransferDialog.vue'
import MergerDialog from '@/components/dialogs/MergerDialog.vue'
import UpdateAccountPerformanceDialog from '@/components/dialogs/UpdateAccountPerformanceDialog.vue'

const api = vi.hoisted(() => ({
  getAccountFormStructure: vi.fn(),
  createAccount: vi.fn(),
  getBrokerFormStructure: vi.fn(),
  createBroker: vi.fn(),
  getPriceImportFormStructure: vi.fn(),
  importPrices: vi.fn(),
  addPrice: vi.fn(),
  getFXFormStructure: vi.fn(),
  addFXRate: vi.fn(),
  updateFXRate: vi.fn(),
  deleteFXRate: vi.fn(),
  getSecurities: vi.fn(),
  createMerger: vi.fn(),
  transferAsset: vi.fn(),
  getTransactionFormStructure: vi.fn(),
  getSecurityPosition: vi.fn(),
  getFXImportStats: vi.fn(),
  importFXRates: vi.fn(),
  cancelFXImport: vi.fn(),
  getAccountPerformanceFormData: vi.fn(),
  getSecurityFormStructure: vi.fn(),
  updateFXImportStats: vi.fn(),
}))
vi.mock('@/services/api', () => api)

const vuetify = createVuetify({ components, directives })

const activeDialog = () =>
  document.querySelector('.v-overlay--active[role="dialog"]') as HTMLElement

const dialogButton = (testid: string) =>
  activeDialog()?.querySelector(`[data-testid="${testid}"]`) as HTMLElement

const dialogText = () => activeDialog()?.textContent ?? ''

const dialogInput = (type: string) =>
  [...(activeDialog()?.querySelectorAll('input') ?? [])].find(
    (el) => el.getAttribute('type') === type,
  ) as HTMLInputElement

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

afterEach(() => {
  document.body.innerHTML = ''
})

async function mountDialog(component: Promise<{ default: any }>, props: Record<string, unknown> = {}): Promise<VueWrapper> {
  const { default: resolved } = await component
  const wrapper = mount(resolved, {
    attachTo: document.body,
    props: { modelValue: true, ...props },
    global: { plugins: [vuetify, createPinia()], provide: { showError: vi.fn(), clearErrors: vi.fn() } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  configureContextFixture('2026-09-08')
  api.getSecurityFormStructure.mockResolvedValue({
    fields: [{ name: 'name', label: 'Name', type: 'textinput', required: true }],
  })
  api.getAccountPerformanceFormData.mockResolvedValue({
    account_choices: [['General', [['All accounts', { type: 'all', id: null }]]]],
    currency_choices: { USD: { value: 'USD', text: 'USD' } },
    is_restricted_choices: { restricted: { value: 'restricted', text: 'Restricted' }, unrestricted: { value: 'unrestricted', text: 'Unrestricted' } },
  })
  api.getAccountFormStructure.mockResolvedValue({
    fields: [
      { name: 'name', label: 'Account Name', type: 'textinput', required: true },
      { name: 'broker', label: 'Broker', type: 'select', choices: [{ text: 'Fixture Broker', value: 1 }] },
      { name: 'restricted', label: 'Restricted', type: 'checkbox' },
    ],
  })
  api.getBrokerFormStructure.mockResolvedValue({ fields: [{ name: 'name', label: 'Broker Name', type: 'textinput' }] })
  api.getPriceImportFormStructure.mockResolvedValue({ securities: [], accounts: [], frequency_choices: [] })
  api.getFXFormStructure.mockResolvedValue({
    fields: [
      { name: 'date', label: 'Date', type: 'datepicker' },
      { name: 'from_currency', label: 'From Currency', type: 'text' },
      { name: 'to_currency', label: 'To Currency', type: 'text' },
      { name: 'rate', label: 'Rate', type: 'number' },
    ],
  })
})

describe('AccountFormDialog form shell', () => {
  it('focuses the first field on open and returns focus to the invoker on close', async () => {
    const invoker = document.createElement('button')
    invoker.textContent = 'Add Account'
    document.body.appendChild(invoker)
    invoker.focus()
    const wrapper = await mountDialog(import('@/components/dialogs/AccountFormDialog.vue'))
    await new Promise((r) => setTimeout(r, 80))
    const firstInput = activeDialog()?.querySelector('input')
    expect(firstInput).toBeTruthy()
    expect(document.activeElement).toBe(firstInput)
    await wrapper.setProps({ modelValue: false })
    await new Promise((r) => setTimeout(r, 60))
    expect(document.activeElement).toBe(invoker)
    invoker.remove()
  })

  it('keeps field values visible after a rejected save with per-field errors', async () => {
    const wrapper = await mountDialog(import('@/components/dialogs/AccountFormDialog.vue'))
    api.createAccount.mockRejectedValueOnce({ response: { status: 400, data: { name: ['Name already exists'] } } })
    const nameInput = dialogInput('text')
    nameInput.value = 'Fixture Duplicate'
    nameInput.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    dialogButton('dialog-save').click()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 40))
    expect(api.createAccount).toHaveBeenCalledTimes(1)
    expect(dialogInput('text').value).toBe('Fixture Duplicate')
    expect(dialogText()).toContain('Name already exists')
    expect(wrapper.vm.dialog).toBe(true)
  })

  it('emits the original account-added event with the raw response payload', async () => {
    api.createAccount.mockResolvedValueOnce({ id: 9, name: 'New' })
    const wrapper = await mountDialog(import('@/components/dialogs/AccountFormDialog.vue'))
    dialogButton('dialog-save').click()
    await flushPromises()
    expect(wrapper.emitted('account-added')).toEqual([[{ id: 9, name: 'New' }]])
  })

  it('names its Cancel action and groups the fields under a section', async () => {
    await mountDialog(import('@/components/dialogs/AccountFormDialog.vue'))
    expect(dialogButton('dialog-cancel')).toBeTruthy()
    expect(activeDialog()?.querySelector('section[aria-label="Account details"]')).toBeTruthy()
  })
})

describe('FXDialog form shell', () => {
  it('labels the pair fields, keeps orientation locked in edit and preserves a rejected rate', async () => {
    api.updateFXRate.mockRejectedValueOnce({ rate: ['Rate must be positive'] })
    await mountDialog(import('@/components/dialogs/FXDialog.vue'), {
      editItem: { id: 5, date: '2026-09-01', from_currency: 'USD', to_currency: 'EUR', rate: '1.08' },
    })
    const text = dialogText()
    expect(text).toContain('From Currency')
    expect(text).toContain('To Currency')
    expect(text).toContain('Rate')
    expect(text).toContain('quoted from the first currency to the second')
    // Edit mode: date disabled (pair locked).
    expect(dialogInput('date').disabled).toBe(true)
    const rateInput = dialogInput('number')
    rateInput.value = '1.10'
    rateInput.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    dialogButton('dialog-save').click()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 40))
    expect(api.updateFXRate).toHaveBeenCalledWith(5, expect.objectContaining({ rate: '1.10' }))
    expect(dialogInput('number').value).toBe('1.10')
    expect(dialogText()).toContain('Rate must be positive')
  })
})

describe('PriceFormDialog unit labels', () => {
  it('labels the price field with the trading-currency/bond-percent hint', async () => {
    await mountDialog(import('@/components/dialogs/PriceFormDialog.vue'), {
      securities: [{ id: 1, name: 'Fixture Security' }],
    })
    const text = dialogText()
    expect(text).toContain('Security')
    expect(text).toContain('Date')
    expect(text).toContain('Price')
    expect(text).toMatch(/security's trading currency|percent of nominal/)
    expect(dialogButton('dialog-cancel')).toBeTruthy()
    expect(dialogButton('dialog-save')).toBeTruthy()
  })
})

describe('MergerDialog sections', () => {
  it('groups merger inputs into visible sections with a preview and named actions', async () => {
    api.getSecurities.mockResolvedValue([
      { id: 1, name: 'Old Security' },
      { id: 2, name: 'New Security' },
    ])
    await mountDialog(import('@/components/dialogs/MergerDialog.vue'))
    const text = dialogText()
    expect(text).toContain('Merger details')
    expect(text).toContain('Consideration')
    expect(text).toContain('Old Security')
    expect(text).toContain('Record Merger')
    expect(dialogButton('dialog-cancel')).toBeTruthy()
  })
})

describe('PriceImportDialog', () => {
  it('exposes named Import Prices submit with date-type choices', { timeout: 20000 }, async () => {
    api.getPriceImportFormStructure.mockResolvedValue({
      securities: [{ id: 1, name: 'Fixture Security' }],
      accounts: [],
      frequency_choices: [{ text: 'Daily', value: 'daily' }],
    })
    await mountDialog(import('@/components/dialogs/PriceImportDialog.vue'))
    const text = dialogText()
    const submit = [...(activeDialog()?.querySelectorAll('button') ?? [])].find(
      (el) => el.textContent?.trim() === 'Import Prices',
    )
    expect(submit).toBeTruthy()
    expect(text).toContain('Securities')
    expect(text).toContain('Date Range')
    expect(text).toContain('Single Date')
  })
})

describe('FXImportDialog', () => {
  it('keeps auto/manual import options with Cancel named', async () => {
    api.getFXImportStats.mockResolvedValue({ total_dates: 3, missing_instances: 1, incomplete_instances: 1 })
    await mountDialog(import('@/components/dialogs/FXImportDialog.vue'))
    const text = dialogText()
    expect(text).toContain('Import Type')
    expect(text).toContain('Auto Import')
    expect(dialogButton('dialog-cancel')).toBeTruthy()
    expect(dialogButton('dialog-save')).toBeTruthy()
  })
})

describe('AssetTransferDialog', () => {
  it('shows the transfer title, the unchanged zero-gain explanation and named actions', async () => {
    api.getTransactionFormStructure.mockResolvedValue({
      fields: [{ name: 'security', label: 'Security', type: 'select', choices: [{ text: 'Fixture Security', value: 1 }] }],
    })
    await mountDialog(import('@/components/dialogs/AssetTransferDialog.vue'))
    const text = dialogText()
    expect(text).toContain('Transfer Asset Between Accounts')
    expect(text).toContain('average cost basis (zero realized gain)')
    expect(text).toContain('Transfer Asset')
    expect(dialogButton('dialog-cancel')).toBeTruthy()
  })
})

describe('UpdateAccountPerformanceDialog sections', () => {
  it('groups selection and options with named actions', async () => {
    await mountDialog(import('@/components/dialogs/UpdateAccountPerformanceDialog.vue'))
    const text = dialogText()
    expect(text).toContain('Update Account Performance')
    expect(dialogButton('dialog-cancel')).toBeTruthy()
    expect(text).toContain('Update')
  })
})


// Review-round compliance matrix: every operational dialog must show a
// VISIBLE section label, a named Cancel action, focus an eligible control on
// open and return focus to the invoker on close. Styling/testids alone do
// not establish compliance; these probe the rendered overlay.
describe.each([
  ['AccountFormDialog', AccountFormDialog, { editItem: null }],
  ['BrokerFormDialog', BrokerFormDialog, { editItem: null }],
  ['SecurityFormDialog', SecurityFormDialog, { editItem: null }],
  ['PriceFormDialog', PriceFormDialog, { securities: [{ id: 1, name: 'Fixture Security' }] }],
  ['FXDialog', FXDialog, { editItem: null }],
  ['PriceImportDialog', PriceImportDialog, {}],
  ['FXImportDialog', FXImportDialog, {}],
  ['AssetTransferDialog', AssetTransferDialog, {}],
  ['MergerDialog', MergerDialog, {}],
  ['UpdateAccountPerformanceDialog', UpdateAccountPerformanceDialog, {}],
])('%s form-shell compliance', (name, component, extraProps) => {
  it('shows a visible section label, named Cancel, focus entry and focus return', async () => {
    const invoker = document.createElement('button')
    invoker.textContent = 'open'
    document.body.appendChild(invoker)
    invoker.focus()
    const wrapper = mount(component, {
      attachTo: document.body,
      props: { modelValue: true, ...extraProps },
      global: { plugins: [vuetify, createPinia()], provide: { showError: vi.fn(), clearErrors: vi.fn() } },
    })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 90))
    const overlay = activeDialog()
    expect(overlay, `${name}: overlay open`).toBeTruthy()
    // Visible section label (rendered text, not an aria-only attribute).
    const heading = overlay.querySelector('h3')
    expect(heading && heading.textContent.trim().length > 0, `${name}: visible section label`).toBe(true)
    // Named cancel action.
    const cancel = dialogButton('dialog-cancel')
    expect(cancel && cancel.textContent.trim() === 'Cancel', `${name}: named Cancel`).toBe(true)
    // Focus entry: an eligible control holds focus while open.
    const focused = document.activeElement
    expect(
      focused && focused !== invoker && overlay.contains(focused),
      `${name}: focus entered the dialog (${focused?.tagName})`,
    ).toBe(true)
    // Focus return on close.
    await wrapper.setProps({ modelValue: false })
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(document.activeElement, `${name}: focus returned to the invoker`).toBe(invoker)
    wrapper.unmount()
    invoker.remove()
  })
})
