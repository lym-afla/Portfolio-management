import { describe, it, expect } from 'vitest'
import { formatQuantity, formatPrice } from '@/utils/formatUtils'

// Unit tests for the adaptive decimal-place formatter used by
// TransactionDescription.vue for quantity/price display.
//
// Rule (per task-7 brief):
//   - |value| >= 1  -> fixed `digits` decimal places (default 2).
//   - |value| < 1   -> show only the first significant digit
//                      (0.6803 -> "0.7", 0.00011659 -> "0.0001").
//   - null / '' / non-numeric -> null (caller falls back to the '–' sentinel).

describe('formatQuantity', () => {
  describe('|value| >= 1 (fixed digits)', () => {
    it('formats to 2 decimal places by default', () => {
      expect(formatQuantity(12.94056)).toBe('12.94')
    })

    it('respects the digits parameter', () => {
      expect(formatQuantity(12.94056, 4)).toBe('12.9406')
      expect(formatQuantity(12.94056, 0)).toBe('13')
      expect(formatQuantity(1.5, 3)).toBe('1.500')
    })

    it('handles integer quantities without NaN/blank', () => {
      expect(formatQuantity(100)).toBe('100.00')
      expect(formatQuantity(5, 2)).toBe('5.00')
    })

    it('handles exactly 1', () => {
      expect(formatQuantity(1)).toBe('1.00')
    })

    it('accepts numeric strings', () => {
      expect(formatQuantity('12.94056', 2)).toBe('12.94')
    })

    it('handles negative values >= 1 in absolute terms', () => {
      expect(formatQuantity(-12.94056, 2)).toBe('-12.94')
    })
  })

  describe('|value| < 1 (first significant digit)', () => {
    it('rounds 0.6803 to "0.7"', () => {
      expect(formatQuantity(0.6803)).toBe('0.7')
    })

    it('rounds 0.00011659 to "0.0001"', () => {
      expect(formatQuantity(0.00011659)).toBe('0.0001')
    })

    it('strips trailing zeros after the decimal point', () => {
      // 0.5 -> 1 decimal place -> toFixed -> "0.5" (no trailing zero to strip)
      expect(formatQuantity(0.5)).toBe('0.5')
      expect(formatQuantity(0.0999)).toBe('0.1')
    })

    it('renders very small magnitudes in plain decimal, not exponential', () => {
      // Regression: the brief's toPrecision(1) approach produced "1e-7" here.
      expect(formatQuantity(1e-7)).toBe('0.0000001')
      expect(formatQuantity(0.0000001)).toBe('0.0000001')
    })

    it('handles small negative values', () => {
      expect(formatQuantity(-0.6803)).toBe('-0.7')
      expect(formatQuantity(-0.00011659)).toBe('-0.0001')
    })
  })

  describe('null / empty / non-numeric input -> null', () => {
    it('returns null for null', () => {
      expect(formatQuantity(null)).toBeNull()
    })

    it('returns null for undefined', () => {
      expect(formatQuantity(undefined)).toBeNull()
    })

    it('returns null for empty string', () => {
      expect(formatQuantity('')).toBeNull()
    })

    it('returns null for whitespace-only string', () => {
      expect(formatQuantity('   ')).toBeNull()
    })

    it('returns null for NaN', () => {
      expect(formatQuantity(NaN)).toBeNull()
    })

    it('returns null for non-numeric strings', () => {
      expect(formatQuantity('abc')).toBeNull()
      expect(formatQuantity('–')).toBeNull() // the sentinel itself
    })

    it('treats 0 as a valid number (not null)', () => {
      // 0 falls in the |value| < 1 branch (log10(0) is -Inf); the toFixed(0)
      // path must still return a sensible string rather than null.
      expect(formatQuantity(0)).toBe('0')
      expect(formatQuantity('0')).toBe('0')
    })
  })
})

describe('formatPrice', () => {
  it('applies the same adaptive rule as formatQuantity', () => {
    expect(formatPrice(12.94056, 2)).toBe('12.94')
    expect(formatPrice(0.6803)).toBe('0.7')
    expect(formatPrice(0.00011659)).toBe('0.0001')
  })

  it('returns null for non-numeric input', () => {
    expect(formatPrice(null)).toBeNull()
    expect(formatPrice('')).toBeNull()
  })
})
