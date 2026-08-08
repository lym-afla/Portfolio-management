import { describe, it, expect } from 'vitest'
import {
  pivotFxRows,
  firstPairInRow,
  pairLabelOf,
  splitPairLabel,
  comparePairLabels,
  PAIR_ORDER,
} from '@/utils/fxPivot'

// Tests for the long->wide pivot that powers the /database/fx table.
//
// Backend rows (long format, one row per date+pair):
//   { id, date, from_currency, to_currency, rate }
// Frontend needs a wide grid: one object per date, keyed by "FROM/TO".
// Missing pairs must be absent (template renders them as '—' via ?? ).

describe('pairLabelOf', () => {
  it('joins from/to with a slash', () => {
    expect(pairLabelOf({ from_currency: 'USD', to_currency: 'EUR' })).toBe(
      'USD/EUR'
    )
  })
})

describe('splitPairLabel', () => {
  it('splits a pair label into [from, to]', () => {
    expect(splitPairLabel('USD/EUR')).toEqual(['USD', 'EUR'])
    expect(splitPairLabel('CHF/GBP')).toEqual(['CHF', 'GBP'])
  })

  it('is the inverse of pairLabelOf', () => {
    const label = pairLabelOf({ from_currency: 'PLN', to_currency: 'USD' })
    expect(splitPairLabel(label)).toEqual(['PLN', 'USD'])
  })

  it('returns ["", ""] for a malformed (slashless) label', () => {
    expect(splitPairLabel('USDEUR')).toEqual(['', ''])
    expect(splitPairLabel('')).toEqual(['', ''])
  })
})

describe('comparePairLabels', () => {
  it('orders known pairs by PAIR_ORDER', () => {
    const out = ['CNY/USD', 'USD/EUR', 'RUB/USD', 'USD/GBP'].sort(
      comparePairLabels
    )
    expect(out).toEqual(['USD/EUR', 'USD/GBP', 'RUB/USD', 'CNY/USD'])
  })

  it('places unknown pairs after known ones, alphabetically', () => {
    const out = ['ZZZ/AAA', 'USD/EUR', 'AAA/BBB'].sort(comparePairLabels)
    expect(out).toEqual(['USD/EUR', 'AAA/BBB', 'ZZZ/AAA'])
  })
})

describe('pivotFxRows', () => {
  const sampleRows = [
    { id: 1, date: '2026-08-06', from_currency: 'USD', to_currency: 'EUR', rate: '0.9234' },
    { id: 2, date: '2026-08-06', from_currency: 'USD', to_currency: 'GBP', rate: '0.7891' },
    { id: 3, date: '2026-08-06', from_currency: 'CHF', to_currency: 'GBP', rate: '0.8812' },
    { id: 4, date: '2026-08-05', from_currency: 'USD', to_currency: 'EUR', rate: '0.9210' },
  ]

  it('collapses rows into one object per date', () => {
    const { pivoted } = pivotFxRows(sampleRows)
    expect(pivoted).toHaveLength(2)
    const today = pivoted.find((r) => r.date === '2026-08-06')
    expect(today['USD/EUR']).toEqual({ rate: '0.9234', id: 1 })
    expect(today['USD/GBP']).toEqual({ rate: '0.7891', id: 2 })
    expect(today['CHF/GBP']).toEqual({ rate: '0.8812', id: 3 })
  })

  it('keeps dates in first-seen order (not reordered)', () => {
    const { pivoted } = pivotFxRows(sampleRows)
    expect(pivoted.map((r) => r.date)).toEqual(['2026-08-06', '2026-08-05'])
  })

  it('derives pairLabels ordered by PAIR_ORDER', () => {
    const { pairLabels } = pivotFxRows(sampleRows)
    expect(pairLabels).toEqual(['USD/EUR', 'USD/GBP', 'CHF/GBP'])
  })

  it('omits pairs that have no row (template renders them as —)', () => {
    const { pivoted } = pivotFxRows(sampleRows)
    const yesterday = pivoted.find((r) => r.date === '2026-08-05')
    expect(yesterday['USD/EUR']).toEqual({ rate: '0.9210', id: 4 })
    // No USD/GBP row for this date -> key absent -> ?? '—' in the template.
    expect(yesterday['USD/GBP']).toBeUndefined()
  })

  it('handles empty / null input gracefully', () => {
    expect(pivotFxRows([])).toEqual({ pivoted: [], pairLabels: [] })
    expect(pivotFxRows(null)).toEqual({ pivoted: [], pairLabels: [] })
    expect(pivotFxRows(undefined)).toEqual({ pivoted: [], pairLabels: [] })
  })

  it('skips malformed rows (no date) without throwing', () => {
    const rows = [
      { id: 9, from_currency: 'USD', to_currency: 'EUR', rate: '1' }, // no date
      { id: 10, date: '2026-08-07', from_currency: 'USD', to_currency: 'EUR', rate: '0.92' },
    ]
    const { pivoted, pairLabels } = pivotFxRows(rows)
    expect(pivoted).toHaveLength(1)
    expect(pairLabels).toEqual(['USD/EUR'])
  })
})

describe('firstPairInRow', () => {
  const row = {
    date: '2026-08-06',
    'USD/EUR': { rate: '0.9234', id: 1 },
    'USD/GBP': { rate: '0.7891', id: 2 },
    'CHF/GBP': { rate: '0.8812', id: 3 },
  }

  it('returns the first pair present in the given column order', () => {
    const first = firstPairInRow(row, ['USD/EUR', 'USD/GBP', 'CHF/GBP'])
    expect(first).toMatchObject({
      id: 1,
      rate: '0.9234',
      from_currency: 'USD',
      to_currency: 'EUR',
      date: '2026-08-06',
    })
  })

  it('respects the supplied column order (not PAIR_ORDER)', () => {
    const first = firstPairInRow(row, ['CHF/GBP', 'USD/EUR'])
    expect(first.id).toBe(3)
  })

  it('falls back to PAIR_ORDER when no order is given', () => {
    expect(firstPairInRow(row).id).toBe(1) // USD/EUR is first in PAIR_ORDER
    expect(PAIR_ORDER[0]).toBe('USD/EUR')
  })

  it('returns null when no pair is present', () => {
    expect(firstPairInRow({ date: '2026-08-06' })).toBeNull()
    expect(firstPairInRow(null)).toBeNull()
  })
})
