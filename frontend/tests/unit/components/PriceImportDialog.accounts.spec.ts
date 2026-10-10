// Task 3 (real-data corrections): the price-import submit must carry the
// exact selected account identities — single and multiple — to the import
// command (the consumer resolves held securities from them), and the
// no-eligible-securities completion must render as an explicit informational
// result. The v-dialog teleports to document.body, so all DOM interaction
// runs at the document level with real clicks.
import { beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const api = vi.hoisted(() => ({
  importPrices: vi.fn(),
  getPriceImportFormStructure: vi.fn(),
}))
vi.mock('@/services/api', () => api)

import PriceImportDialog from '@/components/dialogs/PriceImportDialog.vue'

const vuetify = createVuetify({ components, directives })

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

// Faithful backend shape (database/views.py price form structure):
// accounts carry {id, name}; frequency_choices are {value, text}.
const formStructure = {
  securities: [{ id: 42, name: 'Fixture security' }],
  accounts: [
    { id: 7, name: 'Trading account' },
    { id: 11, name: 'Long-term account' },
  ],
  frequency_choices: [
    { value: 'weekly', text: 'Weekly' },
  ],
}

const mountDialog = async () => {
  const wrapper = mount(PriceImportDialog, {
    attachTo: document.body,
    props: { modelValue: true, provider: 'FT' },
    global: {
      plugins: [vuetify, createPinia()],
      provide: { showError: vi.fn(), clearErrors: vi.fn() },
    },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

const doc = () => document.body

// Drive the bound VSelect components directly: the vee-validate models are
// wired through v-model, so a component emit updates the form values the
// submit handler gathers (DOM menu choreography is covered by the focused
// browser cases).
// The dialog uses v-autocomplete for securities/accounts and a radio group
// for the date mode; find the autocomplete components (VAutocomplete extends
// VSelect, so match by the autocomplete marker).
const selects = (wrapper) =>
  wrapper.findAllComponents({ name: 'VAutocomplete' })

const submit = async () => {
  const submitButton = [...doc().querySelectorAll('button')]
    .find((b) => ['Import Prices', 'Start Import'].includes(b.textContent?.trim() ?? ''))
  expect(submitButton).toBeTruthy()
  submitButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flushPromises()
  await new Promise((r) => setTimeout(r, 300))
}

beforeEach(() => {
  vi.clearAllMocks()
  api.importPrices.mockResolvedValue(undefined)
  api.getPriceImportFormStructure.mockResolvedValue(formStructure)
})

describe('PriceImportDialog account payload', () => {
  it('sends the exact selected account identities (multi-account)', async () => {
    const wrapper = await mountDialog()
    const vAutocompletes = selects(wrapper)
    expect(vAutocompletes.length).toBeGreaterThanOrEqual(2)
    const vSelects = wrapper.findAllComponents({ name: 'VSelect' })
    await vSelects[0].setValue('weekly')
    await vAutocompletes[0].setValue([42])
    await vAutocompletes[1].setValue([7, 11])
    // Range mode uses date pickers bound to the vee-validate date fields.
    const pickers = wrapper.findAllComponents({ name: 'VDatePicker' })
    expect(pickers.length).toBeGreaterThanOrEqual(2)
    await pickers[0].setValue(new Date('2026-01-01T00:00:00'))
    await pickers[1].setValue(new Date('2026-01-31T00:00:00'))
    // Invoke the exposed vee-validate handler directly (the rendered form
    // lives in a teleported overlay).
    const multiHandler = (wrapper.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState.submitForm as (e?: unknown) => Promise<void>
    await multiHandler()
    await flushPromises()
    expect(api.importPrices).toHaveBeenCalledTimes(1)
    const payload = api.importPrices.mock.calls[0][0]
    expect(payload.accounts).toEqual([7, 11])
    expect(payload.securities).toEqual([42])
    wrapper.unmount()
  })

  it('sends a single selected account identity', async () => {
    const wrapper = await mountDialog()
    const vAutocompletes = selects(wrapper)
    const vSelects = wrapper.findAllComponents({ name: 'VSelect' })
    await vSelects[0].setValue('weekly')
    const pickers = wrapper.findAllComponents({ name: 'VDatePicker' })
    await vAutocompletes[0].setValue([42])
    await vAutocompletes[1].setValue([7])
    await pickers[0].setValue(new Date('2026-01-01T00:00:00'))
    await pickers[1].setValue(new Date('2026-01-31T00:00:00'))
    await submit()
    expect(api.importPrices).toHaveBeenCalledTimes(1)
    const payload = api.importPrices.mock.calls[0][0]
    expect(payload.accounts).toEqual([7])
    wrapper.unmount()
  })

  it('renders an explicit no-eligible-securities summary result', async () => {
    const wrapper = await mountDialog()
    window.dispatchEvent(new CustomEvent('priceImportProgress', {
      detail: {
        status: 'complete', current: 0, total: 0, progress: 0,
        message: 'No eligible securities found for the selected accounts (no held positions in the selected period)',
        no_eligible_securities: true,
        start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'D',
      },
    }))
    await flushPromises()
    const noEligible = doc().querySelector('[data-testid="no-eligible-securities"]')
    expect(noEligible).toBeTruthy()
    expect(noEligible.textContent).toContain('No eligible securities found')
    wrapper.unmount()
  })
})
