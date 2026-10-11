// Absent-data breakdown-row rule (owner: "Portfolio breakdown works. I
// would hide rows with no data"). The breakdown wire always emits every
// asset-class row plus TOTAL. A row is absent when EVERY data cell is an
// absence encoding of this contract — an empty string (non-applicable
// cells) or a numeric-zero display ('$0.00', '0.0%'). Numeric zero inside
// a row that carries any real data is retained verbatim; status markers
// ('N/A', 'N/R', a bare dash) are meaningful; TOTAL rows are never hidden.
import { describe, expect, it } from 'vitest'
import {
  isAbsentBreakdownRow,
  visibleBreakdownRows,
} from '@/utils/breakdownRows'

const row = (over) => ({
  name: 'Equity - Int\'l',
  cost: '$0.00',
  unrealized: '$0.00',
  unrealized_percent: '0.0%',
  market_value: '$0.00',
  portfolio_percent: '0.0%',
  realized: '$0.00',
  realized_percent: '0.0%',
  capital_distribution: '$0.00',
  capital_distribution_percent: '0.0%',
  commission: '$0.00',
  commission_percent: '0.0%',
  total: '$0.00',
  total_percent: '0.0%',
  ...over,
})

describe('isAbsentBreakdownRow', () => {
  it('treats an all-zero row as absent (the "no data" signature)', () => {
    expect(isAbsentBreakdownRow(row({}))).toBe(true)
  })

  it('keeps a row with a single nonzero money cell, zeros retained verbatim', () => {
    const kept = row({ realized: '($25.00)' })
    expect(isAbsentBreakdownRow(kept)).toBe(false)
    // The helper decides visibility only; it never rewrites cells.
    expect(kept.cost).toBe('$0.00')
  })

  it('keeps a row with a nonzero percent cell even beside zeros', () => {
    expect(isAbsentBreakdownRow(row({ total_percent: '12.5%' }))).toBe(false)
  })

  it('treats signed zero displays as absence, not data', () => {
    expect(isAbsentBreakdownRow(row({ realized: '($0.00)', total: '-$0.00' }))).toBe(true)
  })

  it('treats empty-string cells as absent (the non-applicable Cash cells)', () => {
    const cash = {
      name: 'Cash',
      cost: '',
      unrealized: '',
      unrealized_percent: '',
      market_value: '$0.00',
      portfolio_percent: '0.0%',
      realized: '',
      realized_percent: '',
      capital_distribution: '',
      capital_distribution_percent: '',
      commission: '$0.00',
      commission_percent: '',
      total: '$0.00',
      total_percent: '0.0%',
    }
    expect(isAbsentBreakdownRow(cash)).toBe(true)
  })

  it('keeps a Cash row with a real balance', () => {
    const cash = {
      name: 'Cash',
      cost: '',
      unrealized: '',
      unrealized_percent: '',
      market_value: '$1,204.55',
      portfolio_percent: '3.1%',
      realized: '',
      realized_percent: '',
      capital_distribution: '',
      capital_distribution_percent: '',
      commission: '($2.50)',
      commission_percent: '',
      total: '$1,202.05',
      total_percent: '3.1%',
    }
    expect(isAbsentBreakdownRow(cash)).toBe(false)
  })

  it.each(['N/A', 'N/R', '—'])('treats the status marker %s as meaningful', (marker) => {
    expect(isAbsentBreakdownRow(row({ unrealized: marker }))).toBe(false)
  })

  it('keeps a row with an unparseable display rather than guessing', () => {
    expect(isAbsentBreakdownRow(row({ total: 'pending' }))).toBe(false)
  })

  it('never hides the TOTAL row, even an all-zero one', () => {
    expect(isAbsentBreakdownRow(row({ name: 'TOTAL' }))).toBe(false)
  })

  it('treats null and undefined cells as absent', () => {
    expect(isAbsentBreakdownRow(row({ cost: null, unrealized: undefined }))).toBe(true)
  })
})

describe('visibleBreakdownRows', () => {
  it('filters absent rows and keeps data rows and totals in order', () => {
    const rows = [
      row({ name: 'Equity - Int\'l', market_value: '$11,000.00' }),
      row({ name: 'Options' }),
      row({ name: 'TOTAL' }),
    ]
    expect(visibleBreakdownRows(rows).map((entry) => entry.name)).toEqual([
      'Equity - Int\'l',
      'TOTAL',
    ])
  })

  it('passes through a non-array unchanged', () => {
    const notAnArray = { length: 0 }
    expect(visibleBreakdownRows(notAnArray)).toBe(notAnArray)
  })

  it('keeps every row of a fully real table', () => {
    const rows = [
      row({ name: 'Stocks', market_value: '$5.00' }),
      row({ name: 'Cash', cost: '', market_value: '$1.00' }),
    ]
    expect(visibleBreakdownRows(rows)).toHaveLength(2)
  })
})
