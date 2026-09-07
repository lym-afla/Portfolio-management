import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { mount } from '@vue/test-utils'
import SummaryCard from '@/components/dashboard/SummaryCard.vue'
import { createVuetify } from 'vuetify'
import { createPinia } from 'pinia'

const vuetify = createVuetify()

describe('SummaryCard', () => {
  it('formats multi-underscore keys fully humanized', () => {
    const wrapper = mount(SummaryCard, {
      global: { plugins: [vuetify, createPinia()] },
      props: { summary: { beginning_of_period_nav: 1, irr: 2 } },
    })
    expect(wrapper.text()).toContain('Beginning of period NAV')
    expect(wrapper.text()).toContain('IRR')
  })

  it('does not use the Vuetify 2 variable or a side-tab border', () => {
    // Source-level assertion on purpose: the CSS-variable failure is
    // invisible at runtime (the compiled component does not carry the
    // style block, so read the SFC source directly).
    const src = readFileSync(
      'src/components/dashboard/SummaryCard.vue',
      'utf-8'
    )
    expect(src).not.toContain('--v-primary-base')
    expect(src).not.toContain('border-left')
  })
})
