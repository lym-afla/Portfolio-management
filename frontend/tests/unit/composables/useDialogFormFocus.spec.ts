// D5 review round — useDialogFormFocus contract: focus goes to the first
// ELIGIBLE control (disabled/hidden/aria-hidden inputs are skipped), fields
// arriving after the ~200ms polling window still get focus through a
// structure observer (not a longer timeout), and close/unmount permanently
// cancel the pending focus so a replacement dialog of the same type never
// has its focus stolen.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import { useDialogFormFocus } from '@/composables/useDialogFormFocus'

const vuetify = createVuetify()

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

type HarnessVm = {
  cardId: string
  close: () => void
  addField: (disabled?: boolean) => HTMLInputElement
}

const Harness = defineComponent({
  name: 'FocusHarness',
  props: {
    cardPrefix: { type: String, required: true },
    immediateField: { type: Boolean, default: false },
    disabledFirst: { type: Boolean, default: false },
    invoker: { type: HTMLElement, default: null },
  },
  setup(props, { expose }) {
    const dialog = ref(true)
    const { cardId } = useDialogFormFocus(dialog, props.cardPrefix)
    expose({
      dialog,
      cardId,
      close: () => {
        dialog.value = false
      },
      addField: (disabled = false) => {
        const card = document.getElementById(cardId)
        if (!card) throw new Error('card element missing')
        const input = document.createElement('input')
        if (disabled) input.disabled = true
        card.appendChild(input)
        return input
      },
    })
    return () =>
      dialog.value
        ? h('div', { id: cardId }, [
            props.disabledFirst ? h('input', { disabled: true }) : null,
            props.disabledFirst ? h('input', { 'aria-hidden': 'true' }) : null,
            props.disabledFirst ? h('input', { type: 'hidden' }) : null,
            props.immediateField || props.disabledFirst ? h('input') : null,
          ])
        : h('div')
  },
})

async function mountHarness(props: { cardPrefix: string; immediateField?: boolean; disabledFirst?: boolean }) {
  const invoker = document.createElement('button')
  document.body.appendChild(invoker)
  invoker.focus()
  const wrapper = mount(Harness, { props, attachTo: document.body, global: { plugins: [vuetify] } })
  await flushPromises()
  return { wrapper, invoker }
}

const vm = (wrapper: ReturnType<typeof mount>) =>
  wrapper.vm as unknown as HarnessVm

beforeEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useDialogFormFocus eligible controls', () => {
  it('skips disabled, aria-hidden and type=hidden inputs and focuses the first eligible one', async () => {
    const { wrapper } = await mountHarness({ cardPrefix: 'eligible', disabledFirst: true })
    const cardId = vm(wrapper).cardId
    await new Promise((resolve) => setTimeout(resolve, 80))
    const inputs = document.querySelectorAll(`#${cardId} input`)
    expect(inputs.length).toBe(4)
    const eligible = inputs[3]
    expect(document.activeElement).toBe(eligible)
    wrapper.unmount()
  })

  it('focuses a field that arrives after the polling window (structure observer, not a longer timeout)', async () => {
    const { wrapper, invoker } = await mountHarness({ cardPrefix: 'late', immediateField: false })
    // Past the composable's ~200ms polling window, still no fields: only
    // the structure observer (or a not-yet-finished poll) can focus now.
    const cardId = vm(wrapper).cardId
    await new Promise((resolve) => setTimeout(resolve, 260))
    expect(document.querySelectorAll(`#${cardId} input`).length).toBe(0)
    // Nothing has been focused into the still-empty dialog; the invoker
    // keeps focus.
    expect(document.activeElement).toBe(invoker)
    // The form structure lands now; focus must follow.
    vm(wrapper).addField()
    await new Promise((resolve) => setTimeout(resolve, 120))
    const arrived = document.querySelector(`#${cardId} input`)
    expect(document.activeElement).toBe(arrived)
    wrapper.unmount()
  }, 10000)

  it('does not focus a late field when the dialog closed before it arrived', async () => {
    const { wrapper, invoker } = await mountHarness({ cardPrefix: 'closed', immediateField: false })
    await new Promise((resolve) => setTimeout(resolve, 60))
    vm(wrapper).close()
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 60))
    // Focus returned to the invoker on close.
    expect(document.activeElement).toBe(invoker)
    // A late structure response must not steal focus into a closed dialog
    // (its card is gone) nor anywhere else.
    const before = document.activeElement
    expect(() => vm(wrapper).addField()).toThrow('card element missing')
    await new Promise((resolve) => setTimeout(resolve, 120))
    expect(document.activeElement).toBe(before)
    wrapper.unmount()
  }, 10000)

  it('unmount permanently cancels the pending focus; a same-type replacement keeps its own focus', async () => {
    const first = await mountHarness({ cardPrefix: 'replace', immediateField: false })
    const firstCardId = vm(first.wrapper).cardId
    // Still empty when unmounted — its pending focus must die with it
    // (beyond the polling window so the observer, not the poll, is what
    // would have fired).
    await new Promise((resolve) => setTimeout(resolve, 450))
    first.wrapper.unmount()

    const second = await mountHarness({ cardPrefix: 'replace2', immediateField: true })
    await new Promise((resolve) => setTimeout(resolve, 120))
    const secondInput = document.querySelector(`#${vm(second.wrapper).cardId} input`)
    expect(document.activeElement).toBe(secondInput)

    // Simulate the first instance's late structure arriving after its death:
    // a detached card with the (unique) first id gains an input. Nothing may
    // observe it, and focus must stay with the replacement dialog.
    const detached = document.createElement('div')
    detached.id = firstCardId
    const lateInput = document.createElement('input')
    detached.appendChild(lateInput)
    document.body.appendChild(detached)
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(document.activeElement).toBe(secondInput)
    detached.remove()
    second.wrapper.unmount()
  }, 10000)

  it('still returns focus to the invoker on close after a late-arriving field was focused', async () => {
    const { wrapper, invoker } = await mountHarness({ cardPrefix: 'return', immediateField: false })
    vm(wrapper).addField()
    await new Promise((resolve) => setTimeout(resolve, 120))
    expect(document.activeElement).toBe(document.querySelector(`#${vm(wrapper).cardId} input`))
    vm(wrapper).close()
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 60))
    expect(document.activeElement).toBe(invoker)
    wrapper.unmount()
  }, 10000)
})
