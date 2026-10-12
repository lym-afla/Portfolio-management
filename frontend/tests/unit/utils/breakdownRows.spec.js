// Absent-data breakdown-row rule (owner round-4 correction): numeric zero
// and formatted zero are MEANINGFUL data and stay visible, including wholly
// zero-valued rows. Only contractually absent cells (empty string,
// null/undefined) are absence; a row hides only when EVERY cell is absent.
// The backend cannot currently distinguish "no activity" from "genuine
// zero" (both arrive as all-zero displays), so ambiguous rows are preserved
// and the limitation is documented rather than guessed around. Status
// markers are meaningful; TOTAL rows are never hidden.
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
  it('keeps a wholly zero-valued row visible (zero is data, not absence)', () => {
    expect(isAbsentBreakdownRow(row({}))).toBe(false)
  })

  it('keeps signed zero displays visible', () => {
    expect(isAbsentBreakdownRow(row({ realized: '($0.00)', total: '-$0.00' }))).toBe(false)
  })

  it('treats empty-string cells as the only contractual absence', () => {
    const cash = {
      name: 'Cash',
      cost: '',
      unrealized: '',
      unrealized_percent: '',
      market_value: '',
      portfolio_percent: '',
      realized: '',
      realized_percent: '',
      capital_distribution: '',
      capital_distribution_percent: '',
      commission: '',
      commission_percent: '',
      total: '',
      total_percent: '',
    }
    expect(isAbsentBreakdownRow(cash)).toBe(true)
  })

  it('keeps a Cash row whose non-applicable cells sit beside zero data', () => {
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
    // The zeros are meaningful: the ambiguous row is preserved, not guessed.
    expect(isAbsentBreakdownRow(cash)).toBe(false)
  })

  it('keeps a row with a single nonzero money cell', () => {
    const kept = row({ realized: '($25.00)' })
    expect(isAbsentBreakdownRow(kept)).toBe(false)
    // The helper decides visibility only; it never rewrites cells.
    expect(kept.cost).toBe('$0.00')
  })

  it.each(['N/A', 'N/R', '—'])('treats the status marker %s as meaningful', (marker) => {
    expect(isAbsentBreakdownRow(row({ unrealized: marker }))).toBe(false)
  })

  it('keeps a row with an unparseable display rather than guessing', () => {
    expect(isAbsentBreakdownRow(row({ total: 'pending' }))).toBe(false)
  })

  it('never hides the TOTAL row, even a fully empty one', () => {
    expect(isAbsentBreakdownRow({ name: 'TOTAL', cost: '', total: '' })).toBe(false)
  })

  it('hides a row only when every cell is null or undefined', () => {
    const allAbsent = row({})
    Object.keys(allAbsent).forEach((key) => {
      if (key !== 'name') allAbsent[key] = null
    })
    expect(isAbsentBreakdownRow(allAbsent)).toBe(true)
    // A single meaningful cell keeps the row.
    expect(isAbsentBreakdownRow({ ...allAbsent, total: '$0.00' })).toBe(false)
  })
})

describe('visibleBreakdownRows', () => {
  it('preserves ambiguous all-zero rows in order (documented wire limitation)', () => {
    const rows = [
      row({ name: 'Stocks', market_value: '$11,000.00' }),
      row({ name: 'Options' }),
      row({ name: 'TOTAL' }),
    ]
    expect(visibleBreakdownRows(rows).map((entry) => entry.name)).toEqual([
      'Stocks',
      'Options',
      'TOTAL',
    ])
  })

  it('filters only the fully-empty row', () => {
    const emptyRow = {}
    Object.keys(row({})).forEach((key) => {
      emptyRow[key] = key === 'name' ? 'Other' : ''
    })
    const rows = [row({ name: 'Stocks', market_value: '$11,000.00' }), emptyRow, row({ name: 'TOTAL' })]
    expect(visibleBreakdownRows(rows).map((entry) => entry.name)).toEqual([
      'Stocks',
      'TOTAL',
    ])
  })

  it('passes through a non-array unchanged', () => {
    const notAnArray = { length: 0 }
    expect(visibleBreakdownRows(notAnArray)).toBe(notAnArray)
  })
})
