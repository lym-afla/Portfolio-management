// Task 1 (real-data corrections): the displayed dashboard range and the
// request end are clamped to the committed valuation date — a persisted
// custom To later than the effective date must never sample periods after it.
import { describe, expect, it } from 'vitest'
import { calculateDateRange } from '@/utils/dateRangeUtils'

describe('calculateDateRange custom-range clamping', () => {
  it('clamps a custom To later than the effective date to the effective date', () => {
    const range = calculateDateRange('custom', '2024-06-30', '2024-01-01', '2026-10-09')
    expect(range.from).toBe('2024-01-01')
    expect(range.to).toBe('2024-06-30')
  })

  it('keeps a custom To within the effective date', () => {
    const range = calculateDateRange('custom', '2026-10-09', '2026-01-01', '2026-06-30')
    expect(range.to).toBe('2026-06-30')
  })

  it('uses the effective date as To when the custom To is empty', () => {
    const range = calculateDateRange('custom', '2024-06-30', '2024-01-01', null)
    expect(range.from).toBe('2024-01-01')
    expect(range.to).toBe('2024-06-30')
  })

  it('non-custom ranges already end at the effective date', () => {
    const range = calculateDateRange('ytd', '2024-06-30')
    expect(range.from).toBe('2024-01-01')
    expect(range.to).toBe('2024-06-30')
  })
})
