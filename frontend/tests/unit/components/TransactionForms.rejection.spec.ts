// D4 Task 5 — rejected saves on the regular/FX transaction forms preserve
// every entered field, show inline errors and visible section labels, manage
// initial/returned focus, and never change save payloads or Yup rules.
import { beforeAll, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import TransactionFormDialog from '@/components/dialogs/TransactionFormDialog.vue'
import FXTransactionFormDialog from '@/components/dialogs/FXTransactionFormDialog.vue'

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

const vuetify = createVuetify({ components, directives })

const mocks = vi.hoisted(() => ({
  getTransactionFormStructure: vi.fn(),
  getFXTransactionFormStructure: vi.fn(),
  addTransaction: vi.fn(),
  updateTransaction: vi.fn(),
  addFXTransaction: vi.fn(),
  updateFXTransaction: vi.fn(),
}))
vi.mock('@/services/api', () => ({ ...mocks }))

const regularFields = [
  { name: 'date', label: 'Date', type: 'datepicker', required: true },
  {
    name: 'type', label: 'Type', type: 'select', required: true,
    choices: [{ value: 'Buy', text: 'Buy' }, { value: 'Sell', text: 'Sell' }, { value: 'Cash in', text: 'Cash in' }],
  },
  {
    name: 'security', label: 'Security', type: 'select', required: false,
    choices: [
      { value: '1', text: 'ACME Corp', type: 'Stock' },
      { value: '2', text: 'UST 2.375% 31', type: 'Bond' },
    ],
  },
  { name: 'quantity', label: 'Quantity', type: 'number', required: false },
  { name: 'price', label: 'Price', type: 'number', required: false },
  { name: 'commission', label: 'Commission', type: 'number', required: false },
  { name: 'cash_flow', label: 'Cash flow', type: 'number', required: false },
  { name: 'notes', label: 'Notes', type: 'textarea', required: false },
]

const fxFields = [
  { name: 'date', label: 'Date', type: 'datepicker', required: true },
  {
    name: 'from_cur', label: 'From currency', type: 'select', required: true,
    choices: [{ value: 'EUR', text: 'Euro' }, { value: 'USD', text: 'Dollar' }],
  },
  {
    name: 'to_cur', label: 'To currency', type: 'select', required: true,
    choices: [{ value: 'USD', text: 'Dollar' }, { value: 'EUR', text: 'Euro' }],
  },
  { name: 'from_amount', label: 'From amount', type: 'number', required: true },
  { name: 'to_amount', label: 'To amount', type: 'number', required: true },
  { name: 'rate', label: 'Rate', type: 'number', required: false },
]

const activeDialog = () =>
  document.querySelector('.v-overlay--active[role="dialog"]') as HTMLElement

const dialogInput = (label: string) =>
  [...activeDialog().querySelectorAll('label')]
    .find((el) => el.textContent?.trim() === label)
    ?.closest('.v-input')?.querySelector('input, textarea') as HTMLInputElement

const sectionHeadings = () =>
  [...activeDialog().querySelectorAll('h3')].map((el) => el.textContent?.trim())

const saveButton = () =>
  [...activeDialog().querySelectorAll('button')]
    .find((el) => el.textContent?.trim() === 'Save') as HTMLElement

async function mountForm(component: typeof TransactionFormDialog, modelValue = true): Promise<VueWrapper> {
  const wrapper = mount(component, {
    attachTo: document.body,
    global: { plugins: [vuetify] },
    props: { modelValue, editItem: null },
  })
  await flushPromises()
  return wrapper
}

const setInputValue = async (label: string, value: string) => {
  const input = dialogInput(label)
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
}

const selectOption = async (label: string, optionText: string) => {
  const input = dialogInput(label)
  ;(input.closest('.v-input')?.querySelector('.v-field') as HTMLElement)?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  ;(input.closest('.v-input')?.querySelector('.v-field') as HTMLElement)?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await new Promise((resolve) => setTimeout(resolve, 50))
  const item = [...document.querySelectorAll('.v-overlay--active .v-list-item')]
    .find((el) => el.textContent?.includes(optionText)) as HTMLElement
  item.click()
  await flushPromises()
}

describe('TransactionFormDialog rejected saves', () => {
  it('preserves entered fields, shows inline and general errors, and section labels', async () => {
    mocks.getTransactionFormStructure.mockResolvedValue({ fields: regularFields })
    mocks.addTransaction.mockRejectedValueOnce({
      quantity: ['Insufficient quantity for the selected type'],
      __all__: ['The transaction was rejected by the server.'],
    })
    const wrapper = await mountForm(TransactionFormDialog)

    expect(sectionHeadings()).toEqual(['Transaction details', 'Amounts'])
    await setInputValue('Date', '2026-09-08')
    await selectOption('Type', 'Buy')
    await selectOption('Security', 'ACME Corp')
    await setInputValue('Quantity', '10')
    await setInputValue('Price', '120.50')
    await setInputValue('Commission', '-15.00')
    await setInputValue('Cash flow', '-1220.50')

    saveButton().click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))

    // Rejected save keeps the dialog and every entered value.
    expect(wrapper.vm.dialog).toBe(true)
    expect(dialogInput('Date').value).toBe('2026-09-08')
    expect(dialogInput('Quantity').value).toBe('10')
    expect(dialogInput('Price').value).toBe('120.50')
    expect(dialogInput('Commission').value).toBe('-15.00')
    expect(dialogInput('Cash flow').value).toBe('-1220.50')
    expect(activeDialog().textContent).toContain('Insufficient quantity for the selected type')
    expect(activeDialog().textContent).toContain('rejected by the server')

    // The rejected field error keeps Save disabled until the value is
    // corrected (the app's existing validation rule, unchanged by D4);
    // submitting through the same save path proves the payload survives.
    await setInputValue('Quantity', '20')
    mocks.addTransaction.mockResolvedValueOnce({ id: 9 })
    await wrapper.vm.submitForm()
    await flushPromises()
    const payload = mocks.addTransaction.mock.calls.at(-1)![0]
    expect(payload).toMatchObject({
      // Numbers cross the wire as strings — the unchanged existing payload
      // contract (the backend parses them into Decimals).
      date: '2026-09-08', type: 'Buy', security: '1',
      quantity: '20', price: '120.50', commission: '-15.00', cash_flow: '-1220.50',
    })
    expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([false])
    wrapper.unmount()
  })

  it('keeps the existing Yup rules (negative price never reaches the API)', async () => {
    mocks.getTransactionFormStructure.mockResolvedValue({ fields: regularFields })
    const wrapper = await mountForm(TransactionFormDialog)
    await setInputValue('Date', '2026-09-08')
    await selectOption('Type', 'Buy')
    await setInputValue('Price', '-5')
    saveButton().click()
    await flushPromises()
    expect(mocks.addTransaction).not.toHaveBeenCalled()
    expect(activeDialog().textContent).toContain('Price must be positive')
    wrapper.unmount()
  })

  it('keeps the bond percent-of-nominal price hint', async () => {
    mocks.getTransactionFormStructure.mockResolvedValue({ fields: regularFields })
    const wrapper = await mountForm(TransactionFormDialog)
    await selectOption('Security', 'UST 2.375% 31')
    const priceInput = dialogInput('Price')
    const inputWrapper = priceInput.closest('.v-input') as HTMLElement
    expect(inputWrapper.textContent).toContain('%')
    wrapper.unmount()
  })

  it('focuses the first field on open and returns focus on close', async () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'Add transaction'
    document.body.appendChild(trigger)
    trigger.focus()
    mocks.getTransactionFormStructure.mockResolvedValue({ fields: regularFields })
    const wrapper = await mountForm(TransactionFormDialog)
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(activeDialog().contains(document.activeElement)).toBe(true)
    await wrapper.setProps({ modelValue: false })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
    wrapper.unmount()
  })
})

describe('FXTransactionFormDialog rejected saves', () => {
  it('preserves entered fields with inline errors and section labels', async () => {
    mocks.getFXTransactionFormStructure.mockResolvedValue({ fields: fxFields })
    mocks.addFXTransaction.mockRejectedValueOnce({
      from_amount: ['From amount must be negative for a sale'],
      __all__: ['FX transaction rejected.'],
    })
    const wrapper = await mountForm(FXTransactionFormDialog)

    expect(sectionHeadings()).toEqual(['Transaction details', 'Amounts'])
    await setInputValue('Date', '2026-09-01')
    await selectOption('From currency', 'Euro')
    await selectOption('To currency', 'Dollar')
    await setInputValue('From amount', '1000')
    await setInputValue('To amount', '1080')

    saveButton().click()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(wrapper.vm.dialog).toBe(true)
    expect(dialogInput('From amount').value).toBe('1000')
    expect(dialogInput('To amount').value).toBe('1080')
    expect(activeDialog().textContent).toContain('From amount must be negative for a sale')
    expect(activeDialog().textContent).toContain('FX transaction rejected')

    mocks.addFXTransaction.mockResolvedValueOnce({ id: 4 })
    saveButton().click()
    await flushPromises()
    expect(mocks.addFXTransaction).toHaveBeenCalledWith(expect.objectContaining({
      date: '2026-09-01', from_cur: 'EUR', to_cur: 'USD', from_amount: '1000', to_amount: '1080',
    }))
    expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([false])
    wrapper.unmount()
  })
})
