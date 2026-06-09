import { mount } from '@vue/test-utils'
import TransactionDescription from '@/components/transactions/TransactionDescription.vue'

describe('TransactionDescription crypto events', () => {
  it('describes crypto rewards as native rewards', () => {
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

    expect(wrapper.text()).toContain('Crypto reward of 0.010000000 BTC')
    expect(wrapper.text()).not.toContain('@50000.000000000')
  })
})
