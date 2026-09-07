import { describe, it, expect } from 'vitest'
import { getChartOptions, colorPalette } from '@/config/chartConfig'

describe('chart config', () => {
  it('exposes horizontal bar options with tooltips enabled', async () => {
    const opts = await getChartOptions('USD')
    expect(opts.barChartOptions.indexAxis).toBe('y')
    expect(opts.barChartOptions.plugins.tooltip.enabled).not.toBe(false)
    expect(opts.pieChartOptions).toBeUndefined() // pies retired as primary breakdown
  })

  it('palette starts with the theme primary', () => {
    expect(colorPalette[0].toLowerCase()).toBe('#0f4c81')
  })
})
