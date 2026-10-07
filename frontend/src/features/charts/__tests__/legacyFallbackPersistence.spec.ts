// C5a review round: a user-chosen allocation fallback must survive a failed
// legacy-chunk download AND its retry. Regression for the reviewed defect:
// BreakdownChart used to swap the legacy download-failure alert in place of
// AllocationChart, unmounting it — the fresh instance lost
// `fallbackActive`, so the retry remounted the MODERN chart instead of the
// chosen legacy one. The alert now renders above the branches; this spec
// pins the preserved choice on the real BreakdownChart composition.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import { createPinia } from 'pinia'

// Modern renderer gate: the mocked VChart throws while failMounts is above
// zero, so the test controls exactly when the modern pie is renderable.
const rendererGates = vi.hoisted(() => ({ failMounts: 0 }))
// Legacy leaf gate: its dynamic import rejects while failures is above zero.
const legacyGates = vi.hoisted(() => ({ failures: 0 }))

vi.mock('vue-chartjs', () => ({
  Bar: { name: 'Bar', template: '<div class="bar-stub" />' },
}))
vi.mock('vue-echarts', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: ['option', 'updateOptions', 'autoresize', 'theme'],
      setup() {
        if (rendererGates.failMounts > 0) {
          rendererGates.failMounts -= 1
          throw new Error('Synthetic modern renderer failure')
        }
        return () => h('div', { class: 'echarts-stub' })
      },
    },
  }
})
vi.mock('@/components/charts/LegacyAllocationChart.vue', async () => {
  const { h } = await import('vue')
  if (legacyGates.failures > 0) {
    legacyGates.failures -= 1
    throw new Error('Synthetic legacy chunk failure')
  }
  // DOM-identical to the real leaf against the mocked vue-chartjs Bar.
  return {
    __esModule: true,
    default: {
      name: 'LegacyAllocationChart',
      props: ['data', 'options'],
      render: () => h('div', { class: 'chart-container' }, [h('div', { class: 'bar-stub' })]),
    },
  }
})
vi.mock('@/config/chartConfig', () => ({
  getChartOptions: vi.fn().mockResolvedValue({ barChartOptions: {} }),
  colorPalette: ['#0F4C81', '#5C6B7A'],
}))

import BreakdownChart from '@/components/dashboard/BreakdownChart.vue'
import { allocationFixture } from './fixtures'

const vuetify = createVuetify()

const mountCard = () =>
  mount(BreakdownChart, {
    props: {
      title: 'Asset Type',
      data: { data: { Stocks: '$62.00' }, percentage: { Stocks: '62%' } },
      totalNAV: '$100.00',
      currency: 'USD',
      chartDocument: allocationFixture(),
    },
    global: { plugins: [vuetify, createPinia()] },
  })

const settleUntil = async (wrapper: { find: (selector: string) => { exists: () => boolean } }, selector: string, attempts = 100) => {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 10))
    if (wrapper.find(selector).exists()) return true
  }
  return wrapper.find(selector).exists()
}

beforeEach(() => {
  rendererGates.failMounts = 0
  legacyGates.failures = 0
})

describe('allocation fallback persistence', () => {
  it('keeps the user-chosen fallback across a legacy-chunk failure and its retry', async () => {
    rendererGates.failMounts = 1
    const wrapper = mountCard()
    // The modern renderer is an async component: settle until its failure
    // has actually surfaced (same settling discipline as allocation.spec).
    expect(await settleUntil(wrapper, '[data-testid="allocation-render-error"]')).toBe(true)

    // The user chooses the incumbent chart; its chunk download fails once.
    legacyGates.failures = 1
    await wrapper.find('[data-testid="allocation-render-fallback"]').trigger('click')
    expect(await settleUntil(wrapper, '[data-testid="allocation-legacy-load-error"]')).toBe(true)
    expect(wrapper.find('.bar-stub').exists()).toBe(false)

    // Retry with the modern renderer disarmed: if the choice had been lost,
    // this would remount a WORKING modern chart instead of the legacy bars.
    rendererGates.failMounts = 0
    await wrapper.find('[data-testid="allocation-legacy-load-retry"]').trigger('click')
    expect(await settleUntil(wrapper, '.bar-stub')).toBe(true)
    expect(wrapper.find('.echarts-stub').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocation-render-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocation-legacy-load-error"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
