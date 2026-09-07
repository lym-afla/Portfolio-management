import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

// Source-level assertions on purpose: the brief's JSON.stringify(Component)
// approach cannot see template source (compiled render functions don't carry
// e.g. the literal <thead markup), so we read the SFC source directly —
// the same pattern used by SummaryCard.spec.js.
const openSrc = readFileSync('src/views/OpenPositionsPage.vue', 'utf-8')
const closedSrc = readFileSync('src/views/ClosedPositionsPage.vue', 'utf-8')

describe('positions pages', () => {
  it('contain no hand-rolled thead or colspan helpers', () => {
    for (const src of [openSrc, closedSrc]) {
      expect(src).not.toContain('getColspan')
      expect(src).not.toContain('getRowspan')
      expect(src.toLowerCase()).not.toContain('<thead')
      expect(src).not.toContain('console.log')
    }
  })

  it('closed positions no longer renders the debug header template', () => {
    expect(closedSrc).not.toContain('header.value')
    expect(closedSrc).not.toContain(' T ')
  })

  it('imports headers from the shared config', () => {
    expect(openSrc).toContain("@/config/positionsHeaders")
    expect(closedSrc).toContain("@/config/positionsHeaders")
    expect(openSrc).not.toContain('const headers = ref(')
    expect(closedSrc).not.toContain('const headers = ref(')
  })

  it('open page uses no literal colspan numbers in footer rows', () => {
    expect(openSrc.toLowerCase()).not.toContain('colspan="')
    expect(openSrc.toLowerCase()).not.toContain(":colspan='")
    expect(openSrc.toLowerCase()).not.toContain('colspan:2')
  })
})
