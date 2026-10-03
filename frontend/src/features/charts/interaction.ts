// Controlled interaction model for the NAV pilot (C3). One source of truth
// for series visibility, inspected period and viewport; zoom never changes
// values, queries or IRR horizons.
import type { ChartDocument, ChartPeriod, ChartSeries } from './contracts'

export interface ChartInteraction {
  visibleSeriesIds: readonly string[]
  viewport: { firstPeriodKey: string; lastPeriodKey: string } | null
  inspectedPeriodKey: string | null
}

export function defaultInteraction(document: ChartDocument): ChartInteraction {
  return {
    visibleSeriesIds: document.series.map((series) => series.id),
    viewport: null,
    inspectedPeriodKey: null,
  }
}

/** Carry interaction across documents without inventing identity. */
export function reconcileInteraction(
  previous: ChartDocument,
  next: ChartDocument,
  state: ChartInteraction,
): ChartInteraction {
  const nextIds = new Set(next.series.map((series) => series.id))
  const previousIds = new Set(previous.series.map((series) => series.id))
  // Surviving IDs keep their hidden/visible state; newly introduced IDs start
  // visible; IDs that disappeared are dropped (they were never selectable).
  const visibleSeriesIds = [
    ...state.visibleSeriesIds.filter((id) => nextIds.has(id)),
    ...next.series.map((series) => series.id).filter((id) => !previousIds.has(id) && !state.visibleSeriesIds.includes(id)),
  ]
  const nextKeys = new Set(next.periods.map((period) => period.key))
  const viewport =
    state.viewport && nextKeys.has(state.viewport.firstPeriodKey) && nextKeys.has(state.viewport.lastPeriodKey)
      ? state.viewport
      : null
  return {
    visibleSeriesIds,
    viewport,
    inspectedPeriodKey: state.inspectedPeriodKey !== null && nextKeys.has(state.inspectedPeriodKey)
      ? state.inspectedPeriodKey
      : null,
  }
}

// Fixed control names for the two IRR horizons so naming never depends on
// server label wording; data itself always comes from the document.
export function seriesControlName(series: ChartSeries): string {
  if (series.metric === 'irr_inception') return 'Since-inception IRR (annualized)'
  if (series.metric === 'irr_interval') return 'Interval IRR (annualized)'
  return series.label
}

// Per-series horizon text: the since-inception IRR always spans inception to
// the endpoint; the interval IRR uses the server-provided interval bounds
// (inception semantics at the first sample).
export function seriesHorizon(series: ChartSeries, period: ChartPeriod): string | null {
  if (series.metric === 'irr_inception') return `Inception to ${period.endDate}`
  if (series.metric === 'irr_interval') {
    return period.interval.kind === 'inception'
      ? `Inception to ${period.interval.endDate}`
      : `${period.interval.startDate} – ${period.interval.endDate}`
  }
  return null
}
