// Account selector label regressions, driven through the REAL Vuetify
// VSelect (no label-simplifying stub): the committed selection must always
// render a safe label — the matching option title, "All accounts" for the
// all selection, "Unavailable" for an unmatched specific selection — never
// Vuetify's raw [object Object] fallback. The fixtures mirror the backend's
// prepare_account_choices structure exactly (General/Your Accounts/Brokers/
// Account Groups sections with __SEPARATOR__ rows).
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { createPinia, setActivePinia } from 'pinia'

import AccountSelection from '@/components/AccountSelection.vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { configurePortfolioContextBackend } from '@/services/api/context'
import { ApiError } from '@/services/http/errors'
import { apiGet } from '@/services/http/client'

// Backend-faithful prepare_account_choices output (users/core/user_utils.py).
export const BACKEND_ACCOUNT_OPTIONS = [
  ['General', [['All accounts', { type: 'all', id: null }]]],
  ['__SEPARATOR__', '__SEPARATOR__'],
  [
    'Your Accounts',
    [
      ['First', { type: 'account', id: 1, display_name: 'First Broker – First account' }],
      ['Second', { type: 'account', id: 2, display_name: 'Second Broker – Second account' }],
    ],
  ],
  ['__SEPARATOR__', '__SEPARATOR__'],
  ['Brokers', [['First Broker', { type: 'broker', id: 3, display_name: 'All First Broker accounts' }]]],
  ['__SEPARATOR__', '__SEPARATOR__'],
  ['Account Groups', [['Long Term', { type: 'group', id: 4, display_name: 'Long Term' }]]],
]

let accountChoices = { options: BACKEND_ACCOUNT_OPTIONS, selected: { type: 'all', id: null } }

vi.mock('@/services/http/client', () => ({
  apiGet: vi.fn(async (url) => {
    if (url.includes('get_account_choices')) return accountChoices
    if (url.includes('dashboard_settings')) {
      return { choices: { default_currency: [['USD', 'US Dollar']] } }
    }
    return {}
  }),
  apiPost: vi.fn(async () => ({})),
}))

const vuetify = createVuetify({ components, directives })

// jsdom has no visualViewport; Vuetify's overlay location strategy needs it.
beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

beforeEach(() => {
  accountChoices = { options: BACKEND_ACCOUNT_OPTIONS, selected: { type: 'all', id: null } }
  setActivePinia(createPinia())
})

const backend = (accountSelection) => {
  // The store confirms context mutations by readback: a successful
  // updateAccount must be reflected by the next read(), like the real backend.
  const state = { current: { ...accountSelection } }
  return {
    state,
    read: vi.fn(async () => ({
      accountSelection: { ...state.current },
      effectiveCurrentDate: '2026-09-08',
      currency: 'USD',
      digits: 2,
    })),
    updateAccount: vi.fn(async (selection) => {
      state.current = { type: selection.type, id: selection.id }
    }),
    updateSettings: vi.fn(async () => {}),
  }
}

const mountSelector = async (accountSelection) => {
  const mockBackend = backend(accountSelection)
  configurePortfolioContextBackend(mockBackend)
  const store = usePortfolioContextStore()
  await store.reconcileContext()
  const wrapper = mount(AccountSelection, {
    global: { plugins: [vuetify, store.$pinia] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, store, mockBackend }
}

const displayedLabel = (wrapper) => {
  const text = wrapper.find('.v-select__selection').text()
  return { text, empty: text.trim().length === 0 }
}

const selectComponent = (wrapper) => wrapper.findComponent({ name: 'VSelect' })

const expectNoRawObject = (wrapper, context) => {
  expect(wrapper.text(), `${context}: no raw object label`).not.toContain('[object Object]')
  expect(wrapper.text(), `${context}: no raw JSON label`).not.toContain('"type"')
}

describe('AccountSelection safe label fallbacks (real Vuetify select)', () => {
  it('renders All accounts for the all selection with full backend options', async () => {
    const { wrapper } = await mountSelector({ type: 'all', id: null })
    expect(displayedLabel(wrapper).text).toBe('All accounts')
    expectNoRawObject(wrapper, 'all selection')
    wrapper.unmount()
  })

  it('renders the display_name of a committed named account', async () => {
    const { wrapper } = await mountSelector({ type: 'account', id: 2 })
    expect(displayedLabel(wrapper).text).toBe('Second Broker – Second account')
    expectNoRawObject(wrapper, 'named account')
    wrapper.unmount()
  })

  it('renders broker and group option titles', async () => {
    const { wrapper } = await mountSelector({ type: 'broker', id: 3 })
    expect(displayedLabel(wrapper).text).toBe('All First Broker accounts')
    expectNoRawObject(wrapper, 'broker selection')
    wrapper.unmount()
    const { wrapper: groupWrapper } = await mountSelector({ type: 'group', id: 4 })
    expect(displayedLabel(groupWrapper).text).toBe('Long Term')
    expectNoRawObject(groupWrapper, 'group selection')
    groupWrapper.unmount()
  })

  it('falls back to All accounts when the options list is empty', async () => {
    accountChoices = { options: [], selected: { type: 'all', id: null } }
    const requestsBefore = vi.mocked(apiGet).mock.calls.length
    const { wrapper } = await mountSelector({ type: 'all', id: null })
    expect(displayedLabel(wrapper).text).toBe('All accounts')
    expectNoRawObject(wrapper, 'empty options, all selection')
    await flushPromises()
    expect(vi.mocked(apiGet).mock.calls.length).toBe(requestsBefore + 2,
      'mounting and labelling adds no repair requests beyond the reconcile pair')
    wrapper.unmount()
  })

  it('falls back to Unavailable for a committed account missing from the options', async () => {
    accountChoices = { options: [], selected: { type: 'account', id: 7 } }
    const { wrapper } = await mountSelector({ type: 'account', id: 7 })
    expect(displayedLabel(wrapper).text).toBe('Unavailable')
    expectNoRawObject(wrapper, 'missing committed account')
    wrapper.unmount()
  })

  it('keeps a safe label before and after delayed option loading', async () => {
    accountChoices = { options: [], selected: { type: 'account', id: 1 } }
    localStorage.setItem('accountSelection', JSON.stringify({ type: 'account', id: 1 }))
    configurePortfolioContextBackend(backend({ type: 'account', id: 1 }))
    const store = usePortfolioContextStore()
    const wrapper = mount(AccountSelection, {
      global: { plugins: [vuetify, store.$pinia] },
      attachTo: document.body,
    })
    await flushPromises()
    // Pre-reconcile: committed cached selection, no options loaded yet.
    expect(displayedLabel(wrapper).text).toBe('Unavailable')
    expectNoRawObject(wrapper, 'delayed loading, before options')
    // Options arrive late (the reconcile that succeeds after the mount).
    accountChoices = { options: BACKEND_ACCOUNT_OPTIONS, selected: { type: 'account', id: 1 } }
    await store.reconcileContext()
    await flushPromises()
    expect(displayedLabel(wrapper).text).toBe('First Broker – First account')
    expect(store.committed.accountSelection).toEqual({ type: 'account', id: 1 })
    expectNoRawObject(wrapper, 'delayed loading, after options')
    wrapper.unmount()
  })

  it('keeps the committed label after a failed context change and never adopts the failed target', async () => {
    const { wrapper, store, mockBackend } = await mountSelector({ type: 'all', id: null })
    mockBackend.updateAccount = vi.fn(async () => {
      throw new ApiError('Account denied', 400, 'context_mutation_rejected')
    })
    configurePortfolioContextBackend(mockBackend)
    selectComponent(wrapper).vm.$emit('update:modelValue', {
      type: 'account', id: 2, display_name: 'Second Broker – Second account',
    })
    await flushPromises()
    expect(mockBackend.updateAccount).toHaveBeenCalledOnce()
    expect(store.committed.accountSelection).toEqual({ type: 'all', id: null },
      'a rejected change never adopts the failed selection')
    expect(displayedLabel(wrapper).text).toBe('All accounts')
    expect(wrapper.text()).toContain('Account denied')
    expectNoRawObject(wrapper, 'failed context change')
    wrapper.unmount()
  })

  it('changes the committed selection and label through a successful select interaction', async () => {
    const { wrapper, store } = await mountSelector({ type: 'all', id: null })
    selectComponent(wrapper).vm.$emit('update:modelValue', {
      type: 'account', id: 2, display_name: 'Second Broker – Second account',
    })
    await flushPromises()
    expect(store.committed.accountSelection).toEqual({ type: 'account', id: 2 })
    expect(displayedLabel(wrapper).text).toBe('Second Broker – Second account')
    expectNoRawObject(wrapper, 'successful change')
    wrapper.unmount()
  })
})
