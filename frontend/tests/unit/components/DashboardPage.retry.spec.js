import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DashboardPage from '@/views/DashboardPage.vue'
import { generateVuetifyStubs } from '../test-utils'

// All dashboard services reject so every widget renders its error alert.
const mocks = vi.hoisted(() => ({
  getDashboardSummary: vi.fn().mockRejectedValue(new Error('summary failed')),
  getDashboardBreakdown: vi
    .fn()
    .mockRejectedValue(new Error('breakdown failed')),
  getDashboardSummaryOverTime: vi
    .fn()
    .mockRejectedValue(new Error('summary over time failed')),
  getNAVChartData: vi.fn().mockRejectedValue(new Error('nav chart failed')),
}))

vi.mock('@/services/api', () => mocks)

// Store fetches (effective date) would also hit the api mock; patch them out.
vi.mock('@/stores/app', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useAppStore: () => ({
      ...actual.useAppStore(),
      fetchEffectiveCurrentDate: vi.fn().mockResolvedValue(undefined),
      updateNavChartParams: vi.fn().mockResolvedValue(undefined),
      updateUserDataForNewAccount: vi.fn().mockResolvedValue(undefined),
    }),
  }
})

const mountPage = () =>
  mount(DashboardPage, {
    global: {
      stubs: {
        ...generateVuetifyStubs(),
        'v-skeleton-loader': true,
        SummaryCard: true,
        BreakdownChart: true,
        SummaryOverTimeTable: true,
        NAVChart: true,
      },
      provide: {
        clearErrors: () => {},
        showError: () => {},
      },
    },
  })

const retryButtons = (wrapper) =>
  wrapper.findAll('.v-btn').filter((b) => b.text().includes('Retry'))

describe('DashboardPage widget error retry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('renders a Retry button in every widget error alert', async () => {
    const wrapper = mountPage()
    await flushPromises()

    // summary, breakdown charts (x3 — one alert per chart), summary over
    // time, nav chart
    expect(wrapper.text()).toContain('summary failed')
    expect(wrapper.text()).toContain('breakdown failed')
    expect(wrapper.text()).toContain('summary over time failed')
    expect(wrapper.text()).toContain('nav chart failed')
    expect(retryButtons(wrapper).length).toBe(6)
  })

  it('re-invokes the matching fetch when Retry is clicked', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(mocks.getDashboardSummary).toHaveBeenCalledTimes(1)
    expect(mocks.getDashboardBreakdown).toHaveBeenCalledTimes(1)
    expect(mocks.getDashboardSummaryOverTime).toHaveBeenCalledTimes(1)
    expect(mocks.getNAVChartData).toHaveBeenCalledTimes(1)

    // Buttons render in template order: summary, breakdown x3, sot, nav.
    // Click one Retry per widget service.
    const buttons = retryButtons(wrapper)
    for (const idx of [0, 1, 4, 5]) {
      await buttons[idx].trigger('click')
    }
    await flushPromises()

    expect(mocks.getDashboardSummary).toHaveBeenCalledTimes(2)
    expect(mocks.getDashboardBreakdown).toHaveBeenCalledTimes(2)
    expect(mocks.getDashboardSummaryOverTime).toHaveBeenCalledTimes(2)
    expect(mocks.getNAVChartData).toHaveBeenCalledTimes(2)
  })
})
