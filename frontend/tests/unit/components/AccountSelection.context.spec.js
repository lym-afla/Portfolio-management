import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import AccountSelection from '@/components/AccountSelection.vue'
import { usePortfolioContextStore } from '@/stores/portfolioContext'
import { configurePortfolioContextBackend } from '@/services/api/context'
import { ApiError } from '@/services/http/errors'
vi.mock('@/services/api', () => ({
  getAccountChoices: vi.fn(async () => ({
    options: [
      ['One', { type: 'account', id: 1, display_name: 'Account One' }],
      ['Two', { type: 'account', id: 2, display_name: 'Account Two' }],
    ],
    selected: { type: 'account', id: 1 },
  })),
}))
vi.mock('@/services/http/client', () => ({
  apiGet: vi.fn(async (url) =>
    url.includes('get_account_choices')
      ? {
          options: [
            ['One', { type: 'account', id: 1, display_name: 'Account One' }],
            ['Two', { type: 'account', id: 2, display_name: 'Account Two' }],
          ],
        }
      : { choices: { default_currency: [['USD', 'Dollar']] } }
  ),
}))
const Select = defineComponent({
  props: ['modelValue', 'items', 'disabled'],
  emits: ['update:modelValue'],
  template:
    '<button :disabled="disabled" @click="$emit(\'update:modelValue\', { type: \'account\', id: 2 })">{{ items.find(i => i.value?.id === modelValue?.id)?.title }}</button>',
})
beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})
it('keeps the rendered committed label while pending and after failure', async () => {
  let reject
  configurePortfolioContextBackend({
    read: vi.fn(async () => ({
      accountSelection: { type: 'account', id: 1 },
      effectiveCurrentDate: '2026-09-08',
      currency: 'USD',
      digits: 2,
    })),
    updateAccount: () =>
      new Promise((_r, no) => {
        reject = no
      }),
    updateSettings: vi.fn(),
  })
  const store = usePortfolioContextStore()
  await store.reconcileContext()
  const wrapper = mount(AccountSelection, {
    global: {
      stubs: {
        VSelect: Select,
        VCard: { template: '<div><slot /></div>' },
        VCardText: { template: '<div><slot /></div>' },
        VBtn: true,
        VIcon: true,
        VAlert: { template: '<div><slot /></div>' },
      },
    },
  })
  await flushPromises()
  await wrapper.find('button').trigger('click')
  await flushPromises()
  expect(wrapper.find('button').text()).toBe('Account One')
  expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  reject(new ApiError('Account denied', 400, 'context_mutation_rejected'))
  await flushPromises()
  expect(wrapper.find('button').text()).toBe('Account One')
  expect(wrapper.text()).toContain('Account denied')
  wrapper.unmount()
})
