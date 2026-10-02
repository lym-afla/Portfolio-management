// D4 Task 5 — ConfirmActionDialog with the REAL Vuetify dialog (teleported
// overlay, attachTo document.body). No generic v-dialog div stubs.
import { beforeAll, afterEach, describe, expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import ConfirmActionDialog from '@/components/workspace/ConfirmActionDialog.vue'
import type { ConfirmationSubject } from '@/components/workspace/types'

afterEach(() => {
  document.body.innerHTML = ''
})

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

const vuetify = createVuetify({ components, directives })

const subject: ConfirmationSubject = {
  title: 'Delete transaction',
  confirmLabel: 'Delete transaction',
  details: [
    { label: 'Account', value: 'Brokerage A' },
    { label: 'Date', value: '2026-09-08' },
    { label: 'Security', value: 'ACME Corp — Buy 10 @ $120.50' },
    { label: 'Amount', value: '($1,205.00) USD' },
  ],
}

const mountDialog = (props: Record<string, unknown> = {}) =>
  mount(ConfirmActionDialog, {
    attachTo: document.body,
    global: { plugins: [vuetify] },
    props: { modelValue: true, subject, busy: false, error: null, ...props },
  })

// Vuetify overlays linger hidden (v-show) during/after the leave transition
// in jsdom, so [role="dialog"] matches stale dialogs; the open one is the
// overlay still flagged active.
const dialogElement = () =>
  document.querySelector('.v-overlay--active[role="dialog"]') as HTMLElement

describe('ConfirmActionDialog', () => {
  it('keeps the identified transaction visible after a failed delete', async () => {
    const wrapper = mountDialog()
    await wrapper.setProps({ error: 'The transaction could not be deleted. Try again.' })
    await flushPromises()
    const dialog = dialogElement()
    expect(dialog).toBeTruthy()
    expect(dialog.textContent).toContain('Brokerage A')
    expect(dialog.textContent).toContain('2026-09-08')
    expect(dialog.textContent).toContain('($1,205.00) USD')
    expect(dialog.textContent).toContain('Try again')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    wrapper.unmount()
  })

  it('associates the dialog with its title and details for assistive tech', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    const dialog = dialogElement()
    expect(dialog.getAttribute('aria-labelledby')).toBeTruthy()
    expect(document.getElementById(dialog.getAttribute('aria-labelledby')!)?.textContent)
      .toContain('Delete transaction')
    expect(dialog.getAttribute('aria-describedby')).toBeTruthy()
    expect(document.getElementById(dialog.getAttribute('aria-describedby')!)?.textContent)
      .toContain('Brokerage A')
    wrapper.unmount()
  })

  it('focuses Cancel when opened for a destructive confirmation', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    const cancel = dialogElement().querySelector('[data-testid="confirm-cancel"]') as HTMLElement
    expect(document.activeElement).toBe(cancel)
    wrapper.unmount()
  })

  it('Cancel and Escape close without ever emitting confirm', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    const cancel = dialogElement().querySelector('[data-testid="confirm-cancel"]') as HTMLElement
    cancel.click()
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    expect(wrapper.emitted('confirm')).toBeUndefined()

    // Reopen and press Escape while idle: one dispatched keydown is caught
    // by the overlay's own handler and closes without confirming.
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    dialogElement().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')!.length).toBeGreaterThanOrEqual(2)
    expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([false])
    wrapper.unmount()
  })

  it('busy blocks repeated confirmation and accidental dismissal', async () => {
    const wrapper = mountDialog({ busy: true })
    await flushPromises()
    const confirm = dialogElement().querySelector('[data-testid="confirm-confirm"]') as HTMLElement
    const cancel = dialogElement().querySelector('[data-testid="confirm-cancel"]') as HTMLElement
    expect(confirm.getAttribute('disabled')).not.toBeNull()
    cancel.click()
    await flushPromises()
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })

  it('emits confirm exactly once per click while idle and shows the exact confirm label', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    const confirm = dialogElement().querySelector('[data-testid="confirm-confirm"]') as HTMLElement
    expect(confirm.textContent).toContain('Delete transaction')
    confirm.click()
    await flushPromises()
    expect(wrapper.emitted('confirm')).toHaveLength(1)
    wrapper.unmount()
  })

  it('restores focus to the previously focused control on close', async () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'Delete regular_5'
    document.body.appendChild(trigger)
    trigger.focus()
    const wrapper = mountDialog()
    await flushPromises()
    expect(document.activeElement).not.toBe(trigger)
    await wrapper.setProps({ modelValue: false })
    await flushPromises()
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
    wrapper.unmount()
  })

  it('shows a loading state and keeps confirmation disabled while details load', async () => {
    const wrapper = mountDialog({ detailsPending: true })
    await flushPromises()
    const dialog = dialogElement()
    expect(dialog.textContent).toMatch(/loading/i)
    const confirm = dialog.querySelector('[data-testid="confirm-confirm"]') as HTMLElement
    expect(confirm.getAttribute('disabled')).not.toBeNull()
    wrapper.unmount()
  })
})
