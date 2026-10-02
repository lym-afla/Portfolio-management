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

  it('cancels delayed focus on unmount: another open dialog keeps its focus', async () => {
    // The OTHER dialog is open with two fields; the user is focused on its
    // second field when the form in question unmounts.
    const fxStructure = deferred()
    mocks.getFXTransactionFormStructure.mockReturnValue(fxStructure.promise)
    const fxWrapper = await mountForm(FXTransactionFormDialog)
    fxStructure.resolve({
      fields: [
        { name: 'date', label: 'Date', type: 'datepicker', required: true },
        { name: 'from_amount', label: 'From amount', type: 'number', required: true },
      ],
    })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))
    const secondInput = [...activeDialog().querySelectorAll('input')]
      .find((input) => input.closest('.v-input')?.textContent?.includes('From amount')) as HTMLInputElement
    secondInput.focus()
    const focusedBefore = document.activeElement

    // The regular form mounts with a structure that never loads in time,
    // then unmounts (route change) before the response arrives.
    const pending = deferred()
    mocks.getTransactionFormStructure.mockReturnValue(pending.promise)
    const wrapper = await mountForm(TransactionFormDialog)
    await new Promise((resolve) => setTimeout(resolve, 100))
    wrapper.unmount()

    pending.resolve({ fields: regularFields })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))
    // The unmounted form must not move focus at all - an unscoped fallback
    // would have refocused the other dialog's FIRST field.
    expect(document.activeElement).toBe(focusedBefore)
    fxWrapper.unmount()
  })

  const instanceTakeoverFields = [
    { name: 'date', label: 'Date', type: 'datepicker', required: true },
    { name: 'quantity', label: 'Quantity', type: 'number', required: false },
    { name: 'price', label: 'Price', type: 'number', required: false },
  ]

  const secondFieldInput = () =>
    [...activeDialog().querySelectorAll('input')]
      .find((input) => input.closest('.v-input')?.textContent?.includes('Quantity')) as HTMLInputElement

  // The late structure response of an UNMOUNTED instance must not start new
  // focus work — not even inside a same-type replacement dialog whose
  // overlay matches the shared title id.
  const assertNoPostUnmountFocusSteal = async (
    mountDelayed: () => Promise<{ wrapper: VueWrapper; resolve: (value: unknown) => void }>,
    mountReplacement: () => Promise<VueWrapper>,
  ) => {
    const first = await mountDelayed()
    await new Promise((resolve) => setTimeout(resolve, 100))
    first.wrapper.unmount()

    const replacement = await mountReplacement()
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))
    const second = secondFieldInput()
    second.focus()
    const focusedBefore = document.activeElement
    expect(focusedBefore).toBe(second)

    first.resolve({ fields: instanceTakeoverFields })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))
    expect(document.activeElement).toBe(focusedBefore)
    replacement.unmount()
  }

  it('regular form: a late structure response after unmount never moves focus into its replacement', async () => {
    const oldStructure = deferred()
    mocks.getTransactionFormStructure.mockReturnValueOnce(oldStructure.promise)
    mocks.getTransactionFormStructure.mockResolvedValueOnce({ fields: instanceTakeoverFields })
    await assertNoPostUnmountFocusSteal(
      async () => {
        const wrapper = await mountForm(TransactionFormDialog)
        return { wrapper, resolve: oldStructure.resolve }
      },
      async () => mountForm(TransactionFormDialog),
    )
  })

  it('FX form: a late structure response after unmount never moves focus into its replacement', async () => {
    const oldStructure = deferred()
    mocks.getFXTransactionFormStructure.mockReturnValueOnce(oldStructure.promise)
    mocks.getFXTransactionFormStructure.mockResolvedValueOnce({ fields: instanceTakeoverFields })
    await assertNoPostUnmountFocusSteal(
      async () => {
        const wrapper = await mountForm(FXTransactionFormDialog)
        return { wrapper, resolve: oldStructure.resolve }
      },
      async () => mountForm(FXTransactionFormDialog),
    )
  })

  it('scopes delayed focus to the owning dialog, not the first active overlay', async () => {
    // The FX dialog is mounted FIRST so its overlay precedes the regular
    // dialog's in DOM order - an unscoped querySelector would hit it.
    const fxStructure = deferred()
    mocks.getFXTransactionFormStructure.mockReturnValue(fxStructure.promise)
    const fxWrapper = await mountForm(FXTransactionFormDialog)
    fxStructure.resolve({
      fields: [{ name: 'date', label: 'Date', type: 'datepicker', required: true }],
    })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))

    const pending = deferred()
    mocks.getTransactionFormStructure.mockReturnValue(pending.promise)
    const wrapper = await mountForm(TransactionFormDialog)
    await new Promise((resolve) => setTimeout(resolve, 100))

    pending.resolve({ fields: regularFields })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 350))
    const focused = document.activeElement as HTMLElement | null
    expect(focused).toBeTruthy()
    // Focus lands inside the regular form's OWN overlay (identified by its
    // title id), never inside the FX dialog.
    const owner = focused?.closest('.v-overlay--active[role="dialog"]') as HTMLElement | null
    expect(owner?.querySelector('#transaction-form-title')).toBeTruthy()
    fxWrapper.unmount()
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
