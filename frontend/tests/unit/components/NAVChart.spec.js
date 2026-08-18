import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import { createPinia } from 'pinia'
import NAVChart from '@/components/dashboard/NAVChart.vue'

const vuetify = createVuetify()

const mountNAVChart = (chartData) =>
  mount(NAVChart, {
    global: {
      plugins: [vuetify, createPinia()],
      stubs: {
        StackedBarLineChart: { template: '<div class="chart-stub" />' },
        DateRangeSelector: { template: '<div class="date-range-stub" />' },
      },
    },
    props: {
      chartData,
      initialParams: {},
      effectiveCurrentDate: '2026-08-18',
    },
  })

describe('NAVChart', () => {
  it('treats an all-zero but non-empty series as data (no "No data" alert)', () => {
    const wrapper = mountNAVChart({
      labels: ['2026-01-01', '2026-01-02'],
      datasets: [{ label: 'NAV', type: 'line', data: [0, 0] }],
    })
    expect(wrapper.find('.chart-wrapper').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('No data available')
  })

  it('shows the no-data alert when series have no points', () => {
    const wrapper = mountNAVChart({
      labels: [],
      datasets: [{ label: 'NAV', type: 'line', data: [] }],
    })
    const alert = wrapper.find('v-alert, .v-alert')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('text')).toBe('No data available')
    expect(wrapper.find('.chart-wrapper').exists()).toBe(false)
  })

  it('renders readable frequency toggle labels and aria-label', () => {
    const wrapper = mountNAVChart({
      labels: ['2026-01-01'],
      datasets: [{ label: 'NAV', type: 'line', data: [1] }],
    })
    const text = wrapper.text()
    for (const word of ['Day', 'Week', 'Month', 'Quarter', 'Year']) {
      expect(text).toContain(word)
    }
    const toggle = wrapper.find('[aria-label="Chart frequency"]')
    expect(toggle.exists()).toBe(true)
  })
})
