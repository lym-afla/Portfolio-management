// Task 3 acceptance (real-data corrections): import ownership. Progress
// events ride a window-level CustomEvent bus, so a stream that outlives its
// dialog (close mid-import, then reopen and start another import) must
// never complete, error or move the progress of a dialog instance that does
// not own it. The transport tags every event with the import id that
// produced it (importPrices increments a module sequence and the dialog
// adopts only its own id — the submit wiring is pinned by the accounts
// no-eligible spec and by the browser import case); this spec pins the
// guard contract itself: adopt the owned id, ignore every other id, and
// release ownership when the dialog closes.
import { beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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

const setupOf = (wrapper) =>
  (wrapper.vm.$ as unknown as { setupState: Record<string, unknown> }).setupState

const summaryText = () =>
  [...document.body.querySelectorAll('.v-dialog .v-card')]
    .map((card) => card.textContent)
    .join('\n')

const detail = (over) => ({
  status: 'progress', progress: 40, current: 2, total: 5,
  result: 'updated', date: '2026-01-05', security_name: 'Fixture security',
  ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  api.currentPriceImportId.mockReturnValue(0)
  api.getPriceImportFormStructure.mockResolvedValue(formStructure)
  api.importPrices.mockResolvedValue(undefined)
  document.body.innerHTML = ''
})

describe('PriceImportDialog import ownership', () => {
  it('adopts only the owned import id and ignores every other stream', async () => {
    const wrapper = await mountDialog()
    const state = setupOf(wrapper)
    // Without ownership (no submission yet) nothing is adopted.
    state.handleProgress({ detail: detail({ importId: 1 }) })
    await flushPromises()
    expect(state.progress).toBe(0)
    // The dialog adopts exactly its own import.
    state.ownedImportId = 7
    state.handleProgress({ detail: detail({ importId: 7 }) })
    await flushPromises()
    expect(state.progress).toBe(40)
    // A stale sibling stream (id 6) moves nothing.
    state.handleProgress({ detail: detail({ importId: 6, progress: 90, security_name: 'Stale stream' }) })
    await flushPromises()
    expect(state.progress).toBe(40)
    state.handleProgress({ detail: { status: 'complete', importId: 6, details: [{ security_name: 'Stale stream', updated_dates: [], skipped_dates: [], errors: [] }], total_dates: 0, start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'weekly' } })
    await flushPromises()
    expect(summaryText()).not.toContain('Stale stream')
    // Its own completion lands.
    state.handleProgress({ detail: { status: 'complete', importId: 7, details: [{ security_name: 'Own stream', updated_dates: ['2026-01-06'], skipped_dates: [], errors: [] }], total_dates: 1, start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'weekly' } })
    await flushPromises()
    expect(summaryText()).toContain('Own stream')
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('keeps the session across the configuration close and adopts nothing on a fresh open', async () => {
    const wrapper = await mountDialog()
    const state = setupOf(wrapper)
    state.ownedImportId = 3
    state.handleProgress({ detail: detail({ importId: 3 }) })
    await flushPromises()
    expect(state.progress).toBe(40)
    // The submit-time configuration close (v-model false) must NOT cancel
    // the in-flight session: delayed events still render.
    await wrapper.setProps({ modelValue: false })
    await flushPromises()
    expect(state.ownedImportId).toBe(3)
    state.handleProgress({ detail: detail({ importId: 3, progress: 80 }) })
    await flushPromises()
    expect(state.progress).toBe(80)
    // A fresh open adopts nothing: the abandoned stream's late completion
    // can never surface in the reopened dialog.
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    expect(state.ownedImportId).toBeNull()
    state.handleProgress({ detail: { status: 'complete', importId: 3, details: [{ security_name: 'Abandoned stream', updated_dates: [], skipped_dates: [], errors: [] }], total_dates: 0, start_date: '2026-01-01', end_date: '2026-01-31', frequency: 'weekly' } })
    await flushPromises()
    expect(summaryText()).not.toContain('Abandoned stream')
    wrapper.unmount()
    document.body.innerHTML = ''
  })
})
