import { describe, expect, it } from 'vitest'
import { fitVisibleActions } from '@/components/workspace/fitActions'

const input = (over: Partial<Parameters<typeof fitVisibleActions>[0]>) => ({
  availableWidth: 800,
  itemWidths: [180, 160, 150, 140],
  gap: 8,
  fixedWidth: 160,
  menuWidth: 40,
  ...over,
})

describe('fitVisibleActions', () => {
  it('keeps every action direct when the full row fits without the menu', () => {
    // Full row with all four candidates direct, no menu:
    // 160 + (8+180)+(8+160)+(8+150)+(8+140) = 822.
    expect(fitVisibleActions(input({ availableWidth: 822 }))).toBe(4)
    // One pixel less rejects the full row; primary + first three + the menu
    // activator (722) still fits, so exactly one action moves to the menu.
    expect(fitVisibleActions(input({ availableWidth: 821 }))).toBe(3)
  })
  it('hides a suffix in order and reserves room for the overflow activator', () => {
    // Fits primary + first two candidates + menu, but not the third.
    const width = 160 + 8 + 180 + 8 + 160 + 8 + 40
    expect(fitVisibleActions(input({ availableWidth: width }))).toBe(2)
  })
  it('keeps ordering: the earliest candidates stay direct', () => {
    const width = 160 + 8 + 180 + 8 + 40
    expect(fitVisibleActions(input({ availableWidth: width }))).toBe(1)
  })
  it('moves everything to the menu when only the primary and activator fit', () => {
    expect(
      fitVisibleActions(input({ availableWidth: 160 + 8 + 40 }))
    ).toBe(0)
  })
  it('collapses to the menu alone when even the primary cannot fit beside it', () => {
    expect(fitVisibleActions(input({ availableWidth: 100 }))).toBe(0)
  })
  it('handles a zero-width measurement without hiding anything numeric', () => {
    expect(fitVisibleActions(input({ availableWidth: 0, itemWidths: [] }))).toBe(0)
  })
})
