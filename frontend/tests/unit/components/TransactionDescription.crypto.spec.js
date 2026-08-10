import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import TransactionDescription from '@/components/transactions/TransactionDescription.vue'

// TransactionDescription now reads the user's `digits` preference via the auth
// store, so each test needs an active Pinia instance. We install a fresh pinia
// per test and seed the auth store's user with a `digits` value.

// Shared stubs: render SecurityLink/CommissionDisplay by their distinguishing
// prop text so assertions can detect their presence.
const globalStubs = {
  SecurityLink: {
    props: ['name'],
    template: '<span>{{ name }}</span>',
  },
  CommissionDisplay: {
    props: ['commission'],
    template: '<span data-commission>{{ commission }}</span>',
  },
}

async function seedDigits(digits) {
  const { useAuthStore } = await import('@/stores/auth')
  const authStore = useAuthStore()
  authStore.user = { digits }
  return authStore
}

describe('TransactionDescription crypto events', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('describes crypto rewards as native rewards', async () => {
    await seedDigits(2)

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
      global: { stubs: globalStubs },
    })

    expect(wrapper.text()).toContain('Crypto reward of 0.01 BTC')
    // Price is present and not the '–' sentinel, so it should be formatted too.
    expect(wrapper.text()).not.toContain('50000.000000000')
  })

  it('renders a crypto trade in with a security link and formatted @price of', async () => {
    // Stablecoin-quote spot trade (e.g. TRUMP/USDT). Must render with a
    // security link + @price, matching the regular Buy/Sell pattern — NOT the
    // bare "type quantity ticker @price" crypto-event format.
    await seedDigits(4)

    const wrapper = mount(TransactionDescription, {
      props: {
        transaction: {
          type: 'Crypto trade in',
          quantity: '0.680300000',
          price: '73.209000000',
          security: {
            id: 42,
            name: 'TRUMP',
            ticker: 'TRUMP',
          },
        },
      },
      global: { stubs: globalStubs },
    })

    const text = wrapper.text()
    // Type label is mapped to the conventional 'Buy' for display (the stored
    // type stays 'Crypto trade in' for calc-layer correctness).
    expect(text).toContain('Buy')
    expect(text).not.toContain('Crypto trade in')
    // Quantity formatted via the adaptive rule (sub-1 -> first significant
    // digit only, so 0.6803 -> "0.7"); price >= 1 uses fixed digits=4.
    expect(text).toContain('0.7')
    expect(text).toContain('@73.2090 of')
    // Security link renders the asset name (not the bare ticker before @price).
    expect(text).toContain('TRUMP')
  })

  it('renders a crypto trade out with commission when present', async () => {
    await seedDigits(4)

    const wrapper = mount(TransactionDescription, {
      props: {
        transaction: {
          type: 'Crypto trade out',
          quantity: '-0.680300000',
          price: '73.209000000',
          commission: '-0.0006803',
          security: {
            id: 42,
            name: 'TRUMP',
            ticker: 'TRUMP',
          },
        },
      },
      global: { stubs: globalStubs },
    })

    const text = wrapper.text()
    // Type label mapped to 'Sell' for display.
    expect(text).toContain('Sell')
    expect(text).not.toContain('Crypto trade out')
    expect(text).toContain('@73.2090 of')
    expect(text).toContain('TRUMP')
    // Commission-display renders when commission is set.
    expect(text).toContain('-0.0006803')
  })

  it('keeps the simpler format for crypto transfers (no security link / @price of)', async () => {
    // Transfers (and rewards/settlements) are not trades: they keep the
    // "type quantity ticker @price" format without the "of <security-link>".
    await seedDigits(4)

    const wrapper = mount(TransactionDescription, {
      props: {
        transaction: {
          type: 'Crypto transfer in',
          quantity: '250.123456789',
          price: '1',
          security: {
            id: 7,
            name: 'Tether',
            ticker: 'USDT',
          },
        },
      },
      global: { stubs: globalStubs },
    })

    const text = wrapper.text()
    expect(text).toContain('Crypto transfer in')
    // Ticker renders inline (simpler format).
    expect(text).toContain('USDT')
    // The trade-only " of" separator must NOT appear for transfers.
    expect(text).not.toContain('of Tether')
    // Transfers have no meaningful price -> suppress @price (finding #6).
    expect(text).not.toContain('@')
  })
})
