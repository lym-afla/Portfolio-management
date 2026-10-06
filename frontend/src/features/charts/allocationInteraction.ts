// Controlled interaction model for the allocation pies (C4). Deliberately
// NOT the NAV interaction type: allocation legends highlight and focus —
// they never hide categories, toggle visibility or renormalize geometry, so
// the only state is which allocation (if any) currently holds the focus.
import type { ChartDocument } from './contracts'

export interface AllocationInteraction {
  focusedSeriesId: string | null
}

export function defaultAllocationInteraction(): AllocationInteraction {
  return { focusedSeriesId: null }
}

/** Carry focus across documents without inventing identity. */
export function reconcileAllocationInteraction(
  _previous: ChartDocument,
  next: ChartDocument,
  state: AllocationInteraction,
): AllocationInteraction {
  if (state.focusedSeriesId === null) return state
  const survives = next.series.some((series) => series.id === state.focusedSeriesId)
  return survives ? state : { focusedSeriesId: null }
}
