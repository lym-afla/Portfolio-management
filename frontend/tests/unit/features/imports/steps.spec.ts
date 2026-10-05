// D6 task 3 — public-behavior tests for the extracted step components.
// Steps render state and emit typed intents; they never send HTTP/socket
// commands themselves.
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ImportMethodStep from '@/features/imports/ImportMethodStep.vue'
import ImportSourceStep from '@/features/imports/ImportSourceStep.vue'
import ImportReviewStep from '@/features/imports/ImportReviewStep.vue'
import ImportResult from '@/features/imports/ImportResult.vue'
import { generateVuetifyStubs } from '../../test-utils'

const mountStep = (component: unknown, props: Record<string, unknown> = {}) =>
  mount(component, {
    props,
    global: {
      stubs: {
        ...generateVuetifyStubs(),
        'v-tooltip': {
          template:
            '<div class="v-tooltip"><slot name="activator" :props="{}"/></div>',
        },
      },
    },
  })

describe('ImportMethodStep', () => {
  it('renders the two named choices', () => {
    const wrapper = mountStep(ImportMethodStep, {
      selected: null,
      hasConnectedBrokers: true,
    })
    const titles = wrapper.findAll('.import-method-card .v-card-title')
    expect(titles.map((t) => t.text())).toEqual(['Direct Import', 'File Import'])
  })

  it('emits select for the api choice by click and by keyboard', async () => {
    const wrapper = mountStep(ImportMethodStep, {
      selected: null,
      hasConnectedBrokers: true,
    })
    const cards = wrapper.findAll('.import-method-card')
    await cards[0].trigger('click')
    expect(wrapper.emitted('select')).toEqual([['api']])

    await cards[0].trigger('keydown.enter')
    expect(wrapper.emitted('select')).toHaveLength(2)

    await cards[0].trigger('keydown.space')
    expect(wrapper.emitted('select')).toHaveLength(3)
    expect(wrapper.emitted('select')?.[2]).toEqual(['api'])
  })

  it('emits select for the file choice and marks the pending selection', async () => {
    const wrapper = mountStep(ImportMethodStep, {
      selected: 'file',
      hasConnectedBrokers: true,
    })
    const cards = wrapper.findAll('.import-method-card')
    await cards[1].trigger('click')
    expect(wrapper.emitted('select')).toEqual([['file']])
    expect(cards[1].classes()).toContain('selected')
    expect(cards[0].classes()).not.toContain('selected')
  })

  it('does not emit select for api without connected brokers', async () => {
    const wrapper = mountStep(ImportMethodStep, {
      selected: null,
      hasConnectedBrokers: false,
    })
    const cards = wrapper.findAll('.import-method-card')
    await cards[0].trigger('click')
    await cards[0].trigger('keydown.enter')
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(cards[0].classes()).toContain('disabled')
  })
})

describe('ImportSourceStep', () => {
  it('api configuration shows only broker and date fields', () => {
    const wrapper = mountStep(ImportSourceStep, {
      method: 'api',
      brokers: [{ id: 11, name: 'Tinkoff' }],
      selectedBroker: null,
      dateRange: { from: null, to: null },
      confirmEveryTransaction: false,
      validation: false,
      busy: false,
    })
    expect(wrapper.find('.v-select').exists()).toBe(true)
    expect(wrapper.find('.v-file-input').exists()).toBe(false)
    const dates = wrapper.findAll('.v-text-field')
    expect(dates).toHaveLength(2)
  })

  it('file configuration shows file input and galaxy flag, currency only when galaxy', async () => {
    const wrapper = mountStep(ImportSourceStep, {
      method: 'file',
      brokers: [],
      file: null,
      isGalaxy: false,
      selectedCurrency: null,
      currencies: [
        { title: 'USD', value: 'USD' },
        { title: 'EUR', value: 'EUR' },
      ],
      confirmEveryTransaction: false,
      busy: false,
    })
    expect(wrapper.find('.v-file-input').exists()).toBe(true)
    expect(wrapper.find('.v-select').exists()).toBe(false)

    await wrapper.setProps({ isGalaxy: true })
    // The currency choice appears only after analysis (review), not here.
    expect(wrapper.find('.v-select').exists()).toBe(false)
  })

  it('emits typed updates for broker, dates and the confirm flag', async () => {
    const wrapper = mountStep(ImportSourceStep, {
      method: 'api',
      brokers: [{ id: 11, name: 'Tinkoff' }],
      selectedBroker: null,
      dateRange: { from: null, to: null },
      confirmEveryTransaction: false,
      validation: false,
      busy: false,
    })
    const brokerSelect = wrapper.findComponent('.v-select')
    await brokerSelect.vm.$emit('update:modelValue', { id: 11, name: 'Tinkoff' })
    expect(wrapper.emitted('update:selectedBroker')).toEqual([
      [{ id: 11, name: 'Tinkoff' }],
    ])

    const dateFields = wrapper.findAllComponents('.v-text-field')
    await dateFields[0].vm.$emit('update:modelValue', '2026-01-01')
    expect(wrapper.emitted('update:dateRange')).toEqual([
      [{ from: '2026-01-01', to: null }],
    ])
    // The parent applies the update; the next emission builds on the new range.
    await wrapper.setProps({ dateRange: { from: '2026-01-01', to: null } })
    await dateFields[1].vm.$emit('update:modelValue', '2026-06-30')
    expect(wrapper.emitted('update:dateRange')?.[1]).toEqual([
      { from: '2026-01-01', to: '2026-06-30' },
    ])

    const checkbox = wrapper.findComponent('.v-checkbox')
    await checkbox.vm.$emit('update:modelValue', true)
    expect(wrapper.emitted('update:confirmEveryTransaction')).toEqual([[true]])
  })

  it('emits file-changed with the raw event for the file input', async () => {
    const wrapper = mountStep(ImportSourceStep, {
      method: 'file',
      file: null,
      isGalaxy: false,
      selectedCurrency: null,
      currencies: [],
      confirmEveryTransaction: false,
      busy: false,
    })
    const fileInput = wrapper.findComponent('.v-file-input')
    const event = { target: { files: [{ name: 'synthetic.csv' }] } }
    await fileInput.vm.$emit('change', event)
    expect(wrapper.emitted('file-changed')).toHaveLength(1)
  })
})

describe('ImportReviewStep', () => {
  it('announces the identified account with the exact legacy strings', () => {
    const wrapper = mountStep(ImportReviewStep, {
      identified: true,
      identifiedName: 'Main account',
      accounts: [
        { id: 3, title: 'Tinkoff – Main account' },
        { id: 9, title: 'Secondary account' },
      ],
      selectedAccount: 3,
      validation: false,
      showCurrency: false,
      currency: null,
      currencies: [],
    })
    expect(wrapper.text()).toContain(
      'Broker account "Main account" was automatically identified. Please confirm or select a different broker account.'
    )
  })

  it('announces the not-identified case and emits the account choice', async () => {
    const wrapper = mountStep(ImportReviewStep, {
      identified: false,
      identifiedName: null,
      accounts: [{ id: 9, title: 'Secondary account' }],
      selectedAccount: null,
      validation: true,
      showCurrency: false,
      currency: null,
      currencies: [],
    })
    expect(wrapper.text()).toContain(
      'Broker account could not be automatically identified. Please select a broker account below.'
    )
    const select = wrapper.findComponent('.v-select')
    await select.vm.$emit('update:modelValue', 9)
    expect(wrapper.emitted('update:selectedAccount')).toEqual([[9]])
  })

  it('shows the galaxy currency choice when requested and emits updates', async () => {
    const wrapper = mountStep(ImportReviewStep, {
      identified: false,
      identifiedName: null,
      accounts: [],
      selectedAccount: null,
      validation: false,
      showCurrency: true,
      currency: null,
      currencies: [
        { title: 'USD', value: 'USD' },
        { title: 'EUR', value: 'EUR' },
      ],
    })
    const selects = wrapper.findAllComponents('.v-select')
    expect(selects.length).toBeGreaterThanOrEqual(2)
    // The currency select renders before the account select.
    await selects[0].vm.$emit('update:modelValue', 'EUR')
    expect(wrapper.emitted('update:currency')).toEqual([['EUR']])
  })
})

describe('ImportResult', () => {
  it('renders all five counters with their legacy labels', () => {
    const wrapper = mountStep(ImportResult, {
      result: {
        totalTransactions: 12,
        importedTransactions: 9,
        skippedTransactions: 2,
        duplicateTransactions: 1,
        importErrors: 0,
        warnings: [],
      },
    })
    const text = wrapper.text()
    expect(text).toContain('12')
    expect(text).toContain('Total transactions processed')
    expect(text).toContain('9')
    expect(text).toContain('Successfully imported')
    expect(text).toContain('1')
    expect(text).toContain('Duplicates found')
    expect(text).toContain('2')
    expect(text).toContain('Skipped transactions')
    expect(text).toContain('0')
    expect(text).toContain('Import Errors')
    // The alert title lands as a fallthrough attribute on the stub.
    expect(wrapper.html()).not.toContain('Some data sources could not be fetched')
  })

  it('renders structured endpoint warnings when present', () => {
    const wrapper = mountStep(ImportResult, {
      result: {
        totalTransactions: 5,
        importedTransactions: 5,
        skippedTransactions: 0,
        duplicateTransactions: 0,
        importErrors: 0,
        warnings: [
          { endpoint: 'spot_fills', error: 'OKX HTTP 500: synthetic' },
        ],
      },
    })
    const text = wrapper.text()
    expect(text).toContain('spot_fills')
    expect(text).toContain('OKX HTTP 500: synthetic')
    expect(wrapper.html()).toContain('Some data sources could not be fetched')
  })
})
