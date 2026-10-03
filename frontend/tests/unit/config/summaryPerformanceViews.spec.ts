// D5 Task 1 — pure display projection for the /summary account-performance
// table. Presentation state only: the projection selects which server
// periods/leaves are visible and derives display labels; it never parses,
// aggregates or recalculates any financial value.
import { describe, expect, it } from 'vitest'
import {
  accountGroupLabel,
  defaultPeriod,
  leafQualifiedLabel,
  metricLeaves,
  performanceCell,
  periodIsHighlight,
  resolveComparisonSelection,
  visiblePeriods,
} from '@/config/summaryPerformanceViews'

const serverYears = ['YTD', '2025', '2024', '2023', 'All-time']

describe('defaultPeriod', () => {
  it('prefers the returned YTD period', () => {
    expect(defaultPeriod(serverYears)).toBe('YTD')
  })

  it('falls back to the latest returned calendar year in server order', () => {
    expect(defaultPeriod(['2024', '2023', 'All-time'])).toBe('2024')
  })

  it('falls back to the first available server period otherwise', () => {
    expect(defaultPeriod(['All-time'])).toBe('All-time')
  })

  it('returns null for empty data', () => {
    expect(defaultPeriod([])).toBeNull()
  })

  it('does not relabel YTD as a calendar year', () => {
    // YTD is its own period key; the default must surface it verbatim.
    expect(defaultPeriod(['YTD', '2025'])).toBe('YTD')
    expect(defaultPeriod(['2025', 'YTD'])).toBe('YTD')
  })
})

describe('visiblePeriods', () => {
  it('single mode shows exactly the selected period', () => {
    expect(visiblePeriods('single', serverYears, '2024', [])).toEqual(['2024'])
  })

  it('history mode shows every returned period in server order', () => {
    expect(visiblePeriods('history', serverYears, 'YTD', [])).toEqual(serverYears)
  })

  it('comparison mode shows the chosen periods in server order', () => {
    expect(
      visiblePeriods('comparison', serverYears, 'YTD', ['2023', 'YTD']),
    ).toEqual(['YTD', '2023'])
  })

  it('drops comparison selections the server no longer returns', () => {
    expect(
      visiblePeriods('comparison', serverYears, 'YTD', ['YTD', '1999', '2024']),
    ).toEqual(['YTD', '2024'])
  })

  it('an empty comparison selection falls back to the single-period default', () => {
    expect(visiblePeriods('comparison', serverYears, '2025', [])).toEqual(['2025'])
  })

  it('single selection not present in the data resolves to the server default', () => {
    expect(visiblePeriods('single', serverYears, '1999', [])).toEqual(['YTD'])
  })
})

describe('resolveComparisonSelection', () => {
  it('keeps the chosen subset and re-derives it when the server data changes', () => {
    expect(resolveComparisonSelection(serverYears, ['2024', 'YTD'])).toEqual(['YTD', '2024'])
    expect(resolveComparisonSelection(['YTD', '2024'], ['2024', 'YTD', '2025'])).toEqual(['YTD', '2024'])
  })
})

describe('metric leaves', () => {
  it('retains all eight leaves with their exact display labels and wire keys', () => {
    expect(metricLeaves).toEqual([
      { label: 'BoP NAV', key: 'BoP NAV' },
      { label: 'Cash-in/(out)', key: 'Cash-in/out' },
      { label: 'Return', key: 'Return' },
      { label: 'FX', key: 'FX' },
      { label: 'TSR', key: 'TSR percentage' },
      { label: 'EoP NAV', key: 'EoP NAV' },
      { label: 'Commissions', key: 'Commission' },
      { label: 'Fee per AuM', key: 'Fee per AuM (percentage)' },
    ])
  })

  it('qualifies a leaf label with its period for single-period flat headers', () => {
    expect(leafQualifiedLabel(metricLeaves[0], 'YTD')).toBe('BoP NAV (YTD)')
    expect(leafQualifiedLabel(metricLeaves[1], '2024')).toBe('Cash-in/(out) (2024)')
    expect(leafQualifiedLabel(metricLeaves[7], 'All-time')).toBe('Fee per AuM (All-time)')
  })
})

describe('performanceCell', () => {
  const line = { name: 'Main', data: { YTD: { 'BoP NAV': '$10,000.00' } } }

  it('returns the server string verbatim', () => {
    expect(performanceCell(line, 'YTD', 'BoP NAV')).toBe('$10,000.00')
  })

  it('keeps the N/A marker for missing periods and keys', () => {
    expect(performanceCell(line, '2023', 'BoP NAV')).toBe('N/A')
    expect(performanceCell(line, 'YTD', 'FX')).toBe('N/A')
    expect(performanceCell(null, 'YTD', 'FX')).toBe('N/A')
  })
})

describe('group labels', () => {
  it('maps the server context keys to their display names', () => {
    expect(accountGroupLabel('public_markets_context')).toBe('Public Markets')
    expect(accountGroupLabel('restricted_investments_context')).toBe('Restricted Investments')
  })

  it('YTD and All-time columns keep their highlight semantics', () => {
    expect(periodIsHighlight('YTD')).toBe(true)
    expect(periodIsHighlight('All-time')).toBe(true)
    expect(periodIsHighlight('2024')).toBe(false)
  })
})
