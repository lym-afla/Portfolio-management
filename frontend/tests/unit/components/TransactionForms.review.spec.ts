// PR #51 review round — regression for review finding 5:
// delayed form structures focus the first field when they become ready,
// and a dialog closed in the meantime cancels the focus entirely.
import { beforeAll, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import TransactionFormDialog from '@/components/dialogs/TransactionFormDialog.vue'
import FXTransactionFormDialog from '@/components/dialogs/FXTransactionFormDialog.vue'
import { deferred } from '../helpers/deferred'

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
  addFXTransaction: vi.fn(),
}))
vi.mock('@/services/api', () => ({ ...mocks }))

const regularFields = [
  { name: 'date', label: 'Date', type: 'datepicker', required: true },
  { name: 'quantity', label: 'Quantity', type: 'number', required: false },
]

const activeDialog = () =>
  document.querySelector('.v-overlay--active[role="dialog"]') as HTMLElement

const mountForm = async (component: typeof TransactionFormDialog): Promise<VueWrapper> => {
  const wrapper = mount(component, {
    attachTo: document.body,
    global: { plugins: [vuetify] },
    props: { modelValue: true, editItem: null },
  })
  await flushPromises()
  return wrapper
}

describe('review 5: focus follows delayed fields; close cancels it', () => {
  it('focuses the first field once a slow form structure finally renders', async () => {
    const pending = deferred()
    mocks.getTransactionFormStructure.mockReturnValue(pending.promise)
    const wrapper = await mountForm(TransactionFormDialog)

    // Let the open-time focus poll window pass while no fields exist yet.
    await new Promise((resolve) => setTimeout(resolve, 350))
    const dialog = activeDialog()
    expect(dialog).toBeTruthy()
    expect(document.activeElement === dialog || dialog.contains(document.activeElement)).toBe(false)

    pending.resolve({ fields: regularFields })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))
    expect(activeDialog().contains(document.activeElement)).toBe(true)
    wrapper.unmount()
  })

  it('cancels the pending focus when the dialog closes before fields arrive', async () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'Add transaction'
    document.body.appendChild(trigger)
    trigger.focus()

    const pending = deferred()
    mocks.getTransactionFormStructure.mockReturnValue(pending.promise)
    const wrapper = await mountForm(TransactionFormDialog)
    await new Promise((resolve) => setTimeout(resolve, 100))

    // The user closes the dialog while the structure is still loading.
    await wrapper.setProps({ modelValue: false })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(document.activeElement).toBe(trigger)

    pending.resolve({ fields: regularFields })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))
    // No focus stealing from the closed dialog's late fields.
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
    wrapper.unmount()
  })

  it('applies the same delayed-focus behavior to the FX form', async () => {
    const pending = deferred()
    mocks.getFXTransactionFormStructure.mockReturnValue(pending.promise)
    const wrapper = await mountForm(FXTransactionFormDialog)
    await new Promise((resolve) => setTimeout(resolve, 350))
    pending.resolve({
      fields: [
        { name: 'date', label: 'Date', type: 'datepicker', required: true },
        { name: 'from_amount', label: 'From amount', type: 'number', required: true },
      ],
    })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))
    expect(activeDialog().contains(document.activeElement)).toBe(true)
    wrapper.unmount()
  })
})
