import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import TransactionDescription from '@/components/transactions/TransactionDescription.vue'

// TransactionDescription now reads the user's `digits` preference via the auth
// store, so each test needs an active Pinia instance. We install a fresh pinia
// per test and seed the auth store's user with a `digits` value.

describe('TransactionDescription crypto events', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('describes crypto rewards as native rewards', async () => {
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    // digits=2 means quantity 0.010000000 formats to "0.01".
    authStore.user = { digits: 2 }

    const wrapper = mount(TransactionDescription, {
      props: {
        transaction: {
          type: 'Crypto reward',
          quantity: '0.010000000',
          price: '50000.000000000',
          security: {
            id: 1,
            name: 'Bitcoin',
            ticker: 'BTC',
          },
        },
      },
      global: {
        stubs: {
          SecurityLink: {
            props: ['name'],
            template: '<span>{{ name }}</span>',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('Crypto reward of 0.01 BTC')
    // Price is present and not the '–' sentinel, so it should be formatted too.
    expect(wrapper.text()).not.toContain('50000.000000000')
  })
})
