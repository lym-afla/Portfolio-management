// D4 Task 4 — WorkspaceActions renders the primary/secondary/overflow
// hierarchy with keyboard-reachable controls and emits exact action ids.
import { beforeAll, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import WorkspaceActions from '@/components/workspace/WorkspaceActions.vue'
import type { WorkspaceAction } from '@/components/workspace/types'

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

const vuetify = createVuetify({ components, directives })

const primary: WorkspaceAction = { id: 'add-transaction', label: 'Add transaction', icon: 'mdi-plus' }
const secondary: WorkspaceAction[] = [
  { id: 'import-transactions', label: 'Import transactions', icon: 'mdi-upload' },
]
const overflow: WorkspaceAction[] = [
  { id: 'add-fx-transaction', label: 'Add FX transaction' },
  { id: 'transfer-asset', label: 'Transfer asset' },
  { id: 'record-merger', label: 'Record merger' },
]

const mountActions = () =>
  mount(WorkspaceActions, {
    attachTo: document.body,
    global: { plugins: [vuetify] },
    props: { primary, secondary, overflow },
  })

describe('WorkspaceActions', () => {
  it('renders the primary and secondary actions as focusable labelled buttons', () => {
    const wrapper = mountActions()
    const buttons = [...wrapper.element.querySelectorAll('button')]
    const add = buttons.find((button) => button.textContent?.includes('Add transaction'))
    const importBtn = buttons.find((button) => button.textContent?.includes('Import transactions'))
    expect(add).toBeTruthy()
    expect(importBtn).toBeTruthy()
    expect(wrapper.element.querySelector('[data-action="add-transaction"]')).toBeTruthy()
    expect(wrapper.element.querySelector('[data-action="import-transactions"]')).toBeTruthy()
    wrapper.unmount()
  })

  it('emits the exact primary and secondary action ids', async () => {
    const wrapper = mountActions()
    await wrapper.find('[data-action="add-transaction"]').trigger('click')
    await wrapper.find('[data-action="import-transactions"]').trigger('click')
    expect(wrapper.emitted('action')).toEqual([
      ['add-transaction'], ['import-transactions'],
    ])
    wrapper.unmount()
  })

  it('exposes overflow actions behind a labelled keyboard-focusable menu control', async () => {
    const wrapper = mountActions()
    const activator = wrapper.element.querySelector('button[aria-label="More actions"]') as HTMLButtonElement
    expect(activator).toBeTruthy()
    activator.click()
    await new Promise((resolve) => setTimeout(resolve, 50))
    const items = [...document.querySelectorAll('.v-overlay--active [data-action]')]
    expect(items.map((item) => item.getAttribute('data-action'))).toEqual([
      'add-fx-transaction', 'transfer-asset', 'record-merger',
    ])
    ;(items[0] as HTMLElement).click()
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(wrapper.emitted('action')).toEqual([['add-fx-transaction']])
    wrapper.unmount()
  })

  it('omits empty tiers entirely', () => {
    const wrapper = mount(WorkspaceActions, {
      global: { plugins: [vuetify] },
      props: { primary, secondary: [], overflow: [] },
    })
    expect(wrapper.element.querySelectorAll('button').length).toBe(1)
    expect(wrapper.element.querySelector('button[aria-label="More actions"]')).toBeNull()
    wrapper.unmount()
  })
})
