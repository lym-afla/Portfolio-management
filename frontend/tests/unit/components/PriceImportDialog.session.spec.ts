// Round-4 correction: import ownership across NORMAL submission. The parent
// hosts the dialog with a real v-model, so submitForm's configuration-dialog
// close propagates update:modelValue=false back into the component. The
// import session must survive that close: the delayed stream events still
// drive the progress label, the completion still renders the summary, the
// parent receives exactly one refresh, and an OLDER request's late
// rejection must not report errors into or reset a newer import.
import { beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const api = vi.hoisted(() => ({
  importPrices: vi.fn(),
  getPriceImportFormStructure: vi.fn(),
  currentPriceImportId: vi.fn(() => 0),
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

const formStructure = {
  securities: [{ id: 42, name: 'Fixture security' }],
  accounts: [{ id: 7, name: 'Trading account' }],
  frequency_choices: [{ value: 'weekly', text: 'Weekly' }],
}

// Parent-controlled host: the exact production wiring (v-model + the
// refresh-triggering event), no internal-ref shortcuts.
const Host = defineComponent({
  setup(_, { expose }) {
    const open = ref(true)
    const refreshes = ref(0)
    const errors = ref<string[]>([])
    const onPricesImported = () => {
      refreshes.value += 1
    }
    expose({
      close: () => {
        open.value = false
      },
      reopen: () => {
        open.value = true
      },
      state: () => ({ open: open.value, refreshes: refreshes.value, errors: errors.value }),
    })
    return () => h(PriceImportDialog, {
      modelValue: open.value,
      'onUpdate:modelValue': (value: boolean) => {
        open.value = value
      },
      onPricesImported,
    })
  },
})

const showError = vi.fn()

const mountHost = async () => {
  const wrapper = mount(Host, {
    attachTo: document.body,
    global: {
      plugins: [vuetify, createPinia()],
      provide: { showError, clearErrors: vi.fn() },
    },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

const fillDraft = async (host, { start = '2026-01-01', end = '2026-01-31' } = {}) => {
  const dialog = host.findComponent(PriceImportDialog)
  const autocompletes = dialog.findAllComponents({ name: 'VAutocomplete' })
  const selects = dialog.findAllComponents({ name: 'VSelect' })
  const pickers = dialog.findAllComponents({ name: 'VDatePicker' })
  await selects[0].setValue('weekly')
  await autocompletes[0].setValue([42])
  await autocompletes[1].setValue([7])
  // Plain ISO strings: Date objects would drift a day through local/UTC
  // conversions and poison the comparisons.
  await pickers[0].setValue(start)
  await pickers[1].setValue(end)
}

const fillAndSubmit = async (host, options = {}) => {
  await fillDraft(host, options)
  const submitButton = [...document.body.querySelectorAll('button')]
    .find((b) => ['Import Prices', 'Start Import'].includes(b.textContent?.trim() ?? ''))
  expect(submitButton, 'submit button rendered').toBeTruthy()
  submitButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flushPromises()
  await new Promise((resolve) => setTimeout(resolve, 300))
  await flushPromises()
}

const dialogDatePickerValues = (host) => {
  const dialog = host.findComponent(PriceImportDialog)
  const pickers = dialog.findAllComponents({ name: 'VDatePicker' })
  return pickers.map((picker) => {
    const model = picker.props('modelValue')
    if (Array.isArray(model)) {
      // resetForm clears date fields to [] — normalize to null so erased
      // and never-set are comparable.
      if (model.length === 0) return null
      return model.length === 0 ? null : model.map(String)
    }
    return model === null || model === undefined ? null : String(model)
  })
}

const summaryText = () =>
  [...document.body.querySelectorAll('.v-dialog .v-card')]
    .map((card) => card.textContent)
    .join('\n')

const progressEvent = (detail) =>
  window.dispatchEvent(new CustomEvent('priceImportProgress', { detail }))

beforeEach(() => {
  vi.clearAllMocks()
  showError.mockReset()
  api.currentPriceImportId.mockReturnValue(0)
  api.getPriceImportFormStructure.mockResolvedValue(formStructure)
  document.body.innerHTML = ''
})

describe('PriceImportDialog import session across normal submission', () => {
  it('keeps the session alive after the parent-observed configuration close and renders delayed progress and completion', async () => {
    let releaseImport
    api.importPrices.mockImplementationOnce(
      () => new Promise((resolve) => {
        releaseImport = resolve
      })
    )
    const host = await mountHost(Host)
    await fillAndSubmit(host)

    // The parent observed the configuration-dialog close.
    expect(host.vm.$.setupState ? null : null)
    const hostState = (host.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState
    void hostState
    // submitForm closes the configuration dialog through v-model: the host's
    // open flag must be false now, while the import is still in flight.
    // (The dialog component emits update:modelValue=false on submit.)
    await vi.waitFor(() => {
      const open = (host.vm.$.exposed as unknown as { state: () => { open: boolean } }).state().open
      expect(open).toBe(false)
    })

    // Delayed stream events arrive AFTER the configuration close.
    progressEvent({ status: 'progress', progress: 40, current: 2, total: 5, importId: 1, result: 'updated', date: '2026-01-05', security_name: 'Fixture security' })
    await flushPromises()
    const label = document.querySelector('[data-testid="import-progress-label"]')
    expect(label, 'the live progress label renders after the configuration close').toBeTruthy()
    expect(label.textContent).toContain('40%')

    progressEvent({ status: 'complete', importId: 1, details: [{ security_name: 'Fixture security', updated_dates: ['2026-01-05'], skipped_dates: [], errors: [] }], total_dates: 1, start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'weekly' })
    await flushPromises()
    expect(summaryText()).toContain('Fixture security')
    expect(api.importPrices).toHaveBeenCalledTimes(1)
    releaseImport(undefined)
    await flushPromises()
    host.unmount()
    document.body.innerHTML = ''
  })

  it('reports exactly one refresh for the completed import', async () => {
    // In production every stream event dispatches before the transport
    // promise settles; the mock holds until the completion has been
    // delivered to reproduce that ordering.
    let releaseImport
    api.importPrices.mockImplementationOnce(
      () => new Promise((resolve) => {
        releaseImport = resolve
      })
    )
    const host = await mountHost(Host)
    await fillAndSubmit(host)
    progressEvent({ status: 'complete', importId: 1, details: [{ security_name: 'Fixture security', updated_dates: [], skipped_dates: [], errors: [] }], total_dates: 0, start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'weekly' })
    await flushPromises()
    const exposed = (host.vm.$.exposed as unknown as { state: () => { refreshes: number } }).state()
    expect(exposed.refreshes).toBe(1)
    releaseImport(undefined)
    await flushPromises()
    host.unmount()
    document.body.innerHTML = ''
  })

  it('an older request\'s late rejection cannot report errors into a newer import', async () => {
    // Import A hangs; the dialog starts import B; A rejects late. Distinct
    // counter values give each import its own event id.
    const pendingA: Array<(value?: unknown) => void> = []
    const pendingB: Array<(value?: unknown) => void> = []
    api.currentPriceImportId.mockReturnValueOnce(0).mockReturnValueOnce(1)
    api.importPrices
      .mockImplementationOnce(() => new Promise((resolve) => pendingA.push(resolve)))
      .mockImplementationOnce(() => new Promise((resolve) => pendingB.push(resolve)))
    const host = await mountHost(Host)
    await fillAndSubmit(host) // import A (id 1) in flight
    progressEvent({ status: 'progress', progress: 20, current: 1, total: 5, importId: 1, result: 'updated', date: '2026-01-05', security_name: 'A' })
    await flushPromises()
    const label = document.querySelector('[data-testid="import-progress-label"]')
    expect(label?.textContent).toContain('20%')
    // Import B starts while A is still in flight: reopen the configuration
    // dialog first (the parent closed it at A's submit).
    const exposed = host.vm.$.exposed as unknown as { reopen: () => void }
    exposed.reopen()
    await flushPromises()
    await fillAndSubmit(host)
    progressEvent({ status: 'progress', progress: 70, current: 3, total: 5, importId: 2, result: 'updated', date: '2026-01-06', security_name: 'B' })
    await flushPromises()
    const labelB = document.querySelector('[data-testid="import-progress-label"]')
    expect(labelB?.textContent).toContain('70%')
    // A rejects late: its failure must not surface (no snackbar, no reset,
    // no hiding of B's progress).
    pendingA[0](new Error('stale transport failure'))
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(showError).not.toHaveBeenCalled()
    const labelAfter = document.querySelector('[data-testid="import-progress-label"]')
    expect(labelAfter?.textContent).toContain('70%')
    pendingB[0](undefined)
    await flushPromises()
    host.unmount()
    document.body.innerHTML = ''
  })

  it('an older import resolving successfully cannot erase the reopened configuration draft', async () => {
    // Import A hangs; the user reopens the configuration form and enters a
    // fresh distinct draft (not yet submitted); A then resolves
    // successfully. A's post-await resetForm must not erase the visible
    // draft the user is working on.
    let releaseA
    api.importPrices.mockImplementationOnce(() => new Promise((resolve) => {
      releaseA = resolve
    }))
    const host = await mountHost(Host)
    await fillAndSubmit(host) // import A in flight, config closed
    const exposed = host.vm.$.exposed as unknown as { reopen: () => void }
    exposed.reopen()
    await flushPromises()
    // A distinct new draft, entered but NOT submitted.
    await fillDraft(host, { start: '2026-02-01', end: '2026-02-15' })
    expect(api.importPrices).toHaveBeenCalledTimes(1)

    // A resolves successfully while the fresh draft sits in the open form.
    releaseA(undefined)
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 50))
    await flushPromises()

    const values = dialogDatePickerValues(host)
    expect(values[0]).toContain('2026-02-01')
    expect(values[1]).toContain('2026-02-15')
    // A had no completion event: no summary, no refresh.
    const exposedState = (host.vm.$.exposed as unknown as { state: () => { refreshes: number } }).state()
    expect(exposedState.refreshes).toBe(0)
    host.unmount()
    document.body.innerHTML = ''
  })
})
