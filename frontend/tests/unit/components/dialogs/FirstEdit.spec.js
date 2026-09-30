import { describe, it, expect, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import AccountFormDialog from '@/components/dialogs/AccountFormDialog.vue'
import BrokerFormDialog from '@/components/dialogs/BrokerFormDialog.vue'
import SecurityFormDialog from '@/components/dialogs/SecurityFormDialog.vue'
import TransactionFormDialog from '@/components/dialogs/TransactionFormDialog.vue'
import FXTransactionFormDialog from '@/components/dialogs/FXTransactionFormDialog.vue'
import FXDialog from '@/components/dialogs/FXDialog.vue'
import PriceFormDialog from '@/components/dialogs/PriceFormDialog.vue'
const fixture = vi.hoisted(() => ({ choicesReady: null }))

vi.mock('@/services/api', () => {
  const structure = async () => {
    if (fixture.choicesReady) await fixture.choicesReady
    return { fields: [
    { name: 'name', type: 'textinput', label: 'Name' },
    { name: 'date', type: 'date', label: 'Date' },
    { name: 'type', type: 'select', label: 'Type', choices: [{ value: 'Cash in', label: 'Cash in' }] },
    { name: 'account', type: 'select', label: 'Account', choices: [{ value: '2', label: 'Main' }] },
    { name: 'price', type: 'number', label: 'Price', decimal_places: 6 },
    { name: 'from_currency', type: 'select', label: 'From', choices: [] },
    { name: 'to_currency', type: 'select', label: 'To', choices: [] },
    { name: 'rate', type: 'number', label: 'Rate' },
    ] }
  }
  return {
    getAccountFormStructure: structure, createAccount: vi.fn(), updateAccount: vi.fn(),
    getBrokerFormStructure: structure, createBroker: vi.fn(), updateBroker: vi.fn(),
    getSecurityFormStructure: structure, createSecurity: vi.fn(), updateSecurity: vi.fn(),
    getTransactionFormStructure: structure, addTransaction: vi.fn(), updateTransaction: vi.fn(),
    getFXTransactionFormStructure: structure, addFXTransaction: vi.fn(), updateFXTransaction: vi.fn(),
    getFXFormStructure: structure, addFXRate: vi.fn(), updateFXRate: vi.fn(), deleteFXRate: vi.fn(),
    addPrice: vi.fn(), updatePrice: vi.fn(),
  }
})
vi.mock('@/composables/useErrorHandler', () => ({ useErrorHandler: () => ({ handleApiError: vi.fn() }) }))

const selected = { id: 17, name: 'Selected record', date: '2026-09-08T12:00:00', account: { id: 2 }, type: 'Cash in', price: '19.25', from_currency: 'USD', to_currency: 'EUR', rate: '0.95' }
describe('first edit after a lazy dialog mount', () => {
  it.each([
    [AccountFormDialog, 'name', 'Selected record'],
    [BrokerFormDialog, 'name', 'Selected record'],
    [SecurityFormDialog, 'name', 'Selected record'],
    [TransactionFormDialog, 'account', '2'],
    [FXTransactionFormDialog, 'account', '2'],
    [FXDialog, 'rate', '0.95'],
    [PriceFormDialog, 'price', '19.25'],
  ])('preserves the selected record after asynchronous choices load', async (component, field, expected) => {
    const wrapper = shallowMount(component, { props: { modelValue: true, editItem: selected }, global: { plugins: [createPinia()] } })
    await flushPromises()
    expect(wrapper.vm.form[field]).toBe(expected)
    wrapper.unmount()
  })
  it('preserves FX empty-cell date/pair prefill on first open', async () => {
    const prefill = { date: '2026-09-08', from_currency: 'USD', to_currency: 'EUR' }
    const wrapper = shallowMount(FXDialog, { props: { modelValue: true, prefill }, global: { plugins: [createPinia()] } })
    await flushPromises()
    expect(wrapper.vm.form).toMatchObject(prefill)
    expect(wrapper.vm.formFields.find(field => field.name === 'date').disabled).toBe(true)
    wrapper.unmount()
  })
  it('uses the current selected record when delayed choices finish loading', async () => {
    let release
    fixture.choicesReady = new Promise(resolve => { release = resolve })
    const wrapper = shallowMount(AccountFormDialog, { props: { modelValue: true, editItem: selected }, global: { plugins: [createPinia()] } })
    await wrapper.setProps({ editItem: { ...selected, name: 'New selection' } })
    release()
    await flushPromises()
    expect(wrapper.vm.form.name).toBe('New selection')
    fixture.choicesReady = null
    wrapper.unmount()
  })
})
