import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PortfolioMetrics from '@/components/dashboard/PortfolioMetrics.vue'
import { summaryMetrics } from '@/components/dashboard/summaryMetrics'
import { decodeDashboardSummary } from '@/services/api/dashboard'

// Fixtures pass through the real API decoder so branded display types are
// honored instead of being cast away in test setup.
const populatedSummary = decodeDashboardSummary({
  'Current NAV': '$0.00',
  Invested: '$100.00',
  'Cash-out': '($100.00)',
  total_return: '−2.40%',
  irr: 'N/A',
})

describe('summaryMetrics display adapter', () => {
  it('maps every actual summary key to the five explicit metric ids in order', () => {
    expect(summaryMetrics(populatedSummary).map((metric) => metric.id)).toEqual([
      'nav',
      'invested',
      'cash-out',
      'total-return',
      'irr',
    ])
  })

  it('uses domain labels and preserves the lifetime horizon meaning', () => {
    const metrics = summaryMetrics(populatedSummary)
    expect(metrics.map((metric) => metric.label)).toEqual([
      'Total NAV',
      'Invested',
      'Cash out',
      'Total return',
      'IRR since inception',
    ])
    expect(metrics.find((metric) => metric.id === 'total-return')?.explanation).toBe('Since inception')
    expect(metrics.find((metric) => metric.id === 'irr')?.explanation).toBeUndefined()
  })

  it('keeps zero, negative, signed and unavailable display strings verbatim', () => {
    const values = summaryMetrics(populatedSummary).map((metric) => metric.value)
    expect(values).toEqual(['$0.00', '$100.00', '($100.00)', '−2.40%', 'N/A'])
  })

  it('maps null fields to the established unavailable marker instead of a blank', () => {
    const metrics = summaryMetrics(
      decodeDashboardSummary({
        'Current NAV': '$1.00',
        Invested: null,
        'Cash-out': 'N/R',
        total_return: null,
        irr: 'N/R',
      })
    )
    const wrapper = mount(PortfolioMetrics, {
      props: { contextLabel: 'All accounts · 2026-10-01 · USD', metrics },
    })
    expect(wrapper.get('[data-metric="invested"] dd').text()).toBe('N/R')
    expect(wrapper.get('[data-metric="cash-out"] dd').text()).toBe('N/R')
    expect(wrapper.get('[data-metric="total-return"] dd').text()).toBe('N/R')
    expect(wrapper.get('[data-metric="irr"] dd').text()).toBe('N/R')
    wrapper.unmount()
  })
})

describe('PortfolioMetrics presentation', () => {
  const mountMetrics = (metrics: readonly ReturnType<typeof summaryMetrics>[number][]) =>
    mount(PortfolioMetrics, {
      props: { contextLabel: 'Brokerage A · 2026-09-08 · USD', metrics },
    })

  it('renders a semantic definition list with one dt/dd pair per metric', () => {
    const wrapper = mountMetrics(summaryMetrics(populatedSummary))
    const list = wrapper.get('dl.portfolio-metrics')
    expect(list.findAll('div').length).toBe(5)
    expect(wrapper.findAll('dt').length).toBe(5)
    expect(wrapper.findAll('dd').length).toBe(5)
    wrapper.unmount()
  })

  it('renders the supplied display values exactly without adding currency decoration', () => {
    const wrapper = mountMetrics(summaryMetrics(populatedSummary))
    expect(wrapper.get('[data-metric="nav"] dd').text()).toBe('$0.00')
    expect(wrapper.get('[data-metric="invested"] dd').text()).toBe('$100.00')
    expect(wrapper.get('[data-metric="cash-out"] dd').text()).toBe('($100.00)')
    expect(wrapper.get('[data-metric="total-return"] dd').text()).toBe('−2.40%')
    expect(wrapper.get('[data-metric="irr"] dd').text()).toBe('N/A')
    // The committed context carries the currency; values must not repeat it.
    expect(wrapper.get('[data-metric="invested"] dd').text()).not.toContain('USD')
    wrapper.unmount()
  })

  it('shows the committed context label and makes the NAV entry dominant', () => {
    const wrapper = mountMetrics(summaryMetrics(populatedSummary))
    expect(wrapper.get('[data-testid="portfolio-context-label"]').text()).toContain('Brokerage A · 2026-09-08 · USD')
    expect(wrapper.get('[data-metric="nav"]').classes()).toContain('portfolio-metrics__primary')
    expect(wrapper.get('[data-metric="invested"]').classes()).not.toContain('portfolio-metrics__primary')
    wrapper.unmount()
  })
})
