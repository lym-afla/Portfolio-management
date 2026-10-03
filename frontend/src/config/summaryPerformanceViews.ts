// D5 Task 1 — pure display projection for the /summary account-performance
// table. This module only selects which server periods/leaves are visible
// and derives display labels; it never parses, aggregates or recalculates
// any financial value. Server period keys and metric keys are preserved
// verbatim (YTD is surfaced as YTD, never relabelled as a calendar year).

export type PerformanceViewMode = 'single' | 'comparison' | 'history'

export interface MetricLeaf {
  /** Display label used in headers (matches the incumbent column titles). */
  label: string
  /** Wire key inside each period object of a summary line. */
  key: string
}

export interface PerformanceLineLike {
  name: string
  data?: Record<string, Record<string, string> | undefined> | null
}

/** The eight incumbent leaves; order is the incumbent column order. */
export const metricLeaves: readonly MetricLeaf[] = [
  { label: 'BoP NAV', key: 'BoP NAV' },
  { label: 'Cash-in/(out)', key: 'Cash-in/out' },
  { label: 'Return', key: 'Return' },
  { label: 'FX', key: 'FX' },
  { label: 'TSR', key: 'TSR percentage' },
  { label: 'EoP NAV', key: 'EoP NAV' },
  { label: 'Commissions', key: 'Commission' },
  { label: 'Fee per AuM', key: 'Fee per AuM (percentage)' },
] as const

/** Default visible period: returned YTD, else latest returned calendar
 * year (server order is YTD, years descending, All-time), else the first
 * returned period. Null only when the server returned no periods. */
export function defaultPeriod(years: readonly string[]): string | null {
  if (!years.length) return null
  if (years.includes('YTD')) return 'YTD'
  const calendarYear = years.find((year) => /^\d{4}$/.test(year))
  return calendarYear ?? years[0]
}

/** Re-derive a stored comparison selection against the current server
 * periods, preserving server order. */
export function resolveComparisonSelection(
  years: readonly string[],
  selected: readonly string[],
): string[] {
  return years.filter((year) => selected.includes(year))
}

/** Periods visible in the table for the active view mode, in server
 * order. Single/comparison selections that no longer exist fall back to
 * the server default period; an empty comparison selection keeps the
 * active single period so switching modes never jumps context. */
export function visiblePeriods(
  mode: PerformanceViewMode,
  years: readonly string[],
  singlePeriod: string | null,
  comparisonSelection: readonly string[],
): string[] {
  if (!years.length) return []
  const fallback =
    singlePeriod && years.includes(singlePeriod) ? singlePeriod : defaultPeriod(years)
  if (mode === 'history') return [...years]
  if (mode === 'comparison') {
    const resolved = resolveComparisonSelection(years, comparisonSelection)
    return resolved.length ? resolved : fallback ? [fallback] : []
  }
  return fallback ? [fallback] : []
}

/** Flat qualified label for single-period headers, e.g. `BoP NAV (YTD)`. */
export function leafQualifiedLabel(leaf: MetricLeaf, period: string): string {
  return `${leaf.label} (${period})`
}

/** Verbatim server string for a cell; the incumbent N/A marker when the
 * period or key is missing. No parsing, no recalculation. */
export function performanceCell(
  line: PerformanceLineLike | null | undefined,
  period: string,
  key: string,
): string {
  const value = line?.data?.[period]?.[key]
  return value ?? 'N/A'
}

const groupLabels: Record<string, string> = {
  public_markets_context: 'Public Markets',
  restricted_investments_context: 'Restricted Investments',
}

export function accountGroupLabel(contextKey: string): string {
  return groupLabels[contextKey] ?? contextKey
}

/** YTD and All-time columns keep the incumbent highlight treatment. */
export function periodIsHighlight(period: string): boolean {
  return period === 'YTD' || period === 'All-time'
}
