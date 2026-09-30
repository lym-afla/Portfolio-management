import { describe, it, expect } from 'vitest'
import { getChartOptions, colorPalette } from '@/config/chartConfig'

describe('chart config', () => {
  it('exposes horizontal bar options with tooltips enabled', async () => {
    const opts = await getChartOptions('USD')
    expect(opts.barChartOptions.indexAxis).toBe('y')
    expect(opts.barChartOptions.plugins.tooltip.enabled).not.toBe(false)
    expect(opts.pieChartOptions).toBeUndefined() // transitional bar renderer; C4 introduces the requested solid allocation pies
  })

  it('palette starts with the theme primary', () => {
    expect(colorPalette[0].toLowerCase()).toBe('#0f4c81')
  })
})

it('shows the same 25.0% as the allocation API for a complete positive partition', async () => {
  const { barChartOptions } = await getChartOptions('USD')
  const formatter = barChartOptions.plugins.datalabels.formatter
  const chart = { data: { datasets: [{ data: [25, 75] }] } }
  expect(formatter(25, { chart })).toBe('25 (25.0%)')
  expect(formatter(75, { chart })).toBe('75 (75.0%)')
})
