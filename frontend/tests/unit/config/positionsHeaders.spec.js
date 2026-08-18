// tests/unit/config/positionsHeaders.spec.js
import { describe, it, expect } from 'vitest'
import {
  openPositionsHeaders,
  closedPositionsHeaders,
  flattenHeaders,
} from '@/config/positionsHeaders'

const maxDepth = (hs) =>
  hs.reduce((m, h) => Math.max(m, h.children ? 1 + maxDepth(h.children) : 0), 0)

describe('positions headers', () => {
  it('never nests deeper than 2 levels', () => {
    expect(maxDepth(openPositionsHeaders)).toBeLessThanOrEqual(1) // children = 1 extra level
    expect(maxDepth(closedPositionsHeaders)).toBeLessThanOrEqual(1)
  })

  it('right-aligns every numeric leaf, start-aligns identity leaves', () => {
    for (const leaf of flattenHeaders(openPositionsHeaders)) {
      if (['type', 'name'].includes(leaf.key)) expect(leaf.align).toBe('start')
      else expect(leaf.align).toBe('end')
    }
  })

  it('flattens to unique keys', () => {
    const keys = flattenHeaders(openPositionsHeaders).map((h) => h.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})
